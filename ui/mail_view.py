from __future__ import annotations

import asyncio
import logging
import os
import threading
import re
import tempfile
from concurrent.futures import TimeoutError as FutureTimeoutError
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

from PyQt6.QtCore import QEventLoop, Qt, QTimer, QUrl
from PyQt6.QtGui import QFont, QDesktopServices
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QComboBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSplitter,
    QStackedWidget,
    QTextEdit,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

try:
    from PyQt6.QtWebEngineWidgets import QWebEngineView
    HAS_WEBENGINE = True
except ImportError:
    HAS_WEBENGINE = False
    QWebEngineView = None  # type: ignore

from core.mail import (
    EmailAttachment,
    EmailClient,
    EmailMessageSummary,
    ImapProvider,
    MicrosoftProvider,
    MICROSOFT_CLIENT_CONFIG_ENV,
)
from core.settings import SettingsManager
from data.validation import sanitize_header, validate_emails, trim_length


class MailView(QWidget):
    def __init__(self, settings: SettingsManager, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("mailRoot")

        self.settings = settings
        self.client = EmailClient()

        provider_choices = self.client.provider_choices()
        self._provider_order: List[str] = [provider_id for provider_id, _ in provider_choices]
        self._provider_display_names: Dict[str, str] = {
            provider_id: display for provider_id, display in provider_choices
        }

        self._folder_order: List[str] = ["inbox", "sent", "drafts", "spam", "trash"]
        self._folder_labels: Dict[str, str] = {
            "inbox": "Odebrane",
            "sent": "Wyslane",
            "drafts": "Szkice",
            "spam": "Spam",
            "trash": "Kosz",
        }
        self._folder_items: Dict[str, QListWidgetItem] = {}
        self._active_folder: str = "inbox"

        self._messages: List[EmailMessageSummary] = []
        self._connected_accounts: set[str] = set()
        self._active_provider: Optional[str] = None
        self._logger = logging.getLogger(__name__)

        self._async_loop = asyncio.new_event_loop()
        self._loop_ready = threading.Event()
        self._async_thread = threading.Thread(
            target=self._start_async_loop,
            name="MailAsyncLoop",
            daemon=True,
        )
        self._async_thread.start()

        app = QApplication.instance()
        if app is not None:
            app.aboutToQuit.connect(self._shutdown_async_executor)

        self._build_ui()
        self._restore_last_provider()

    def _build_ui(self) -> None:
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        self.stack = QStackedWidget()
        self.stack.setObjectName("mailStack")
        root_layout.addWidget(self.stack)

        self._onboarding_page = self._create_onboarding_page()
        self._workspace_page = self._create_workspace_page()

        self._onboarding_index = self.stack.addWidget(self._onboarding_page)
        self._workspace_index = self.stack.addWidget(self._workspace_page)

    def _create_onboarding_page(self) -> QWidget:
        page = QWidget()
        page.setObjectName("mailOnboarding")

        layout = QVBoxLayout(page)
        layout.setContentsMargins(80, 80, 80, 80)
        layout.setSpacing(28)

        layout.addStretch(1)

        title = QLabel("Polacz swoja skrzynke pocztowa")
        title.setObjectName("mailOnboardingTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        subtitle = QLabel("Wybierz konto, ktore chcesz polaczyc ze StudyHub.")
        subtitle.setObjectName("mailOnboardingSubtitle")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)

        buttons_container = QVBoxLayout()
        buttons_container.setSpacing(14)
        buttons_container.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        self._onboarding_buttons: Dict[str, QPushButton] = {}

        for provider_id in self._provider_order:
            display = self._provider_display(provider_id)
            button_text = self._onboarding_label(provider_id, display)
            button = QPushButton(button_text)
            button.setObjectName("mailOnboardingButton")
            button.setMinimumWidth(280)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(lambda _, pid=provider_id: self._start_onboarding_flow(pid))
            buttons_container.addWidget(button)
            self._onboarding_buttons[provider_id] = button

        layout.addLayout(buttons_container)
        layout.addStretch(2)

        return page

    def _start_async_loop(self) -> None:
        asyncio.set_event_loop(self._async_loop)
        self._loop_ready.set()
        self._async_loop.run_forever()

    def _shutdown_async_executor(self) -> None:
        if self._async_loop.is_running():
            self._async_loop.call_soon_threadsafe(self._async_loop.stop)

    def _onboarding_label(self, provider_id: str, display: str) -> str:
        if provider_id == "gmail":
            return "Zaloguj się z Google"
        if provider_id == "microsoft":
            return "Zaloguj się z Microsoft"
        if provider_id == "imap":
            return "Zaloguj się z innych"
        return f"Zaloguj się z {display}"

    def _create_workspace_page(self) -> QWidget:
        page = QWidget()
        page.setObjectName("mailWorkspace")

        outer_layout = QVBoxLayout(page)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        self.workspace_shell = QFrame()
        self.workspace_shell.setObjectName("mailWorkspaceShell")
        self.workspace_shell.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        shell_layout = QVBoxLayout(self.workspace_shell)
        shell_layout.setContentsMargins(0, 0, 0, 0)
        shell_layout.setSpacing(0)

        top_bar = QWidget()
        top_bar.setObjectName("mailTopBar")
        top_bar.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        top_layout = QHBoxLayout(top_bar)
        top_layout.setContentsMargins(24, 20, 24, 20)
        top_layout.setSpacing(12)

        actions_layout = QHBoxLayout()
        actions_layout.setSpacing(8)

        self.compose_button = self._create_action_button("Nowa wiadomosc", primary=True)
        self.compose_button.clicked.connect(lambda: self._open_compose_dialog())
        actions_layout.addWidget(self.compose_button)

        self.reply_button = self._create_action_button("Odpowiedz")
        self.reply_button.clicked.connect(self._reply_to_current)
        actions_layout.addWidget(self.reply_button)

        self.forward_button = self._create_action_button("Przekaz dalej")
        self.forward_button.clicked.connect(self._forward_current)
        actions_layout.addWidget(self.forward_button)

        self.delete_button = self._create_action_button("Usun")
        self.delete_button.clicked.connect(self._delete_selected)
        actions_layout.addWidget(self.delete_button)

        self.refresh_button = self._create_action_button("Odswiez")
        self.refresh_button.clicked.connect(self._refresh_messages)
        actions_layout.addWidget(self.refresh_button)

        top_layout.addLayout(actions_layout)
        top_layout.addStretch(1)

        self.provider_combo = QComboBox()
        self.provider_combo.setObjectName("mailProviderSelect")
        self.provider_combo.setMinimumWidth(220)
        self.provider_combo.setCursor(Qt.CursorShape.PointingHandCursor)
        self.provider_combo.addItem("Wybierz konto", "")
        for provider_id in self._provider_order:
            display = self._provider_display(provider_id)
            self.provider_combo.addItem(display, provider_id)
        self.provider_combo.currentIndexChanged.connect(self._on_provider_selected)
        top_layout.addWidget(self.provider_combo)
        shell_layout.addWidget(top_bar)

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setObjectName("mailSplitter")
        self.splitter.setMinimumHeight(520)
        self.splitter.setHandleWidth(1)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.setStyleSheet(
            """
            QSplitter#mailSplitter::handle {
                background-color: #eaedf3;
                margin: 0;
                padding: 0;
            }
            QSplitter#mailSplitter::handle:pressed {
                background-color: #d0d5e3;
            }
            """
        )

        self.folder_list = QListWidget()
        self.folder_list.setObjectName("mailFolderList")
        self.folder_list.setMinimumWidth(120)
        self.folder_list.setMaximumWidth(160)
        self.folder_list.setFrameShape(QFrame.Shape.NoFrame)
        self.folder_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.folder_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.folder_list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.folder_list.setSpacing(0)
        self.folder_list.itemSelectionChanged.connect(self._on_folder_selected)
        self.splitter.addWidget(self.folder_list)

        self.messages_list = QListWidget()
        self.messages_list.setObjectName("mailThreadList")
        self.messages_list.setFrameShape(QFrame.Shape.NoFrame)
        self.messages_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.messages_list.setWordWrap(False)
        self.messages_list.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.messages_list.setStyleSheet("""
            QListWidget { font-size: 14px; }
            QListWidget::item { 
                font-size: 14px; 
                padding: 8px 12px;
            }
        """)
        self.messages_list.setCursor(Qt.CursorShape.PointingHandCursor)
        self.messages_list.itemSelectionChanged.connect(self._display_selected)
        self.splitter.addWidget(self.messages_list)

        # Right panel: attachments bar + email content
        self.content_panel = QWidget()
        self.content_panel.setObjectName("mailContentPanel")
        content_panel_layout = QVBoxLayout(self.content_panel)
        content_panel_layout.setContentsMargins(0, 0, 0, 0)
        content_panel_layout.setSpacing(0)

        # Attachments bar (hidden by default)
        self.attachments_bar = QWidget()
        self.attachments_bar.setObjectName("mailAttachmentsBar")
        self.attachments_bar.setVisible(False)
        attachments_bar_layout = QHBoxLayout(self.attachments_bar)
        attachments_bar_layout.setContentsMargins(12, 8, 12, 8)
        attachments_bar_layout.setSpacing(8)
        self.attachments_container = QHBoxLayout()
        self.attachments_container.setSpacing(6)
        attachments_bar_layout.addLayout(self.attachments_container)
        attachments_bar_layout.addStretch(1)
        content_panel_layout.addWidget(self.attachments_bar)

        # Loading indicator
        self.loading_bar = QProgressBar()
        self.loading_bar.setObjectName("mailLoadingBar")
        self.loading_bar.setMaximum(0)  # Indeterminate
        self.loading_bar.setMinimum(0)
        self.loading_bar.setFixedHeight(3)
        self.loading_bar.setTextVisible(False)
        self.loading_bar.setVisible(False)
        content_panel_layout.addWidget(self.loading_bar)

        # Email body view - prefer QWebEngineView for full HTML, fallback to QTextEdit
        if HAS_WEBENGINE:
            from PyQt6.QtWebEngineWidgets import QWebEngineView as WebView
            from PyQt6.QtWebEngineCore import QWebEngineSettings, QWebEnginePage, QWebEngineProfile
            
            # Configure profile for remote content loading
            profile = QWebEngineProfile.defaultProfile()
            profile_settings = profile.settings()
            profile_settings.setAttribute(QWebEngineSettings.WebAttribute.AutoLoadImages, True)
            profile_settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
            profile_settings.setAttribute(QWebEngineSettings.WebAttribute.AllowRunningInsecureContent, True)
            
            self.body_view = WebView()
            self.body_view.setObjectName("mailContentWebView")
            # Enable loading of remote images and content on page level too
            settings = self.body_view.page().settings()
            settings.setAttribute(QWebEngineSettings.WebAttribute.AutoLoadImages, True)
            settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
            settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
            settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
            settings.setAttribute(QWebEngineSettings.WebAttribute.AllowRunningInsecureContent, True)
            settings.setAttribute(QWebEngineSettings.WebAttribute.LocalStorageEnabled, True)
            self.body_view.setStyleSheet("""
                QWebEngineView {
                    background: white;
                }
            """)
            self._logger.info("Using QWebEngineView for mail content rendering")
        else:
            self.body_view = QTextEdit()
            self.body_view.setObjectName("mailContentView")
            self.body_view.setReadOnly(True)
            self.body_view.setFrameStyle(QFrame.Shape.NoFrame)
            self.body_view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            self.body_view.setFont(QFont("Segoe UI", 11))
            self.body_view.setStyleSheet("QTextEdit { font-size: 14px; }")
            self.body_view.document().setDefaultFont(QFont("Segoe UI", 11))
            self.body_view.document().setDefaultStyleSheet(
                "body, p, div, span, td, li { font-size: 14px; font-family: 'Segoe UI'; }"
            )
            self._logger.info("Using QTextEdit fallback for mail content rendering")
        content_panel_layout.addWidget(self.body_view, stretch=1)

        self.splitter.addWidget(self.content_panel)

        # Proportions: ~15% folders, ~30% messages, ~55% content
        self.splitter.setStretchFactor(0, 15)
        self.splitter.setStretchFactor(1, 30)
        self.splitter.setStretchFactor(2, 55)

        shell_layout.addWidget(self.splitter, stretch=1)

        # Subtle status bar - single line
        status_wrapper = QWidget()
        status_wrapper.setObjectName("mailStatusBar")
        status_wrapper.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        status_layout = QHBoxLayout(status_wrapper)
        status_layout.setContentsMargins(16, 6, 16, 6)
        status_layout.setSpacing(0)

        self.status_label = QLabel("Wybierz konto, aby wyswietlic wiadomosci.")
        self.status_label.setObjectName("mailStatusLabel")
        self.status_label.setWordWrap(False)
        self.status_label.setStyleSheet("font-size: 12px; color: #6b7280;")
        status_layout.addWidget(self.status_label)
        status_layout.addStretch(1)

        shell_layout.addWidget(status_wrapper)

        QTimer.singleShot(0, self._apply_splitter_sizes)

        outer_layout.addWidget(self.workspace_shell)

        self._populate_folder_list()
        self._refresh_provider_choices()

        return page

    def _create_action_button(self, label: str, primary: bool = False) -> QPushButton:
        button = QPushButton(label)
        button.setObjectName("mailActionPrimaryButton" if primary else "mailActionButton")
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        return button

    def _populate_folder_list(self) -> None:
        self.folder_list.clear()
        self._folder_items.clear()
        for folder_id in self._folder_order:
            label = self._folder_display(folder_id)
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, folder_id)
            self.folder_list.addItem(item)
            self._folder_items[folder_id] = item
        self._ensure_folder_selection()

    def _ensure_folder_selection(self) -> None:
        target = self._folder_items.get(self._active_folder)
        if target is None and self._folder_order:
            self._active_folder = self._folder_order[0]
            target = self._folder_items.get(self._active_folder)
        if target is None:
            return
        self.folder_list.blockSignals(True)
        self.folder_list.setCurrentItem(target)
        self.folder_list.blockSignals(False)

    def _apply_splitter_sizes(self) -> None:
        if self.splitter.count() < 3:
            return
        total_width = self.splitter.width() or self.width()
        if total_width <= 0:
            # Default fallback sizes: 15% | 30% | 55%
            self.splitter.setSizes([150, 300, 550])
            return
        # Target proportions: 15% folders, 30% messages, 55% content
        folders_width = max(120, int(total_width * 0.15))
        messages_width = max(200, int(total_width * 0.30))
        content_width = max(300, total_width - folders_width - messages_width)
        self.splitter.setSizes([folders_width, messages_width, content_width])

    def _on_folder_selected(self) -> None:
        item = self.folder_list.currentItem()
        if item is None:
            return
        folder_id = item.data(Qt.ItemDataRole.UserRole)
        if not folder_id or folder_id == self._active_folder:
            return
        self._active_folder = folder_id
        if self.client.current_provider is None:
            folder_name = self._folder_display(folder_id)
            self.status_label.setText(f"Wybrano folder {folder_name}.")
            return
        self._load_messages()

    def _restore_last_provider(self) -> None:
        last_provider = self.settings.get_mail_provider()
        if last_provider and last_provider in self._provider_display_names:
            if not self._activate_provider(last_provider, source="restore"):
                self.settings.clear_mail_provider()
                self._show_onboarding()
        else:
            self._show_onboarding()

    def _show_onboarding(self) -> None:
        self.stack.setCurrentIndex(self._onboarding_index)
        self._active_provider = None
        self.messages_list.clear()
        self.body_view.clear()
        self.status_label.setText("Wybierz konto, aby wyswietlic wiadomosci.")
        self._refresh_provider_choices()

    def _switch_to_workspace(self) -> None:
        self.stack.setCurrentIndex(self._workspace_index)

    def _start_onboarding_flow(self, provider_id: str) -> None:
        self._activate_provider(provider_id, source="onboarding")

    def _on_provider_selected(self, index: int) -> None:
        provider_id = self.provider_combo.itemData(index)
        if not provider_id:
            return
        if provider_id == self._active_provider and provider_id in self._connected_accounts:
            return
        self._activate_provider(provider_id)

    def _activate_provider(self, provider_id: str, source: str = "manual") -> bool:
        if provider_id not in self._provider_display_names:
            self.status_label.setText("Wybrany dostawca nie jest dostepny.")
            return False

        self._switch_to_workspace()
        QTimer.singleShot(0, self._apply_splitter_sizes)

        display = self._provider_display(provider_id)
        was_connected = provider_id in self._connected_accounts
        previous_provider = self._active_provider

        self.client.set_provider(provider_id)

        current_provider = self.client.current_provider
        if isinstance(current_provider, MicrosoftProvider):
            if not current_provider.is_configured():
                self._handle_missing_microsoft_config(previous_provider, source)
                return False
        if isinstance(current_provider, ImapProvider):
            if not current_provider.is_configured():
                if not self._ensure_imap_configuration(current_provider):
                    self.status_label.setText("Konfiguracja IMAP zostala anulowana.")
                    if previous_provider:
                        self._active_provider = previous_provider
                        self.client.set_provider(previous_provider)
                        self.client.set_folder(self._active_folder)
                        self._refresh_provider_choices()
                        if source == "onboarding":
                            self._switch_to_workspace()
                    else:
                        self.client.current_provider = None
                        self._refresh_provider_choices()
                        if source == "onboarding":
                            self._show_onboarding()
                    return False
        self.client.set_folder(self._active_folder)

        if not was_connected:
            self.status_label.setText(f"Logowanie do {display}...")
            if not self._authenticate_provider(provider_id):
                self.status_label.setText(f"Nie udalo sie zalogowac do {display}.")
                if previous_provider:
                    self._active_provider = previous_provider
                    self.client.set_provider(previous_provider)
                    self._refresh_provider_choices()
                    self._load_messages()
                else:
                    self._active_provider = None
                    self.client.current_provider = None
                    self.messages_list.clear()
                    self.body_view.clear()
                    self._refresh_provider_choices()
                if source == "onboarding":
                    self._show_onboarding()
                return False
            self._connected_accounts.add(provider_id)
            self.status_label.setText(f"Polaczono z {display}.")
        else:
            self.status_label.setText(f"Przelaczono na {display}.")
        self._active_provider = provider_id
        self.settings.set_mail_provider(provider_id)
        self._ensure_folder_selection()
        self._refresh_provider_choices()
        self._load_messages()
        return True

    def _handle_missing_microsoft_config(
        self, previous_provider: Optional[str], source: str
    ) -> None:
        QMessageBox.information(
            self,
            "Brak konfiguracji Microsoft",
            (
                "Nie znaleziono pliku konfiguracyjnego Microsoft OAuth.\n\n"
                "Dodaj plik .env/microsoft_client.json lub ustaw zmienna srodowiskowa "
                f"{MICROSOFT_CLIENT_CONFIG_ENV}, aby korzystac z konta Microsoft."
            ),
        )
        self.status_label.setText("Brak konfiguracji Microsoft.")
        if previous_provider:
            self._active_provider = previous_provider
            self.client.set_provider(previous_provider)
            self.client.set_folder(self._active_folder)
            self._refresh_provider_choices()
            if source == "onboarding":
                self._switch_to_workspace()
        else:
            self.client.current_provider = None
            self._refresh_provider_choices()
            if source == "onboarding":
                self._show_onboarding()

    def _ensure_imap_configuration(self, provider: ImapProvider) -> bool:
        existing = provider.get_config(include_secret=False)
        dialog = ImapCredentialsDialog(self, existing_config=existing)
        while True:
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return False
            config = dialog.get_config()
            try:
                self.client.configure_imap(config)
                return True
            except Exception as exc:
                QMessageBox.critical(
                    self,
                    "Bledna konfiguracja IMAP/SMTP",
                    f"Nie udalo sie zapisac konfiguracji: {exc}",
                )
                dialog = ImapCredentialsDialog(self, existing_config=config)

    def _authenticate_provider(self, provider_id: str) -> bool:
        try:
            success = self._run_async(self.client.authenticate())
        except Exception as exc:
            self.status_label.setText(f"Blad logowania: {exc}")
            self._logger.error(
                "Mail authenticate failed",
                exc_info=exc,
                extra={"event": "mail_auth_failed", "provider": provider_id},
            )
            QMessageBox.critical(self, "Błąd logowania", f"Nie udało się zalogować: {exc}")
            return False
        return bool(success)

    def _refresh_provider_choices(self) -> None:
        for index, provider_id in enumerate(self._provider_order, start=1):
            self.provider_combo.setItemText(index, self._provider_label(provider_id))
        if self._active_provider:
            combo_index = self.provider_combo.findData(self._active_provider)
            if combo_index >= 0 and combo_index != self.provider_combo.currentIndex():
                self.provider_combo.blockSignals(True)
                self.provider_combo.setCurrentIndex(combo_index)
                self.provider_combo.blockSignals(False)
        else:
            if self.provider_combo.currentIndex() != 0:
                self.provider_combo.blockSignals(True)
                self.provider_combo.setCurrentIndex(0)
                self.provider_combo.blockSignals(False)

    def _render_messages(self, messages: List[EmailMessageSummary]) -> None:
        previous_selection = None
        current_item = self.messages_list.currentItem()
        if current_item is not None:
            previous_selection = current_item.data(Qt.ItemDataRole.UserRole)

        self.messages_list.blockSignals(True)
        self.messages_list.clear()
        for message in messages:
            headline = message.subject or "(Brak tematu)"
            preview_parts = [message.sender]
            if message.snippet:
                preview_parts.append(message.snippet)
            preview = " | ".join(part for part in preview_parts if part)
            item = QListWidgetItem(f"{headline}\n{preview}")
            item.setData(Qt.ItemDataRole.UserRole, message.message_id)
            self.messages_list.addItem(item)
        self.messages_list.blockSignals(False)

        if not messages:
            self.body_view.clear()
            return

        target_index = 0
        if previous_selection is not None:
            for index, message in enumerate(messages):
                if message.message_id == previous_selection:
                    target_index = index
                    break
        self.messages_list.setCurrentRow(target_index)

    def _load_messages(self) -> None:
        if self.client.current_provider is None or self._active_provider is None:
            self.messages_list.clear()
            self._clear_body_content()
            self._clear_attachments_bar()
            self.status_label.setText("Wybierz konto, aby wyswietlic wiadomosci.")
            return

        provider_display = self._provider_display(self._active_provider)
        folder_display = self._folder_display(self._active_folder)
        self.status_label.setText(f"Pobieram {folder_display}...")

        try:
            self.client.set_folder(self._active_folder)
            self._messages = self._run_async(self.client.fetch_messages())
        except Exception as exc:
            self.messages_list.clear()
            self._clear_body_content()
            self._clear_attachments_bar()
            self.status_label.setText(f"Blad pobierania: {exc}")
            self._logger.error(
                "Mail fetch failed",
                exc_info=exc,
                extra={"event": "mail_fetch_failed", "provider": self._active_provider, "folder": self._active_folder},
            )
            QMessageBox.critical(self, "Błąd", f"Nie udało się pobrać wiadomości:\n{exc}")
            return

        self._render_messages(self._messages)
        if self._messages:
            self.status_label.setText(
                f"{len(self._messages)} wiadomosci • {folder_display}"
            )
        else:
            self.status_label.setText(f"Brak wiadomosci w {folder_display}")
            self._clear_body_content()
            self._clear_attachments_bar()

    def _provider_display(self, provider_id: str) -> str:
        return self._provider_display_names.get(provider_id, provider_id.title())

    def _provider_label(self, provider_id: str) -> str:
        base = self._provider_display(provider_id)
        if provider_id == self._active_provider and provider_id in self._connected_accounts:
            return f"{base} (aktywne)"
        if provider_id in self._connected_accounts:
            return f"{base} (polaczono)"
        if provider_id == self._active_provider:
            return f"{base} (aktywne)"
        return base

    def _folder_display(self, folder_id: str) -> str:
        return self._folder_labels.get(folder_id, folder_id.title())

    def _clear_attachments_bar(self) -> None:
        """Clear all attachment chips from the bar."""
        while self.attachments_container.count():
            item = self.attachments_container.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        self.attachments_bar.setVisible(False)

    def _add_attachment_chip(self, message_id: str, attachment: "EmailAttachment") -> None:
        """Add a clickable attachment chip to the attachments bar."""
        from core.mail import EmailAttachment
        
        chip = QPushButton(attachment.filename)
        chip.setObjectName("mailAttachmentChip")
        chip.setCursor(Qt.CursorShape.PointingHandCursor)
        chip.setToolTip(f"Pobierz: {attachment.filename} ({self._format_size(attachment.size)})")
        chip.setStyleSheet("""
            QPushButton#mailAttachmentChip {
                background: #e5edff;
                border: 1px solid #c7d7fe;
                border-radius: 12px;
                padding: 4px 12px;
                font-size: 12px;
                color: #3960f5;
            }
            QPushButton#mailAttachmentChip:hover {
                background: #c7d7fe;
            }
        """)
        chip.clicked.connect(
            lambda: self._download_attachment(message_id, attachment.attachment_id, attachment.filename)
        )
        self.attachments_container.addWidget(chip)
        self.attachments_bar.setVisible(True)

    def _format_size(self, size_bytes: int) -> str:
        """Format file size in human-readable format."""
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} KB"
        else:
            return f"{size_bytes / (1024 * 1024):.1f} MB"

    def _download_attachment(self, message_id: str, attachment_id: str, filename: str) -> None:
        """Download an attachment and save it to user-selected location."""
        save_path, _ = QFileDialog.getSaveFileName(
            self,
            "Zapisz zalacznik",
            filename,
            "Wszystkie pliki (*.*)"
        )
        if not save_path:
            return
        try:
            data = self._run_async(self.client.download_attachment(message_id, attachment_id))
            with open(save_path, "wb") as f:
                f.write(data)
            self.status_label.setText(f"Pobrano: {filename}")
        except Exception as exc:
            self._logger.error(
                "Attachment download failed",
                exc_info=exc,
                extra={"event": "mail_attachment_failed", "message_id": message_id},
            )
            QMessageBox.critical(self, "Błąd", f"Nie udało się pobrać załącznika:\n{exc}")

    def _extract_domain(self, url: str) -> str:
        """Extract domain name from URL (e.g., 'https://www.aliexpress.com/path' -> 'aliexpress')."""
        try:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            domain = parsed.netloc or parsed.path.split('/')[0]
            # Remove www. prefix and get main domain
            domain = domain.lower().replace('www.', '')
            # Get the main part (e.g., 'mail.google.com' -> 'google')
            parts = domain.split('.')
            if len(parts) >= 2:
                # Return second-to-last part (main domain name)
                return parts[-2]
            return domain
        except Exception:
            return url[:20] if url else 'link'

    def _html_to_plain_with_links(self, html: str) -> str:
        """Convert HTML to plain text, keeping links as clickable domain names."""
        if not html:
            return ""
        
        text = html
        
        # Remove script, style, head, and comments
        text = re.sub(r'<script[^>]*>.*?</script>', '', text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'<head[^>]*>.*?</head>', '', text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'<!--.*?-->', '', text, flags=re.DOTALL)
        
        # Remove images (they don't add value in plain text)
        text = re.sub(r'<img[^>]*>', '', text, flags=re.IGNORECASE)
        
        # Collect links for later - replace with placeholders
        links = []
        def collect_link(match):
            href = match.group(1)
            link_text = re.sub(r'<[^>]+>', '', match.group(2)).strip()
            # Skip empty links, tracking pixels, and unsubscribe links
            if not link_text or len(link_text) < 2:
                return ''
            if href and href.startswith(('http://', 'https://')):
                domain = self._extract_domain(href)
                links.append((href, domain))
                return f"{link_text} [[LINK:{len(links)-1}]]"
            elif link_text:
                return link_text
            return ''
        
        text = re.sub(r'<a[^>]*href=["\']([^"\']*)["\'][^>]*>(.*?)</a>', collect_link, text, flags=re.DOTALL | re.IGNORECASE)
        
        # Replace block elements with appropriate spacing
        text = re.sub(r'<br\s*/?>', '\n', text, flags=re.IGNORECASE)
        text = re.sub(r'</p>', '\n', text, flags=re.IGNORECASE)
        text = re.sub(r'<p[^>]*>', '\n', text, flags=re.IGNORECASE)
        text = re.sub(r'</div>', '\n', text, flags=re.IGNORECASE)
        text = re.sub(r'</tr>', '\n', text, flags=re.IGNORECASE)
        text = re.sub(r'</td>', ' ', text, flags=re.IGNORECASE)
        text = re.sub(r'</th>', ' ', text, flags=re.IGNORECASE)
        text = re.sub(r'<li[^>]*>', '• ', text, flags=re.IGNORECASE)
        text = re.sub(r'</li>', '\n', text, flags=re.IGNORECASE)
        text = re.sub(r'<hr[^>]*>', '\n---\n', text, flags=re.IGNORECASE)
        text = re.sub(r'</h[1-6]>', '\n', text, flags=re.IGNORECASE)
        
        # Remove all remaining HTML tags
        text = re.sub(r'<[^>]+>', '', text)
        
        # Decode HTML entities
        import html as html_module
        text = html_module.unescape(text)
        
        # Aggressive whitespace cleanup
        text = re.sub(r'[ \t]+', ' ', text)  # Multiple spaces to single
        text = re.sub(r' *\n *', '\n', text)  # Remove spaces around newlines
        text = re.sub(r'\n{2,}', '\n\n', text)  # Max 1 blank line
        text = re.sub(r'^\n+', '', text)  # Remove leading newlines
        text = re.sub(r'\n+$', '', text)  # Remove trailing newlines
        
        # Remove lines that are just whitespace or very short (likely formatting artifacts)
        lines = text.split('\n')
        cleaned_lines = []
        for line in lines:
            stripped = line.strip()
            # Skip empty lines if previous was also empty
            if not stripped:
                if cleaned_lines and cleaned_lines[-1] == '':
                    continue
                cleaned_lines.append('')
            # Skip very short lines that are likely artifacts (unless they have links)
            elif len(stripped) < 3 and '[[LINK:' not in stripped:
                continue
            else:
                cleaned_lines.append(stripped)
        
        text = '\n'.join(cleaned_lines)
        
        # Final cleanup - remove excessive blank lines again
        text = re.sub(r'\n{3,}', '\n\n', text)
        
        # Escape HTML special characters for display
        text = text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
        
        # Replace link placeholders with actual HTML links
        for i, (href, domain) in enumerate(links):
            placeholder = f"[[LINK:{i}]]"
            link_html = f'(<a href="{href}" style="color:#3960f5;">{domain}</a>)'
            text = text.replace(placeholder, link_html)
        
        # Convert newlines to <br>
        text = text.replace('\n\n', '<br><br>')
        text = text.replace('\n', '<br>')
        
        # Remove excessive <br> tags
        text = re.sub(r'(<br>){3,}', '<br><br>', text)
        
        return text.strip()

    def _set_body_content(self, html_content: str, is_plain: bool = False) -> None:
        """Set content in the body view. Converts HTML to plain text with clickable domain links."""
        if is_plain:
            # Already plain text
            display_html = html_content.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('\n', '<br>')
        else:
            # Convert HTML to plain text with domain links
            display_html = self._html_to_plain_with_links(html_content)
        
        # Wrap in simple HTML that will always fit
        final_html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<style>
