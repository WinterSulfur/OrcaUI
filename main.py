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
from PySide6.QtWidgets import QFileDialog, QMenuBar, QMenu
from PySide6.QtGui import QFont, QKeySequence, QShortcut, QIcon
from PySide6.QtCore import Qt, QModelIndex, QMimeData, QUrl
from PySide6.QtGui import QDragEnterEvent, QDropEvent

import settings
import orca_queue
import find_dialog


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
        self.resize(1400, 800)

        # === Paths and core data ===
        app_dir = Path(__file__).parent
        self.state_file = app_dir / "state.json"
        self.settings_file = app_dir / "settings.json"
        self.load_settings()
        self.orca_exe = Path(r"F:\Modelling\ORCA\orca.exe")
        self.chemcraft_exe = Path(r"F:\Modelling\Chemcraft\Chemcraft.exe")
        self.queue = orca_queue.OrcaQueue(self.orca_exe, log_dir=app_dir / "logs", gui=self)
        self._manually_stopped = False
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
        self.model.setNameFilters(["*.inp", "*.out", "*trj.xyz", "*.json"])
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

        # === Queue control buttons ===
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

        # === Кнопка Create Pipeline (отдельно снизу) ===
        self.create_pipeline_btn = QPushButton("📦 Create Pipeline")
        self.create_pipeline_btn.clicked.connect(self.create_pipeline)

        # === Right panel: queue list + buttons ===
        queue_layout = QVBoxLayout()
        queue_layout.addWidget(self.queue_list)
        queue_layout.addWidget(queue_main_buttons_container)
        queue_layout.addWidget(self.create_pipeline_btn)  # ← теперь снизу

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

        self.find_shortcut = QShortcut(QKeySequence("Ctrl+F"), self)
        self.find_shortcut.activated.connect(self.show_find_dialog)

        self.find_dialog = None  # кэш диалога

        # === Open initial folder ===
        self.load_state()
        

    def save_state(self):
        """Сохраняет текущее состояние в state.json."""
        state = {
            "root_path": str(self.model.rootPath()) if self.model.rootPath() else None,
            "current_file": self.current_file if self.current_file else None,
            "queue": []
        }

        # Сохраняем очередь
        for i in range(len(self.queue._jobs)):
            job = self.queue._jobs[i]
            state["queue"].append({
                "inp": str(job['inp']),
                "display_name": job['display_name']
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

        # Для ЛЮБОГО файла — открытие в Chemcraft (если поддерживается)
        if p.is_file():
            menu.addAction("🔬 Open in Chemcraft", lambda: self.open_in_chemcraft(p))

        if not menu.isEmpty():
            menu.exec(self.tree.viewport().mapToGlobal(position))

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
            # Сохраняем состояние после выбора
            self.save_state()

    def on_file_double_clicked(self, index: QModelIndex):
        path = self.model.filePath(index)
        if Path(path).is_file() and path.endswith(('.inp', '.out', '.txt', '.log', '.json', '.xyz')):
            try:
                with open(path, 'r', encoding='utf-8', errors='replace') as f:
                    content = f.read()
                self.editor.setPlainText(content)
                self.current_file = path
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

        # === Закрываем открытый файл ===
        self.editor.setPlainText("")
        self.current_file = None
        self.file_path_label.setText("No file opened")

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
    
    def stop_queue(self):
        self._manually_stopped = True
        self.queue.terminate_current_job()
        if self.queue._current_index >= 0 and self.queue._current_index < len(self.queue._jobs):
            self.queue._jobs[self.queue._current_index]['status'] = '⏹️ Stopped'
            self.queue._write_log()
        self._on_queue_stopped()

    def _on_queue_stopped(self):
        self.start_queue_btn.setEnabled(True)
        self.stop_queue_btn.setEnabled(False)
        self.clear_queue_btn.setEnabled(True)

    def clear_queue(self):
        if self.queue._current_index >= 0:
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

    def open_in_chemcraft(self, file_path: Path):
        if not self.chemcraft_exe.is_file():
            QMessageBox.critical(self, "Error", f"Chemcraft not found:\n{self.chemcraft_exe}")
            return

        if not file_path.is_file():
            return

        try:
            # Запускаем Chemcraft с файлом
            subprocess.Popen([str(self.chemcraft_exe), str(file_path)])
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to open in Chemcraft:\n{e}")
    
    def save_settings(self):
        settings = {
            "orca_exe": str(self.orca_exe),
            "chemcraft_exe": str(self.chemcraft_exe)
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
            self.orca_exe = Path(settings.get("orca_exe", r"F:\Modelling\ORCA\orca.exe"))
            self.chemcraft_exe = Path(settings.get("chemcraft_exe", r"F:\Modelling\Chemcraft\Chemcraft.exe"))
        except Exception as e:
            print(f"[WARN] Failed to load settings: {e}")

    def open_settings(self):
        dialog = settings.SettingsDialog(
            str(self.orca_exe),
            str(self.chemcraft_exe),
            self
        )
        if dialog.exec() == QDialog.Accepted:
            self.orca_exe = Path(dialog.get_orca_path())
            self.chemcraft_exe = Path(dialog.get_chemcraft_path())
            self.save_settings()
            QMessageBox.information(self, "Success", "Settings saved.")

    def show_find_dialog(self):
        if self.find_dialog is None:
            self.find_dialog = find_dialog.FindDialog(self.editor, self)
        self.find_dialog.search_input.setText(self.editor.textCursor().selectedText())
        self.find_dialog.show()
        self.find_dialog.raise_()
        self.find_dialog.activateWindow()

    def release_filesystem_model(self):
        """Полностью отключает модель от дерева."""
        self._saved_root_path = self.model.rootPath()
        self._expanded_paths = self._get_expanded_paths(self.tree.rootIndex())
        self.tree.setModel(None)  # ← ключевое!

    def restore_filesystem_model(self):
        """Восстанавливает модель и состояние дерева."""
        self.tree.setModel(self.model)
        if hasattr(self, '_saved_root_path') and self._saved_root_path:
            self.model.setRootPath(self._saved_root_path)
            self.tree.setRootIndex(self.model.index(self._saved_root_path))
            self._restore_expanded_paths(self.tree.rootIndex(), self._expanded_paths)

    def _get_expanded_paths(self, index):
        """Сохраняет развёрнутые пути."""
        paths = []
        if self.tree.isExpanded(index):
            path = self.model.filePath(index)
            if path:
                paths.append(path)
            for row in range(self.model.rowCount(index)):
                child = self.model.index(row, 0, index)
                paths.extend(self._get_expanded_paths(child))
        return paths

    def _restore_expanded_paths(self, index, saved_paths):
        """Восстанавливает развёрнутые пути."""
        if not saved_paths:
            return
        path = self.model.filePath(index)
        if path in saved_paths:
            self.tree.expand(index)
        for row in range(self.model.rowCount(index)):
            child = self.model.index(row, 0, index)
            self._restore_expanded_paths(child, saved_paths)

    

def main():
    app = QApplication(sys.argv)
    window = OrcaGUI()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()