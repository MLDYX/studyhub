from __future__ import annotations

from PyQt6.QtWidgets import QFrame, QHBoxLayout, QMainWindow, QStackedWidget, QVBoxLayout, QWidget

from core.calendar import CalendarStore
from ui.calendar_view import CalendarView
from ui.flashcards_view import FlashcardsView
from ui.home_view import HomeView
from ui.notes_view import NotesView
from ui.sidebar import Sidebar, load_icon


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("StudyHub – Prototyp")
        self.resize(1200, 800)
        self.setWindowIcon(load_icon("icon.png"))

        self._store = CalendarStore()

        central = QWidget()
        self.setCentralWidget(central)

        layout = QHBoxLayout(central)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        self.sidebar = Sidebar()
        layout.addWidget(self.sidebar)

        self.stack = QStackedWidget()

        self.content_container = QWidget()
        self.content_container.setObjectName("contentArea")
        content_layout = QVBoxLayout(self.content_container)
        content_layout.setContentsMargins(28, 28, 28, 28)
        content_layout.setSpacing(0)
        content_layout.addWidget(self.stack)

        layout.addWidget(self.content_container, stretch=1)

        self.home_view = HomeView(self._store)
        self.calendar_view = CalendarView(self._store)
        self.notes_view = NotesView()
        self.flashcards_view = FlashcardsView()

        self.stack.addWidget(self.home_view)
        self.stack.addWidget(self.calendar_view)
        self.stack.addWidget(self.notes_view)
        self.stack.addWidget(self.flashcards_view)

        self._view_indices = {
            "home": self.stack.indexOf(self.home_view),
            "calendar": self.stack.indexOf(self.calendar_view),
            "notes": self.stack.indexOf(self.notes_view),
            "flashcards": self.stack.indexOf(self.flashcards_view),
        }

        self.sidebar.home_clicked.connect(lambda: self._switch_view("home"))
        self.sidebar.calendar_clicked.connect(lambda: self._switch_view("calendar"))
        self.calendar_view.calendar_updated.connect(self._handle_calendar_update)

        self._apply_styles()
        self.sidebar.set_active("home")
        self._switch_view("home")

    def _switch_view(self, key: str) -> None:
        index = self._view_indices.get(key)
        if index is None:
            return
        self.stack.setCurrentIndex(index)
        self.sidebar.set_active(key)

    def _handle_calendar_update(self) -> None:
        self.home_view.refresh()

    def _apply_styles(self) -> None:
        self.setStyleSheet(
            """
            QWidget {
                background-color: #f9faff;
                color: #1f1f24;
                font-family: 'Segoe UI', 'Helvetica Neue', Arial, sans-serif;
            }
            QLabel {
                background-color: transparent;
            }
            #sidebar {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #f4f6ff, stop:1 #ffffff);
                border: 1px solid rgba(76, 110, 245, 0.18);
                border-radius: 18px;
                padding: 14px 0;
            }
            #sidebarLogo {
                padding: 10px 0 6px 0;
            }
            #contentArea {
                background-color: #ffffff;
                border-radius: 22px;
                border: 1px solid rgba(76, 110, 245, 0.08);
            }
            #contentArea > QStackedWidget {
                background-color: transparent;
                border: none;
            }
            #contentArea > QStackedWidget > QWidget {
                background-color: transparent;
            }
            #homeRoot,
            #calendarRoot,
            #notesRoot,
            #flashcardsRoot {
                background-color: transparent;
            }
            #cardsContainer,
            #cardsContainer QWidget {
                background-color: transparent;
                border: none;
            }
            QPushButton#sidebarButton {
                text-align: left;
                padding: 12px 16px;
                border-radius: 12px;
                border: none;
                font-size: 15px;
                color: #586176;
                background-color: transparent;
            }
            QPushButton#sidebarButton:hover:enabled {
                background-color: #f1f4ff;
                color: #1f3c88;
            }
            QPushButton#sidebarButton[active="true"] {
                background-color: #e6edff;
                color: #1f3c88;
                font-weight: 600;
                border-left: 4px solid #4c6ef5;
                padding-left: 12px;
            }
            QPushButton#sidebarButton:disabled {
                color: #a7acba;
            }
            QLabel#h1 {
                font-size: 26px;
                font-weight: 600;
                color: #1f2a4a;
            }
            QLabel#subtitle {
                font-size: 16px;
                color: #6b7287;
            }
            QFrame#card {
                background-color: #ffffff;
                border-radius: 18px;
                border: 1px solid #e4e7f7;
            }
            QFrame#card[muted="true"] QLabel#cardValue {
                color: #a0a5b4;
            }
            QFrame#card[variant="indigo"] {
                border-top: 4px solid #4c6ef5;
            }
            QFrame#card[variant="indigo"] QLabel#cardValue {
                color: #2b44ff;
            }
            QFrame#card[variant="teal"] {
                border-top: 4px solid #1dbf8c;
            }
            QFrame#card[variant="teal"] QLabel#cardValue {
                color: #109c70;
            }
            QFrame#card[variant="magenta"] {
                border-top: 4px solid #bd5cff;
            }
            QFrame#card[variant="magenta"] QLabel#cardValue {
                color: #8b32d7;
            }
            QFrame#card[variant="amber"] {
                border-top: 4px solid #ffb84d;
            }
            QFrame#card[variant="amber"] QLabel#cardValue {
                color: #d98324;
            }
            QLabel#cardTitle {
                font-size: 15px;
                color: #5d647a;
            }
            QLabel#cardValue {
                font-size: 32px;
                font-weight: 600;
            }
            QLabel#cardDescription {
                font-size: 13px;
                color: #6f778e;
            }
            QFrame#dayPanel,
            QFrame#daySection {
                background-color: #ffffff;
                border-radius: 16px;
                border: 1px solid #e3e8ff;
            }
            QFrame#calendarBoard {
                background-color: #ffffff;
                border-radius: 20px;
                border: 1px solid #e4e7f7;
            }
            #calendarToolbar {
                background-color: #ffffff;
                border: 1px solid #e4e7f7;
                border-radius: 16px;
            }
            #calendarSegment {
                background-color: rgba(76, 110, 245, 0.08);
                border-radius: 12px;
                padding: 4px;
            }
            QToolButton#calendarSegmentButton {
                border: none;
                border-radius: 10px;
                padding: 6px 14px;
                font-size: 14px;
                font-weight: 600;
                color: #415165;
                background-color: transparent;
            }
            QToolButton#calendarSegmentButton:checked {
                background-color: #4c6ef5;
                color: #ffffff;
            }
            QToolButton#calendarSegmentButton:hover:!checked {
                background-color: rgba(76, 110, 245, 0.16);
            }
            QPushButton#calendarActionPrimary {
                background-color: #4c6ef5;
                color: #ffffff;
                border-radius: 12px;
                padding: 10px 20px;
                font-weight: 600;
                font-size: 14px;
                border: none;
            }
            QPushButton#calendarActionPrimary:hover {
                background-color: #3d59d4;
            }
            QPushButton#calendarActionPrimary:pressed {
                background-color: #324abb;
            }
            QPushButton#calendarActionSecondary {
                background-color: transparent;
                color: #1f3c88;
                border: 1px solid #4c6ef5;
                border-radius: 12px;
                padding: 10px 18px;
                font-weight: 600;
                font-size: 14px;
            }
            QPushButton#calendarActionSecondary:hover {
                background-color: rgba(76, 110, 245, 0.12);
            }
            QPushButton#calendarActionSecondary:pressed {
                background-color: rgba(76, 110, 245, 0.2);
            }
            QListWidget#upcomingList {
                border: none;
                background-color: transparent;
            }
            QListWidget#upcomingList::item {
                padding: 10px 12px;
                border-radius: 10px;
            }
            QListWidget#upcomingList::item:selected {
                background-color: rgba(76, 110, 245, 0.2);
                color: #1f1f24;
            }
            QLabel#panelTitle,
            QLabel#daySectionTitle {
                font-size: 16px;
                font-weight: 600;
                color: #1f2a4a;
            }
            QListWidget {
                border: none;
                background-color: transparent;
                outline: none;
            }
            QListWidget::item {
                padding: 8px;
                border-radius: 10px;
            }
            QListWidget::item:selected {
                background-color: rgba(76, 110, 245, 0.18);
                color: #1f1f24;
            }
            QScrollArea,
            QScrollArea QWidget,
            QScrollArea > QWidget > QWidget {
                background-color: transparent;
                border: none;
            }
            QScrollBar:vertical {
                background: transparent;
                width: 9px;
                margin: 6px 2px 6px 0;
            }
            QScrollBar:horizontal {
                background: transparent;
                height: 9px;
                margin: 0 6px 2px 6px;
            }
            QScrollBar::handle:vertical {
                background-color: rgba(76, 110, 245, 0.45);
                border-radius: 4px;
                min-height: 24px;
            }
            QScrollBar::handle:horizontal {
                background-color: rgba(76, 110, 245, 0.45);
                border-radius: 4px;
                min-width: 24px;
            }
            QScrollBar::handle:hover {
                background-color: rgba(76, 110, 245, 0.65);
            }
            QScrollBar::add-line,
            QScrollBar::sub-line {
                width: 0;
                height: 0;
            }
            QScrollBar::add-page,
            QScrollBar::sub-page {
                background: none;
            }
            QCalendarWidget {
                background-color: #ffffff;
                border: none;
            }
            QCalendarWidget QWidget {
                background-color: transparent;
            }
            QCalendarWidget QToolButton {
                color: #1f2742;
                font-weight: 600;
                border: none;
                background: transparent;
            }
            QCalendarWidget QToolButton:hover {
                color: #4c6ef5;
            }
            QLabel#calendarHeaderLabel {
                font-size: 16px;
                font-weight: 600;
                color: #1f2a4a;
                letter-spacing: 0.2px;
            }
            QCalendarWidget QAbstractItemView {
                outline: none;
                selection-background-color: transparent;
                selection-color: #1f1f24;
            }
            QCalendarWidget #qt_calendar_navigationbar {
                background: transparent;
            }
            QCalendarWidget #qt_calendar_prevmonth,
            QCalendarWidget #qt_calendar_nextmonth {
                border-radius: 12px;
                padding: 4px;
            }
            QCalendarWidget #qt_calendar_prevmonth:hover,
            QCalendarWidget #qt_calendar_nextmonth:hover {
                background-color: rgba(76, 110, 245, 0.12);
            }
            QFrame#moduleTile {
                border-radius: 14px;
                border: 1px solid #d5d8e5;
                background-color: #f7f8fd;
            }
            QFrame#moduleTile[variant="notes"] {
                background-color: #fff6f1;
                border: 1px solid #ffd9c7;
            }
            QFrame#moduleTile[variant="notes"] QLabel#moduleTitle {
                color: #d05c1f;
            }
            QFrame#moduleTile[variant="flashcards"] {
                background-color: #f2f5ff;
                border: 1px solid #cfd9ff;
            }
            QFrame#moduleTile[variant="flashcards"] QLabel#moduleTitle {
                color: #3960f5;
            }
            QLabel#moduleTitle {
                font-size: 15px;
                font-weight: 600;
                color: #1f2a4a;
            }
            QLabel#moduleSubtitle {
                font-size: 13px;
                color: #7b8295;
            }
            QPushButton#dangerButton {
                color: #ff3b30;
            }
            QPushButton#dangerButton:hover {
                background-color: rgba(255, 59, 48, 0.12);
            }
            QDialog {
                background-color: #ffffff;
            }
            #eventDialog {
                background-color: #ffffff;
                border-radius: 20px;
            }
            #eventDialog QLabel {
                color: #1f2a4a;
                font-size: 14px;
            }
            #eventDialog QLineEdit,
            #eventDialog QDateTimeEdit,
            #eventDialog QTextEdit,
            #eventDialog QComboBox {
                border: 1px solid #d8dcf0;
                border-radius: 10px;
                padding: 8px 10px;
                background-color: #f9faff;
                font-size: 14px;
            }
            #eventDialog QDateTimeEdit#eventDateTime {
                padding-right: 28px;
            }
            #eventDialog QDateTimeEdit::drop-down {
                width: 20px;
                border: none;
            }
            #eventDialog QDateTimeEdit::down-arrow {
                image: url(assets/icons/chevron_down.svg);
                width: 12px;
                height: 12px;
            }
            #eventDialog QTextEdit {
                min-height: 96px;
            }
            #eventDialog QDialogButtonBox QPushButton {
                border-radius: 12px;
                padding: 8px 18px;
                font-weight: 600;
            }
            #eventDialog QDialogButtonBox QPushButton:hover {
                background-color: rgba(76, 110, 245, 0.12);
            }
            #popupCalendarTitle {
                font-weight: 600;
                color: #1f2a4a;
            }
            #importDialog {
                background-color: #ffffff;
                border-radius: 20px;
            }
            #importDialog QLabel#dialogHeading {
                font-size: 18px;
                font-weight: 600;
                color: #1f2a4a;
            }
            #importDialog QLabel#dialogLabel {
                font-size: 14px;
                color: #586176;
            }
            #importDialog QLineEdit#importUrlField {
                border: 1px solid #d8dcf0;
                border-radius: 10px;
                padding: 8px 10px;
                background-color: #f9faff;
            }
            #importDialog QPushButton#importUrlButton,
            #importDialog QPushButton#importFileButton {
                border-radius: 12px;
                padding: 8px 18px;
                font-weight: 600;
                font-size: 14px;
                background-color: #4c6ef5;
                color: #ffffff;
            }
            #importDialog QPushButton#importUrlButton:hover,
            #importDialog QPushButton#importFileButton:hover {
                background-color: #3d59d4;
            }
            #importDialog QPushButton#importUrlButton:pressed,
            #importDialog QPushButton#importFileButton:pressed {
                background-color: #324abb;
            }
            #importDialog QDialogButtonBox QPushButton {
                border-radius: 10px;
                padding: 6px 16px;
            }
            """
        )