body {{ 
    font-family: 'Segoe UI', Arial, sans-serif; 
    font-size: 14px; 
    line-height: 1.6; 
    color: #1f2937; 
    padding: 16px; 
    margin: 0; 
    background: #fff; 
    word-wrap: break-word;
    overflow-wrap: break-word;
}}
a {{ color: #3960f5; text-decoration: none; }}
a:hover {{ text-decoration: underline; }}
</style></head>
<body>{display_html}</body></html>"""
        
        if HAS_WEBENGINE and 'WebEngine' in type(self.body_view).__name__:
            self.body_view.setZoomFactor(1.0)
            self.body_view.setHtml(final_html)
        else:
            self.body_view.setHtml(final_html)

    def _clear_body_content(self) -> None:
        """Clear the body view content."""
        if HAS_WEBENGINE and hasattr(self.body_view, 'setHtml') and 'WebEngine' in type(self.body_view).__name__:
            self.body_view.setHtml("")
        else:
            self.body_view.clear()

    def _display_selected(self) -> None:
        item = self.messages_list.currentItem()
        self._clear_attachments_bar()
        
        if item is None:
            self._clear_body_content()
            return
        
        placeholder_payload = item.data(Qt.ItemDataRole.UserRole + 1)
        if isinstance(placeholder_payload, dict) and placeholder_payload.get("placeholder"):
            body = placeholder_payload.get("body", "")
            self._set_body_content(body, is_plain=False)
            return
        
        message_id = item.data(Qt.ItemDataRole.UserRole)
        if not message_id:
            self._clear_body_content()
            return
        
        # Show loading indicator
        self.loading_bar.setVisible(True)
        
        try:
            # Fetch body
            body = self._run_async(self.client.fetch_body(message_id))
            
            # Fetch attachments
            try:
                attachments = self._run_async(self.client.fetch_attachments(message_id))
                for attachment in attachments:
                    self._add_attachment_chip(message_id, attachment)
            except Exception as att_exc:
                self._logger.warning(
                    "Failed to fetch attachments",
                    exc_info=att_exc,
                    extra={"event": "mail_attachments_failed", "message_id": message_id},
                )
            
            if not body:
                self._set_body_content("(Brak treści)", is_plain=True)
            else:
                self._set_body_content(body, is_plain=False)
        except Exception as exc:
            self._set_body_content(f"Nie udało się pobrać treści: {exc}", is_plain=True)
            self._logger.error(
                "Mail body fetch failed",
                exc_info=exc,
                extra={"event": "mail_body_failed", "provider": self._active_provider, "message_id": message_id},
            )
            QMessageBox.critical(self, "Błąd", f"Nie udało się pobrać treści wiadomości:\n{exc}")
        finally:
            self.loading_bar.setVisible(False)

    def _preprocess_email_html(self, html: str) -> str:
        """Preprocess email HTML to fix common issues."""
        if not html:
            return ""
        
        result = html
        
        # Convert rgba() to hex colors
        def rgba_to_hex(match):
            try:
                r, g, b = int(match.group(1)), int(match.group(2)), int(match.group(3))
                a = float(match.group(4))
                r = int(r * a + 255 * (1 - a))
                g = int(g * a + 255 * (1 - a))
                b = int(b * a + 255 * (1 - a))
                return f"#{r:02x}{g:02x}{b:02x}"
            except (ValueError, IndexError):
                return "#cccccc"
        
        result = re.sub(
            r"rgba\s*\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*([\d.]+)\s*\)",
            rgba_to_hex,
            result,
            flags=re.IGNORECASE
        )
        
        return result

    def _wrap_html(self, body: str) -> str:
        """Wrap HTML body with proper styling for display."""
        processed_body = self._preprocess_email_html(body)
        
        # Remove external image tags and replace with nothing
        # This prevents broken image icons from showing
        # Keep only data: URIs (embedded images)
        def handle_img(match):
            full_tag = match.group(0)
            src_match = re.search(r'src\s*=\s*["\']([^"\']+)["\']', full_tag, re.IGNORECASE)
            if src_match:
                src = src_match.group(1)
                # Keep data: URIs (embedded/inline images)
                if src.startswith('data:'):
                    return full_tag
            # Remove other images (external URLs that won't load)
            return ''
        
        processed_body = re.sub(r'<img\s+[^>]*>', handle_img, processed_body, flags=re.IGNORECASE)
        
        return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
html, body {{ margin: 0; padding: 0; background: #fff; }}
body {{ font-family: 'Segoe UI', Arial, sans-serif; font-size: 14px; line-height: 1.5; color: #1f2937; padding: 16px; }}
img {{ max-width: 100%; height: auto; }}
a {{ color: #3960f5; }}
</style>
</head>
<body>
{processed_body}
</body>
</html>"""

    def _refresh_messages(self) -> None:
        if self._active_provider is None:
            self.status_label.setText("Wybierz konto, aby wyswietlic wiadomosci.")
            return
        self._load_messages()

    def navigate_to_message(self, *, provider_id: str, message_id: str) -> None:
        """Navigate to mail view, activate provider if needed, and select message."""
        if not self._provider_order:
            return
        
        target_provider = (
            provider_id
            if provider_id in self._provider_display_names
            else (self._provider_order[0] if self._provider_order else None)
        )
        if not target_provider:
            self.status_label.setText("Brak skonfigurowanego dostawcy poczty.")
            return
        
        # Activate provider if different from current
        if self._active_provider != target_provider:
            if not self._activate_provider(target_provider):
                return
        
        # Switch to workspace and apply layout
        self.stack.setCurrentIndex(self._workspace_index)
        QTimer.singleShot(0, self._apply_splitter_sizes)
        
        # Select the message if specified
        if message_id:
            for row in range(self.messages_list.count()):
                item = self.messages_list.item(row)
                if item and item.data(Qt.ItemDataRole.UserRole) == message_id:
                    self.messages_list.setCurrentItem(item)
                    self.messages_list.scrollToItem(item)
                    break

    def open_home_preview(
        self,
        *,
        provider_id: str,
        subject: str,
        sender: str,
        snippet: str,
        body: str,
    ) -> None:
        if not self._provider_order:
            return
        target_provider = (
            provider_id
            if provider_id in self._provider_display_names
            else (self._provider_order[0])
        )
        if not target_provider:
            self.status_label.setText("Brak skonfigurowanego dostawcy poczty.")
            return
        if self._active_provider != target_provider:
            if not self._activate_provider(target_provider):
                return
        self.stack.setCurrentIndex(self._workspace_index)
        self._apply_splitter_sizes()

        headline = subject or "(Brak tematu)"
        summary = EmailMessageSummary(f"home-{uuid4().hex}", headline, sender, snippet)
        self._messages.insert(0, summary)

        subtitle = summary.sender
        if summary.snippet:
            subtitle += f" | {summary.snippet}"
        item = QListWidgetItem(f"{summary.subject or '(Brak tematu)'}\n{subtitle}")
        item.setData(Qt.ItemDataRole.UserRole, summary.message_id)
        item.setData(Qt.ItemDataRole.UserRole + 1, {"placeholder": True, "body": body})
        self.messages_list.insertItem(0, item)
        self.messages_list.setCurrentItem(item)
        self.messages_list.scrollToItem(item)

        html_content = self._wrap_html(body)
        self._set_body_content(html_content)
        provider_name = self._provider_display(target_provider)
        self.status_label.setText(f"Podglad wiadomosci z {provider_name}.")

    def _current_message(self) -> Optional[EmailMessageSummary]:
        item = self.messages_list.currentItem()
        if item is None:
            return None
        message_id = item.data(Qt.ItemDataRole.UserRole)
        for message in self._messages:
            if message.message_id == message_id:
                return message
        return None

    def _reply_to_current(self) -> None:
        if self.client.current_provider is None:
            self.status_label.setText("Polacz konto, aby odpowiedziec na wiadomosc.")
            return
        message = self._current_message()
        if message is None:
            self.status_label.setText("Wybierz wiadomosc, aby odpowiedziec.")
            return
        subject = message.subject or ""
        reply_subject = subject if subject.lower().startswith("re:") else f"Re: {subject}"
        self._open_compose_dialog(recipients=[message.sender], subject=reply_subject, body="\n\n")

    def _forward_current(self) -> None:
        if self.client.current_provider is None:
            self.status_label.setText("Polacz konto, aby przekazac wiadomosc dalej.")
            return
        message = self._current_message()
        if message is None:
            self.status_label.setText("Wybierz wiadomosc, aby przekazac dalej.")
            return
        subject = message.subject or ""
        forward_subject = subject if subject.lower().startswith("fw:") else f"Fw: {subject}"
        quoted = (
            f"\n\n--- Przekazywana wiadomosc ---\nOd: {message.sender}\nTemat: {message.subject}\n"
        )
        self._open_compose_dialog(subject=forward_subject, body=quoted)

    def _delete_selected(self) -> None:
        message = self._current_message()
        if message is None:
            self.status_label.setText("Wybierz wiadomosc, aby usunac.")
            return
        message_id = message.message_id
        row = self.messages_list.currentRow()
        self._messages = [msg for msg in self._messages if msg.message_id != message_id]
        self.messages_list.takeItem(row)
        self.body_view.clear()
        if self.messages_list.count():
            next_row = min(row, self.messages_list.count() - 1)
            self.messages_list.setCurrentRow(next_row)
        self.status_label.setText("Wiadomosc usunieta (tryb demonstracyjny).")

    def _open_compose_dialog(
        self,
        *,
        recipients: Optional[List[str]] = None,
        subject: str = "",
        body: str = "",
    ) -> None:
        if self.client.current_provider is None:
            self.status_label.setText("Polacz konto, aby wysylac wiadomosci.")
            return
        dialog = ComposeDialog(self, recipients=recipients, subject=subject, body=body)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        to_list, composed_subject, composed_body = dialog.get_data()
        self._send_message(to_list, composed_subject, composed_body)

    def _send_message(self, recipients: List[str], subject: str, body: str) -> None:
        if not recipients or not subject or not body:
            return
        try:
            self._run_async(self.client.send(recipients, subject, body))
        except Exception as exc:
            self.status_label.setText(f"Nie udalo sie wyslac wiadomosci: {exc}")
            self._logger.error(
                "Mail send failed",
                exc_info=exc,
                extra={"event": "mail_send_failed", "provider": self._active_provider},
            )
            QMessageBox.critical(self, "Błąd wysyłki", f"Nie udało się wysłać wiadomości:\n{exc}")
            return
        self._logger.info(
            "Mail send success",
            extra={
                "event": "mail_send_success",
                "provider": self._active_provider,
                "recipients_count": len(recipients),
            },
        )

        summary = EmailMessageSummary(
            f"sent-{uuid4().hex}",
            f"[Wyslano] {subject}",
            ", ".join(recipients),
        )
        self._messages.insert(0, summary)
        item = QListWidgetItem(f"{summary.subject}\n{summary.sender}")
        item.setData(Qt.ItemDataRole.UserRole, summary.message_id)
        self.messages_list.insertItem(0, item)
        self.messages_list.setCurrentRow(0)
        self.body_view.setPlainText(body)
        self.status_label.setText("Wiadomosc wyslana (tryb demonstracyjny).")

    def _run_async(self, coro):
        self._loop_ready.wait()
        future = asyncio.run_coroutine_threadsafe(coro, self._async_loop)
        done = threading.Event()
        result_holder: Dict[str, object] = {}

        def _callback(fut):
            try:
                result_holder["result"] = fut.result()
            except Exception as exc:
                result_holder["error"] = exc
            finally:
                done.set()

        future.add_done_callback(_callback)

        while not done.wait(timeout=0.05):
            QApplication.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 50)

        if "error" in result_holder:
            raise result_holder["error"]  # type: ignore[return-value]
        return result_holder.get("result")

    def _sanitize_html(self, html: str) -> str:
        """Sanitize HTML for QTextEdit compatibility."""
        if not html:
            return ""
        
        # Use the same preprocessing
        cleaned = self._preprocess_email_html(html)
        
        # Fix font-size:0 which makes text invisible
        cleaned = re.sub(r"font-size\s*:\s*0[^;>]*", "font-size:14px", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"font-size\s*:\s*0\s*(px|pt|em|rem)?", "font-size:14px", cleaned, flags=re.IGNORECASE)
        
        return f'<div style="font-size:14px; font-family:\'Segoe UI\'; max-width:100%; word-wrap:break-word;">{cleaned}</div>'


class ImapCredentialsDialog(QDialog):
    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        existing_config: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Konfiguracja IMAP/SMTP")
        self.setObjectName("imapCredentialsDialog")
        self.setMinimumWidth(420)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(18)

        imap_label = QLabel("Ustawienia IMAP")
        imap_label.setStyleSheet("font-weight: 600;")
        layout.addWidget(imap_label)

        imap_form = QFormLayout()
        imap_form.setSpacing(12)

        self.imap_host_edit = QLineEdit()
        self.imap_host_edit.setPlaceholderText("np. poczta.example.edu")
        imap_form.addRow("Serwer IMAP", self.imap_host_edit)

        self.imap_port_spin = QSpinBox()
        self.imap_port_spin.setRange(1, 65535)
        self.imap_port_spin.setValue(993)
        imap_form.addRow("Port IMAP", self.imap_port_spin)

        self.imap_security_combo = QComboBox()
        self.imap_security_combo.addItem("SSL/TLS", "ssl")
        self.imap_security_combo.addItem("STARTTLS", "starttls")
        self.imap_security_combo.addItem("Brak", "none")
        imap_form.addRow("Szyfrowanie IMAP", self.imap_security_combo)

        layout.addLayout(imap_form)

        smtp_label = QLabel("Ustawienia SMTP")
        smtp_label.setStyleSheet("font-weight: 600;")
        layout.addWidget(smtp_label)

        smtp_form = QFormLayout()
        smtp_form.setSpacing(12)

        self.smtp_host_edit = QLineEdit()
        self.smtp_host_edit.setPlaceholderText("np. smtp.example.edu")
        smtp_form.addRow("Serwer SMTP", self.smtp_host_edit)

        self.smtp_port_spin = QSpinBox()
        self.smtp_port_spin.setRange(1, 65535)
        self.smtp_port_spin.setValue(465)
        smtp_form.addRow("Port SMTP", self.smtp_port_spin)

        self.smtp_security_combo = QComboBox()
        self.smtp_security_combo.addItem("SSL/TLS", "ssl")
        self.smtp_security_combo.addItem("STARTTLS", "starttls")
        self.smtp_security_combo.addItem("Brak", "none")
        smtp_form.addRow("Szyfrowanie SMTP", self.smtp_security_combo)

        layout.addLayout(smtp_form)

        auth_label = QLabel("Dane logowania")
        auth_label.setStyleSheet("font-weight: 600;")
        layout.addWidget(auth_label)

        auth_form = QFormLayout()
        auth_form.setSpacing(12)

        self.username_edit = QLineEdit()
        self.username_edit.setPlaceholderText("Pełny adres e-mail")
        auth_form.addRow("Nazwa użytkownika", self.username_edit)

        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        auth_form.addRow("Hasło", self.password_edit)

        layout.addLayout(auth_form)

        folders_label = QLabel("Nazwy folderów (opcjonalnie)")
        folders_label.setStyleSheet("font-weight: 600;")
        layout.addWidget(folders_label)

        folder_form = QFormLayout()
        folder_form.setSpacing(8)
        self.folder_fields: Dict[str, QLineEdit] = {}
        folder_labels = {
            "inbox": "Odebrane",
            "sent": "Wysłane",
            "drafts": "Szkice",
            "spam": "Spam",
            "trash": "Kosz",
        }
        for key, label in folder_labels.items():
            edit = QLineEdit()
            edit.setPlaceholderText(f"Domyślnie: {label}")
            folder_form.addRow(label, edit)
            self.folder_fields[key] = edit

        layout.addLayout(folder_form)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok
        )
        self.buttons.accepted.connect(self._on_accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

        self._result: Optional[Dict[str, Any]] = None
        self._apply_existing(existing_config or {})

    def _apply_existing(self, config: Dict[str, Any]) -> None:
        self.imap_host_edit.setText(str(config.get("imap_host", "")))
        if "imap_port" in config:
            try:
                self.imap_port_spin.setValue(int(config.get("imap_port", 993)))
            except (TypeError, ValueError):
                pass
        imap_security = "ssl"
        if config.get("imap_starttls"):
            imap_security = "starttls"
        elif not config.get("imap_ssl", True):
            imap_security = "none"
        index = self.imap_security_combo.findData(imap_security)
        if index >= 0:
            self.imap_security_combo.setCurrentIndex(index)

        self.smtp_host_edit.setText(str(config.get("smtp_host", "")))
        if "smtp_port" in config:
            try:
                self.smtp_port_spin.setValue(int(config.get("smtp_port", 465)))
            except (TypeError, ValueError):
                pass
        smtp_security = "ssl"
        if config.get("smtp_starttls"):
            smtp_security = "starttls"
        elif not config.get("smtp_ssl", True):
            smtp_security = "none"
        index = self.smtp_security_combo.findData(smtp_security)
        if index >= 0:
            self.smtp_security_combo.setCurrentIndex(index)

        self.username_edit.setText(str(config.get("username", "")))
        if config.get("password"):
            self.password_edit.setText(str(config.get("password", "")))

        folder_map = config.get("folder_map", {}) or {}
        if isinstance(folder_map, dict):
            for key, edit in self.folder_fields.items():
                value = folder_map.get(key)
                if value:
                    edit.setText(str(value))

    def _on_accept(self) -> None:
        imap_host = self.imap_host_edit.text().strip()
        smtp_host = self.smtp_host_edit.text().strip()
        username = self.username_edit.text().strip()
        password = self.password_edit.text()

        if not imap_host or not smtp_host or not username or not password:
            QMessageBox.warning(
                self,
                "Brak danych",
                "Podaj adresy serwerów IMAP i SMTP oraz nazwę użytkownika i hasło.",
            )
            return

        folder_map: Dict[str, str] = {}
        for key, edit in self.folder_fields.items():
            value = edit.text().strip()
            if value:
                folder_map[key] = value

        self._result = {
            "imap_host": imap_host,
            "imap_port": self.imap_port_spin.value(),
            "imap_ssl": self.imap_security_combo.currentData() == "ssl",
            "imap_starttls": self.imap_security_combo.currentData() == "starttls",
            "smtp_host": smtp_host,
            "smtp_port": self.smtp_port_spin.value(),
            "smtp_ssl": self.smtp_security_combo.currentData() == "ssl",
            "smtp_starttls": self.smtp_security_combo.currentData() == "starttls",
            "username": username,
            "password": password,
            "folder_map": folder_map,
        }
        self.accept()

    def get_config(self) -> Dict[str, Any]:
        return self._result or {}


class ComposeDialog(QDialog):
    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        recipients: Optional[List[str]] = None,
        subject: str = "",
        body: str = "",
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Wyslij wiadomosc")
        self.setObjectName("mailComposeDialog")
        self.setMinimumWidth(420)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        form = QFormLayout()
        form.setSpacing(12)

        self.to_edit = QLineEdit()
        self.to_edit.setObjectName("mailComposeTo")
        self.to_edit.setPlaceholderText("Adresaci (oddziel przecinkami)")
        if recipients:
            self.to_edit.setText(", ".join(recipients))
        form.addRow("Do", self.to_edit)

        self.subject_edit = QLineEdit()
        self.subject_edit.setObjectName("mailComposeSubject")
        self.subject_edit.setPlaceholderText("Temat wiadomosci")
        if subject:
            self.subject_edit.setText(subject)
        form.addRow("Temat", self.subject_edit)

        self.body_edit = QTextEdit()
        self.body_edit.setObjectName("mailComposeBody")
        self.body_edit.setPlaceholderText("Tresc wiadomosci...")
        if body:
            self.body_edit.setPlainText(body)
        form.addRow("Tresc", self.body_edit)

        layout.addLayout(form)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok
        )
        self.buttons.accepted.connect(self._on_accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

        self._result: Optional[Tuple[List[str], str, str]] = None

    def _on_accept(self) -> None:
        recipients_raw = self.to_edit.text().strip()
        subject = sanitize_header(self.subject_edit.text().strip(), max_len=255)
        body = trim_length(self.body_edit.toPlainText().strip(), 30000)

        try:
            recipients = validate_emails(recipients_raw)
        except ValueError as exc:
            QMessageBox.warning(self, "Błędne dane", str(exc))
            return
        if not recipients or not subject or not body:
            QMessageBox.warning(
                self, "Brak danych", "Uzupelnij adresata, temat i tresc wiadomosci."
            )
            return

        self._result = (recipients, subject, body)
        self.accept()

    def get_data(self) -> Tuple[List[str], str, str]:
        if self._result is None:
            return [], "", ""
        return self._result
