# main.py
import sys
import subprocess
import json
from pathlib import Path
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QSplitter, QTreeView,
    QFileSystemModel, QPlainTextEdit, QWidget, QVBoxLayout,
    QPushButton, QListWidget, QListWidgetItem, QHBoxLayout,
    QMessageBox, QAbstractItemView, QLabel, QLineEdit, QDialog
) 
from PySide6.QtWidgets import QFileDialog, QMenuBar, QMenu, QHeaderView, QInputDialog
from PySide6.QtGui import QFont, QKeySequence, QShortcut, QIcon
from PySide6.QtCore import Qt, QModelIndex, QMimeData, QUrl
from PySide6.QtGui import QDragEnterEvent, QDropEvent

import settings
import orca_queue
import find_dialog
import shutil 
from send2trash import send2trash
from create_file_dialog import CreateFileDialog

class CreateTemplateDialog(QDialog):
    def __init__(self, original_name: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Create Template")
        self.resize(350, 120)
        
        self.name_input = QLineEdit(original_name)
        self.name_input.selectAll()  # выделяем всё для быстрого редактирования
        
        layout = QVBoxLayout()
        layout.addWidget(QLabel("Template name:"))
        layout.addWidget(self.name_input)
        
        btn_layout = QHBoxLayout()
        btn_create = QPushButton("Create")
        btn_cancel = QPushButton("Cancel")
        btn_create.clicked.connect(self.accept)
        btn_cancel.clicked.connect(self.reject)
        btn_layout.addStretch()
        btn_layout.addWidget(btn_create)
        btn_layout.addWidget(btn_cancel)
        
        layout.addLayout(btn_layout)
        self.setLayout(layout)
    
    def get_template_name(self) -> str:
        return self.name_input.text().strip()

class QueueListWidget(QListWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.DropOnly)
        self.setDefaultDropAction(Qt.CopyAction)
        self.setSelectionMode(QAbstractItemView.SingleSelection)

    def dragEnterEvent(self, event: QDragEnterEvent):
        mime = event.mimeData()
        if mime.hasUrls():
            # Проверяем, что все файлы — .inp
            urls = mime.urls()
            if all(url.isLocalFile() and url.toLocalFile().endswith('.inp') for url in urls):
                event.acceptProposedAction()
        super().dragEnterEvent(event)

    def dropEvent(self, event: QDropEvent):
        mime = event.mimeData()
        if mime.hasUrls():
            for url in mime.urls():
                path = Path(url.toLocalFile())
                if path.suffix == '.inp':
                    self.parent().add_inp_to_queue(path)
            event.acceptProposedAction()
        super().dropEvent(event)

class PipelineDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Create Pipeline")
        self.resize(300, 100)

        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("Enter pipeline name")

        btn_ok = QPushButton("Accept")
        btn_cancel = QPushButton("Cancel")

        btn_ok.clicked.connect(self.accept)
        btn_cancel.clicked.connect(self.reject)

        h_layout = QHBoxLayout()
        h_layout.addWidget(btn_ok)
        h_layout.addWidget(btn_cancel)

        layout = QVBoxLayout()
        layout.addWidget(QLabel("Pipeline name:"))
        layout.addWidget(self.name_input)
        layout.addLayout(h_layout)
        self.setLayout(layout)

    def get_name(self) -> str:
        return self.name_input.text().strip()

class OrcaGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ORCA Project Manager")
        self.resize(1600, 900)

        # === Paths and core data ===
        app_dir = self.get_app_dir()
        self.state_file = app_dir / "state.json"
        self.settings_file = app_dir / "settings.json"

        default_disable_gpu = True  # ← рекомендуется по умолчанию
        self.disable_gpu = default_disable_gpu
        # Сначала задаём значения по умолчанию
        default_orca = "/home/winter-sulfur/programs/orca_6_1_1_linux_x86-64_shared_openmpi418_nodmrg/orca"
        default_chemcraft_linux = "/home/winter-sulfur/programs/Chemcraft_b638l_lin64/Chemcraft"
        default_chemcraft_windows = "/media/winter-sulfur/Bistriy/Modelling/Chemcraft/Chemcraft.exe"
        default_locale = "C.UTF-8"  

        self.orca_exe = Path(default_orca)
        self.chemcraft_linux_exe = Path(default_chemcraft_linux)
        self.chemcraft_windows_exe = Path(default_chemcraft_windows)
        self.orca_locale = default_locale

        # ЗАТЕМ загружаем настройки
        self.load_settings()

        self.queue = orca_queue.OrcaQueue(self.orca_exe, log_dir=app_dir / "logs", locale=self.orca_locale)
        self._manually_stopped = False
        self.current_root = None
        self.current_file = None

        # === Window icon ===
        icon_path = app_dir / "Picture.png"
        if icon_path.is_file():
            self.setWindowIcon(QIcon(str(icon_path)))

        # === Menu bar ===
        menubar = self.menuBar()
        file_menu = menubar.addMenu("File")
        settings_menu = menubar.addMenu("Settings")
        settings_action = settings_menu.addAction("Preferences...")
        settings_action.triggered.connect(self.open_settings)
        open_folder_action = file_menu.addAction("Open Folder...")
        open_folder_action.setShortcut("Ctrl+O")
        open_folder_action.triggered.connect(self.open_folder)

        save_action = file_menu.addAction("Save")
        save_action.setShortcut("Ctrl+S")
        save_action.triggered.connect(self.save_current_file)

        # === File system model ===
        self.model = QFileSystemModel()
        self.model.setRootPath("")
        self.model.setNameFilters(["*.inp", "*.out", "*_MEP_trj.xyz", "*.json", "*_MEP_ALL_trj.xyz"])
        self.model.setNameFilterDisables(False)

        # === File tree (left panel) ===
        self.tree = QTreeView()
        self.tree.setModel(self.model)
        self.tree.setRootIndex(self.model.index(""))
        self.tree.setAnimated(False)
        self.tree.setIndentation(20)
        self.tree.setSortingEnabled(True)
        self.tree.sortByColumn(0, Qt.AscendingOrder)
        self.tree.doubleClicked.connect(self.on_file_double_clicked)
        self.tree.setColumnWidth(0, 250)
        self.tree.setHeaderHidden(True)
        self.tree.setRootIsDecorated(True)
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self.on_tree_context_menu)
        self.tree.setTextElideMode(Qt.ElideNone)  # ← отключает обрезание текста
        self.tree.header().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self._clipboard_path = None
        self._clipboard_is_cut = False

        # === Text editor components ===
        self.editor = QPlainTextEdit()
        font = QFont("Consolas")
        font.setPointSize(11)
        self.editor.setFont(font)

        self.file_path_label = QLabel("No file opened")
        self.file_path_label.setStyleSheet("font-size: 9pt; color: #666;")

        # === Central area: label + editor + search ===
        editor_layout = QVBoxLayout()
        editor_layout.addWidget(self.file_path_label)
        editor_layout.addWidget(self.editor)
        editor_container = QWidget()
        editor_container.setLayout(editor_layout)

        # === Queue list (right panel) ===
        self.queue_list = QueueListWidget(self)
        self.queue_list.setFixedWidth(300)
        self.queue_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.queue_list.customContextMenuRequested.connect(self.on_queue_context_menu)

        # === Queue control buttons (основные) ===
        self.start_queue_btn = QPushButton("▶ Start Queue")
        self.stop_queue_btn = QPushButton("⏹ Stop Queue")
        self.clear_queue_btn = QPushButton("🗑 Clear Queue")

        self.start_queue_btn.clicked.connect(self.start_queue)
        self.stop_queue_btn.clicked.connect(self.stop_queue)
        self.clear_queue_btn.clicked.connect(self.clear_queue)
        self.stop_queue_btn.setEnabled(False)

        queue_main_buttons_layout = QHBoxLayout()
        queue_main_buttons_layout.addWidget(self.start_queue_btn)
        queue_main_buttons_layout.addWidget(self.stop_queue_btn)
        queue_main_buttons_layout.addWidget(self.clear_queue_btn)

        queue_main_buttons_container = QWidget()
        queue_main_buttons_container.setLayout(queue_main_buttons_layout)

        # === Дополнительные кнопки: Resume + Create Pipeline ===
        self.resume_queue_btn = QPushButton("⏯ Resume Queue")
        self.create_pipeline_btn = QPushButton("📦 Create Pipeline")

        self.resume_queue_btn.clicked.connect(self.resume_queue)
        self.create_pipeline_btn.clicked.connect(self.create_pipeline)
        self.resume_queue_btn.setEnabled(False)

        # Располагаем их в одну строку
        extra_buttons_layout = QHBoxLayout()
        extra_buttons_layout.addWidget(self.resume_queue_btn)
        extra_buttons_layout.addWidget(self.create_pipeline_btn)

        extra_buttons_container = QWidget()
        extra_buttons_container.setLayout(extra_buttons_layout)

        # === Right panel: queue list + все кнопки ===
        queue_layout = QVBoxLayout()
        queue_layout.addWidget(self.queue_list)
        queue_layout.addWidget(queue_main_buttons_container)
        queue_layout.addWidget(extra_buttons_container)  # ← обе кнопки в одной строке

        queue_container = QWidget()
        queue_container.setLayout(queue_layout)

        # === Center splitter: editor + queue ===
        center_splitter = QSplitter(Qt.Horizontal)
        center_splitter.addWidget(editor_container)
        center_splitter.addWidget(queue_container)
        center_splitter.setSizes([700, 300])

        # === Main layout: file tree + center ===
        main_splitter = QSplitter(Qt.Horizontal)
        main_splitter.addWidget(self.tree)
        main_splitter.addWidget(center_splitter)
        main_splitter.setSizes([300, 1100])

        self.setCentralWidget(main_splitter)

        # === Connect queue signals ===
        self.queue.job_started.connect(self.on_job_started)
        self.queue.job_finished.connect(self.on_job_finished)
        self.queue.error_occurred.connect(self.on_job_error)
        self.queue.queue_finished.connect(self.on_queue_finished)

        self.reload_shortcut = QShortcut(QKeySequence("Ctrl+R"), self)
        self.reload_shortcut.activated.connect(self.reload_current_file)

        self.find_shortcut = QShortcut(QKeySequence("Ctrl+F"), self)
        self.find_shortcut.activated.connect(self.show_find_dialog)

        self.find_dialog = None  # кэш диалога

        # === Open initial folder ===
        self.load_state()
        

    def save_state(self):
        """Сохраняет текущее состояние программы"""
        state = {
            "root_path": str(self.current_root) if self.current_root else "",
            "current_file": str(self.current_file) if self.current_file else "",
            "queue": []
        }
        
        # Сохраняем очередь
        for i in range(self.queue_list.count()):
            item = self.queue_list.item(i)
            job_data = self.queue.get_job_data(i)  # ← нужно реализовать этот метод
            if job_data:
                state["queue"].append({
                    "inp": str(job_data["inp"]),
                    "out": str(job_data["out"]),
                    "display_name": job_data["display_name"]
                })
        
        try:
            with open(self.state_file, 'w', encoding='utf-8') as f:
                json.dump(state, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[WARN] Failed to save state: {e}")

    def load_state(self):
        """Загружает состояние из state.json."""
        if not self.state_file.is_file():
            return

        try:
            with open(self.state_file, 'r', encoding='utf-8') as f:
                state = json.load(f)

            # Восстанавливаем очередь
            if "queue" in state:
                for item in state["queue"]:
                    inp_path = Path(item["inp"])
                    if inp_path.is_file():
                        out_path = inp_path.parent / ".." / "Results" / (inp_path.stem + ".out")
                        out_path = out_path.resolve()
                        # Воссоздаём job вручную (без display_name пересчёта)
                        self.queue._jobs.append({
                            'inp': inp_path,
                            'out': out_path,
                            'display_name': item.get('display_name', inp_path.name),
                            'status': '⏹️ Pending'
                        })
                        # Обновляем UI
                        display_name = item.get('display_name', inp_path.name)
                        list_item = QListWidgetItem(f"⏹️ {display_name}")
                        list_item.setData(Qt.UserRole, str(inp_path))
                        list_item.setData(Qt.UserRole + 1, display_name)
                        self.queue_list.addItem(list_item)

            # Восстанавливаем открытый файл
            if state.get("current_file") and Path(state["current_file"]).is_file():
                self.current_file = state["current_file"]
                try:
                    with open(self.current_file, 'r', encoding='utf-8', errors='replace') as f:
                        self.editor.setPlainText(f.read())
                    self.file_path_label.setText(self.current_file)
                except:
                    pass

            # Восстанавливаем корневую папку
            root_path = state.get("root_path")
            if root_path and Path(root_path).is_dir():
                self.current_root = Path(root_path)  # ← важно: сохраняем в self.current_root
                self.model.setRootPath(root_path)
                self.tree.setRootIndex(self.model.index(root_path))
                self.setWindowTitle(f"ORCA Project Manager - {Path(root_path).name}")

        except Exception as e:
            print(f"[WARN] Failed to load state: {e}")

    def on_queue_context_menu(self, position):
        item = self.queue_list.itemAt(position)
        if not item:
            return

        menu = QMenu(self)
        action = menu.addAction("🗑️ Remove from Queue")
        action.triggered.connect(lambda: self.remove_queue_item(item))
        menu.exec(self.queue_list.viewport().mapToGlobal(position))

    def on_tree_context_menu(self, position):
        index = self.tree.indexAt(position)
        if not index.isValid():
            return

        path = self.model.filePath(index)
        p = Path(path)

        menu = QMenu(self)

        # Для .inp — добавление в очередь
        if p.is_file() and p.suffix == '.inp':
            menu.addAction("➕ Add to Queue", lambda: self.add_inp_to_queue(p))

        # Для .json — загрузка pipeline
        elif p.is_file() and p.suffix == '.json':
            menu.addAction("📥 Add Pipeline to Queue", lambda: self.load_pipeline(p))

        # Операции с файлами/папками (доступны для любого существующего пути)
        if p.exists():
            # Переименовать — доступно всегда
            menu.addAction("✏️ Rename", lambda: self.rename_file(p))
            
            # Копировать
            menu.addAction("📋 Copy", lambda: self._copy_path(p))
            # Вырезать
            menu.addAction("✂️ Cut", lambda: self._cut_path(p))
            # Удалить
            menu.addAction("🗑️ Delete", lambda: self._delete_path(p))

        # Вставить (доступно всегда, если есть буфер)
        if self._clipboard_path and self._clipboard_path.exists():
            target_dir = p if p.is_dir() else p.parent
            menu.addAction("📋 Paste", lambda: self._paste_to(target_dir))

        # Создать текстовый файл (только в папке)
        if p.is_dir():
            menu.addAction("📄 New File...", lambda: self._create_text_file(p))

        # Открытие в Chemcraft и создание шаблона (только для файлов)
        if p.is_file():
            if self.chemcraft_linux_exe.is_file():
                menu.addAction("🔬 Open in Chemcraft (Linux)", 
                            lambda: self.open_in_chemcraft_linux(p))
            if self.chemcraft_windows_exe.is_file():
                menu.addAction("🔬 Open in Chemcraft (Windows)", 
                            lambda: self.open_in_chemcraft_windows(p))
            menu.addAction("📄 Create Template", lambda: self._create_template_from_file(p))

        if not menu.isEmpty():
            menu.exec(self.tree.mapToGlobal(position))

    def remove_queue_item(self, item):
        row = self.queue_list.row(item)
        self.queue_list.takeItem(row)
        self.queue.remove_job(row)  # ← требует обновления OrcaQueue

    # В orca_queue.py
    def remove_job(self, index: int):
        if self._current_index >= 0:
            raise RuntimeError("Cannot modify queue after it has started")
        if 0 <= index < len(self._jobs):
            del self._jobs[index]


    def open_folder(self):
        folder = QFileDialog.getExistingDirectory(
            self, "Select Project Folder", str(Path.home()), QFileDialog.ShowDirsOnly
        )
        if folder:
            folder_path = Path(folder)
            self.model.setRootPath(str(folder_path))
            self.tree.setRootIndex(self.model.index(str(folder_path)))
            self.setWindowTitle(f"ORCA Project Manager - {folder_path.name}")
            self.current_root = folder_path  # ← добавлено
            self.save_state()

    def on_file_double_clicked(self, index: QModelIndex):
        path = self.model.filePath(index)
        if Path(path).is_file() and path.endswith(('.inp', '.out', '.txt', '.log', '.json', '.xyz')):
            try:
                with open(path, 'r', encoding='utf-8', errors='replace') as f:
                    content = f.read()
                self.editor.setPlainText(content)
                self.current_file = Path(path)
                self.file_path_label.setText(path)  # ← обновляем метку
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to open file:\n{e}")

    def get_selected_inp_path(self) -> Path | None:
        indexes = self.tree.selectedIndexes()
        if not indexes:
            return None
        path = self.model.filePath(indexes[0])
        p = Path(path)
        if p.is_file() and p.suffix == '.inp':
            return p
        return None

    def add_selected_inp_to_queue(self):
        inp_path = self.get_selected_inp_path()
        if inp_path:
            self.add_inp_to_queue(inp_path)
        else:
            QMessageBox.warning(self, "No .inp selected", "Please select a .inp file in the file manager.")

    def add_inp_to_queue(self, inp_path: Path):
        out_path = inp_path.parent / ".." / "Results" / (inp_path.stem + ".out")
        out_path = out_path.resolve()
        self.queue.add_job(inp_path, out_path)

        display_name = self.queue.get_display_name(len(self.queue._jobs) - 1)
        item = QListWidgetItem(f"⏹️ {display_name}")
        item.setData(Qt.UserRole, str(inp_path))
        item.setData(Qt.UserRole + 1, display_name)
        item.setToolTip(str(inp_path))
        self.queue_list.addItem(item)

    def start_queue(self):
        if self.queue.is_empty():
            QMessageBox.information(self, "Queue empty", "No jobs to run.")
            return
        self.start_queue_btn.setEnabled(False)
        self.stop_queue_btn.setEnabled(True)
        self.clear_queue_btn.setEnabled(False)
        self.queue.start()

    # === Обновление статусов в очереди ===
    def _update_queue_item_status(self, display_name: str, status_emoji: str):
        found = False
        for i in range(self.queue_list.count()):
            item = self.queue_list.item(i)
            stored_name = item.data(Qt.UserRole + 1)
            if stored_name == display_name:
                item.setText(f"{status_emoji} {display_name}")
                break

    def on_job_started(self, inp_name: str):
        idx = self.queue._current_index
        if 0 <= idx < len(self.queue._jobs):
            display_name = self.queue._jobs[idx]['display_name']
            self._update_queue_item_status(display_name, "▶️")

    def on_job_finished(self, inp_name: str, success: bool, out_path: str, display_name: str):
        emoji = "✅" if success else "❌"
        self._update_queue_item_status(display_name, emoji)

    def on_job_error(self, inp_name: str, error: str, display_name: str):
        self._update_queue_item_status(display_name, "⚠️")

    def on_queue_finished(self):
        if not self._manually_stopped:
            QMessageBox.information(self, "Queue done", "All calculations completed.")
        else:
            self._manually_stopped = False  # сброс
        self._on_queue_stopped()
        self.resume_queue_btn.setEnabled(False)
    
    def stop_queue(self):
        self._manually_stopped = True
        self.queue.terminate_current_job()
        self._on_queue_stopped()

    def _on_queue_stopped(self):
        self.start_queue_btn.setEnabled(True)
        self.stop_queue_btn.setEnabled(False)
        self.clear_queue_btn.setEnabled(True)
        self.resume_queue_btn.setEnabled(True)

    def clear_queue(self):
        if self.queue._is_running:
            QMessageBox.warning(self, "Running", "Stop queue before clearing.")
            return
        self.queue_list.clear()
        self.queue.clear()

    def save_current_file(self):
        if not self.current_file:
            return
        try:
            content = self.editor.toPlainText()
            with open(self.current_file, 'w', encoding='utf-8') as f:
                f.write(content)
        except Exception as e:
            QMessageBox.critical(self, "Save Error", f"Failed to save file:\n{e}")

    def closeEvent(self, event):
        self.save_state()
        event.accept()

    def create_pipeline(self):
        if not self.queue._jobs:
            QMessageBox.warning(self, "Empty Queue", "Queue is empty. Nothing to save.")
            return

        # Определяем папку: родитель последнего .inp
        last_inp = self.queue._jobs[-1]['inp']
        pipeline_dir = last_inp.parent

        dialog = PipelineDialog(self)
        if dialog.exec() == QDialog.Accepted:
            name = dialog.get_name()
            if not name:
                QMessageBox.warning(self, "Invalid Name", "Pipeline name cannot be empty.")
                return

            # Формируем имя файла: name.json
            pipeline_path = pipeline_dir / f"{name}.json"

            # Сохраняем данные
            pipeline_data = []
            for job in self.queue._jobs:
                pipeline_data.append({
                    "inp": str(job['inp']),
                    "display_name": job['display_name']
                })

            try:
                with open(pipeline_path, 'w', encoding='utf-8') as f:
                    json.dump(pipeline_data, f, indent=2, ensure_ascii=False)
                QMessageBox.information(self, "Success", f"Pipeline saved to:\n{pipeline_path}")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to save pipeline:\n{e}")

    def load_pipeline(self, json_path: Path):
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                pipeline_data = json.load(f)

            if not isinstance(pipeline_data, list):
                raise ValueError("Invalid pipeline format")

            added = 0
            for item in pipeline_data:
                inp_path = Path(item.get("inp", ""))
                if not inp_path.is_file():
                    continue

                out_path = inp_path.parent / ".." / "Results" / (inp_path.stem + ".out")
                out_path = out_path.resolve()

                # Добавляем в очередь
                self.queue.add_job(inp_path, out_path)
                display_name = item.get("display_name", inp_path.name)
                list_item = QListWidgetItem(f"⏹️ {display_name}")
                list_item.setData(Qt.UserRole, str(inp_path))
                list_item.setData(Qt.UserRole + 1, display_name)
                self.queue_list.addItem(list_item)
                added += 1

            QMessageBox.information(self, "Pipeline Loaded", f"Added {added} jobs to queue.")

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load pipeline:\n{e}")

    def open_in_chemcraft_linux(self, file_path: Path):
        try:
            subprocess.Popen([str(self.chemcraft_linux_exe), str(file_path)])
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to open in Chemcraft (Linux):\n{e}")

    def open_in_chemcraft_windows(self, file_path: Path):
        try:
            wine_prefix = Path.home() / ".wine-chemcraft"
            subprocess.Popen([
                "env",
                "WINEDEBUG=-all",
                f"WINEPREFIX={wine_prefix}",
                "wine",
                str(self.chemcraft_windows_exe),
                str(file_path)
            ])
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to open in Chemcraft (Windows):\n{e}")
            
    def save_settings(self):
        settings = {
            "orca_exe": str(self.orca_exe),
            "chemcraft_linux": str(self.chemcraft_linux_exe),
            "chemcraft_windows": str(self.chemcraft_windows_exe),
            "orca_locale": self.orca_locale,
            "disable_gpu": self.disable_gpu 
        }
        try:
            with open(self.settings_file, 'w', encoding='utf-8') as f:
                json.dump(settings, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[WARN] Failed to save settings: {e}")

    def load_settings(self):
        if not self.settings_file.is_file():
            return

        try:
            with open(self.settings_file, 'r', encoding='utf-8') as f:
                settings = json.load(f)
            
            if "orca_exe" in settings:
                self.orca_exe = Path(settings["orca_exe"])
            if "chemcraft_linux" in settings:
                self.chemcraft_linux_exe = Path(settings["chemcraft_linux"])
            if "chemcraft_windows" in settings:
                self.chemcraft_windows_exe = Path(settings["chemcraft_windows"])
            if "orca_locale" in settings:
                self.orca_locale = settings["orca_locale"]
            if "disable_gpu" in settings:
                self.disable_gpu = settings["disable_gpu"]
                
        except Exception as e:
            print(f"[WARN] Failed to load settings: {e}")

    def open_settings(self):
        dialog = settings.SettingsDialog(
            str(self.orca_exe),
            str(self.chemcraft_linux_exe),
            str(self.chemcraft_windows_exe),
            self.orca_locale,  # ← передаём текущую локаль
            self.disable_gpu,
            self
        )
        if dialog.exec() == QDialog.Accepted:
            self.orca_exe = Path(dialog.get_orca_path())
            self.chemcraft_linux_exe = Path(dialog.get_chemcraft_linux_path())
            self.chemcraft_windows_exe = Path(dialog.get_chemcraft_windows_path())
            self.orca_locale = dialog.get_locale()  # ← сохраняем выбранную локаль
            self.disable_gpu = dialog.get_disable_gpu()
            self.save_settings()
            QMessageBox.information(self, "Success", "Settings saved.")

    def show_find_dialog(self):
        if self.find_dialog is None:
            self.find_dialog = find_dialog.FindDialog(self.editor, self)
        self.find_dialog.search_input.setText(self.editor.textCursor().selectedText())
        self.find_dialog.show()
        self.find_dialog.raise_()
        self.find_dialog.activateWindow()
    
    def get_app_dir(self) -> Path:
        """Возвращает директорию, где находится исполняемый файл."""
        if getattr(sys, 'frozen', False):
            # Запущено как исполняемый файл (PyInstaller)
            return Path(sys.executable).parent
        else:
            # Запущено как скрипт
            return Path(__file__).parent
    
    def resume_queue(self):
        if self.queue.is_empty():
            QMessageBox.information(self, "Queue empty", "No jobs to resume.")
            return
        self.start_queue_btn.setEnabled(False)
        self.resume_queue_btn.setEnabled(False)
        self.stop_queue_btn.setEnabled(True)
        self.clear_queue_btn.setEnabled(False)
        self.queue.resume()
    
    def _copy_path(self, path: Path):
        self._clipboard_path = path
        self._clipboard_is_cut = False

    def _cut_path(self, path: Path):
        self._clipboard_path = path
        self._clipboard_is_cut = True

    def _paste_to(self, target_dir: Path):
        if not self._clipboard_path or not self._clipboard_path.exists():
            return
            
        try:
            base_name = self._clipboard_path.name
            stem = self._clipboard_path.stem
            suffix = self._clipboard_path.suffix
            new_path = target_dir / base_name
            counter = 1

            # Генерируем уникальное имя: file.txt → file_copy1.txt → file_copy2.txt ...
            while new_path.exists():
                new_name = f"{stem}_copy{counter}{suffix}" if suffix else f"{stem}_copy{counter}"
                new_path = target_dir / new_name
                counter += 1

            if self._clipboard_is_cut:
                import shutil
                if self._clipboard_path.is_dir():
                    shutil.move(str(self._clipboard_path), str(new_path))
                else:
                    self._clipboard_path.rename(new_path)
                self._clipboard_path = None
                self._clipboard_is_cut = False
            else:
                import shutil
                if self._clipboard_path.is_dir():
                    shutil.copytree(str(self._clipboard_path), str(new_path))
                else:
                    shutil.copy2(str(self._clipboard_path), str(new_path))
                    
            # Обновляем модель
            self.model.setRootPath(self.model.rootPath())
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to paste:\n{e}")

    def _delete_path(self, path: Path):
        if not path.exists():
            return
        try:
            send2trash(str(path))  # ← перемещает в корзину
            self.model.setRootPath(self.model.rootPath())
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to move to trash:\n{e}")

    def _create_text_file(self, target_dir: Path):
        # Получаем папку шаблонов
        app_dir = self.get_app_dir()
        templates_dir = app_dir / "Templates"
        templates_dir.mkdir(exist_ok=True)
        
        # Собираем список шаблонов (.inp файлы)
        templates = []
        for item in templates_dir.iterdir():
            if item.is_file() and item.suffix == '.inp':
                templates.append(item)
        
        # Показываем диалог
        dialog = CreateFileDialog(templates, self)
        if dialog.exec() == QDialog.Accepted:
            try:
                # Проверяем, выбран ли шаблон
                template = dialog.get_selected_template()
                if template:
                    # Копируем шаблон как есть
                    new_path = target_dir / template.name
                    counter = 1
                    while new_path.exists():
                        stem = template.stem
                        suffix = template.suffix
                        new_name = f"{stem}_copy{counter}{suffix}"
                        new_path = target_dir / new_name
                        counter += 1
                    
                    import shutil
                    shutil.copy2(template, new_path)
                    
                else:
                    # Создаём пустой файл
                    name = dialog.get_custom_name()
                    if not name:
                        return
                    new_path = target_dir / name
                    
                    # Проверяем корректность имени
                    if '/' in name or '\\' in name:
                        QMessageBox.warning(self, "Invalid name", "Filename cannot contain path separators.")
                        return
                        
                    counter = 1
                    base_new_path = new_path
                    while new_path.exists():
                        stem = base_new_path.stem
                        suffix = base_new_path.suffix
                        new_name = f"{stem}_copy{counter}{suffix}" if suffix else f"{stem}_copy{counter}"
                        new_path = target_dir / new_name
                        counter += 1
                    
                    new_path.write_text('', encoding='utf-8')
                
                # Обновляем модель
                self.model.setRootPath(self.model.rootPath())
                
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to create file:\n{e}")

    def _create_template_from_file(self, file_path: Path):
        if not file_path.is_file():
            return
            
        try:
            # Показываем диалог для ввода имени шаблона
            dialog = CreateTemplateDialog(file_path.name, self)
            if dialog.exec() != QDialog.Accepted:
                return
                
            template_name = dialog.get_template_name()
            if not template_name:
                QMessageBox.warning(self, "Invalid name", "Template name cannot be empty.")
                return
                
            app_dir = self.get_app_dir()
            templates_dir = app_dir / "Templates"
            templates_dir.mkdir(exist_ok=True)
            
            template_path = templates_dir / template_name
            
            # Проверяем, существует ли шаблон с таким именем
            if template_path.exists():
                QMessageBox.warning(
                    self, "Template exists", 
                    f"Template '{template_name}' already exists in Templates folder.\n"
                    "Please choose a different name or delete the existing template."
                )
                return
                
            # Копируем файл как шаблон
            import shutil
            shutil.copy2(file_path, template_path)
            
            # Обновляем модель
            self.model.setRootPath(self.model.rootPath())
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to create template:\n{e}")

    def reload_current_file(self):
        """Перезагружает текущий файл из диска"""
        if not self.current_file or not self.current_file.is_file():
            return
        
        try:
            with open(self.current_file, 'r', encoding='utf-8') as f:
                content = f.read()
            self.editor.setPlainText(content)
            self.file_path_label.setText(f"Opened: {self.current_file}")
        except Exception as e:
            QMessageBox.warning(self, "Reload Error", f"Failed to reload file:\n{e}")

    def rename_file(self, old_path: Path):
        """Переименовывает файл или папку"""
        old_name = old_path.name
        
        new_name, ok = QInputDialog.getText(
            self, "Rename", "New name:", text=old_name
        )
        
        if not ok or not new_name.strip() or new_name == old_name:
            return
            
        new_name = new_name.strip()
        new_path = old_path.parent / new_name
        
        if new_path.exists():
            QMessageBox.warning(self, "Error", f"File/folder already exists:\n{new_path}")
            return
            
        try:
            old_path.rename(new_path)
            # Обновляем текущий открытый файл, если он был переименован
            if self.current_file and self.current_file == old_path:
                self.current_file = new_path
                self.file_path_label.setText(str(new_path))
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to rename:\n{e}")
    

def main():
    app = QApplication(sys.argv)
    window = OrcaGUI()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()