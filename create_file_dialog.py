from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QListWidget, QGroupBox
from pathlib import Path
from PySide6.QtWidgets import (QVBoxLayout,
    QPushButton, QListWidget, QListWidgetItem, QHBoxLayout, QLabel, QLineEdit, QDialog) 
from PySide6.QtCore import Qt


class CreateFileDialog(QDialog):
    def __init__(self, templates: list[Path], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Create New File")
        self.resize(400, 300)
        
        # === Поле для произвольного имени ===
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("filename.inp or script.py")
        
        custom_group = QGroupBox("Create empty file")
        custom_layout = QVBoxLayout()
        custom_layout.addWidget(QLabel("File name (with extension):"))
        custom_layout.addWidget(self.name_input)
        custom_group.setLayout(custom_layout)
        
        # === Список шаблонов ===
        self.template_list = QListWidget()
        for template in templates:
            item = QListWidgetItem(template.name)
            item.setData(Qt.UserRole, str(template))
            self.template_list.addItem(item)
        
        template_group = QGroupBox("Create from template")
        template_layout = QVBoxLayout()
        template_layout.addWidget(QLabel("Select template:"))
        template_layout.addWidget(self.template_list)
        template_group.setLayout(template_layout)
        
        # === Кнопки ===
        btn_create = QPushButton("Create")
        btn_cancel = QPushButton("Cancel")
        btn_create.clicked.connect(self.accept)
        btn_cancel.clicked.connect(self.reject)
        
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_layout.addWidget(btn_create)
        btn_layout.addWidget(btn_cancel)
        
        # === Основной layout ===
        layout = QVBoxLayout()
        layout.addWidget(custom_group)
        layout.addWidget(template_group)
        layout.addLayout(btn_layout)
        self.setLayout(layout)
    
    def get_custom_name(self) -> str:
        return self.name_input.text().strip()
    
    def get_selected_template(self) -> Path | None:
        items = self.template_list.selectedItems()
        if items:
            return Path(items[0].data(Qt.UserRole))
        return None