from __future__ import annotations

import asyncio
import logging
import threading
from datetime import datetime, timedelta
from typing import Callable, Dict, List
import os

from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QEventLoop
from PyQt6.QtWidgets import (
    QApplication,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QSpacerItem,
    QVBoxLayout,
    QWidget,
)

from core.calendar import CalendarStore, Event, WARSAW_TZ
from core.mail import EmailClient, EmailMessageSummary
from core.settings import SettingsManager
from core.notes import get_all_favorites, get_all_notes, NOTES_DIR
from core.file_operations import get_file_info


class HomeView(QWidget):
    notes_requested = pyqtSignal(str)
    mail_requested = pyqtSignal(dict)

    def __init__(
        self,
        store: CalendarStore,
        settings: SettingsManager,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._store = store
        self._settings = settings
        self._logger = logging.getLogger(__name__)

        self._mail_client = EmailClient()
        self._provider_names: Dict[str, str] = {
            provider_id: display for provider_id, display in self._mail_client.provider_choices()
        }
        
        # Async loop for fetching real mails
        self._async_loop = asyncio.new_event_loop()
        self._loop_ready = threading.Event()
        self._async_thread = threading.Thread(
            target=self._start_async_loop,
            name="HomeMailAsyncLoop",
            daemon=True,
        )
        self._async_thread.start()
        
        # Real mail cache
        self._real_mail_messages: List[Dict[str, str]] = []

        self.setObjectName("homeRoot")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(24)

        header = QLabel("Witamy w StudyHub")
        header.setObjectName("h1")
        layout.addWidget(header)

        subheader = QLabel("Szybki podglad nadchodzacych zadan i modulu.")
        subheader.setObjectName("subtitle")
        layout.addWidget(subheader)

        cards_container = QWidget()
        cards_container.setObjectName("cardsContainer")
        cards_container.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        cards_layout = QGridLayout(cards_container)
        cards_layout.setContentsMargins(0, 0, 0, 0)
        cards_layout.setSpacing(16)

        self.today_card = self._create_card("Dzisiejsze wydarzenia", "0")
        self.week_card = self._create_card("Wydarzenia w tym tygodniu", "0")
        self.next_card = self._create_card(
            "Najblizsze wydarzenie", "Brak zaplanowanych", has_description=True
        )
        if getattr(self.next_card, "description_label", None):
            self.next_card.description_label.setText("Dodaj wydarzenie, aby pojawilo sie tutaj.")

        self._decorate_card(self.today_card, "indigo")
        self._decorate_card(self.week_card, "teal")
        self._decorate_card(self.next_card, "amber")

        cards_layout.addWidget(self.today_card, 0, 0)
        cards_layout.addWidget(self.week_card, 0, 1)
        cards_layout.addWidget(self.next_card, 0, 2)
        cards_layout.setColumnStretch(0, 1)
        cards_layout.setColumnStretch(1, 1)
        cards_layout.setColumnStretch(2, 1)

        layout.addWidget(cards_container)

        self.notes_frame = QFrame()
        self.notes_frame.setObjectName("card")
        notes_layout = QVBoxLayout(self.notes_frame)
        notes_layout.setContentsMargins(24, 24, 24, 24)
        notes_layout.setSpacing(12)

        notes_title = QLabel("Szybkie notatki")
        notes_title.setObjectName("cardTitle")
        notes_layout.addWidget(notes_title)

        self.notes_container = QWidget()
        self.notes_container.setObjectName("homeNotesContainer")
        self.notes_grid = QGridLayout(self.notes_container)
        self.notes_grid.setContentsMargins(0, 0, 0, 0)
        self.notes_grid.setSpacing(12)
        notes_layout.addWidget(self.notes_container)

        self.mail_frame = QFrame()
        self.mail_frame.setObjectName("card")
        mail_layout = QVBoxLayout(self.mail_frame)
        mail_layout.setContentsMargins(24, 24, 24, 24)
        mail_layout.setSpacing(12)

        self.mail_title = QLabel("Skrzynka podgladu")
        self.mail_title.setObjectName("cardTitle")
        mail_layout.addWidget(self.mail_title)

        self.mail_list_widget = QWidget()
        self.mail_list_widget.setObjectName("homeMailContainer")
        self.mail_list_layout = QVBoxLayout(self.mail_list_widget)
        self.mail_list_layout.setContentsMargins(0, 0, 0, 0)
        self.mail_list_layout.setSpacing(10)
        mail_layout.addWidget(self.mail_list_widget)

        content_row = QHBoxLayout()
        content_row.setContentsMargins(0, 0, 0, 0)
        content_row.setSpacing(16)
        content_row.addWidget(self.notes_frame, 1)
        content_row.addWidget(self.mail_frame, 1)
        layout.addLayout(content_row)

        layout.addStretch(1)

        self.refresh()

    def _create_card(
        self,
        title: str,
        value: str,
        *,
        muted: bool = False,
        has_description: bool = False,
    ) -> QFrame:
        frame = QFrame()
        frame.setObjectName("card")
        frame.setProperty("muted", muted)
        frame.setFrameShape(QFrame.Shape.StyledPanel)

        layout = QVBoxLayout(frame)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(8)

        title_label = QLabel(title)
        title_label.setObjectName("cardTitle")
        value_label = QLabel(value)
        value_label.setObjectName("cardValue")
        value_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        layout.addWidget(title_label)
        layout.addWidget(value_label)

        frame.value_label = value_label  # type: ignore[attr-defined]

        if has_description:
            description_label = QLabel("")
            description_label.setObjectName("cardDescription")
            description_label.setWordWrap(True)
            layout.addWidget(description_label)
            frame.description_label = description_label  # type: ignore[attr-defined]
        else:
            frame.description_label = None  # type: ignore[attr-defined]

        return frame

    def _decorate_card(self, card: QFrame, variant: str) -> None:
        card.setProperty("variant", variant)
        card.style().unpolish(card)
        card.style().polish(card)

    def _start_async_loop(self) -> None:
        asyncio.set_event_loop(self._async_loop)
        self._loop_ready.set()
        self._async_loop.run_forever()

    def _run_async(self, coro):
        """Run async coroutine and wait for result."""
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
            raise result_holder["error"]  # type: ignore
        return result_holder.get("result")

    def refresh(self) -> None:
        now = datetime.now(WARSAW_TZ)
        today = now.date()
        today_events = self._store.events_for_day(today)
        week_events = self._store.events_for_week(today)
        all_events = self._store.all_events()

        self.today_card.value_label.setText(str(len(today_events)))
        self.week_card.value_label.setText(str(len(week_events)))

        upcoming_events = self._collect_upcoming_events(all_events, now)
        self._update_next_card(upcoming_events)
        self._populate_notes_list()
        self._populate_mail_preview()

    def _collect_upcoming_events(self, events: List[Event], now: datetime) -> List[Event]:
        horizon = now + timedelta(days=7)
        upcoming: List[Event] = []
        for event in events:
            start_local = event.start.astimezone(WARSAW_TZ)
            end_local = event.end.astimezone(WARSAW_TZ)
            if end_local < now or start_local > horizon:
                continue
            upcoming.append(event)
        return sorted(upcoming, key=lambda ev: ev.start)

    def _update_next_card(self, events: List[Event]) -> None:
        description_label = getattr(self.next_card, "description_label", None)
        if not events:
            self.next_card.value_label.setText("Brak zaplanowanych")
            if description_label is not None:
                description_label.setText("Dodaj wydarzenie, aby pojawilo sie tutaj.")
            return

        next_event = events[0]
        start_local = next_event.start.astimezone(WARSAW_TZ)
        end_local = next_event.end.astimezone(WARSAW_TZ)
        slot = f"{start_local.strftime('%d.%m %H:%M')} - {end_local.strftime('%H:%M')}"
        self.next_card.value_label.setText(slot)
        if description_label is not None:
            description_label.setText(next_event.title)

    def _populate_notes_list(self) -> None:
        """Populate notes list with favorite files or recently modified files."""
        self._clear_layout(self.notes_grid)
        
        MAX_TILES = 6
        
        # Get favorite files first
        try:
            favorite_files = get_all_favorites()
        except Exception as exc:
            self._logger.warning("Failed to get favorites", exc_info=exc)
            favorite_files = []
        
        # Get all files sorted by modification time for filling up to 6 tiles
        recent_files = []
        try:
            all_files = get_all_notes()
            if all_files:
                # Sort by modification time (newest first)
                all_files_with_mtime = []
                for file_path in all_files:
                    try:
                        info = get_file_info(file_path)
                        if info:
                            all_files_with_mtime.append((file_path, info.get('modified', 0)))
                    except Exception:
                        continue
                all_files_with_mtime.sort(key=lambda x: x[1], reverse=True)
                recent_files = [path for path, _ in all_files_with_mtime]
        except Exception as exc:
            self._logger.warning("Failed to get recent files", exc_info=exc)
        
        # Combine favorites with recent files to reach MAX_TILES
        files_to_display = []
        favorite_set = set(favorite_files)
        
        # Add favorites first
        files_to_display.extend(favorite_files[:MAX_TILES])
        
        # If we have less than MAX_TILES, fill with recently modified files
        if len(files_to_display) < MAX_TILES:
            for file_path in recent_files:
                if file_path not in favorite_set:
                    files_to_display.append(file_path)
                    if len(files_to_display) >= MAX_TILES:
                        break
        
        # Convert file paths to note card format
        notes_data = []
        for file_path in files_to_display[:MAX_TILES]:
            try:
                file_info = get_file_info(file_path)
                if not file_info:
                    continue
                
                filename = file_info.get('name', 'Nieznany plik')
                
                # Get folder name relative to NOTES_DIR
                folder_path = file_info.get('directory', '')
                folder_name = os.path.relpath(folder_path, NOTES_DIR) if folder_path else 'Nieznany folder'
                
                notes_data.append({
                    'id': file_path,
                    'title': filename,
                    'preview': f'Folder: {folder_name}'
                })
            except Exception as exc:
                self._logger.warning(f"Failed to get info for file {file_path}", exc_info=exc)
                continue
        
        # If still no notes, show a message
        if not notes_data:
            empty_label = QLabel("Brak notatek. Dodaj pliki w zakladce Notatki.")
            empty_label.setObjectName("homeMailEmpty")
            empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty_label.setWordWrap(True)
            self.notes_grid.addWidget(empty_label, 0, 0, 1, 2)
            return
        
        columns = 2 if len(notes_data) > 1 else 1
        for index, note in enumerate(notes_data):
            note_card = self._create_note_card(note)
            row, col = divmod(index, columns)
            self.notes_grid.addWidget(note_card, row, col)
        for col in range(columns):
            self.notes_grid.setColumnStretch(col, 1)
        self.notes_grid.addItem(
            QSpacerItem(0, 0, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum), 0, columns
        )
        self.notes_grid.setRowStretch(
            (len(notes_data) + columns - 1) // columns + 1, 1
        )

    def _populate_mail_preview(self) -> None:
        """Populate mail preview with real inbox messages from default provider."""
        provider_id = self._settings.get_mail_provider()
        provider_name = self._provider_names.get(provider_id, provider_id or "")

        if provider_id:
            self.mail_title.setText(f"Skrzynka: {provider_name}")
        else:
            self.mail_title.setText("Skrzynka: brak domyslnego konta")

        self._clear_layout(self.mail_list_layout)

        if not provider_id:
            placeholder = self._create_mail_empty_state(
                "Wybierz domyslne konto w zakladce Ustawienia."
            )
            self.mail_list_layout.addWidget(placeholder)
            self.mail_list_layout.addStretch(1)
            return

        # Try to fetch real messages from inbox
        messages = self._fetch_inbox_messages(provider_id)
        
        if not messages:
            placeholder = self._create_mail_empty_state("Brak wiadomosci w skrzynce.")
            self.mail_list_layout.addWidget(placeholder)
            self.mail_list_layout.addStretch(1)
            return

        # Display up to 4 latest messages
        for entry in messages[:4]:
            mail_card = self._create_mail_card(entry)
            self.mail_list_layout.addWidget(mail_card)
        self.mail_list_layout.addStretch(1)

    def _fetch_inbox_messages(self, provider_id: str) -> List[Dict[str, str]]:
        """Fetch real inbox messages from the specified provider."""
        try:
            # Set provider and folder
            self._mail_client.set_provider(provider_id)
            self._mail_client.set_folder("inbox")
            
            # First try to get cached messages (fast)
            cached = self._mail_client.cached_messages()
            if cached:
                return self._convert_messages_to_dicts(cached, provider_id)
            
            # If no cache, try to authenticate and fetch (if already authenticated)
            provider = self._mail_client.current_provider
            if provider is None:
                return []
            
            # Check if we have stored credentials (don't trigger OAuth flow on home page)
            if hasattr(provider, 'tokens') and provider.tokens:
                try:
                    messages = self._run_async(self._mail_client.fetch_messages())
                    return self._convert_messages_to_dicts(messages, provider_id)
                except Exception as exc:
                    self._logger.warning(
                        "Failed to fetch home mail preview",
                        exc_info=exc,
                        extra={"event": "home_mail_fetch_failed", "provider": provider_id},
                    )
            return []
        except Exception as exc:
            self._logger.warning(
                "Failed to setup mail provider for home preview",
                exc_info=exc,
                extra={"event": "home_mail_setup_failed", "provider": provider_id},
            )
            return []

    def _convert_messages_to_dicts(
        self, messages: List[EmailMessageSummary], provider_id: str
    ) -> List[Dict[str, str]]:
        """Convert EmailMessageSummary objects to dict format for display."""
        result: List[Dict[str, str]] = []
        for msg in messages:
            result.append({
                "id": msg.message_id,
                "provider_id": provider_id,
                "subject": msg.subject or "(Brak tematu)",
                "sender": msg.sender,
                "snippet": msg.snippet,
            })
        return result

    def _create_note_card(self, note: Dict[str, str]) -> QFrame:
        card = QFrame()
        card.setObjectName("homeNoteCard")
        card.setCursor(Qt.CursorShape.PointingHandCursor)
        card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        card.setMinimumHeight(80)
        card.setMaximumHeight(80)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(6)

        title_label = QLabel()
        title_label.setObjectName("homeNoteCardTitle")
        title_label.setTextFormat(Qt.TextFormat.PlainText)
        title_label.setWordWrap(False)
        title_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        
        # Use font metrics to elide text manually
        from PyQt6.QtGui import QFontMetrics
        fm = QFontMetrics(title_label.font())
        elided_title = fm.elidedText(note["title"], Qt.TextElideMode.ElideRight, card.width() - 32)
        title_label.setText(elided_title)
        title_label.setToolTip(note["title"])  # Show full text on hover
        
        preview_label = QLabel()
        preview_label.setObjectName("homeNoteCardPreview")
        preview_label.setTextFormat(Qt.TextFormat.PlainText)
        preview_label.setWordWrap(False)
        preview_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        
        elided_preview = fm.elidedText(note["preview"], Qt.TextElideMode.ElideRight, card.width() - 32)
        preview_label.setText(elided_preview)
        preview_label.setToolTip(note["preview"])  # Show full text on hover

        layout.addWidget(title_label)
        layout.addWidget(preview_label)
        layout.addStretch(1)

        self._set_click_handler(card, lambda: self.notes_requested.emit(note["id"]))
        return card

    def _create_mail_card(self, payload: Dict[str, str]) -> QFrame:
        card = QFrame()
        card.setObjectName("homeMailCard")
        card.setCursor(Qt.CursorShape.PointingHandCursor)
        card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(4)

        subject = payload.get("subject") or "(Brak tematu)"
        snippet = payload.get("snippet", "")
        sender = payload.get("sender", "nadawca@przyklad.pl")

        subject_label = QLabel(subject)
        subject_label.setObjectName("homeMailSubject")
        meta_label = QLabel(f"{sender} | {snippet}" if snippet else sender)
        meta_label.setObjectName("homeMailMeta")
        meta_label.setWordWrap(True)

        layout.addWidget(subject_label)
        layout.addWidget(meta_label)

        self._set_click_handler(card, lambda: self.mail_requested.emit(payload))
        return card

    def _create_mail_empty_state(self, message: str) -> QLabel:
        label = QLabel(message)
        label.setObjectName("homeMailEmpty")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setWordWrap(True)
        label.setMargin(12)
        return label

    def _clear_layout(self, layout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            child_layout = item.layout()
            if widget is not None:
                widget.setParent(None)
            if child_layout is not None:
                self._clear_layout(child_layout)

    def _set_click_handler(self, card: QFrame, callback: Callable[[], None]) -> None:
        def handler(event):
            if event.button() == Qt.MouseButton.LeftButton:
                callback()
            QFrame.mousePressEvent(card, event)

        card.mousePressEvent = handler  # type: ignore[assignment]
