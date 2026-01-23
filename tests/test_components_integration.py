"""
Component integration tests across major modules.
"""

import asyncio
import os
import tempfile
import unittest

from datetime import datetime, timezone
from pathlib import Path

import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.calendar import CalendarStore
from data.calendar_persistence import CalendarPersistence
from data.credentials import CredentialsStore, UserCredentials
from data.auth_service import AuthService
from core.mail import BaseMailProvider, EmailClient, EmailMessageSummary, TokenStorage
import core.notes as notes


class FakeSupabase:
    def __init__(self):
        self.created = []
        self.rows = []

    def login_or_register_username_password(self, username, password):
        return UserCredentials(
            user_id="user-1",
            secret_token="token",
            username=username,
            last_login_iso=datetime.now(timezone.utc).isoformat(),
        )

    def create_calendar_event(self, **kwargs):
        self.created.append(kwargs)

    def list_calendar_events(self, user_id):
        return list(self.rows)


class FakeMailProvider(BaseMailProvider):
    provider_id = "fake"
    display_name = "Fake"

    def __init__(self, storage):
        super().__init__(storage)
        self.messages = [EmailMessageSummary("msg-1", "Subject", "Sender", "Snippet")]
        self.sent = []
        self.active_folder = "inbox"

    async def authenticate(self):
        return True

    async def fetch_messages(self, force=False):
        return list(self.messages)

    async def fetch_message_body(self, message_id):
        return f"Body for {message_id}"

    async def send_message(self, to, subject, body):
        self.sent.append((list(to), subject, body))

    def set_active_folder(self, folder_id):
        self.active_folder = folder_id

    def cached_messages(self):
        return list(self.messages)


class TestAuthServiceComponent(unittest.TestCase):
    def test_login_saves_credentials(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = CredentialsStore(Path(tmp) / "creds.json")
            supabase = FakeSupabase()
            service = AuthService(supabase, store=store)

            result = service.login_or_register("user", "pass")

            self.assertEqual(result.credentials.username, "user")
            loaded = store.load()
            self.assertIsNotNone(loaded, "CredentialsStore should persist credentials")
            self.assertEqual(loaded.user_id, "user-1")


class TestCalendarComponent(unittest.TestCase):
    def test_calendar_store_persists_and_loads(self):
        supabase = FakeSupabase()
        user = UserCredentials(
            user_id="user-1",
            secret_token="token",
            username="user",
            last_login_iso=datetime.now(timezone.utc).isoformat(),
        )
        persistence = CalendarPersistence(supabase, user)
        store = CalendarStore(persistence=persistence)

        start = datetime(2025, 1, 1, 9, 0, tzinfo=timezone.utc)
        end = datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc)
        store.add_event("Meeting", start, end, "Niebieski")

        self.assertEqual(len(supabase.created), 1, "CalendarPersistence should call supabase")

        supabase.rows = [
            {
                "id": "event-1",
                "title": "Loaded",
                "starts_at": start.isoformat(),
                "ends_at": end.isoformat(),
                "color_key": "",
                "description": "",
            }
        ]
        loaded = persistence.load_events()
        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0].title, "Loaded")


class TestMailComponent(unittest.TestCase):
    def test_email_client_flow(self):
        with tempfile.TemporaryDirectory() as tmp:
            storage = TokenStorage(Path(tmp) / "tokens.json")
            provider = FakeMailProvider(storage)
            client = EmailClient()
            client.providers = {"fake": provider}

            client.set_provider("fake")
            client.set_folder("sent")
            self.assertEqual(provider.active_folder, "sent")

            messages = asyncio.run(client.fetch_messages())
            self.assertEqual(len(messages), 1)

            asyncio.run(client.send(["a@b.pl"], "Hi", "Body"))
            self.assertEqual(len(provider.sent), 1)


class TestNotesComponent(unittest.TestCase):
    def test_notes_favorites_flow(self):
        with tempfile.TemporaryDirectory() as tmp:
            notes.NOTES_DIR = os.path.join(tmp, "notes")
            notes.FAVORITES_PATH = os.path.join(tmp, "favorites.json")
            os.makedirs(notes.NOTES_DIR, exist_ok=True)

            folder = "Folder"
            src = Path(tmp) / "note.txt"
            src.write_text("note", encoding="utf-8")

            result_path = notes.add_existing_note_file(folder, str(src))
            added = notes.toggle_favorite(result_path)

            self.assertTrue(added)
            favs = notes.get_favorites_in_folder(folder)
            self.assertIn(result_path, favs)


if __name__ == "__main__":
    unittest.main(verbosity=2)
