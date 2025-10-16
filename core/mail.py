from __future__ import annotations

import asyncio
import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from google.auth.transport.requests import Request  # type: ignore
from msal import ConfidentialClientApplication  # type: ignore
from imap_tools import MailBox  # type: ignore
import aiosmtplib  # type: ignore

TOKEN_FILE = Path.home() / ".studyhub_mail_tokens.json"


@dataclass
class EmailMessageSummary:

    message_id: str
    subject: str
    sender: str
    snippet: str = ""


class TokenStorage:

    def __init__(self, path: Path = TOKEN_FILE) -> None:
        self.path = path

    def load_all(self) -> Dict[str, Dict[str, str]]:
        if not self.path.exists():
            return {}
        try:
            with self.path.open("r", encoding="utf-8") as handle:
                return json.load(handle)
        except json.JSONDecodeError:
            return {}

    def save_all(self, payload: Dict[str, Dict[str, str]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)

    def load(self, provider_id: str) -> Dict[str, str]:
        return self.load_all().get(provider_id, {})

    def save(self, provider_id: str, tokens: Dict[str, str]) -> None:
        data = self.load_all()
        data[provider_id] = tokens
        self.save_all(data)

    def clear(self, provider_id: str) -> None:
        data = self.load_all()
        if provider_id in data:
            del data[provider_id]
            self.save_all(data)


class BaseMailProvider:

    provider_id: str = "base"
    display_name: str = "Base"

    def __init__(self, storage: TokenStorage) -> None:
        self.storage = storage
        self.tokens: Dict[str, str] = storage.load(self.provider_id)

    async def authenticate(self) -> bool:
        raise NotImplementedError

    async def fetch_messages(self) -> List[EmailMessageSummary]:
        return []

    async def fetch_message_body(self, message_id: str) -> str:
        return ""

    async def send_message(self, to: Iterable[str], subject: str, body: str) -> None:
        raise NotImplementedError

    def _store_tokens(self, tokens: Dict[str, str]) -> None:
        self.tokens = tokens
        self.storage.save(self.provider_id, tokens)


class GmailProvider(BaseMailProvider):
    provider_id = "gmail"
    display_name = "Gmail"

    async def authenticate(self) -> bool:
        # Placeholder for OAuth flow; would use google_auth_oauthlib in production.
        self._store_tokens({"access_token": "demo", "refresh_token": "demo"})
        return True

    async def fetch_messages(self) -> List[EmailMessageSummary]:
        # Replace with Gmail API calls. Demo returns static data.
        return [
            EmailMessageSummary("gmail-1", "Przykładowa wiadomość", "noreply@gmail.com", "Demo snippet"),
            EmailMessageSummary("gmail-2", "Inne powiadomienie", "info@gmail.com", "Kolejne demo"),
        ]

    async def fetch_message_body(self, message_id: str) -> str:
        return (
            "<h3>Przykładowa treść</h3><p>Tu pojawi się zawartość wiadomości Gmail o ID"
            f" <b>{message_id}</b>.</p>"
        )

    async def send_message(self, to: Iterable[str], subject: str, body: str) -> None:
        # Demo wysyłki – w prawdziwej integracji należy użyć Gmail API.
        await asyncio.sleep(0)


class MicrosoftProvider(BaseMailProvider):
    provider_id = "microsoft"
    display_name = "Microsoft 365 / Outlook"

    async def authenticate(self) -> bool:
        # Placeholder for MSAL flow.
        self._store_tokens({"access_token": "demo"})
        return True

    async def fetch_messages(self) -> List[EmailMessageSummary]:
        return [
            EmailMessageSummary("ms-1", "Spotkanie zespołu", "manager@contoso.com", "Agenda spotkania"),
            EmailMessageSummary("ms-2", "Plan urlopów", "hr@contoso.com", "Szczegóły planu"),
        ]

    async def fetch_message_body(self, message_id: str) -> str:
        return (
            "<h3>Microsoft Graph demo</h3><p>To jest przykładowa wiadomość o ID"
            f" <b>{message_id}</b>.</p>"
        )

    async def send_message(self, to: Iterable[str], subject: str, body: str) -> None:
        await asyncio.sleep(0)


class ImapProvider(BaseMailProvider):
    provider_id = "imap"
    display_name = "Inny (IMAP/SMTP)"

    async def authenticate(self) -> bool:
        # In production ask for credentials; for prototype store placeholder access.
        self._store_tokens({"host": "imap.example.com", "username": "demo"})
        return True

    async def fetch_messages(self) -> List[EmailMessageSummary]:
        return [
            EmailMessageSummary("imap-1", "Powitanie", "support@example.com", "Serdecznie witamy!"),
        ]

    async def fetch_message_body(self, message_id: str) -> str:
        return (
            "<p>Podgląd wiadomości IMAP o identyfikatorze <b>"
            f"{message_id}</b>. Implementacja produkcyjna pobierze treść z serwera.</p>"
        )

    async def send_message(self, to: Iterable[str], subject: str, body: str) -> None:
        await asyncio.sleep(0)


class EmailClient:

    def __init__(self) -> None:
        self.storage = TokenStorage()
        self.providers: Dict[str, BaseMailProvider] = {
            GmailProvider.provider_id: GmailProvider(self.storage),
            MicrosoftProvider.provider_id: MicrosoftProvider(self.storage),
            ImapProvider.provider_id: ImapProvider(self.storage),
        }
        self.current_provider: Optional[BaseMailProvider] = None

    def provider_choices(self) -> List[Tuple[str, str]]:
        return [(key, provider.display_name) for key, provider in self.providers.items()]

    def set_provider(self, provider_id: str) -> None:
        self.current_provider = self.providers.get(provider_id)

    async def authenticate(self) -> bool:
        if self.current_provider is None:
            raise RuntimeError("Provider not selected")
        return await self.current_provider.authenticate()

    async def fetch_messages(self) -> List[EmailMessageSummary]:
        if self.current_provider is None:
            return []
        return await self.current_provider.fetch_messages()

    async def fetch_body(self, message_id: str) -> str:
        if self.current_provider is None:
            return ""
        return await self.current_provider.fetch_message_body(message_id)

    async def send(self, to: Iterable[str], subject: str, body: str) -> None:
        if self.current_provider is None:
            raise RuntimeError("Provider not selected")
        await self.current_provider.send_message(to, subject, body)
