"""
Integration test sketches for calendar module.
"""

import unittest
import sys
import os
import tempfile

from datetime import datetime, timedelta

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.calendar import CalendarStore, Event, WARSAW_TZ
from data.calendar_persistence import CalendarPersistence
from data.credentials import UserCredentials


class FakeCalendarPersistence:
    def __init__(self) -> None:
        self.created_events = []
        self.updated_events = []
        self.soft_deleted = []
        self.soft_deleted_sources = []
        self.bulk_upserts = []

    def create_event(self, event: Event, source_id=None, source_type=None) -> None:
        self.created_events.append((event, source_id, source_type))

    def update_event(self, event: Event) -> None:
        self.updated_events.append(event)

    def soft_delete(self, event_id: str) -> None:
        self.soft_deleted.append(event_id)

    def soft_delete_source(self, source_id: str) -> None:
        self.soft_deleted_sources.append(source_id)

    def bulk_upsert(self, events, source_id: str, source_type=None) -> None:
        self.bulk_upserts.append((events, source_id, source_type))


class FakeSupabase:
    def __init__(self) -> None:
        self.created = []
        self.updated = []
        self.deleted = []
        self.deleted_by_source = []
        self.bulk_created = []
        self.soft_deleted_past = []
        self.hard_deleted_old = []
        self.rows = []

    def create_calendar_event(self, **kwargs):
        self.created.append(kwargs)

    def update_calendar_event(self, **kwargs):
        self.updated.append(kwargs)

    def delete_calendar_event(self, user_id, event_id):
        self.deleted.append((user_id, event_id))

    def soft_delete_events_by_source(self, user_id, source_id):
        self.deleted_by_source.append((user_id, source_id))

    def list_calendar_events(self, user_id):
        return list(self.rows)

    def create_calendar_events_bulk(self, **kwargs):
        self.bulk_created.append(kwargs)

    def soft_delete_events_past(self, user_id, cutoff):
        self.soft_deleted_past.append((user_id, cutoff))

    def hard_delete_old_deleted(self, user_id, cutoff):
        self.hard_deleted_old.append((user_id, cutoff))


def _print_suite_overview():
    lines = [
        "1. Dodanie wydarzenia, zapis",
        "2. Aktualizacja wydarzenia, zapis",
        "3. Usuniecie wydarzenia, wykonuje soft delete",
        "4. Import ICS: bulk upsert i czyszczenie zrodla",
        "5. Wczytanie wydarzen parsuje ISO",
        "6. Cleanup wywoluje Supabase",
        "-" * 62,
    ]
    print("\n".join(lines))


def load_tests(loader, tests, pattern):
    _print_suite_overview()
    return tests


class OkTestCase(unittest.TestCase):
    def run(self, result=None):
        result = super().run(result)
        failures = [test for test, _ in result.failures]
        errors = [test for test, _ in result.errors]
        skipped = [test for test, _ in result.skipped]
        if self not in failures and self not in errors and self not in skipped:
            name = self.id().split(".")[-2:]
            short = ".".join(name)
            print(f"{short} ... ok")
        return result


class TestCalendarStoreIntegration(OkTestCase):
    def setUp(self):
        self.persistence = FakeCalendarPersistence()
        self.store = CalendarStore(persistence=self.persistence)

    def test_add_event_persists(self):
        start = datetime(2025, 1, 10, 9, 0)
        end = datetime(2025, 1, 10, 10, 0)

        event_id = self.store.add_event("Meeting", start, end, "Niebieski")

        self.assertIn(event_id, self.store._events)
        self.assertEqual(len(self.persistence.created_events), 1)
        created_event, _, _ = self.persistence.created_events[0]
        self.assertEqual(created_event.id, event_id)
        self.assertEqual(created_event.start.tzinfo, WARSAW_TZ)

    def test_update_event_persists(self):
        start = datetime(2025, 1, 10, 9, 0)
        end = datetime(2025, 1, 10, 10, 0)
        event_id = self.store.add_event("Meeting", start, end, "Niebieski", persist=False)

        self.store.update_event(event_id, title="Updated")

        self.assertEqual(self.store.get_event(event_id).title, "Updated")
        self.assertEqual(len(self.persistence.updated_events), 1)

    def test_remove_event_soft_delete(self):
        start = datetime(2025, 1, 10, 9, 0)
        end = datetime(2025, 1, 10, 10, 0)
        event_id = self.store.add_event("Meeting", start, end, "Niebieski", persist=False)

        self.store.remove_event(event_id)

        self.assertIsNone(self.store.get_event(event_id))
        self.assertIn(event_id, self.persistence.soft_deleted)

    def test_import_ics_bulk_upsert_and_source_cleanup(self):
        ics_content = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//StudyHub//EN
BEGIN:VEVENT
UID:1
DTSTAMP:20250101T100000Z
DTSTART:20250102T090000Z
DTEND:20250102T100000Z
SUMMARY:Event One
DESCRIPTION:Desc 1
END:VEVENT
BEGIN:VEVENT
UID:2
DTSTAMP:20250101T100000Z
DTSTART;VALUE=DATE:20250103
SUMMARY:All Day Event
END:VEVENT
END:VCALENDAR
"""
        with tempfile.NamedTemporaryFile(delete=False, suffix=".ics") as handle:
            handle.write(ics_content.encode("utf-8"))
            ics_path = handle.name

        try:
            imported = self.store.import_ics(ics_path, source_id="source-1")
        finally:
            os.remove(ics_path)

        self.assertEqual(imported, 2)
        self.assertEqual(len(self.persistence.bulk_upserts), 1)
        events, source_id, _ = self.persistence.bulk_upserts[0]
        self.assertEqual(len(events), 2)
        self.assertEqual(source_id, "source-1")
        self.assertEqual(len(self.persistence.soft_deleted_sources), 1)


class TestCalendarPersistenceIntegration(OkTestCase):
    def setUp(self):
        self.supabase = FakeSupabase()
        self.user = UserCredentials(
            user_id="user-1",
            secret_token="token",
            username="user",
            last_login_iso="2025-01-01T00:00:00+00:00",
        )
        self.persistence = CalendarPersistence(self.supabase, self.user)

    def test_load_events_parses_iso_strings(self):
        self.supabase.rows = [
            {
                "id": "event-1",
                "title": "Title",
                "starts_at": "2025-01-10T09:00:00+00:00",
                "ends_at": "2025-01-10T10:00:00+00:00",
                "color_key": "",
                "description": "Desc",
            }
        ]

        events = self.persistence.load_events()

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].id, "event-1")
        self.assertEqual(events[0].color_key, "Niebieski")
        self.assertIsNotNone(events[0].start.tzinfo)

    def test_cleanup_calls_supabase(self):
        now = datetime(2025, 1, 1, 0, 0, tzinfo=WARSAW_TZ)
        self.persistence.cleanup(
            soft_delete_before=now - timedelta(days=1),
            hard_delete_older_than=now - timedelta(days=30),
        )

        self.assertEqual(len(self.supabase.soft_deleted_past), 1)
        self.assertEqual(len(self.supabase.hard_deleted_old), 1)


if __name__ == "__main__":
    _print_suite_overview()
    unittest.main(verbosity=2)
