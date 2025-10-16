from PyQt6.QtCore import Qt, QSize
from PyQt6.QtWidgets import (
    QLabel, QVBoxLayout, QWidget, QFrame, QMessageBox, QFileDialog,
    QHBoxLayout, QPushButton, QTextEdit, QSpacerItem, QSizePolicy
)
from PyQt6.QtGui import QIcon
import os
import shutil

FOLDER_BG_COLOR = "#fff9c4"

class NotesView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("notesRoot")
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(32, 32, 32, 32)
        self.main_layout.setSpacing(16)
        self.init_notes_sidebar()
        self.init_main_view()

    def init_main_view(self):
        self.clear_layout(self.main_layout)

        title = QLabel("Notatki")
        title.setObjectName("h1")
        self.main_layout.addWidget(title)

        self.folders = [
            {"label": "Zeszyt", "folder_path": os.path.join(os.path.expanduser("~"), "Desktop")},
            {"label": "Zdjęcia", "folder_path": os.path.join(os.path.expanduser("~"), "Pictures")},
            {"label": "Inne", "folder_path": os.path.join(os.path.expanduser("~"), "Desktop")},
        ]

        folders_row = QHBoxLayout()
        folders_row.setSpacing(24)
        for folder in self.folders:
            tile = self.create_folder_tile(folder["label"], FOLDER_BG_COLOR, folder["folder_path"])
            folders_row.addWidget(tile)
        self.main_layout.addLayout(folders_row)
        self.main_layout.addStretch(1)
        self.notes_sidebar.raise_()

    def init_notes_sidebar(self):
        self.sidebar_width = 300
        self.sidebar_collapsed_width = 32

        self.notes_sidebar = QFrame(self)
        self.notes_sidebar.setObjectName("notesSidebar")
        self.notes_sidebar.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.notes_sidebar.setStyleSheet("""
            QFrame#notesSidebar {
                background-color: rgba(255,255,255,180);
                border-left: 2px solid #e0e4f6;
                border-top-left-radius: 60px;
                border-bottom-left-radius: 60px;
            }
        """)
        self.notes_sidebar.setGeometry(self.width() - self.sidebar_collapsed_width, 0, self.sidebar_width, self.height())
        self.notes_sidebar.raise_()

        # Przycisk toggle zawsze przy prawej krawędzi, wyśrodkowany w pionie
        self.toggle_btn = QPushButton("<")
        self.toggle_btn.setFixedWidth(self.sidebar_collapsed_width)
        self.toggle_btn.setFixedHeight(48)
        self.toggle_btn.setStyleSheet("""
            QPushButton {
                background: #e6edff;
                border: none;
                border-top-left-radius: 24px;
                border-bottom-left-radius: 24px;
                font-size: 18px;
                color: #3960f5;
            }
            QPushButton:hover {
                background: #d0e0ff;
            }
        """)
        self.toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.toggle_btn.clicked.connect(self.toggle_notes_sidebar)

        # Kalkulator
        self.calc_btn = QPushButton()
        self.calc_btn.setIcon(QIcon.fromTheme("accessories-calculator"))
        self.calc_btn.setIconSize(QSize(28, 28))
        self.calc_btn.setFixedSize(44, 44)
        self.calc_btn.setStyleSheet("border: none; background: transparent;")
        self.calc_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.calc_btn.clicked.connect(self.show_calculator)

        # Notatki
        self.notes_content = QWidget()
        notes_content_layout = QVBoxLayout(self.notes_content)
        notes_content_layout.setContentsMargins(16, 16, 16, 16)
        notes_content_layout.setSpacing(12)
        notes_label = QLabel("Twoje notatki")
        notes_label.setStyleSheet("font-size: 18px; font-weight: bold;")
        notes_content_layout.addWidget(notes_label)
        self.notes_edit = QTextEdit()
        self.notes_edit.setPlaceholderText("Zapisz tutaj swoje notatki...")
        self.notes_edit.setStyleSheet("""
            font-size: 15px;
            border: 2px solid rgba(57, 96, 245, 0.3);
            border-radius: 8px;
            background: #f8faff;
            margin-left: 8px;
            min-height: 180px;
            min-width: 180px;
            padding: 14px;
        """)
        notes_content_layout.addWidget(self.notes_edit, stretch=1)

        self.sidebar_layout = QVBoxLayout(self.notes_sidebar)
        self.sidebar_layout.setContentsMargins(0, 0, 0, 0)
        self.sidebar_layout.setSpacing(0)

        self.sidebar_expanded = False
        self.set_sidebar_state(False)

    def set_sidebar_state(self, expanded):
        self.sidebar_expanded = expanded
        # Wyczyść sidebar_layout
        while self.sidebar_layout.count():
            item = self.sidebar_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.setParent(None)
            else:
                sublayout = item.layout()
                if sublayout:
                    while sublayout.count():
                        subitem = sublayout.takeAt(0)
                        subwidget = subitem.widget()
                        if subwidget:
                            subwidget.setParent(None)
        if expanded:
            # Panel wysunięty: notatki na całą wysokość, toggle po prawej, kalkulator ukryty
            content_row = QHBoxLayout()
            content_row.setContentsMargins(0, 0, 0, 0)
            content_row.setSpacing(0)
            content_row.addWidget(self.notes_content, stretch=1)
            # Przycisk toggle po prawej, wyśrodkowany w pionie
            btn_col = QVBoxLayout()
            btn_col.addStretch(1)
            btn_col.addWidget(self.toggle_btn, alignment=Qt.AlignmentFlag.AlignRight)
            btn_col.addStretch(1)
            content_row.addLayout(btn_col)
            self.sidebar_layout.addLayout(content_row)
            self.calc_btn.hide()
            self.notes_content.show()
            self.toggle_btn.setText(">")
            self.notes_sidebar.setGeometry(self.width() - self.sidebar_width, 0, self.sidebar_width, self.height())
        else:
            # Panel zwinięty: tylko toggle i kalkulator na dole
            col = QVBoxLayout()
            col.setContentsMargins(0, 0, 0, 0)
            col.setSpacing(0)
            col.addStretch(1)
            col.addWidget(self.toggle_btn, alignment=Qt.AlignmentFlag.AlignHCenter)
            col.addStretch(1)
            col.addWidget(self.calc_btn, alignment=Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom)
            self.sidebar_layout.addLayout(col)
            self.calc_btn.show()
            self.notes_content.hide()
            self.toggle_btn.setText("<")
            self.notes_sidebar.setGeometry(self.width() - self.sidebar_collapsed_width, 0, self.sidebar_collapsed_width, self.height())

    def resizeEvent(self, event):
        if hasattr(self, 'notes_sidebar'):
            if self.sidebar_expanded:
                self.notes_sidebar.setGeometry(self.width() - self.sidebar_width, 0, self.sidebar_width, self.height())
            else:
                self.notes_sidebar.setGeometry(self.width() - self.sidebar_collapsed_width, 0, self.sidebar_collapsed_width, self.height())
        super().resizeEvent(event)

    def toggle_notes_sidebar(self):
        self.set_sidebar_state(not self.sidebar_expanded)

    def show_calculator(self):
        from ui.calculator_view import CalculatorDialog
        dlg = CalculatorDialog(self)
        dlg.exec()

    def clear_layout(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.setParent(None)
            else:
                sublayout = item.layout()
                if sublayout:
                    self.clear_layout(sublayout)

    def create_folder_tile(self, label, bg_color, folder_path):
        tile = QFrame()
        tile.setObjectName("folderTile")
        tile.setCursor(Qt.CursorShape.PointingHandCursor)
        tile.setFixedSize(120, 120)
        tile.setStyleSheet(f"""
            QFrame#folderTile {{
                background-color: {bg_color};
                border-radius: 20px;
                border: 1.5px solid #cfd9ff;
            }}
            QFrame#folderTile:hover {{
                background-color: #e6edff;
                border: 1.5px solid #3960f5;
            }}
        """)
        tile_layout = QVBoxLayout(tile)
        tile_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        folder_icon = QLabel("📁")
        folder_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        folder_icon.setStyleSheet("font-size: 48px;")
        tile_layout.addWidget(folder_icon)

        text_label = QLabel(label)
        text_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        text_label.setStyleSheet("font-size: 15px; font-weight: 600;")
        tile_layout.addWidget(text_label)

        def mousePressEvent(event):
            self.show_folder_view(folder_path, label)
        tile.mousePressEvent = mousePressEvent

        return tile

    def show_folder_view(self, folder_path, label):
        self.clear_layout(self.main_layout)

        back_btn = QPushButton("← Powrót")
        back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        back_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: none;
                font-size: 15px;
                color: #3960f5;
                text-align: left;
            }
            QPushButton:hover {
                text-decoration: underline;
            }
        """)
        back_btn.clicked.connect(self.init_main_view)
        self.main_layout.addWidget(back_btn, alignment=Qt.AlignmentFlag.AlignLeft)

        folder_label = QLabel(f"Folder: {label}")
        folder_label.setObjectName("h1")
        self.main_layout.addWidget(folder_label)

        add_tile = self.create_add_file_tile(folder_path)
        row = QHBoxLayout()
        row.addWidget(add_tile)
        self.main_layout.addLayout(row)
        self.main_layout.addStretch(1)

        self.notes_sidebar.raise_()

    def create_add_file_tile(self, folder_path):
        tile = QFrame()
        tile.setObjectName("addFileTile")
        tile.setCursor(Qt.CursorShape.PointingHandCursor)
        tile.setFixedSize(120, 120)
        tile.setStyleSheet("""
            QFrame#addFileTile {
                background-color: #f2f5ff;
                border-radius: 20px;
                border: 1.5px solid #cfd9ff;
            }
            QFrame#addFileTile:hover {
                background-color: #e6edff;
                border: 1.5px solid #3960f5;
            }
        """)
        layout = QVBoxLayout(tile)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        plus_label = QLabel("+")
        plus_label.setObjectName("tilePlus")
        plus_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        plus_label.setStyleSheet("""
            QLabel#tilePlus {
                font-size: 48px;
                color: #3960f5;
                font-weight: bold;
            }
        """)
        layout.addWidget(plus_label)

        text_label = QLabel("Dodaj plik")
        text_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        text_label.setStyleSheet("font-size: 15px; font-weight: 600;")
        layout.addWidget(text_label)

        def mousePressEvent(event):
            self.add_file_to_folder(folder_path)
        tile.mousePressEvent = mousePressEvent

        return tile

    def add_file_to_folder(self, folder_path):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Wybierz plik do dodania",
            folder_path,
            "Wszystkie pliki (*.*)"
        )
        if file_path:
            try:
                shutil.copy(file_path, folder_path)
                QMessageBox.information(self, "Dodano plik", f"Plik został dodany do {folder_path}")
            except Exception as e:
                QMessageBox.warning(self, "Błąd", f"Nie udało się dodać pliku: {e}")
