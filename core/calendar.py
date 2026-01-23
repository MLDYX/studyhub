from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone, tzinfo
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from uuid import uuid4

from icalendar import Calendar
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from data.validation import trim_length

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
    ("Zloty", "#FFCC00"),
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

    def __init__(self, persistence=None) -> None:
        self._events: Dict[str, Event] = {}
        self._source_events: Dict[str, List[str]] = {}
        self._persistence = persistence

    # --- operacje CRUD -------------------------------------------------
    def add_event(
        self,
        title: str,
        start_dt: datetime,
        end_dt: datetime,
        color_key: str,
        description: str = "",
        source_id: Optional[str] = None,
        *,
        persist: bool = True,
    ) -> str:
        event_id = str(uuid4())
        event = Event(
            id=event_id,
            title=trim_length(title.strip() or "Bez tytulu", 255),
            start=_ensure_timezone(start_dt),
            end=_ensure_timezone(end_dt),
            color_key=self._validate_color(color_key),
            description=trim_length(description.strip(), 1024),
        )
        if event.end < event.start:
            raise ValueError("Data zakonczenia nie moze byc wczesniejsza niz data rozpoczecia.")
        self._events[event_id] = event
        if source_id:
            self._source_events.setdefault(source_id, []).append(event_id)
        if persist and self._persistence:
            self._persistence.create_event(event, source_id=source_id)
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
            event.title = title.strip() or "Bez tytulu"
        if start_dt is not None:
            event.start = _ensure_timezone(start_dt)
        if end_dt is not None:
            event.end = _ensure_timezone(end_dt)
        if color_key is not None:
            event.color_key = self._validate_color(color_key)
        if description is not None:
            event.description = trim_length(description.strip(), 1024)
        if event.end < event.start:
            raise ValueError("Data zakonczenia nie moze byc wczesniejsza niz data rozpoczecia.")
        if self._persistence:
            self._persistence.update_event(event)

    def remove_event(self, event_id: str) -> None:
        self._events.pop(event_id, None)
        if self._persistence:
            self._persistence.soft_delete(event_id)

    # --- zapytania ------------------------------------------------------
    def get_event(self, event_id: str) -> Optional[Event]:
        return self._events.get(event_id)

    def all_events(self) -> List[Event]:
        cutoff = _today_start()
        return sorted(
            (event for event in self._events.values() if event.end >= cutoff),
            key=lambda ev: ev.start,
        )

    def events_for_day(self, day: date) -> List[Event]:
        target = _normalize_to_date(day)
        cutoff = _today_start()
        return sorted(
            (
                event
                for event in self._events.values()
                if _normalize_to_date(event.start) == target and event.end >= cutoff
            ),
            key=lambda ev: ev.start,
        )

    def events_for_week(self, day: date) -> List[Event]:
        week_start = _week_start(_normalize_to_date(day))
        week_end = week_start + timedelta(days=6)
        cutoff = _today_start()
        return sorted(
            (
                event
                for event in self._events.values()
                if week_start <= _normalize_to_date(event.start) <= week_end and event.end >= cutoff
            ),
            key=lambda ev: (ev.start, ev.end),
        )

    # --- import ---------------------------------------------------------
    def import_ics(self, path: str | Path, *, source_id: Optional[str] = None) -> int:
        file_path = Path(path)
        if not file_path.exists():
            raise FileNotFoundError(f"Nie znaleziono pliku: {file_path}")
        if file_path.stat().st_size > 5 * 1024 * 1024:
            raise ValueError("Plik ICS jest za duzy (limit 5 MB).")

        with file_path.open("rb") as handle:
            calendar = Calendar.from_ical(handle.read())

        if source_id:
            self.remove_source_events(source_id)

        imported_ids: List[str] = []
        imported = 0
        max_events = 1000
        for component in calendar.walk():
            if component.name != "VEVENT":
                continue
            if imported >= max_events:
                break

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

            event_id = self.add_event(
                title=trim_length(summary, 255),
                start_dt=start_dt,
                end_dt=end_dt,
                color_key=DEFAULT_COLOR_KEY,
                description=trim_length(description, 1024),
                source_id=source_id,
                persist=False,
            )
            imported_ids.append(event_id)
            imported += 1

        # zapis zbiorczy do bazy aby nie blokowac UI pojedynczymi requestami
        if imported_ids and self._persistence:
            events = [self._events[eid] for eid in imported_ids if eid in self._events]
            self._persistence.bulk_upsert(events, source_id=source_id or "")

        if source_id:
            self._source_events[source_id] = imported_ids

        return imported

    def remove_source_events(self, source_id: str) -> None:
        event_ids = self._source_events.pop(source_id, [])
        for event_id in event_ids:
            self._events.pop(event_id, None)
        if self._persistence:
            self._persistence.soft_delete_source(source_id)

    def replace_events(self, events: List[Event]) -> None:
        self._events = {ev.id: ev for ev in events}
        self._source_events.clear()

    # --- pomocnicze -----------------------------------------------------
    def _validate_color(self, color_key: str) -> str:
        if color_key in COLOR_KEYS:
            return color_key
        return DEFAULT_COLOR_KEY


# --- funkcje pomocnicze -------------------------------------------------


def _normalize_to_date(value: date | datetime) -> date:
    if isinstance(value, datetime):
        return _ensure_timezone(value).date()
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
    raise TypeError(f"Nieobslugiwany typ daty: {type(value)}")


def _today_start() -> datetime:
    return datetime.now(WARSAW_TZ).replace(hour=0, minute=0, second=0, microsecond=0)
