# settings.py
from PySide6.QtWidgets import (
    QDialog, QLabel, QLineEdit, QPushButton, QComboBox,
    QVBoxLayout, QHBoxLayout, QFileDialog, QCheckBox
)

class SettingsDialog(QDialog):
    def __init__(self, orca_path: str, chemcraft_linux: str, chemcraft_windows: str, locale: str,  disable_gpu: bool, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.resize(600, 220)

        # ORCA
        self.orca_input = QLineEdit(orca_path)
        orca_browse = QPushButton("Browse...")
        orca_browse.clicked.connect(lambda: self._browse_file(self.orca_input, "Select ORCA executable"))

        orca_layout = QHBoxLayout()
        orca_layout.addWidget(QLabel("ORCA path:"))
        orca_layout.addWidget(self.orca_input)
        orca_layout.addWidget(orca_browse)

        # Chemcraft Linux
        self.chemcraft_linux_input = QLineEdit(chemcraft_linux)
        chemcraft_linux_browse = QPushButton("Browse...")
        chemcraft_linux_browse.clicked.connect(
            lambda: self._browse_file(self.chemcraft_linux_input, "Select Chemcraft (Linux)")
        )

        chemcraft_linux_layout = QHBoxLayout()
        chemcraft_linux_layout.addWidget(QLabel("Chemcraft (Linux):"))
        chemcraft_linux_layout.addWidget(self.chemcraft_linux_input)
        chemcraft_linux_layout.addWidget(chemcraft_linux_browse)

        # Chemcraft Windows
        self.chemcraft_windows_input = QLineEdit(chemcraft_windows)
        chemcraft_windows_browse = QPushButton("Browse...")
        chemcraft_windows_browse.clicked.connect(
            lambda: self._browse_file(self.chemcraft_windows_input, "Select Chemcraft.exe (Windows)")
        )

        chemcraft_windows_layout = QHBoxLayout()
        chemcraft_windows_layout.addWidget(QLabel("Chemcraft (Windows):"))
        chemcraft_windows_layout.addWidget(self.chemcraft_windows_input)
        chemcraft_windows_layout.addWidget(chemcraft_windows_browse)

        # Locale
        self.locale_combo = QComboBox()
        self.locale_combo.addItems([
            "C.UTF-8",
            "en_US.UTF-8",
            "ru_RU.UTF-8",
            "POSIX"
        ])
        self.locale_combo.setCurrentText(locale)

        locale_layout = QHBoxLayout()
        locale_layout.addWidget(QLabel("Locale for ORCA:"))
        locale_layout.addWidget(self.locale_combo)

        self.disable_gpu_checkbox = QCheckBox("Disable GPU for ORCA (prevents crashes)")
        self.disable_gpu_checkbox.setChecked(disable_gpu)

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
        layout.addLayout(chemcraft_linux_layout)
        layout.addLayout(chemcraft_windows_layout)
        layout.addLayout(locale_layout)
        layout.addLayout(btn_layout)
        self.setLayout(layout)
        layout.addWidget(self.disable_gpu_checkbox)

    def _browse_file(self, line_edit: QLineEdit, title: str):
        path, _ = QFileDialog.getOpenFileName(self, title, "", "Executable (*)")
        if path:
            line_edit.setText(path)

    def get_orca_path(self) -> str:
        return self.orca_input.text()

    def get_chemcraft_linux_path(self) -> str:
        return self.chemcraft_linux_input.text()

    def get_chemcraft_windows_path(self) -> str:
        return self.chemcraft_windows_input.text()
    
    def get_locale(self) -> str:
        return self.locale_combo.currentText()
    
    def get_disable_gpu(self) -> bool:
        return self.disable_gpu_checkbox.isChecked()