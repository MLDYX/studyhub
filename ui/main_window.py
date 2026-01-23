from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QMainWindow,
    QStackedWidget,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from core.calendar import CalendarStore, WARSAW_TZ
from core.settings import SettingsManager
from data.auth_service import AuthService
from data.calendar_persistence import CalendarPersistence
from data.credentials import UserCredentials
from data.supabase_client import SupabaseService
from data.cleanup_state import load_last_cleanup, save_last_cleanup
from ui.calendar_view import CalendarView
from ui.home_view import HomeView
from ui.notes_view import NotesView
from ui.mail_view import MailView
from ui.settings_view import SettingsView
from ui.login_overlay import LoginOverlay
from ui.sidebar import Sidebar, load_icon


class MainWindow(QMainWindow):
    def __init__(
        self,
        *,
        supabase_service: SupabaseService | None = None,
        auth_service: AuthService | None = None,
        user_credentials: UserCredentials | None = None,
    ) -> None:
        super().__init__()
        self.setWindowTitle("StudyHub")
        self.setFixedSize(1200, 700)
        self.setWindowIcon(load_icon("icon.png"))

        self._store = CalendarStore()
        self._settings = SettingsManager()
        self.supabase_service = supabase_service
        self.auth_service = auth_service
        self.user_credentials = user_credentials
        self.calendar_persistence: CalendarPersistence | None = None
        self._maybe_setup_calendar_persistence()
        self._setup_stack()

    def _setup_stack(self) -> None:
        self.main_stack = QStackedWidget()
        self.setCentralWidget(self.main_stack)

        self.login_overlay = LoginOverlay(self.auth_service, self._handle_login_success)
        self.main_stack.addWidget(self.login_overlay)

        self.app_root = self._build_app_root()
        self.main_stack.addWidget(self.app_root)

        if self.user_credentials:
            self.main_stack.setCurrentWidget(self.app_root)
        else:
            self.main_stack.setCurrentWidget(self.login_overlay)

    def _build_app_root(self) -> QWidget:
        central = QWidget()

        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 16, 0)
        layout.setSpacing(0)

        self.sidebar = Sidebar()
        layout.addWidget(self.sidebar)

        self.sidebar_separator = QFrame()
        self.sidebar_separator.setObjectName("sidebarSeparator")
        self.sidebar_separator.setFrameShape(QFrame.Shape.NoFrame)
        self.sidebar_separator.setFixedWidth(1)
        self.sidebar_separator.setSizePolicy(
            QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding
        )
        layout.addWidget(self.sidebar_separator)
        layout.addSpacing(8)

        self.stack = QStackedWidget()

        self.content_container = QWidget()
        self.content_container.setObjectName("contentArea")
        content_layout = QVBoxLayout(self.content_container)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        self._content_inner = QWidget()
        self._content_inner.setObjectName("contentInner")
        inner_layout = QVBoxLayout(self._content_inner)
        inner_layout.setContentsMargins(24, 24, 24, 24)
        inner_layout.setSpacing(0)
        inner_layout.addWidget(self.stack)

        content_layout.addWidget(self._content_inner)

        layout.addWidget(self.content_container, stretch=1)

        self.home_view = HomeView(self._store, self._settings)
        self.calendar_view = CalendarView(self._store, self._settings)
        self.notes_view = NotesView()
        self.mail_view = MailView(self._settings)
        self.settings_view = SettingsView(self._settings)

        self.stack.addWidget(self.home_view)
        self.stack.addWidget(self.calendar_view)
        self.stack.addWidget(self.notes_view)
        self.stack.addWidget(self.mail_view)
        self.stack.addWidget(self.settings_view)

        self._view_indices = {
            "home": self.stack.indexOf(self.home_view),
            "calendar": self.stack.indexOf(self.calendar_view),
            "notes": self.stack.indexOf(self.notes_view),
            "mail": self.stack.indexOf(self.mail_view),
            "settings": self.stack.indexOf(self.settings_view),
        }

        self.sidebar.home_clicked.connect(lambda: self._switch_view("home"))
        self.sidebar.calendar_clicked.connect(lambda: self._switch_view("calendar"))
        self.sidebar.notes_clicked.connect(lambda: self._switch_view("notes"))
        self.sidebar.mail_clicked.connect(lambda: self._switch_view("mail"))
        self.sidebar.settings_clicked.connect(lambda: self._switch_view("settings"))
        self.calendar_view.calendar_updated.connect(self._handle_calendar_update)
        self.home_view.notes_requested.connect(self._handle_home_note_request)
        self.home_view.mail_requested.connect(self._handle_home_mail_request)
        self.settings_view.calendar_sources_changed.connect(
            lambda: self.calendar_view.reload_external_sources()
        )

        self._apply_styles()
        self.sidebar.set_active("home")
        self._switch_view("home")
        return central

    def _switch_view(self, key: str) -> None:
        index = self._view_indices.get(key)
        if index is None:
            return
        self.stack.setCurrentIndex(index)
        self.sidebar.set_active(key)

    def _handle_login_success(self, creds: UserCredentials) -> None:
        self.user_credentials = creds
        self._maybe_setup_calendar_persistence()
        self._load_calendar_from_remote()
        self.main_stack.setCurrentWidget(self.app_root)

    def _handle_calendar_update(self) -> None:
        self.home_view.refresh()

    def _handle_home_note_request(self, file_path: str) -> None:
        """Handle note click from home page - navigate to notes view and open file."""
        if not file_path or not os.path.exists(file_path):
            return
        
        # Navigate to notes view
        self._switch_view("notes")
        
        # Open the file in the notes viewer
        ext = os.path.splitext(file_path)[1].lower()
        if ext == ".bgh":
            # For .bgh files, open in the built-in viewer
            if hasattr(self.notes_view, '_folder_view') and self.notes_view._folder_view:
                self.notes_view._folder_view.open_file_in_viewer(file_path)
            else:
                # Create folder view if it doesn't exist
                from ui.folders_view import FolderView
                self.notes_view._folder_view = FolderView(self.notes_view)
                self.notes_view._folder_view.open_file_in_viewer(file_path)
        else:
            # For other file types, open with system default application
            from PyQt6.QtCore import QUrl
            from PyQt6.QtGui import QDesktopServices
            try:
                QDesktopServices.openUrl(QUrl.fromLocalFile(file_path))
            except Exception:
                pass

    def _handle_home_mail_request(self, payload: dict) -> None:
        """Handle mail click from home page - navigate to mail view and select message."""
        provider_id = payload.get("provider_id") or self._settings.get_mail_provider()
        message_id = payload.get("id", "")
        
        if not provider_id:
            return
        
        # Navigate to mail view and select the message
        self.mail_view.navigate_to_message(
            provider_id=provider_id,
            message_id=message_id,
        )
        self._switch_view("mail")

    def _maybe_setup_calendar_persistence(self) -> None:
        if self.supabase_service and self.user_credentials:
            self.calendar_persistence = CalendarPersistence(self.supabase_service, self.user_credentials)
            self._store._persistence = self.calendar_persistence
            self._load_calendar_from_remote()
            self._run_calendar_cleanup_if_due()

    def _load_calendar_from_remote(self) -> None:
        if not self.calendar_persistence:
            return
        events = self.calendar_persistence.load_events()
        self._store.replace_events(events)

    def _run_calendar_cleanup_if_due(self) -> None:
        last_cleanup = load_last_cleanup()
        now = datetime.now(timezone.utc)
        if last_cleanup and (now - last_cleanup).days < 1:
            return
        if not self.calendar_persistence:
            return
        # soft-delete events that ended before today, hard-delete deleted older than 7 days
        today_start = datetime.now(WARSAW_TZ).replace(hour=0, minute=0, second=0, microsecond=0)
        hard_delete_before = now - timedelta(days=7)
        self.calendar_persistence.cleanup(
            soft_delete_before=today_start,
            hard_delete_older_than=hard_delete_before,
        )
        save_last_cleanup(now)

    def _apply_styles(self) -> None:
        self.setStyleSheet(
            """
            QWidget {
                background-color: #ffffff;
                color: #1f1f24;
                font-family: 'Segoe UI', 'Helvetica Neue', Arial, sans-serif;
            }
            QLabel {
                background-color: transparent;
            }
            #sidebar {
                background-color: #fdfdff;
                border: 1px solid rgba(31, 45, 61, 0.14);
                border-radius: 22px;
                padding: 10px 0;
            }
            #sidebarLogo {
                padding: 6px 0 2px 0;
            }
            #sidebarDivider {
                border: none;
                background-color: rgba(36, 44, 74, 0.16);
                min-height: 1px;
                max-height: 1px;
                margin-left: -8px;
                margin-right: -16px;
            }
            QFrame#sidebarSeparator {
                border: none;
                background-color: rgba(31, 45, 61, 0.12);
                min-width: 1px;
                max-width: 1px;
            }
            #contentArea {
                background-color: transparent;
                border: none;
            }
            #contentArea > QStackedWidget {
                background-color: transparent;
                border: none;
            }
            #contentArea > QStackedWidget > QWidget {
                background-color: transparent;
            }
            #contentInner {
                background-color: transparent;
            }
            #homeRoot,
            #calendarRoot,
            #notesRoot,
            #mailRoot {
                background-color: transparent;
            }
            #cardsContainer,
            #cardsContainer QWidget {
                background-color: transparent;
                border: none;
            }
            QPushButton#sidebarButton {
                text-align: left;
                padding: 10px 12px;
                border-radius: 10px;
                border: none;
                font-size: 14px;
                color: #586176;
                background-color: transparent;
            }
            QPushButton#sidebarButton:hover:enabled {
                background-color: #f2f3f7;
                color: #1f2a4a;
            }
            QPushButton#sidebarButton[active="true"] {
                background-color: #eceef3;
                color: #1f2a4a;
                font-weight: 600;
                border-left: 4px solid #4c6ef5;
                padding-left: 8px;
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
            QFrame#mailContainer {
                background-color: #ffffff;
                border-radius: 20px;
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
            QWidget#homeNotesContainer,
            QWidget#homeMailContainer {
                background-color: transparent;
            }
            QFrame#homeNoteCard,
            QFrame#homeMailCard {
                border: 1px solid #eaedf3;
                border-radius: 16px;
                background-color: #ffffff;
            }
            QFrame#homeNoteCard {
                background-color: #f8faff;
            }
            QFrame#homeNoteCard:hover {
                border-color: rgba(76, 110, 245, 0.32);
                background-color: #eef1ff;
            }
            QFrame#homeMailCard:hover {
                border-color: rgba(76, 110, 245, 0.24);
                background-color: #f6f7fc;
            }
            QLabel#homeNoteCardTitle {
                font-size: 15px;
                font-weight: 600;
                color: #1f2742;
                max-height: 20px;
            }
            QLabel#homeNoteCardPreview {
                font-size: 13px;
                color: #5a6075;
                max-height: 18px;
            }
            QLabel#homeMailSubject {
                font-size: 15px;
                font-weight: 600;
                color: #1f2742;
            }
            QLabel#homeMailMeta {
                font-size: 13px;
                color: #5a6075;
            }
            QLabel#homeMailEmpty {
                font-size: 13px;
                color: #6a7080;
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
            QSplitter#mailSplitter::handle {
                background-color: #eef1ff;
                width: 4px;
            }
            QSplitter#mailSplitter::handle:hover {
                background-color: #d9defa;
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
            QFrame#moduleTile[variant="mail"] {
                background-color: #f2f5ff;
                border: 1px solid #cfd9ff;
            }
            QFrame#moduleTile[variant="mail"] QLabel#moduleTitle {
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
                background-color: #f4f5f8;
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
            #mailOnboarding {
                background-color: #ffffff;
                border-radius: 24px;
                border: 1px dashed rgba(31, 45, 61, 0.15);
            }
            #mailOnboardingTitle {
                font-size: 28px;
                font-weight: 700;
                color: #1f2335;
            }
            #mailOnboardingSubtitle {
                font-size: 15px;
                color: #5d6479;
            }
            QPushButton#mailOnboardingButton {
                border-radius: 14px;
                padding: 12px 32px;
                font-size: 15px;
                font-weight: 600;
                background-color: #ffffff;
                border: 1px solid rgba(31, 45, 61, 0.18);
                color: #2f3a55;
            }
            QPushButton#mailOnboardingButton:hover {
                background-color: #f3f4f7;
            }
            QPushButton#mailOnboardingButton:pressed {
                background-color: #e6e8ef;
            }
            #mailTopBar {
                background-color: transparent;
                border-bottom: 1px solid #eaedf3;
            }
            #mailWorkspaceShell {
                background-color: #ffffff;
                border-radius: 22px;
                border: 1px solid #dfe3f0;
            }
            QPushButton#mailActionPrimaryButton {
                border-radius: 12px;
                padding: 8px 20px;
                font-weight: 600;
                font-size: 14px;
                background-color: #4c6ef5;
                color: #ffffff;
                border: none;
            }
            QPushButton#mailActionPrimaryButton:hover {
                background-color: #3d59d4;
            }
            QPushButton#mailActionPrimaryButton:pressed {
                background-color: #324abb;
            }
            QPushButton#mailActionButton {
                border-radius: 12px;
                padding: 8px 18px;
                font-weight: 600;
                font-size: 14px;
                background-color: #f3f4f7;
                color: #2f3a55;
                border: 1px solid rgba(31, 45, 61, 0.12);
            }
            QPushButton#mailActionButton:hover {
                background-color: #e7e9ef;
            }
            QPushButton#mailActionButton:pressed {
                background-color: #dcdfe8;
            }
            QComboBox#mailProviderSelect {
                border-radius: 12px;
                padding: 6px 36px 6px 14px;
                font-weight: 600;
                font-size: 14px;
                border: 1px solid rgba(31, 45, 61, 0.18);
                background-color: #ffffff;
                color: #2f3a55;
            }
            QComboBox#mailProviderSelect:hover {
                border-color: rgba(76, 110, 245, 0.3);
            }
            QComboBox#mailProviderSelect::drop-down {
                subcontrol-origin: padding;
                subcontrol-position: right;
                width: 28px;
                border-left: 1px solid rgba(31, 45, 61, 0.12);
            }
            QComboBox#mailProviderSelect::down-arrow {
                image: url(assets/icons/chevron_down.svg);
                width: 12px;
                height: 12px;
            }
            QComboBox#mailProviderSelect QAbstractItemView {
                background-color: #ffffff;
                border: 1px solid rgba(31, 45, 61, 0.18);
                selection-background-color: #eef0f4;
                selection-color: #1f2335;
            }
            QSplitter#mailSplitter::handle {
                background-color: #eaedf3;
                width: 1px;
            }
            QListWidget#mailFolderList {
                background: transparent;
                padding: 16px 0;
                margin: 0;
            }
            QListWidget#mailFolderList::item {
                border: none;
                border-radius: 0;
                padding: 8px 20px;
                color: #2f344f;
            }
            QListWidget#mailFolderList::item:selected {
                background-color: #eef0f4;
                font-weight: 600;
            }
            QListWidget#mailThreadList {
                background: transparent;
                padding: 0;
            }
            QListWidget#mailThreadList::item {
                border: none;
                border-radius: 0;
                padding: 14px 20px;
                margin: 0;
                color: #2d3147;
                border-bottom: 1px solid #f0f1f5;
            }
            QListWidget#mailThreadList::item:selected {
                background-color: #f1f3f8;
                border-left: 3px solid #4c6ef5;
                color: #1f2335;
            }
            QTextEdit#mailContentView {
                border: none;
                border-radius: 0;
                padding: 24px;
                background-color: transparent;
                font-size: 14px;
            }
            QLabel#mailStatusLabel {
                font-size: 12px;
                color: #6b7280;
            }
            #mailStatusBar {
                background-color: transparent;
                border-top: 1px solid #eaedf3;
                max-height: 32px;
            }
            #mailAttachmentsBar {
                background-color: #f8f9fc;
                border-bottom: 1px solid #eaedf3;
            }
            #mailLoadingBar {
                background-color: transparent;
            }
            #mailLoadingBar::chunk {
                background-color: #4c6ef5;
            }
            #mailContentPanel {
                background-color: #ffffff;
            }
            QDialog#mailComposeDialog {
                background-color: #ffffff;
            }
            QLineEdit#mailComposeTo,
            QLineEdit#mailComposeSubject,
            QTextEdit#mailComposeBody {
                border: 1px solid #d8dcf0;
                border-radius: 10px;
                padding: 8px 10px;
                background-color: #ffffff;
                font-size: 14px;
            }
            QTextEdit#mailComposeBody {
                min-height: 140px;
            }
            QDialog#mailComposeDialog QDialogButtonBox QPushButton {
                border-radius: 10px;
                padding: 6px 16px;
                font-weight: 600;
            }
            #settingsRoot {
                background-color: transparent;
            }
            #settingsTitle {
                font-size: 28px;
                font-weight: 700;
                color: #1f2335;
            }
            #settingsSubtitle {
                font-size: 15px;
                color: #5d6479;
            }
            #settingsCard {
                background-color: #ffffff;
                border-radius: 20px;
                border: 1px solid rgba(31, 45, 61, 0.12);
            }
            #settingsCardTitle {
                font-size: 16px;
                font-weight: 600;
                color: #2d3147;
            }
            #settingsCardDescription,
            #settingsFeedback {
                font-size: 13px;
                color: #5d6479;
            }
            QComboBox#settingsMailCombo {
                border: 1px solid #d8dcf0;
                border-radius: 12px;
                padding: 8px 12px;
                font-size: 14px;
                background-color: #ffffff;
            }
            QComboBox#settingsMailCombo::drop-down {
                subcontrol-origin: padding;
                subcontrol-position: right;
                width: 26px;
                border-left: 1px solid rgba(76, 110, 245, 0.12);
            }
            QComboBox#settingsMailCombo::down-arrow {
                image: url(assets/icons/chevron_down.svg);
                width: 12px;
                height: 12px;
            }
            QPushButton#settingsClearMailButton {
                border-radius: 12px;
                padding: 8px 16px;
                font-weight: 600;
                font-size: 14px;
                border: 1px solid rgba(31, 45, 61, 0.18);
                background-color: #ffffff;
                color: #2f3a55;
            }
            QPushButton#settingsClearMailButton:hover {
                background-color: #f3f4f7;
            }
            QPushButton#settingsClearMailButton:pressed {
                background-color: #e6e8ef;
            }
            QListWidget#settingsCalendarList {
                border: 1px solid #d8dcf0;
                border-radius: 12px;
                padding: 6px;
                background-color: #f7f8ff;
            }
            QListWidget#settingsCalendarList::item {
                border-radius: 10px;
                padding: 10px 12px;
                margin-bottom: 4px;
            }
            QListWidget#settingsCalendarList::item:selected {
                background-color: rgba(76, 110, 245, 0.16);
                color: #1f2335;
            }
            QPushButton#settingsAddCalendarButton,
            QPushButton#settingsRemoveCalendarButton {
                border-radius: 12px;
                padding: 8px 16px;
                font-weight: 600;
                font-size: 14px;
                border: 1px solid rgba(31, 45, 61, 0.18);
                background-color: #ffffff;
                color: #2f3a55;
            }
            QPushButton#settingsAddCalendarButton:hover,
            QPushButton#settingsRemoveCalendarButton:hover {
                background-color: #f3f4f7;
            }
            QPushButton#settingsAddCalendarButton:pressed,

            QPushButton#settingsRemoveCalendarButton:pressed {
                background-color: #e6e8ef;
            }
            /* Login overlay */
            #loginContainer {
                background-color: #ffffff;
                border-radius: 28px;
                border: none;
            }
            QLabel#loginTitle {
                font-size: 32px;
                font-weight: 700;
                color: #1f2335;
            }
            QLabel {
                font-size: 15px;
                color: #4a4f61;
            }
            QLabel#loginLogo {
                margin-bottom: 8px;
            }
            QLineEdit {
                border: 1px solid #d8dcf0;
                border-radius: 12px;
                padding: 12px 14px;
                font-size: 15px;
            }
            QLineEdit:focus {
                border-color: #4c6ef5;
            }
            QLabel#errorLabel {
                color: #d14343;
                font-weight: 600;
            }
            QPushButton#loginButton {
                border-radius: 12px;
                padding: 10px 18px;
                font-weight: 700;
                font-size: 15px;
                background-color: #4c6ef5;
                color: #ffffff;
                border: none;
                min-width: 140px;
            }
            QPushButton#loginButton:hover {
                background-color: #3d59d4;
            }
            QPushButton#loginButton:pressed {
                background-color: #324abb;
            }
            """
        )
