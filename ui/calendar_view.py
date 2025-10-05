from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Dict, Optional

from PyQt6.QtCore import (
    QDate,
    QDateTime,
    QLocale,
    QPoint,
    QPropertyAnimation,
    QEasingCurve,
    QSize,
    Qt,
    pyqtSignal,
)
from PyQt6.QtGui import QColor, QIcon, QPainter, QPixmap
from PyQt6.QtWidgets import (
    QButtonGroup,
    QCalendarWidget,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
    QDateTimeEdit,
    QGraphicsOpacityEffect,
)

ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets" / "icons"

from core.calendar import CalendarStore, Event, COLOR_KEYS, COLOR_PRESETS, _week_start


class CalendarView(QWidget):
    calendar_updated = pyqtSignal()

    def __init__(self, store: CalendarStore, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._store = store
        self.setObjectName("calendarRoot")

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(16)

        main_layout.addWidget(self._build_toolbar())

        self._view_stack = QStackedWidget()
        self._month_view = MonthlyCalendarPage(store)
        self._week_view = WeeklyCalendarPage(store)

        self._view_stack.addWidget(self._month_view)
        self._view_stack.addWidget(self._week_view)
        main_layout.addWidget(self._view_stack)

        self._stack_effect = QGraphicsOpacityEffect(self._view_stack)
        self._view_stack.setGraphicsEffect(self._stack_effect)
        self._stack_effect.setOpacity(1.0)
        self._fade_anim = QPropertyAnimation(self._stack_effect, b"opacity")
        self._fade_anim.setDuration(220)
        self._fade_anim.setEasingCurve(QEasingCurve.Type.InOutQuad)

        self._month_view.day_selected.connect(self._week_view.show_week_for_date)
        self._month_view.event_edit_requested.connect(self._edit_event)
        self._week_view.event_edit_requested.connect(self._edit_event)
        self._week_view.week_changed.connect(self._month_view.select_date)

        self._month_view.select_date(date.today())
        self._week_view.show_week_for_date(date.today())
        self._play_fade_in()

    def _build_toolbar(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("calendarToolbar")
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)

        self._segment_group = QButtonGroup(self)
        self._segment_group.setExclusive(True)
        self._segment_buttons: Dict[int, QToolButton] = {}

        self._segment_frame = QFrame()
        self._segment_frame.setObjectName("calendarSegment")
        segment_layout = QHBoxLayout(self._segment_frame)
        segment_layout.setContentsMargins(4, 4, 4, 4)
        segment_layout.setSpacing(4)

        for index, label in enumerate(["Miesiąc", "Tydzień"]):
            button = QToolButton()
            button.setObjectName("calendarSegmentButton")
            button.setText(label)
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            segment_layout.addWidget(button)
            self._segment_group.addButton(button, index)
            self._segment_buttons[index] = button
            button.clicked.connect(lambda _, idx=index: self._switch_view(idx))

        self._segment_buttons[0].setChecked(True)

        layout.addWidget(self._segment_frame)
        layout.addStretch(1)

        self._import_button = QPushButton("Import .ics")
        self._import_button.setObjectName("calendarActionSecondary")
        self._import_button.clicked.connect(self._import_ics)

        self._add_button = QPushButton("Dodaj wydarzenie")
        self._add_button.setObjectName("calendarActionPrimary")
        self._add_button.clicked.connect(self._add_event)

        layout.addWidget(self._import_button)
        layout.addWidget(self._add_button)
        return frame

    def _switch_view(self, index: int) -> None:
        if self._view_stack.currentIndex() == index:
            return

        target_button = self._segment_group.button(index)
        if target_button is not None and not target_button.isChecked():
            self._segment_group.blockSignals(True)
            target_button.setChecked(True)
            self._segment_group.blockSignals(False)

        self._view_stack.setCurrentIndex(index)
        self._play_fade_in()

    def _import_ics(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Importuj wydarzenia",
            "",
            "Pliki iCalendar (*.ics)",
        )
        if not path:
            return
        try:
            imported = self._store.import_ics(path)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Import nieudany", str(exc))
            return

        self.refresh_views()
        self.calendar_updated.emit()
        if imported:
            QMessageBox.information(
                self,
                "Import zakończony",
                f"Zaimportowano {imported} wydarzeń.",
            )
        else:
            QMessageBox.information(
                self,
                "Brak nowych wydarzeń",
                "Nie znaleziono wydarzeń do importu w wybranym pliku.",
            )

    def _add_event(self) -> None:
        dialog = EventDialog(parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        data = dialog.get_data()
        try:
            self._store.add_event(**data)
        except ValueError as exc:
            QMessageBox.warning(self, "Błąd danych", str(exc))
            return

        self.refresh_views()
        self.calendar_updated.emit()

    def _edit_event(self, event_id: str) -> None:
        event = self._store.get_event(event_id)
        if event is None:
            return

        dialog = EventDialog(parent=self, event=event)
        result = dialog.exec()
        if result != QDialog.DialogCode.Accepted:
            return

        if dialog.delete_requested:
            self._store.remove_event(event_id)
        else:
            data = dialog.get_data()
            try:
                self._store.update_event(event_id, **data)
            except ValueError as exc:
                QMessageBox.warning(self, "Błąd danych", str(exc))
                return

        self.refresh_views()
        self.calendar_updated.emit()

    def refresh_views(self) -> None:
        self._month_view.refresh()
        self._week_view.refresh()

    def _play_fade_in(self) -> None:
        self._fade_anim.stop()
        self._stack_effect.setOpacity(0.0)
        self._fade_anim.setStartValue(0.0)
        self._fade_anim.setEndValue(1.0)
        self._fade_anim.start()


class MonthlyCalendarPage(QWidget):
    event_edit_requested = pyqtSignal(str)
    day_selected = pyqtSignal(date)

    def __init__(self, store: CalendarStore, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._store = store
        self._selected_day = date.today()

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        container = QFrame()
        container.setObjectName("calendarBoard")
        layout = QHBoxLayout(container)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(24)

        self._calendar = EventCalendarWidget(store)
        self._calendar.selectionChanged.connect(self._on_selection_changed)
        layout.addWidget(self._calendar, stretch=3)

        self._side_panel = QFrame()
        self._side_panel.setObjectName("dayPanel")
        side_layout = QVBoxLayout(self._side_panel)
        side_layout.setContentsMargins(16, 16, 16, 16)
        side_layout.setSpacing(12)

        self._panel_title = QLabel()
        self._panel_title.setObjectName("panelTitle")
        side_layout.addWidget(self._panel_title)

        self._events_list = QListWidget()
        self._events_list.itemDoubleClicked.connect(self._emit_event_edit)
        side_layout.addWidget(self._events_list)

        layout.addWidget(self._side_panel, stretch=2)

        root_layout.addWidget(container)

        self.refresh()

    def select_date(self, target: date) -> None:
        qdate = QDate(target.year, target.month, target.day)
        if self._calendar.selectedDate() != qdate:
            self._calendar.setSelectedDate(qdate)
        self._selected_day = target
        self.refresh()

    def refresh(self) -> None:
        self._calendar.updateCells()
        self._populate_events(self._selected_day)

    def _on_selection_changed(self) -> None:
        qdate = self._calendar.selectedDate()
        self._selected_day = qdate.toPyDate()
        self.day_selected.emit(self._selected_day)
        self._populate_events(self._selected_day)

    def _populate_events(self, target_day: date) -> None:
        self._events_list.clear()
        events = self._store.events_for_day(target_day)
        formatted_date = target_day.strftime("%d.%m.%Y")
        self._panel_title.setText(f"{formatted_date}")

        if not events:
            placeholder = QListWidgetItem("Brak wydarzeń")
            placeholder.setFlags(Qt.ItemFlag.NoItemFlags)
            self._events_list.addItem(placeholder)
            return

        for event in events:
            item = QListWidgetItem(_format_event_label(event))
            item.setData(Qt.ItemDataRole.UserRole, event.id)
            item.setIcon(create_color_icon(COLOR_KEYS.get(event.color_key, "#3A7AFE")))
            self._events_list.addItem(item)

    def _emit_event_edit(self, item: QListWidgetItem) -> None:
        event_id = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(event_id, str):
            self.event_edit_requested.emit(event_id)


class EventCalendarWidget(QCalendarWidget):
    def __init__(self, store: CalendarStore, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._store = store
        self.setGridVisible(True)
        self.setFirstDayOfWeek(Qt.DayOfWeek.Monday)
        self.setLocale(QLocale(QLocale.Language.Polish, QLocale.Country.Poland))
        self.setVerticalHeaderFormat(QCalendarWidget.VerticalHeaderFormat.NoVerticalHeader)
        self.setHorizontalHeaderFormat(QCalendarWidget.HorizontalHeaderFormat.ShortDayNames)
        self.setMinimumWidth(520)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(
            """
            QWidget#qt_calendar_calendarview {
                background-color: #ffffff;
                selection-background-color: transparent;
                border-radius: 12px;
            }
            QWidget#qt_calendar_navigationbar {
                background-color: #ffffff;
            }
            QWidget {
                background-color: transparent;
            }
            """
        )

        prev_button = self.findChild(QToolButton, "qt_calendar_prevmonth")
        next_button = self.findChild(QToolButton, "qt_calendar_nextmonth")
        month_button = self.findChild(QToolButton, "qt_calendar_monthbutton")
        year_button = self.findChild(QToolButton, "qt_calendar_yearbutton")

        for button, icon_name in ((prev_button, "chevron_left.svg"), (next_button, "chevron_right.svg")):
            if button is not None:
                button.setIcon(QIcon(str(ASSETS_DIR / icon_name)))
                button.setIconSize(QSize(18, 18))
                button.setText("")
                button.setAutoRaise(True)
                button.setCursor(Qt.CursorShape.PointingHandCursor)

        if month_button is not None:
            month_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            month_button.setIcon(QIcon(str(ASSETS_DIR / "chevron_down.svg")))
            month_button.setIconSize(QSize(12, 12))
            month_button.setCursor(Qt.CursorShape.PointingHandCursor)

        if year_button is not None:
            year_button.setCursor(Qt.CursorShape.PointingHandCursor)

    def paintCell(self, painter: QPainter, rect, date: QDate) -> None:  # type: ignore[override]
        super().paintCell(painter, rect, date)

        is_selected = date == self.selectedDate()
        is_today = date == QDate.currentDate()

        if is_selected or is_today:
            painter.save()
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            highlight_rect = rect.adjusted(6, 6, -6, -6) if is_selected else rect.adjusted(8, 8, -8, -8)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor("#4c6ef5") if is_selected else QColor("#eaf0ff"))
            painter.drawRoundedRect(highlight_rect, 10, 10)
            painter.restore()

        py_date = date.toPyDate()
        events = self._store.events_for_day(py_date)

        if events:
            painter.save()
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

            dot_radius = max(3, min(rect.width(), rect.height()) // 12)
            max_dots = min(len(events), 3)
            spacing = dot_radius * 2 + 4
            start_x = rect.center().x() - ((max_dots - 1) * spacing) / 2
            center_y = rect.bottom() - dot_radius - 3

            for index in range(max_dots):
                event = events[index]
                color_hex = COLOR_KEYS.get(event.color_key, "#3A7AFE")
                color = QColor(color_hex)
                cx = int(start_x + index * spacing)
                painter.setBrush(color)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawEllipse(QPoint(cx, center_y), dot_radius, dot_radius)

            painter.restore()

        if is_selected or is_today:
            painter.save()
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            painter.setPen(QColor("#ffffff") if is_selected else QColor("#1f3c88"))
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, str(date.day()))
            painter.restore()


class WeeklyCalendarPage(QWidget):
    event_edit_requested = pyqtSignal(str)
    week_changed = pyqtSignal(date)

    def __init__(self, store: CalendarStore, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._store = store
        self._current_day = date.today()

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        container = QFrame()
        container.setObjectName("calendarBoard")
        main_layout = QVBoxLayout(container)
        main_layout.setContentsMargins(24, 24, 24, 24)
        main_layout.setSpacing(16)

        controls = QHBoxLayout()
        controls.setSpacing(8)

        self._prev_button = QPushButton("← Poprzedni tydzień")
        self._prev_button.clicked.connect(self._go_previous_week)
        self._next_button = QPushButton("Następny tydzień →")
        self._next_button.clicked.connect(self._go_next_week)

        self._range_label = QLabel()
        self._range_label.setObjectName("panelTitle")

        controls.addWidget(self._prev_button)
        controls.addWidget(self._next_button)
        controls.addStretch(1)
        controls.addWidget(self._range_label)

        main_layout.addLayout(controls)

        self._scroll_area = QScrollArea()
        self._scroll_area.setWidgetResizable(True)
        self._content = QWidget()
        self._scroll_area.setWidget(self._content)
        main_layout.addWidget(self._scroll_area)

        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(0, 0, 0, 0)
        self._content_layout.setSpacing(12)

        self._day_sections = self._build_day_sections()

        self.refresh()

        root_layout.addWidget(container)

    def _build_day_sections(self) -> Dict[int, "_DaySection"]:
        sections: Dict[int, _DaySection] = {}
        for index in range(7):
            frame = QFrame()
            frame.setObjectName("daySection")
            frame_layout = QVBoxLayout(frame)
            frame_layout.setContentsMargins(16, 16, 16, 16)
            frame_layout.setSpacing(8)

            header = QLabel()
            header.setObjectName("daySectionTitle")
            frame_layout.addWidget(header)

            events_list = QListWidget()
            events_list.itemDoubleClicked.connect(self._handle_item_double_click)
            frame_layout.addWidget(events_list)

            self._content_layout.addWidget(frame)
            sections[index] = _DaySection(header_label=header, events_list=events_list)
        self._content_layout.addStretch(1)
        return sections

    def show_week_for_date(self, target_day: date) -> None:
        self._current_day = target_day
        self.refresh()

    def refresh(self) -> None:
        week_start = _week_start(self._current_day)
        week_end = week_start + timedelta(days=6)
        self._range_label.setText(
            f"{week_start.strftime('%d.%m.%Y')} – {week_end.strftime('%d.%m.%Y')}"
        )

        polish_locale = QLocale(QLocale.Language.Polish, QLocale.Country.Poland)
        for index, section in self._day_sections.items():
            day_date = week_start + timedelta(days=index)
            day_name = polish_locale.dayName(QDate(day_date.year, day_date.month, day_date.day).dayOfWeek(), QLocale.FormatType.LongFormat)
            section.header_label.setText(f"{day_name}, {day_date.strftime('%d.%m.%Y')}")
            section.events_list.clear()
            section.events_list.setProperty("day_date", day_date)

            events = self._store.events_for_day(day_date)
            if not events:
                placeholder = QListWidgetItem("Brak wydarzeń")
                placeholder.setFlags(Qt.ItemFlag.NoItemFlags)
                section.events_list.addItem(placeholder)
                continue

            for event in events:
                item = QListWidgetItem(_format_event_label(event))
                item.setData(Qt.ItemDataRole.UserRole, event.id)
                item.setIcon(create_color_icon(COLOR_KEYS.get(event.color_key, "#3A7AFE")))
                section.events_list.addItem(item)

    def _go_previous_week(self) -> None:
        self._current_day -= timedelta(days=7)
        self.refresh()
        self.week_changed.emit(_week_start(self._current_day))

    def _go_next_week(self) -> None:
        self._current_day += timedelta(days=7)
        self.refresh()
        self.week_changed.emit(_week_start(self._current_day))

    def _handle_item_double_click(self, item: QListWidgetItem) -> None:
        event_id = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(event_id, str):
            self.event_edit_requested.emit(event_id)


class EventDialog(QDialog):
    def __init__(self, parent: QWidget | None = None, event: Optional[Event] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Edytuj wydarzenie" if event else "Nowe wydarzenie")
        self.delete_requested = False

        self._event = event

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        form = QFormLayout()
        form.setSpacing(12)

        self.title_edit = QLineEdit(event.title if event else "")
        form.addRow("Tytuł", self.title_edit)

        self.start_edit = QDateTimeEdit()
        self.start_edit.setDisplayFormat("dd.MM.yyyy HH:mm")
        self.start_edit.setCalendarPopup(True)
        form.addRow("Początek", self.start_edit)

        self.end_edit = QDateTimeEdit()
        self.end_edit.setDisplayFormat("dd.MM.yyyy HH:mm")
        self.end_edit.setCalendarPopup(True)
        form.addRow("Koniec", self.end_edit)

        self.color_combo = _color_combo()
        form.addRow("Kolor", self.color_combo)

        self.description_edit = QTextEdit()
        self.description_edit.setPlaceholderText("Opis (opcjonalnie)")
        form.addRow("Opis", self.description_edit)

        layout.addLayout(form)

        self._buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        layout.addWidget(self._buttons)

        if event is not None:
            self._delete_button = QPushButton("Usuń")
            self._delete_button.setObjectName("dangerButton")
            self._delete_button.clicked.connect(self._handle_delete)
            self._buttons.addButton(self._delete_button, QDialogButtonBox.ButtonRole.DestructiveRole)

        self._buttons.accepted.connect(self.accept)
        self._buttons.rejected.connect(self.reject)

        self._apply_defaults()

    def _apply_defaults(self) -> None:
        if self._event is None:
            current = QDateTime.currentDateTime()
            self.start_edit.setDateTime(current)
            self.end_edit.setDateTime(current.addSecs(3600))
            self.color_combo.setCurrentIndex(0)
            return

        local_start = self._event.start.astimezone(self._event.start.tzinfo)
        local_end = self._event.end.astimezone(self._event.end.tzinfo)
        self.start_edit.setDateTime(_to_qdatetime(local_start))
        self.end_edit.setDateTime(_to_qdatetime(local_end))
        self.description_edit.setText(self._event.description)

        current_index = next(
            (index for index, (name, _) in enumerate(COLOR_PRESETS) if name == self._event.color_key),
            0,
        )
        self.color_combo.setCurrentIndex(current_index)

    def _handle_delete(self) -> None:
        self.delete_requested = True
        self.accept()

    def get_data(self) -> Dict[str, object]:
        start_dt = self.start_edit.dateTime().toPyDateTime()
        end_dt = self.end_edit.dateTime().toPyDateTime()
        return {
            "title": self.title_edit.text(),
            "start_dt": start_dt,
            "end_dt": end_dt,
            "color_key": self.color_combo.currentData(),
            "description": self.description_edit.toPlainText(),
        }


class _DaySection:
    def __init__(self, header_label: QLabel, events_list: QListWidget) -> None:
        self.header_label = header_label
        self.events_list = events_list


def _format_event_label(event: Event) -> str:
    start = event.start.astimezone(event.start.tzinfo)
    end = event.end.astimezone(event.end.tzinfo)
    time_str = f"{start.strftime('%H:%M')} – {end.strftime('%H:%M')}"
    return f"{time_str}  {event.title}"


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


def _color_combo() -> "QComboBox":
    from PyQt6.QtWidgets import QComboBox

    combo = QComboBox()
    for name, hex_code in COLOR_PRESETS:
        combo.addItem(create_color_icon(hex_code), name, userData=name)
    return combo


def _to_qdatetime(value: datetime) -> QDateTime:
    return QDateTime(value.year, value.month, value.day, value.hour, value.minute)
