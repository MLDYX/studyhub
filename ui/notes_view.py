from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QLabel, QVBoxLayout, QWidget, QFrame, QMessageBox, QFileDialog, QHBoxLayout, QPushButton, QSizePolicy
)
import sys
import os
import subprocess
import shutil

class NotesView(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("notesRoot")
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(32, 32, 32, 32)
        self.main_layout.setSpacing(16)
        self.init_main_view()

    def init_main_view(self):
        self.clear_layout(self.main_layout)

        title = QLabel("Notatki")
        title.setObjectName("h1")
        self.main_layout.addWidget(title)

        # Przycisk rozwijający sekcję aplikacji
        self.expand_btn = QPushButton("▶ Aplikacje biurowe")
        self.expand_btn.setCheckable(True)
        self.expand_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: none;
                font-size: 15px;
                text-align: left;
            }
            QPushButton:checked {
                font-weight: bold;
            }
        """)
        self.expand_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.expand_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.expand_btn.clicked.connect(self.toggle_office_section)
        self.main_layout.addWidget(self.expand_btn)

        # Kontener na kafelki aplikacji
        self.office_section = QWidget()
        office_row = QHBoxLayout(self.office_section)
        office_row.setSpacing(16)
        office_row.setContentsMargins(0, 0, 0, 0)

        office_tiles = [
            {
                "label": "Word",
                "icon": "W",
                "bg_color": "#e6edff",
                "icon_color": "#2b44ff",
                "open_cmd": ["start", "", "winword:"]
            },
            {
                "label": "Excel",
                "icon": "E",
                "bg_color": "#e6fff2",
                "icon_color": "#109c70",
                "open_cmd": ["start", "", "excel:"]
            },
            {
                "label": "PowerPoint",
                "icon": "P",
                "bg_color": "#fff6f1",
                "icon_color": "#d05c1f",
                "open_cmd": ["start", "", "powerpoint:"]
            },
            {
                "label": "Access",
                "icon": "A",
                "bg_color": "#f1fff6",
                "icon_color": "#1f8a3a",
                "open_cmd": ["start", "", "access:"]
            },
            {
                "label": "Kalkulator",
                "icon": "C",
                "bg_color": "#f7f8fd",
                "icon_color": "#7b8295",
                "open_cmd": ["calc"]
            },
            {
                "label": "Notatnik",
                "icon": "N",
                "bg_color": "#f7f8fd",
                "icon_color": "#7b8295",
                "open_cmd": ["notepad"]
            },
        ]
        for tile_def in office_tiles:
            tile = self.create_app_tile(
                tile_def["label"],
                tile_def["icon"],
                tile_def["bg_color"],
                tile_def["icon_color"],
                tile_def["open_cmd"],
                small=True
            )
            office_row.addWidget(tile)

        self.office_section.setVisible(False)
        self.main_layout.addWidget(self.office_section)

        #Foldery
        self.folders = [
            {
                "label": "Zeszyt",
                "bg_color": "#fff9c4",  
                "folder_path": os.path.join(os.path.expanduser("~"), "Desktop")
            },
            {
                "label": "Zdjęcia",
                "bg_color": "#fff9c4", 
                "folder_path": os.path.join(os.path.expanduser("~"), "Pictures")
            },
            {
                "label": "Inne",
                "bg_color": "#fff9c4", 
                "folder_path": os.path.join(os.path.expanduser("~"), "Desktop")
            },
        ]

        folders_row = QHBoxLayout()
        folders_row.setSpacing(24)

        for folder_def in self.folders:
            tile = self.create_folder_tile(folder_def["label"], folder_def["bg_color"], folder_def["folder_path"])
            folders_row.addWidget(tile)

        self.main_layout.addLayout(folders_row)
        self.main_layout.addStretch(1)

    def clear_layout(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
            else:
                sublayout = item.layout()
                if sublayout is not None:
                    self.clear_layout(sublayout)

    def toggle_office_section(self):
        expanded = self.expand_btn.isChecked()
        self.office_section.setVisible(expanded)
        self.expand_btn.setText("▼ Aplikacje biurowe" if expanded else "▶ Aplikacje biurowe")

    def create_app_tile(self, label, icon, bg_color, icon_color, open_cmd, small=False):
        tile = QFrame()
        tile.setObjectName("appTile")
        tile.setCursor(Qt.CursorShape.PointingHandCursor)
        if small:
            tile.setFixedSize(80, 80)
            icon_size = 32
            border_radius = 14
            border_width = 1.2
            font_size = 12
        else:
            tile.setFixedSize(120, 120)
            icon_size = 48
            border_radius = 20
            border_width = 1.5
            font_size = 15
        tile.setStyleSheet(f"""
            QFrame#appTile {{
                background-color: {bg_color};
                border-radius: {border_radius}px;
                border: {border_width}px solid #cfd9ff;
            }}
            QFrame#appTile:hover {{
                background-color: #e6edff;
                border: {border_width}px solid #3960f5;
            }}
        """)
        tile_layout = QVBoxLayout(tile)
        tile_layout.setContentsMargins(0, 0, 0, 0)
        tile_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        icon_label = QLabel(icon)
        icon_label.setObjectName("tileIcon")
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_label.setStyleSheet(f"""
            QLabel#tileIcon {{
                font-size: {icon_size}px;
                color: {icon_color};
                font-weight: bold;
            }}
        """)
        tile_layout.addWidget(icon_label)

        text_label = QLabel(label)
        text_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        text_label.setStyleSheet(f"font-size: {font_size}px; font-weight: 600;")
        tile_layout.addWidget(text_label)

        def mousePressEvent(event):
            self.open_app(open_cmd, label)
        tile.mousePressEvent = mousePressEvent

        return tile

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
        tile_layout.setContentsMargins(0, 0, 0, 0)
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

        # Dodaj tytuł folderu
        folder_label = QLabel(f"Folder: {label}")
        folder_label.setObjectName("h1")
        self.main_layout.addWidget(folder_label)

        # Dodaj kafelek "Dodaj plik"
        add_tile = self.create_add_file_tile(folder_path)
        row = QHBoxLayout()
        row.addWidget(add_tile)
        self.main_layout.addLayout(row)
        self.main_layout.addStretch(1)

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
        layout.setContentsMargins(0, 0, 0, 0)
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

    def open_app(self, open_cmd, label):
        try:
            if sys.platform.startswith("win") and open_cmd[0] == "start":
                subprocess.Popen(" ".join(open_cmd), shell=True)
            else:
                subprocess.Popen(open_cmd)
        except Exception:
            QMessageBox.warning(self, "Błąd", f"Nie można odnaleźć aplikacji: {label}")