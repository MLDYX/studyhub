from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Dict, Optional, Tuple
import tempfile
from urllib import request, error as urlerror
import os

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
    QLineEdit,
    QDialogButtonBox,
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

        self._import_button = QPushButton("Importuj kalendarz")
        self._import_button.setObjectName("calendarActionSecondary")
        self._import_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._import_button.clicked.connect(self._import_ics)

        self._add_button = QPushButton("Dodaj wydarzenie")
        self._add_button.setObjectName("calendarActionPrimary")
        self._add_button.setCursor(Qt.CursorShape.PointingHandCursor)
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
        dialog = ImportCalendarDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        info = dialog.get_result()
        if info is None:
            return

        mode, value = info
        temp_path: Optional[str] = None
        try:
            if mode == "url":
                try:
                    data = request.urlopen(value, timeout=15).read()
                except urlerror.URLError as exc:  # type: ignore[assignment]
                    QMessageBox.warning(self, "Import nieudany", f"Nie można pobrać danych: {exc}")
                    return
                with tempfile.NamedTemporaryFile(delete=False, suffix=".ics") as tmp:
                    tmp.write(data)
                    temp_path = tmp.name
                target_path = temp_path
            else:
                target_path = value

            imported = self._store.import_ics(target_path)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Import nieudany", str(exc))
            return
        finally:
            if temp_path and os.path.exists(temp_path):
                os.remove(temp_path)

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
                "Nie znaleziono wydarzeń do importu.",
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
        self.setGridVisible(False)
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
                border-radius: 14px;
                selection-background-color: transparent;
                alternate-background-color: #ffffff;
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
        nav_bar = self.findChild(QWidget, "qt_calendar_navigationbar")

        for button, icon_name in ((prev_button, "chevron_left.svg"), (next_button, "chevron_right.svg")):
            if button is not None:
                button.setIcon(QIcon(str(ASSETS_DIR / icon_name)))
                button.setIconSize(QSize(18, 18))
                button.setText("")
                button.setAutoRaise(True)
                button.setCursor(Qt.CursorShape.PointingHandCursor)

        if month_button is not None:
            month_button.hide()
        if year_button is not None:
            year_button.hide()

        self._title_label: Optional[QLabel] = None
        if nav_bar is not None:
            layout = nav_bar.layout()
            if layout is not None:
                layout.setContentsMargins(12, 4, 12, 4)
                layout.setSpacing(12)
                self._title_label = QLabel()
                self._title_label.setObjectName("calendarHeaderLabel")
                self._title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                layout.insertWidget(1, self._title_label, 1)

        self.currentPageChanged.connect(self._update_title)
        self._update_title(self.yearShown(), self.monthShown())

    def paintCell(self, painter: QPainter, rect, date: QDate) -> None:  # type: ignore[override]
        current_month = date.month() == self.monthShown() and date.year() == self.yearShown()

        if not current_month:
            painter.save()
            painter.fillRect(rect, QColor("#ffffff"))
            painter.restore()
            return

        painter.save()
        painter.fillRect(rect, QColor("#ffffff"))
        painter.restore()

        is_selected = date == self.selectedDate()
        is_today = date == QDate.currentDate()
        day_number = date.dayOfWeek()
        is_weekend = day_number in (6, 7)

        if is_selected or (is_today and is_selected):
            painter.save()
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            inset = 6
            highlight_rect = rect.adjusted(inset, inset, -inset, -inset)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor("#ff3b30") if is_today else QColor("#dfe3eb"))
            painter.drawRoundedRect(highlight_rect, 10, 10)
            painter.restore()

        font = painter.font()
        font.setPointSize(font.pointSize() + 2)
        font.setBold(is_today)

        text_color = QColor("#1f2a4a")
        if is_weekend:
            text_color = QColor("#a0a5b4")
        if is_today and not is_selected:
            text_color = QColor("#ff3b30")
        if is_today and is_selected:
            text_color = QColor("#ffffff")
        if is_selected and not is_today:
            text_color = QColor("#1f1f24")

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setFont(font)
        painter.setPen(text_color)
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, str(date.day()))
        painter.restore()

        py_date = date.toPyDate()
        events = self._store.events_for_day(py_date)

        if events:
            painter.save()
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

            dot_radius = max(2, min(rect.width(), rect.height()) // 16)
            max_dots = min(len(events), 3)
            spacing = dot_radius * 2 + 6
            start_x = rect.center().x() - ((max_dots - 1) * spacing) / 2
            center_y = rect.bottom() - dot_radius - 8

            for index in range(max_dots):
                event = events[index]
                color_hex = COLOR_KEYS.get(event.color_key, "#3A7AFE")
                color = QColor(color_hex)
                cx = int(start_x + index * spacing)
                painter.setBrush(color)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawEllipse(QPoint(cx, center_y), dot_radius, dot_radius)

            painter.restore()

    def event(self, event):  # type: ignore[override]
        if event.type() in (event.Type.Enter, event.Type.HoverEnter):
            self.setCursor(Qt.CursorShape.PointingHandCursor)
        elif event.type() in (event.Type.Leave, event.Type.HoverLeave):
            self.unsetCursor()
        return super().event(event)

    def _update_title(self, year: int | None = None, month: int | None = None) -> None:
        if self._title_label is None:
            return
        if year is None:
            year = self.yearShown()
        if month is None:
            month = self.monthShown()

        locale = QLocale(QLocale.Language.Polish, QLocale.Country.Poland)
        month_name = locale.standaloneMonthName(month, QLocale.FormatType.LongFormat)
        self._title_label.setText(f"{month_name.capitalize()} {year}")


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
        self.setObjectName("eventDialog")
        self.setMinimumWidth(440)

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
        self._setup_datetime_edit(self.start_edit)
        form.addRow("Początek", self.start_edit)

        self.end_edit = QDateTimeEdit()
        self.end_edit.setDisplayFormat("dd.MM.yyyy HH:mm")
        self.end_edit.setCalendarPopup(True)
        self._setup_datetime_edit(self.end_edit)
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

    def _setup_datetime_edit(self, edit: QDateTimeEdit) -> None:
        edit.setObjectName("eventDateTime")
        edit.setMinimumHeight(36)
        calendar = edit.calendarWidget()
        if calendar is None:
            calendar = QCalendarWidget(edit)
            edit.setCalendarWidget(calendar)

        calendar.setGridVisible(False)
        calendar.setHorizontalHeaderFormat(QCalendarWidget.HorizontalHeaderFormat.ShortDayNames)
        calendar.setVerticalHeaderFormat(QCalendarWidget.VerticalHeaderFormat.NoVerticalHeader)
        calendar.setFirstDayOfWeek(Qt.DayOfWeek.Monday)
        calendar.setLocale(QLocale(QLocale.Language.Polish, QLocale.Country.Poland))
        calendar.setStyleSheet(
            """
            QWidget#qt_calendar_calendarview {
                background-color: #ffffff;
                border-radius: 12px;
                selection-background-color: transparent;
            }
            QWidget#qt_calendar_navigationbar {
                background-color: #ffffff;
                border: none;
            }
            QWidget {
                background-color: transparent;
            }
            """
        )

        try:
            prev_button = calendar.findChild(QToolButton, "qt_calendar_prevmonth")
            next_button = calendar.findChild(QToolButton, "qt_calendar_nextmonth")
            for button, icon_name in ((prev_button, "chevron_left.svg"), (next_button, "chevron_right.svg")):
                if button is not None:
                    button.setIcon(QIcon(str(ASSETS_DIR / icon_name)))
                    button.setIconSize(QSize(16, 16))
                    button.setText("")
                    button.setAutoRaise(True)

            month_button = calendar.findChild(QToolButton, "qt_calendar_monthbutton")
            year_button = calendar.findChild(QToolButton, "qt_calendar_yearbutton")
            if month_button is not None:
                month_button.hide()
            if year_button is not None:
                year_button.hide()

            nav_bar = calendar.findChild(QWidget, "qt_calendar_navigationbar")
            if nav_bar is not None:
                layout = nav_bar.layout()
                if layout is not None:
                    layout.setContentsMargins(12, 6, 12, 6)
                    layout.setSpacing(12)
                    title = nav_bar.findChild(QLabel, "popupCalendarTitle")
                    if title is None:
                        title = QLabel(nav_bar)
                        title.setObjectName("popupCalendarTitle")
                        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
                        layout.insertWidget(1, title, 1)

                    def update_label(year: int | None = None, month: int | None = None) -> None:
                        local_locale = QLocale(QLocale.Language.Polish, QLocale.Country.Poland)
                        y = year if year is not None else calendar.yearShown()
                        m = month if month is not None else calendar.monthShown()
                        month_name = local_locale.standaloneMonthName(m, QLocale.FormatType.LongFormat)
                        title.setText(f"{month_name.capitalize()} {y}")

                    calendar.currentPageChanged.connect(update_label)
                    update_label()
        except Exception:
            # Jeśli modyfikacja UI kalendarza się nie powiedzie, ignorujemy aby uniknąć awarii.
            pass


class _DaySection:
    def __init__(self, header_label: QLabel, events_list: QListWidget) -> None:
        self.header_label = header_label
        self.events_list = events_list


class ImportCalendarDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Importuj kalendarz")
        self.setObjectName("importDialog")
        self.setMinimumWidth(420)
        self._result: Optional[Tuple[str, str]] = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(18)

        title = QLabel("Dodaj kalendarz z linku lub pliku .ics")
        title.setObjectName("dialogHeading")
        layout.addWidget(title)

        url_layout = QVBoxLayout()
        url_layout.setSpacing(8)

        url_label = QLabel("Adres URL kalendarza (ICS)")
        url_label.setObjectName("dialogLabel")
        url_layout.addWidget(url_label)

        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText("https://...")
        self.url_edit.setObjectName("importUrlField")
        url_layout.addWidget(self.url_edit)

        self.url_button = QPushButton("Importuj z linku")
        self.url_button.setObjectName("importUrlButton")
        self.url_button.clicked.connect(self._accept_url)
        url_layout.addWidget(self.url_button)

        layout.addLayout(url_layout)

        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setFrameShadow(QFrame.Shadow.Plain)
        divider.setStyleSheet("color: #e4e7f7;")
        layout.addWidget(divider)

        self.file_button = QPushButton("Wybierz plik .ics")
        self.file_button.setObjectName("importFileButton")
        self.file_button.clicked.connect(self._select_file)
        layout.addWidget(self.file_button)

        self.button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        self.button_box.rejected.connect(self.reject)
        layout.addWidget(self.button_box)

    def _accept_url(self) -> None:
        url = self.url_edit.text().strip()
        if not url:
            QMessageBox.warning(self, "Brak adresu", "Podaj poprawny adres URL kalendarza.")
            return
        self._result = ("url", url)
        self.accept()

    def _select_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Wybierz plik kalendarza",
            "",
            "Pliki iCalendar (*.ics)",
        )
        if not path:
            return
        self._result = ("file", path)
        self.accept()

    def get_result(self) -> Optional[Tuple[str, str]]:
        return self._result


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


def _color_combo():
    from PyQt6.QtWidgets import QComboBox

    combo = QComboBox()
    for name, hex_code in COLOR_PRESETS:
        combo.addItem(create_color_icon(hex_code), name, userData=name)
    return combo


def _to_qdatetime(value: datetime) -> QDateTime:
    return QDateTime(value.year, value.month, value.day, value.hour, value.minute)
