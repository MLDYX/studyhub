from __future__ import annotations

from datetime import datetime, timedelta
from typing import List

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QIcon, QPainter, QPixmap
from PyQt6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.calendar import CalendarStore, COLOR_KEYS, Event, WARSAW_TZ


class HomeView(QWidget):
    def __init__(self, store: CalendarStore, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._store = store
        self.setObjectName("homeRoot")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(24)

        header = QLabel("Witamy w StudyHub")
        header.setObjectName("h1")
        layout.addWidget(header)

        subheader = QLabel("Szybki podgląd nadchodzących zadań i modułów")
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
        self.total_card = self._create_card("Wszystkie wydarzenia", "0")
        self.next_card = self._create_card("Najbliższe wydarzenie", "Brak zaplanowanych", has_description=True)
        if getattr(self.next_card, "description_label", None):
            self.next_card.description_label.setText("Dodaj wydarzenie, aby pojawiły się tutaj.")

        self._decorate_card(self.today_card, "indigo")
        self._decorate_card(self.week_card, "teal")
        self._decorate_card(self.total_card, "magenta")
        self._decorate_card(self.next_card, "amber")

        cards_layout.addWidget(self.today_card, 0, 0)
        cards_layout.addWidget(self.week_card, 0, 1)
        cards_layout.addWidget(self.total_card, 0, 2)
        cards_layout.addWidget(self.next_card, 0, 3)
        cards_layout.setColumnStretch(0, 1)
        cards_layout.setColumnStretch(1, 1)
        cards_layout.setColumnStretch(2, 1)
        cards_layout.setColumnStretch(3, 1)

        layout.addWidget(cards_container)

        self.upcoming_frame = QFrame()
        self.upcoming_frame.setObjectName("card")
        upcoming_layout = QVBoxLayout(self.upcoming_frame)
        upcoming_layout.setContentsMargins(24, 24, 24, 24)
        upcoming_layout.setSpacing(12)

        upcoming_title = QLabel("Najbliższe wydarzenia (7 dni)")
        upcoming_title.setObjectName("cardTitle")
        upcoming_layout.addWidget(upcoming_title)

        self.upcoming_list = QListWidget()
        self.upcoming_list.setObjectName("upcomingList")
        self.upcoming_list.setUniformItemSizes(True)
        upcoming_layout.addWidget(self.upcoming_list)

        layout.addWidget(self.upcoming_frame)

        self.modules_frame = QFrame()
        self.modules_frame.setObjectName("card")
        modules_layout = QVBoxLayout(self.modules_frame)
        modules_layout.setContentsMargins(24, 24, 24, 24)
        modules_layout.setSpacing(12)

        modules_title = QLabel("Moduły w przygotowaniu")
        modules_title.setObjectName("cardTitle")
        modules_layout.addWidget(modules_title)

        modules_tiles = QHBoxLayout()
        modules_tiles.setContentsMargins(0, 0, 0, 0)
        modules_tiles.setSpacing(12)
        modules_tiles.addWidget(self._create_module_tile("Notatki", "Funkcja dostępna wkrótce", variant="notes"))
        modules_tiles.addWidget(self._create_module_tile("Mail", "Funkcja dostępna wkrótce", variant="mail"))
        modules_tiles.addStretch(1)

        modules_layout.addLayout(modules_tiles)

        layout.addWidget(self.modules_frame)
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

    def _create_module_tile(self, title: str, subtitle: str, *, variant: str | None = None) -> QFrame:
        tile = QFrame()
        tile.setObjectName("moduleTile")
        tile.setFrameShape(QFrame.Shape.StyledPanel)

        layout = QVBoxLayout(tile)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(6)

        title_label = QLabel(title)
        title_label.setObjectName("moduleTitle")
        subtitle_label = QLabel(subtitle)
        subtitle_label.setObjectName("moduleSubtitle")
        subtitle_label.setWordWrap(True)

        layout.addWidget(title_label)
        layout.addWidget(subtitle_label)
        layout.addStretch(1)

        if variant:
            tile.setProperty("variant", variant)
            tile.style().unpolish(tile)
            tile.style().polish(tile)
        return tile

    def refresh(self) -> None:
        now = datetime.now(WARSAW_TZ)
        today = now.date()
        today_events = self._store.events_for_day(today)
        week_events = self._store.events_for_week(today)
        all_events = self._store.all_events()

        self.today_card.value_label.setText(str(len(today_events)))
        self.week_card.value_label.setText(str(len(week_events)))
        self.total_card.value_label.setText(str(len(all_events)))

        upcoming_events = self._collect_upcoming_events(all_events, now)
        self._update_next_card(upcoming_events)
        self._populate_upcoming_list(upcoming_events)

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
                description_label.setText("Dodaj wydarzenie, aby pojawiły się tutaj.")
            return

        next_event = events[0]
        start_local = next_event.start.astimezone(WARSAW_TZ)
        end_local = next_event.end.astimezone(WARSAW_TZ)
        self.next_card.value_label.setText(
            f"{start_local.strftime('%d.%m %H:%M')} – {end_local.strftime('%H:%M')}"
        )
        if description_label is not None:
            description_label.setText(next_event.title)

    def _populate_upcoming_list(self, events: List[Event]) -> None:
        self.upcoming_list.clear()
        if not events:
            placeholder = QListWidgetItem("Brak zaplanowanych wydarzeń")
            placeholder.setFlags(Qt.ItemFlag.NoItemFlags)
            self.upcoming_list.addItem(placeholder)
            return

        for event in events[:6]:
            start_local = event.start.astimezone(WARSAW_TZ)
            end_local = event.end.astimezone(WARSAW_TZ)
            time_window = f"{start_local.strftime('%d.%m %H:%M')} – {end_local.strftime('%H:%M')}"
            item = QListWidgetItem(f"{time_window}  {event.title}")
            item.setData(Qt.ItemDataRole.UserRole, event.id)
            if event.description:
                item.setToolTip(event.description)
            color_hex = COLOR_KEYS.get(event.color_key, "#3A7AFE")
            item.setIcon(create_color_icon(color_hex))
            self.upcoming_list.addItem(item)


def create_color_icon(color_hex: str, size: int = 14) -> QIcon:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setBrush(QColor(color_hex))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawEllipse(0, 0, size, size)
    painter.end()
    return QIcon(pixmap)
