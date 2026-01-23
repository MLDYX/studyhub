from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import List

from core.calendar import Event, WARSAW_TZ
from data.credentials import UserCredentials
from data.supabase_client import SupabaseService


class CalendarPersistence:
    """Warstwa zapisu/odczytu kalendarza do Supabase."""

    def __init__(self, supabase: SupabaseService, user: UserCredentials) -> None:
        self.supabase = supabase
        self.user = user

    def create_event(self, event: Event, *, source_id: str | None = None, source_type: str | None = None) -> None:
        self.supabase.create_calendar_event(
            user_id=self.user.user_id,
            title=event.title,
            starts_at=event.start,
            ends_at=event.end,
            event_id=event.id,
            location="",
            description=event.description,
            color_key=event.color_key,
            source_id=source_id,
            source_type=source_type,
        )

    def update_event(self, event: Event) -> None:
        self.supabase.update_calendar_event(
            user_id=self.user.user_id,
            event_id=event.id,
            title=event.title,
            starts_at=event.start.isoformat(),
            ends_at=event.end.isoformat(),
            description=event.description,
            color_key=event.color_key,
        )

    def soft_delete(self, event_id: str) -> None:
        self.supabase.delete_calendar_event(self.user.user_id, event_id)

    def soft_delete_source(self, source_id: str) -> None:
        self.supabase.soft_delete_events_by_source(self.user.user_id, source_id)

    def load_events(self) -> List[Event]:
        rows = self.supabase.list_calendar_events(self.user.user_id)
        events: List[Event] = []
        for row in rows:
            start = _parse_dt(row.get("starts_at"))
            end = _parse_dt(row.get("ends_at"))
            events.append(
                Event(
                    id=str(row["id"]),
                    title=str(row.get("title", "")),
                    start=start,
                    end=end,
                    color_key=str(row.get("color_key", "")) or "Niebieski",
                    description=str(row.get("description", "")),
                )
            )
        return events

    def bulk_upsert(self, events: List[Event], source_id: str, source_type: str | None = None) -> None:
        self.supabase.create_calendar_events_bulk(
            user_id=self.user.user_id,
            events=events,
            source_id=source_id,
            source_type=source_type,
        )

    def cleanup(self, *, soft_delete_before: datetime, hard_delete_older_than: datetime) -> None:
        self.supabase.soft_delete_events_past(self.user.user_id, soft_delete_before.isoformat())
        self.supabase.hard_delete_old_deleted(self.user.user_id, hard_delete_older_than.isoformat())


def _parse_dt(value) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=WARSAW_TZ)
    if isinstance(value, str):
        parsed = datetime.fromisoformat(value)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=WARSAW_TZ)
    raise ValueError("Nieprawidlowy format daty")
