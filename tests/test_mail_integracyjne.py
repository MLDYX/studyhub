"""
Testy integracyjne dla modułu poczty (core.mail).
"""

import unittest
import sys
import os
import tempfile
import asyncio

from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.mail import (
    BaseMailProvider,
    EmailClient,
    EmailMessageSummary,
    ImapProvider,
    TokenStorage,
)


class FakeProvider(BaseMailProvider):
    provider_id = "fake"
    display_name = "Fake"

    def __init__(self, storage: TokenStorage) -> None:
        super().__init__(storage)
        self.active_folder = None
        self.sent_messages = []
        self.cached = [EmailMessageSummary("msg-1", "Subject", "Sender", "Snippet")]

    async def authenticate(self) -> bool:
        return True

    async def fetch_messages(self, force: bool = False):
        return list(self.cached)

    async def fetch_message_body(self, message_id: str) -> str:
        return f"Body for {message_id}"

    async def send_message(self, to, subject: str, body: str) -> None:
        self.sent_messages.append((list(to), subject, body))

    def set_active_folder(self, folder_id: str) -> None:
        self.active_folder = folder_id

    def cached_messages(self):
        return list(self.cached)


class OkTestCase(unittest.TestCase):
    def run(self, result=None):
        result = super().run(result)
        failures = [test for test, _ in result.failures]
        errors = [test for test, _ in result.errors]
        skipped = [test for test, _ in result.skipped]
        if self not in failures and self not in errors and self not in skipped:
            print(f"{self.id()} ... ok")
        return result


class Test1_TokenStorageRoundtrip(OkTestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.token_path = Path(self.temp_dir.name) / "tokens.json"
        self.storage = TokenStorage(self.token_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_save_load_clear(self):
        self.storage.save("gmail", {"token": "abc"})
        self.assertEqual(self.storage.load("gmail"), {"token": "abc"})

        self.storage.clear("gmail")
        self.assertEqual(self.storage.load("gmail"), {})


class Test2_ImapConfigNormalization(OkTestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.token_path = Path(self.temp_dir.name) / "imap_tokens.json"
        self.storage = TokenStorage(self.token_path)
        self.provider = ImapProvider(self.storage)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_update_config_normalizes_ports_and_folders(self):
        payload = {
            "imap_host": "imap.example.com",
            "imap_port": 993,
            "imap_ssl": False,
            "imap_starttls": True,
            "smtp_host": "smtp.example.com",
            "smtp_port": 465,
            "smtp_ssl": False,
            "smtp_starttls": True,
            "username": "user@example.com",
            "password": "secret",
            "folder_map": {"spam": "SpamFolder"},
        }

        self.provider.update_config(payload)
        config = self.provider.get_config(include_secret=True)

        self.assertEqual(config["imap_port"], 143)
        self.assertEqual(config["smtp_port"], 587)
        self.assertEqual(config["folder_map"]["spam"], "SpamFolder")
        self.assertEqual(config["password"], "secret")

    def test_update_config_requires_password(self):
        payload = {
            "imap_host": "imap.example.com",
            "smtp_host": "smtp.example.com",
            "username": "user@example.com",
        }

        with self.assertRaises(ValueError):
            self.provider.update_config(payload)


class Test3_ImapMessageId(OkTestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.token_path = Path(self.temp_dir.name) / "imap_tokens.json"
        self.storage = TokenStorage(self.token_path)
        self.provider = ImapProvider(self.storage)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_compose_and_parse_message_id(self):
        message_id = self.provider._compose_message_id("INBOX", "123")
        folder, uid = self.provider._parse_message_identity(message_id)
        self.assertEqual(folder, "INBOX")
        self.assertEqual(uid, "123")

    def test_parse_invalid_message_id(self):
        with self.assertRaises(ValueError):
            self.provider._parse_message_identity("invalid")


class Test4_EmailClientFlow(OkTestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.token_path = Path(self.temp_dir.name) / "client_tokens.json"
        self.storage = TokenStorage(self.token_path)
        self.client = EmailClient()
        self.fake_provider = FakeProvider(self.storage)
        self.client.providers = {"fake": self.fake_provider}

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_provider_and_folder_switch(self):
        self.client.set_provider("fake")
        self.client.set_folder("sent")

        self.assertIs(self.client.current_provider, self.fake_provider)
        self.assertEqual(self.fake_provider.active_folder, "sent")

    def test_fetch_and_send(self):
        self.client.set_provider("fake")
        messages = asyncio.run(self.client.fetch_messages())
        self.assertEqual(len(messages), 1)

        asyncio.run(self.client.send(["a@example.com"], "Hi", "Body"))
        self.assertEqual(len(self.fake_provider.sent_messages), 1)


def _print_suite_overview():
    lines = [
        "1. Token storage roundtrip",
        "2. IMAP config normalization",
        "3. IMAP message id compose/parse",
        "4. Email client provider flow",
        "-" * 62,
    ]
    print("\n".join(lines))


def load_tests(loader, tests, pattern):
    _print_suite_overview()
    return tests


if __name__ == "__main__":
    _print_suite_overview()
    unittest.main(verbosity=2)
