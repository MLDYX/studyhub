from __future__ import annotations

from pathlib import Path
from typing import Dict

from PyQt6.QtCore import Qt, QSize, pyqtSignal
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QLabel, QPushButton, QSpacerItem, QSizePolicy, QVBoxLayout, QWidget

ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets" / "icons"


class Sidebar(QWidget):
    home_clicked = pyqtSignal()
    calendar_clicked = pyqtSignal()
    notes_clicked = pyqtSignal()
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("sidebar")
        self.setFixedWidth(200)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 24, 20, 20)
        layout.setSpacing(14)

        self.logo_label = QLabel()
        self.logo_label.setObjectName("sidebarLogo")
        self.logo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo_icon = load_icon("logo.png")
        if not logo_icon.isNull():
            self.logo_label.setPixmap(logo_icon.pixmap(150, 50))
        layout.addWidget(self.logo_label, alignment=Qt.AlignmentFlag.AlignHCenter)

        self._buttons: Dict[str, QPushButton] = {}
        self._active_key = ""

        layout.addLayout(self._create_section())
        layout.addSpacerItem(QSpacerItem(20, 40, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding))

    def _create_section(self) -> QVBoxLayout:
        section = QVBoxLayout()
        section.setSpacing(8)

        self._buttons["home"] = self._create_button("Strona Główna", "home.svg")
        self._buttons["calendar"] = self._create_button("Kalendarz", "calendar.svg")
        self._buttons["notes"] = self._create_button("Notatki", "notes.svg")
        self._buttons["flashcards"] = self._create_button("Fiszki", "flashcards.svg", enabled=False)

        section.addWidget(self._buttons["home"])
        section.addWidget(self._buttons["calendar"])
        section.addWidget(self._buttons["notes"])
        section.addWidget(self._buttons["flashcards"])

        self._buttons["home"].clicked.connect(lambda: self._handle_click("home"))
        self._buttons["calendar"].clicked.connect(lambda: self._handle_click("calendar"))
        self._buttons["notes"].clicked.connect(lambda: self._handle_click("notes"))

        return section

    def _create_button(self, text: str, icon_name: str, *, enabled: bool = True) -> QPushButton:
        button = QPushButton(text)
        button.setObjectName("sidebarButton")
        button.setCheckable(True)
        button.setEnabled(enabled)
        button.setCursor(Qt.CursorShape.PointingHandCursor if enabled else Qt.CursorShape.ArrowCursor)
        button.setIcon(load_icon(icon_name))
        button.setIconSize(QSize(20, 20))
        button.setStyleSheet("")  # wymusza aktywację qss
        button.setMinimumHeight(44)
        return button

    def _handle_click(self, key: str) -> None:
        self.set_active(key)
        if key == "home":
            self.home_clicked.emit()
        elif key == "calendar":
            self.calendar_clicked.emit()
        elif key == "notes":
            self.notes_clicked.emit()  
    def set_active(self, key: str) -> None:
        if key == self._active_key:
            return
        self._active_key = key
        for name, button in self._buttons.items():
            is_active = name == key
            button.setChecked(is_active)
            button.setProperty("active", is_active)
            button.style().unpolish(button)
            button.style().polish(button)


def load_icon(name: str) -> QIcon:
    icon_path = ASSETS_DIR / name
    if not icon_path.exists():
        return QIcon()
    return QIcon(str(icon_path))
