from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone, tzinfo
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from uuid import uuid4

from icalendar import Calendar
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def _load_warsaw_timezone() -> tzinfo:
    try:
        return ZoneInfo("Europe/Warsaw")
    except ZoneInfoNotFoundError:
        try:
            from dateutil import tz  # type: ignore
        except ImportError:
            return timezone(timedelta(hours=1), name="Europe/Warsaw")

        warsaw = tz.gettz("Europe/Warsaw")
        if warsaw is None:
            return tz.tzoffset("Europe/Warsaw", 3600)
        return warsaw


WARSAW_TZ = _load_warsaw_timezone()

# Stała paleta kolorów inspirowana Apple Calendar
COLOR_PRESETS: List[Tuple[str, str]] = [
    ("Niebieski", "#3A7AFE"),
    ("Zielony", "#34C759"),
    ("Czerwony", "#FF3B30"),
    ("Fioletowy", "#AF52DE"),
    ("Żółty", "#FFCC00"),
]
COLOR_KEYS = {name: hex_code for name, hex_code in COLOR_PRESETS}
DEFAULT_COLOR_KEY = COLOR_PRESETS[0][0]


@dataclass
class Event:
    """Prosta struktura opisująca wydarzenie w kalendarzu."""

    id: str
    title: str
    start: datetime
    end: datetime
    color_key: str
    description: str = ""

    def as_dict(self) -> Dict[str, object]:
        return {
            "id": self.id,
            "title": self.title,
            "start": self.start,
            "end": self.end,
            "color_key": self.color_key,
            "description": self.description,
        }


class CalendarStore:
    """Wszystkie dane kalendarza przechowujemy w pamięci."""

    def __init__(self) -> None:
        self._events: Dict[str, Event] = {}

    # --- operacje CRUD -------------------------------------------------
    def add_event(
        self,
        title: str,
        start_dt: datetime,
        end_dt: datetime,
        color_key: str,
        description: str = "",
    ) -> str:
        event_id = str(uuid4())
        event = Event(
            id=event_id,
            title=title.strip() or "Bez tytułu",
            start=_ensure_timezone(start_dt),
            end=_ensure_timezone(end_dt),
            color_key=self._validate_color(color_key),
            description=description.strip(),
        )
        if event.end < event.start:
            raise ValueError("Data zakończenia nie może być wcześniejsza niż data rozpoczęcia.")
        self._events[event_id] = event
        return event_id

    def update_event(
        self,
        event_id: str,
        *,
        title: Optional[str] = None,
        start_dt: Optional[datetime] = None,
        end_dt: Optional[datetime] = None,
        color_key: Optional[str] = None,
        description: Optional[str] = None,
    ) -> None:
        event = self._events.get(event_id)
        if event is None:
            raise KeyError(f"Brak wydarzenia o ID {event_id}")

        if title is not None:
            event.title = title.strip() or "Bez tytułu"
        if start_dt is not None:
            event.start = _ensure_timezone(start_dt)
        if end_dt is not None:
            event.end = _ensure_timezone(end_dt)
        if color_key is not None:
            event.color_key = self._validate_color(color_key)
        if description is not None:
            event.description = description.strip()
        if event.end < event.start:
            raise ValueError("Data zakończenia nie może być wcześniejsza niż data rozpoczęcia.")

    def remove_event(self, event_id: str) -> None:
        self._events.pop(event_id, None)

    # --- zapytania ------------------------------------------------------
    def get_event(self, event_id: str) -> Optional[Event]:
        return self._events.get(event_id)

    def all_events(self) -> List[Event]:
        return sorted(self._events.values(), key=lambda ev: ev.start)

    def events_for_day(self, day: date) -> List[Event]:
        target = _normalize_to_date(day)
        return sorted(
            (
                event
                for event in self._events.values()
                if _normalize_to_date(event.start) == target
            ),
            key=lambda ev: ev.start,
        )

    def events_for_week(self, day: date) -> List[Event]:
        week_start = _week_start(_normalize_to_date(day))
        week_end = week_start + timedelta(days=6)
        return sorted(
            (
                event
                for event in self._events.values()
                if week_start <= _normalize_to_date(event.start) <= week_end
            ),
            key=lambda ev: (ev.start, ev.end),
        )

    # --- import ---------------------------------------------------------
    def import_ics(self, path: str | Path) -> int:
        file_path = Path(path)
        if not file_path.exists():
            raise FileNotFoundError(f"Nie znaleziono pliku: {file_path}")

        with file_path.open("rb") as handle:
            calendar = Calendar.from_ical(handle.read())

        imported = 0
        for component in calendar.walk():
            if component.name != "VEVENT":
                continue

            summary = str(component.get("SUMMARY", "Wydarzenie"))
            description = str(component.get("DESCRIPTION", ""))
            start_raw = component.get("DTSTART")
            end_raw = component.get("DTEND")

            if start_raw is None:
                continue

            start_dt = _as_datetime(component.decoded("DTSTART"))
            if end_raw is None:
                end_dt = start_dt + timedelta(hours=1)
            else:
                end_dt = _as_datetime(component.decoded("DTEND"))

            self.add_event(
                title=summary,
                start_dt=start_dt,
                end_dt=end_dt,
                color_key=DEFAULT_COLOR_KEY,
                description=description,
            )
            imported += 1

        return imported

    # --- pomocnicze -----------------------------------------------------
    def _validate_color(self, color_key: str) -> str:
        if color_key in COLOR_KEYS:
            return color_key
        return DEFAULT_COLOR_KEY


# --- funkcje pomocnicze -------------------------------------------------

def _normalize_to_date(value: date | datetime) -> date:
    if isinstance(value, datetime):
        return value.date()
    return value


def _ensure_timezone(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=WARSAW_TZ)
    return dt.astimezone(WARSAW_TZ)


def _week_start(day: date) -> date:
    return day - timedelta(days=day.weekday())


def _as_datetime(value) -> datetime:
    if isinstance(value, datetime):
        return _ensure_timezone(value)
    if isinstance(value, date):
        return _ensure_timezone(datetime.combine(value, datetime.min.time()))
    raise TypeError(f"Nieobsługiwany typ daty: {type(value)}")
