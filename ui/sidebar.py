from __future__ import annotations

from pathlib import Path
from typing import Dict

from PyQt6.QtCore import Qt, QSize, pyqtSignal
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets" / "icons"


class Sidebar(QWidget):
    home_clicked = pyqtSignal()
    calendar_clicked = pyqtSignal()
    notes_clicked = pyqtSignal()
    mail_clicked = pyqtSignal()
    settings_clicked = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("sidebar")
        self.setFixedWidth(185)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 20, 0, 24)
        layout.setSpacing(14)

        self.logo_label = QLabel()
        self.logo_label.setObjectName("sidebarLogo")
        self.logo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo_icon = load_icon("logo.png")
        if not logo_icon.isNull():
            self.logo_label.setPixmap(logo_icon.pixmap(150, 50))
        self._add_padded_widget(layout, self.logo_label, alignment=Qt.AlignmentFlag.AlignHCenter)

        self._buttons: Dict[str, QPushButton] = {}
        self._active_key = ""

        self._add_nav_section(layout)
        layout.addStretch(1)
        layout.addSpacing(36)
        layout.addWidget(self._create_divider())

        self._buttons["settings"] = self._create_button("Ustawienia", "settings.svg")
        self._buttons["settings"].setMinimumHeight(48)
        self._buttons["settings"].clicked.connect(
            lambda _checked=False: self._handle_click("settings")
        )
        self._add_padded_widget(layout, self._buttons["settings"])

    def _add_nav_section(self, layout: QVBoxLayout) -> None:
        button_meta = [
            ("home", "Strona Glowna", "home.svg"),
            ("calendar", "Kalendarz", "calendar.svg"),
            ("notes", "Notatki", "notes.svg"),
            ("mail", "Mail", "mail.svg"),
        ]

        for index, (key, label, icon) in enumerate(button_meta):
            button = self._create_button(label, icon)
            self._buttons[key] = button
            self._add_padded_widget(layout, button)
            if index < len(button_meta) - 1:
                layout.addWidget(self._create_divider())
            button.clicked.connect(lambda _checked=False, route=key: self._handle_click(route))

    def _create_button(self, text: str, icon_name: str, *, enabled: bool = True) -> QPushButton:
        button = QPushButton(text)
        button.setObjectName("sidebarButton")
        button.setCheckable(True)
        button.setEnabled(enabled)
        button.setCursor(
            Qt.CursorShape.PointingHandCursor if enabled else Qt.CursorShape.ArrowCursor
        )
        button.setIcon(load_icon(icon_name))
        button.setIconSize(QSize(20, 20))
        button.setStyleSheet("")  # force qss activation
        button.setMinimumHeight(44)
        return button

    def _add_padded_widget(
        self,
        parent_layout: QVBoxLayout,
        widget: QWidget,
        *,
        alignment: Qt.AlignmentFlag | None = None,
    ) -> None:
        wrapper = QWidget()
        wrapper_layout = QHBoxLayout(wrapper)
        wrapper_layout.setContentsMargins(18, 0, 18, 0)
        wrapper_layout.setSpacing(0)
        if alignment is not None:
            wrapper_layout.addWidget(widget, alignment=alignment)
        else:
            wrapper_layout.addWidget(widget)
        parent_layout.addWidget(wrapper)

    def _handle_click(self, key: str) -> None:
        self.set_active(key)
        if key == "home":
            self.home_clicked.emit()
        elif key == "calendar":
            self.calendar_clicked.emit()
        elif key == "notes":
            self.notes_clicked.emit()
        elif key == "mail":
            self.mail_clicked.emit()
        elif key == "settings":
            self.settings_clicked.emit()

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

    def _create_divider(self) -> QFrame:
        divider = QFrame()
        divider.setObjectName("sidebarDivider")
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setFrameShadow(QFrame.Shadow.Plain)
        divider.setLineWidth(1)
        divider.setFixedHeight(1)
        divider.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        return divider


def load_icon(name: str) -> QIcon:
    icon_path = ASSETS_DIR / name
    if not icon_path.exists():
        return QIcon()
    return QIcon(str(icon_path))
