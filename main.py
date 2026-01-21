# main.py
import sys
from pathlib import Path
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QSplitter, QTreeView,
    QFileSystemModel, QPlainTextEdit, QWidget, QVBoxLayout,
    QPushButton, QListWidget, QListWidgetItem, QHBoxLayout,
    QMessageBox, QAbstractItemView, QLabel, QLineEdit
) 
from PySide6.QtWidgets import QFileDialog, QMenuBar, QMenu
from PySide6.QtGui import QFont, QKeySequence, QShortcut, QIcon
from PySide6.QtCore import Qt, QModelIndex, QMimeData, QUrl
from PySide6.QtGui import QDragEnterEvent, QDropEvent
import orca_queue


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


class OrcaGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ORCA Project Manager")
        self.resize(1400, 800)

        # === Paths and core data ===
        app_dir = Path(__file__).parent
        self.orca_exe = Path(r"F:\Modelling\ORCA\orca.exe")
        self.queue = orca_queue.OrcaQueue(self.orca_exe, log_dir=app_dir / "logs")
        self._manually_stopped = False
        self.current_file = None

        # === Window icon ===
        icon_path = app_dir / "Picture.png"
        if icon_path.is_file():
            self.setWindowIcon(QIcon(str(icon_path)))

        # === Menu bar ===
        menubar = self.menuBar()
        file_menu = menubar.addMenu("File")
        open_folder_action = file_menu.addAction("Open Folder...")
        open_folder_action.setShortcut("Ctrl+O")
        open_folder_action.triggered.connect(self.open_folder)

        save_action = file_menu.addAction("Save")
        save_action.setShortcut("Ctrl+S")
        save_action.triggered.connect(self.save_current_file)

        # === File system model ===
        self.model = QFileSystemModel()
        self.model.setRootPath("")
        self.model.setNameFilters(["*.inp", "*.out", "*trj.xyz"])
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

        queue_button_layout = QHBoxLayout()
        queue_button_layout.addWidget(self.start_queue_btn)
        queue_button_layout.addWidget(self.stop_queue_btn)
        queue_button_layout.addWidget(self.clear_queue_btn)

        queue_button_container = QWidget()
        queue_button_container.setLayout(queue_button_layout)

        # === Right panel: queue list + buttons ===
        queue_layout = QVBoxLayout()
        queue_layout.addWidget(self.queue_list)
        queue_layout.addWidget(queue_button_container)
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

        # === Open initial folder ===
        self.open_folder()

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
        if not (p.is_file() and p.suffix == '.inp'):
            return

        menu = QMenu(self)
        action = menu.addAction("➕ Add to Queue")
        action.triggered.connect(lambda: self.add_inp_to_queue(p))
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
            self.setWindowTitle(f"ORCA Project Manager")
        else:
            # Если пользователь отменил — завершить или оставить пустым
            if self.tree.model().rowCount(self.tree.rootIndex()) == 0:
                # Можно выйти, если не выбрана папка
                pass

    def on_file_double_clicked(self, index: QModelIndex):
        path = self.model.filePath(index)
        if Path(path).is_file() and path.endswith(('.inp', '.out', '.txt', '.log')):
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

def main():
    app = QApplication(sys.argv)
    window = OrcaGUI()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()