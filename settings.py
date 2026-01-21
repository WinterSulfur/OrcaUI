from PySide6.QtWidgets import QDialog, QLabel, QLineEdit, QPushButton, QVBoxLayout, QHBoxLayout, QFileDialog

class SettingsDialog(QDialog):
    def __init__(self, orca_path: str, chemcraft_path: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.resize(500, 150)

        # ORCA
        self.orca_input = QLineEdit(orca_path)
        orca_browse = QPushButton("Browse...")
        orca_browse.clicked.connect(lambda: self._browse_file(self.orca_input, "Select ORCA executable"))

        orca_layout = QHBoxLayout()
        orca_layout.addWidget(QLabel("ORCA path:"))
        orca_layout.addWidget(self.orca_input)
        orca_layout.addWidget(orca_browse)

        # Chemcraft
        self.chemcraft_input = QLineEdit(chemcraft_path)
        chemcraft_browse = QPushButton("Browse...")
        chemcraft_browse.clicked.connect(lambda: self._browse_file(self.chemcraft_input, "Select Chemcraft executable"))

        chemcraft_layout = QHBoxLayout()
        chemcraft_layout.addWidget(QLabel("Chemcraft path:"))
        chemcraft_layout.addWidget(self.chemcraft_input)
        chemcraft_layout.addWidget(chemcraft_browse)

        # Кнопки
        btn_ok = QPushButton("Apply")
        btn_cancel = QPushButton("Cancel")
        btn_ok.clicked.connect(self.accept)
        btn_cancel.clicked.connect(self.reject)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_layout.addWidget(btn_ok)
        btn_layout.addWidget(btn_cancel)

        layout = QVBoxLayout()
        layout.addLayout(orca_layout)
        layout.addLayout(chemcraft_layout)
        layout.addLayout(btn_layout)
        self.setLayout(layout)

    def _browse_file(self, line_edit: QLineEdit, title: str):
        path, _ = QFileDialog.getOpenFileName(self, title, "", "Executable (*.exe)")
        if path:
            line_edit.setText(path)

    def get_orca_path(self) -> str:
        return self.orca_input.text()

    def get_chemcraft_path(self) -> str:
        return self.chemcraft_input.text()