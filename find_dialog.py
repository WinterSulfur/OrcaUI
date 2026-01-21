from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QCheckBox, QPushButton, QTextEdit, QPlainTextEdit
)
from PySide6.QtGui import QTextDocument
import re


class FindDialog(QDialog):
    def __init__(self, editor: QPlainTextEdit, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Find")
        self.resize(700, 500)
        self.editor = editor

        # Поле поиска
        self.search_input = QLineEdit()
        self.case_sensitive = QCheckBox("Match case")
        self.whole_words = QCheckBox("Whole words only")

        find_btn = QPushButton("Find All")
        find_btn.clicked.connect(self.find_all)

        top_layout = QHBoxLayout()
        top_layout.addWidget(QLabel("Find what:"))
        top_layout.addWidget(self.search_input)
        top_layout.addWidget(self.case_sensitive)
        top_layout.addWidget(self.whole_words)
        top_layout.addWidget(find_btn)

        # Текстовое поле для результатов
        self.results_text = QTextEdit()
        self.results_text.setReadOnly(True)
        self.results_text.setStyleSheet("font-family: Consolas; font-size: 10pt;")

        layout = QVBoxLayout()
        layout.addLayout(top_layout)
        layout.addWidget(self.results_text)
        self.setLayout(layout)

    def find_all(self):
        text = self.editor.toPlainText()
        if not text.strip():
            self.results_text.clear()
            return

        pattern = self.search_input.text()
        if not pattern:
            self.results_text.clear()
            return

        # Флаги
        flags = 0
        if not self.case_sensitive.isChecked():
            flags |= re.IGNORECASE

        escaped = re.escape(pattern)
        if self.whole_words.isChecked():
            escaped = r'\b' + escaped + r'\b'

        regex = re.compile(escaped, flags)

        lines = text.split('\n')
        html_lines = []
        for i, line in enumerate(lines, 1):
            matches = list(regex.finditer(line))
            if matches:
                # Подсвечиваем совпадения
                highlighted = self._highlight_matches(line, matches)
                html_lines.append(f'<span style="color:#888;">{i:4}:</span> {highlighted}')

        if html_lines:
            html = '<br>'.join(html_lines)
            self.results_text.setHtml(html)
        else:
            self.results_text.setPlainText("No matches found.")

    def _highlight_matches(self, line: str, matches) -> str:
        """Возвращает HTML-строку с жёлтым фоном для совпадений."""
        last_end = 0
        parts = []
        for match in matches:
            start, end = match.span()
            # Экранируем HTML
            before = self._escape_html(line[last_end:start])
            match_text = self._escape_html(line[start:end])
            parts.append(before)
            parts.append(f'<span style="background-color:#FFFF00;">{match_text}</span>')
            last_end = end
        after = self._escape_html(line[last_end:])
        parts.append(after)
        return ''.join(parts)

    def _escape_html(self, text: str) -> str:
        return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")