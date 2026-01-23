from __future__ import annotations

import asyncio
import base64
import contextlib
import html
import json
import logging
import os
import re
import smtplib
import ssl
import textwrap
import time
import threading
from email.message import EmailMessage
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from google.auth.transport.requests import Request  # type: ignore
from google.oauth2.credentials import Credentials  # type: ignore
from google_auth_oauthlib.flow import InstalledAppFlow  # type: ignore
from googleapiclient.discovery import build  # type: ignore
from googleapiclient.errors import HttpError  # type: ignore
from msal import ConfidentialClientApplication, PublicClientApplication, SerializableTokenCache  # type: ignore
from imap_tools import AND, MailBox  # type: ignore
import requests  # type: ignore

ENV_DIR = Path(__file__).resolve().parent.parent / ".env"
TOKEN_FILE = ENV_DIR / "studyhub_mail_tokens.json"
GOOGLE_CLIENT_SECRET_ENV = "STUDYHUB_GOOGLE_CLIENT_SECRET"
DEFAULT_GOOGLE_CLIENT_SECRET = ENV_DIR / "google_client_secret.json"
GMAIL_MAX_RESULTS = 9

MICROSOFT_CLIENT_CONFIG_ENV = "STUDYHUB_MICROSOFT_CONFIG"
DEFAULT_MICROSOFT_CONFIG = ENV_DIR / "microsoft_client.json"
GRAPH_BASE_URL = "https://graph.microsoft.com/v1.0"
OUTLOOK_MAX_RESULTS = 9
IMAP_MAX_RESULTS = 9

logger = logging.getLogger(__name__)


@dataclass
class EmailMessageSummary:
    message_id: str
    subject: str
    sender: str
    snippet: str = ""


@dataclass
class EmailAttachment:
    """Represents an email attachment."""
    attachment_id: str
    filename: str
    mime_type: str
    size: int = 0  # in bytes


class TokenStorage:
    def __init__(self, path: Path = TOKEN_FILE) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def load_all(self) -> Dict[str, Dict[str, str]]:
        if not self.path.exists():
            return {}
        with self._lock:
            try:
                with self.path.open("r", encoding="utf-8") as handle:
                    return json.load(handle)
            except json.JSONDecodeError:
                return {}

    def save_all(self, payload: Dict[str, Dict[str, str]]) -> None:
        with self._lock:
            temp_path = self.path.with_suffix(".tmp")
            with temp_path.open("w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2)
            temp_path.replace(self.path)

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

    async def fetch_messages(self, force: bool = False) -> List[EmailMessageSummary]:
        return []

    async def fetch_message_body(self, message_id: str) -> str:
        return ""

    async def fetch_attachments(self, message_id: str) -> List[EmailAttachment]:
        """Fetch list of attachments for a message."""
        return []

    async def download_attachment(self, message_id: str, attachment_id: str) -> bytes:
        """Download attachment content."""
        return b""

    async def send_message(self, to: Iterable[str], subject: str, body: str) -> None:
        raise NotImplementedError

    def set_active_folder(self, folder_id: str) -> None:
        """Allow providers to adjust behavior for selected folder."""
        return None

    def _store_tokens(self, tokens: Dict[str, str]) -> None:
        self.tokens = tokens
        self.storage.save(self.provider_id, tokens)

    def _update_token_entries(self, entries: Dict[str, str]) -> None:
        data = dict(self.tokens)
        data.update(entries)
        self._store_tokens(data)

    def _remove_token_entry(self, key: str) -> None:
        data = dict(self.tokens)
        if key in data:
            del data[key]
            self._store_tokens(data)

    def cached_messages(self) -> List[EmailMessageSummary]:
        return []


class GmailProvider(BaseMailProvider):
    provider_id = "gmail"
    display_name = "Gmail"

    SCOPES = [
        "https://www.googleapis.com/auth/gmail.modify",
        "https://www.googleapis.com/auth/gmail.send",
    ]

    _FOLDER_LABELS = {
        "inbox": ["INBOX"],
        "sent": ["SENT"],
        "drafts": ["DRAFT"],
        "spam": ["SPAM"],
        "trash": ["TRASH"],
    }

    def __init__(self, storage: TokenStorage) -> None:
        super().__init__(storage)
        self._credentials: Credentials | None = None
        self._service = None
        self._active_folder: str = "inbox"
        self._body_cache: Dict[str, str] = {}
        self._messages_cache: Dict[str, Tuple[float, List[EmailMessageSummary]]] = (
            self._load_message_cache()
        )
        self._cache_ttl = 60.0

    def set_active_folder(self, folder_id: str) -> None:
        target = folder_id if folder_id in self._FOLDER_LABELS else "inbox"
        if target != self._active_folder:
            self._active_folder = target
            self._body_cache.clear()
        else:
            self._active_folder = target

    async def authenticate(self) -> bool:
        credentials = await asyncio.to_thread(self._ensure_credentials)
        return credentials is not None

    async def fetch_messages(self, force: bool = False) -> List[EmailMessageSummary]:
        return await asyncio.to_thread(self._fetch_messages_sync, force)

    async def fetch_message_body(self, message_id: str) -> str:
        return await asyncio.to_thread(self._fetch_message_body_sync, message_id)

    async def send_message(self, to: Iterable[str], subject: str, body: str) -> None:
        await asyncio.to_thread(self._send_message_sync, to, subject, body)

    # --- internal helpers -------------------------------------------------
    def _ensure_credentials(self) -> Credentials | None:
        credentials = self._credentials or self._load_credentials_from_storage()
        if credentials is None:
            credentials = self._run_desktop_oauth_flow()
        if credentials is None:
            return None
        if credentials.expired and credentials.refresh_token:
            try:
                credentials.refresh(Request())
                self._store_credentials(credentials)
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning("Failed to refresh Gmail token: %s", exc)
                self.storage.clear(self.provider_id)
                return None
        self._credentials = credentials
        return credentials

    def _load_credentials_from_storage(self) -> Credentials | None:
        serialized = self.tokens.get("credentials")
        if not isinstance(serialized, str):
            return None
        try:
            payload = json.loads(serialized)
            return Credentials.from_authorized_user_info(payload, scopes=self.SCOPES)
        except Exception as exc:  # pragma: no cover - defensive
            logger.debug("Stored Gmail credentials invalid: %s", exc)
            return None

    def _store_credentials(self, credentials: Credentials) -> None:
        serialized = credentials.to_json()
        self._update_token_entries({"credentials": serialized})

    def _run_desktop_oauth_flow(self) -> Credentials | None:
        client_secret = self._locate_client_secret_file()
        if client_secret is None:
            raise RuntimeError(
                "Brak pliku client_secret.json Google. Umiesc plik w "
                f"{DEFAULT_GOOGLE_CLIENT_SECRET} lub ustaw zmienna {GOOGLE_CLIENT_SECRET_ENV}."
            )
        flow = InstalledAppFlow.from_client_secrets_file(str(client_secret), scopes=self.SCOPES)
        credentials = flow.run_local_server(
            port=0,
            prompt="consent",
            authorization_prompt_message="",
            success_message="Logowanie do Gmail zakonczone. Mozesz zamknac okno przegladarki.",
        )
        self._store_credentials(credentials)
        return credentials

    def _locate_client_secret_file(self) -> Path | None:
        env_value = os.getenv(GOOGLE_CLIENT_SECRET_ENV, "").strip()
        if env_value:
            candidate = Path(env_value).expanduser()
            if candidate.exists():
                return candidate
        if DEFAULT_GOOGLE_CLIENT_SECRET.exists():
            return DEFAULT_GOOGLE_CLIENT_SECRET
        return None

    def _get_service(self):
        credentials = self._ensure_credentials()
        if credentials is None:
            raise RuntimeError("Brak autoryzacji do Gmail.")
        if self._service is None:
            self._service = build("gmail", "v1", credentials=credentials, cache_discovery=False)
        return self._service

    def _folder_labels(self) -> List[str]:
        return self._FOLDER_LABELS.get(self._active_folder, ["INBOX"])

    def cached_messages(self) -> List[EmailMessageSummary]:
        cache = self._messages_cache.get(self._active_folder)
        if not cache:
            return []
        timestamp, messages = cache
        if time.time() - timestamp > self._cache_ttl:
            return []
        return list(messages)

    def _fetch_messages_sync(self, force: bool = False) -> List[EmailMessageSummary]:
        cache = self._messages_cache.get(self._active_folder)
        now = time.time()
        if cache and not force and now - cache[0] < self._cache_ttl:
            return list(cache[1])
        service = self._get_service()
        try:
            response = (
                service.users()
                .messages()
                .list(
                    userId="me",
                    labelIds=self._folder_labels(),
                    maxResults=GMAIL_MAX_RESULTS,
                    fields="messages/id,nextPageToken",
                )
                .execute()
            )
        except HttpError as exc:
            raise RuntimeError(f"Blad Gmail API: {exc}") from exc

        message_ids: List[str] = []
        for item in response.get("messages", []):
            message_id = item.get("id")
            if not message_id:
                continue
            message_ids.append(str(message_id))

        if not message_ids:
            return []

        fetched: Dict[str, Dict[str, Any]] = {}
        errors: Dict[str, Exception] = {}

        def _callback(request_id: str, result: Any, exception: Exception | None) -> None:
            if exception is not None:
                errors[request_id] = exception
                return
            if isinstance(result, dict):
                fetched[request_id] = result

        batch = service.new_batch_http_request(callback=_callback)
        for message_id in message_ids:
            request = (
                service.users()
                .messages()
                .get(
                    userId="me",
                    id=message_id,
                    format="metadata",
                    metadataHeaders=["Subject", "From"],
                    fields="id,snippet,payload/headers",
                )
            )
            batch.add(request, request_id=message_id)

        try:
            batch.execute()
        except HttpError as exc:
            raise RuntimeError(f"Blad Gmail API: {exc}") from exc

        summaries: List[EmailMessageSummary] = []
        for message_id in message_ids:
            message = fetched.get(message_id)
            if message is None:
                error = errors.get(message_id)
                if error is not None:
                    logger.warning("Gmail: nie udalo sie pobrac naglowka %s: %s", message_id, error)
                continue
            summaries.append(self._build_summary_from_metadata(message))
        self._messages_cache[self._active_folder] = (time.time(), summaries)
        self._persist_message_cache()
        return summaries

    def _build_summary_from_metadata(self, message: Dict[str, Any]) -> EmailMessageSummary:
        headers_list: List[Dict[str, Any]] = []
        payload = message.get("payload")
        if isinstance(payload, dict):
            candidate = payload.get("headers")
            if isinstance(candidate, list):
                headers_list = [entry for entry in candidate if isinstance(entry, dict)]
        headers: Dict[str, str] = {}
        for entry in headers_list:
            name = str(entry.get("name", "")).lower()
            value = str(entry.get("value", ""))
            if name:
                headers[name] = value
        subject = headers.get("subject", "")
        sender = headers.get("from", "")
        snippet = str(message.get("snippet", ""))
        message_id = str(message.get("id", ""))
        return EmailMessageSummary(message_id, subject, sender, snippet)

    def _fetch_message_body_sync(self, message_id: str) -> str:
        cached = self._body_cache.get(message_id)
        if cached is not None:
            return cached

        service = self._get_service()
        try:
            message = (
                service.users().messages().get(userId="me", id=message_id, format="full").execute()
            )
        except HttpError as exc:
            raise RuntimeError(f"Blad pobierania tresci Gmail: {exc}") from exc
        payload = message.get("payload")
        if not isinstance(payload, dict):
            result = "<p>(Brak tresci wiadomosci)</p>"
            self._body_cache[message_id] = result
            return result
        body = self._extract_body(payload) or "<p>(Brak tresci wiadomosci)</p>"
        self._body_cache[message_id] = body
        return body

    def _send_message_sync(self, to: Iterable[str], subject: str, body: str) -> None:
        recipients = [addr.strip() for addr in to if addr.strip()]
        if not recipients:
            raise ValueError("Nie podano adresatow.")
        message = EmailMessage()
        message["To"] = ", ".join(recipients)
        message["Subject"] = subject
        message.set_content(body or "")
        if body:
            message.add_alternative(body, subtype="html")
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
        service = self._get_service()
        try:
            service.users().messages().send(userId="me", body={"raw": raw}).execute()
        except HttpError as exc:
            raise RuntimeError(f"Nie udalo sie wyslac wiadomosci: {exc}") from exc
        self._messages_cache.pop(self._active_folder, None)
        self._messages_cache.pop("sent", None)
        self._persist_message_cache()

    def _extract_body(self, payload: Dict[str, Any]) -> str:
        html_parts: List[str] = []
        text_parts: List[str] = []
        stack: List[Dict[str, Any]] = [payload]
        while stack:
            part = stack.pop()
            mime_type = str(part.get("mimeType", ""))
            body = part.get("body")
            data = None
            if isinstance(body, dict):
                data = body.get("data")
            if isinstance(data, str) and data:
                try:
                    decoded = base64.urlsafe_b64decode(data.encode("utf-8")).decode(
                        "utf-8", errors="replace"
                    )
                except Exception as exc:  # pragma: no cover - defensive
                    logger.debug("Gmail body decode failed: %s", exc)
                    decoded = ""
                if mime_type == "text/html":
                    html_parts.append(decoded)
                elif mime_type == "text/plain":
                    text_parts.append(decoded)
            parts = part.get("parts")
            if isinstance(parts, list):
                for sub in parts:
                    if isinstance(sub, dict):
                        stack.append(sub)
        if html_parts:
            return "\n".join(html_parts)
        if text_parts:
            escaped = html.escape("\n".join(text_parts))
            return f"<pre>{escaped}</pre>"
        return ""

    def _extract_attachments(self, payload: Dict[str, Any]) -> List[EmailAttachment]:
        """Extract attachment metadata from message payload."""
        attachments: List[EmailAttachment] = []
        stack: List[Dict[str, Any]] = [payload]
        while stack:
            part = stack.pop()
            filename = part.get("filename", "")
            body = part.get("body", {})
            attachment_id = body.get("attachmentId") if isinstance(body, dict) else None
            if filename and attachment_id:
                mime_type = str(part.get("mimeType", "application/octet-stream"))
                size = int(body.get("size", 0)) if isinstance(body, dict) else 0
                attachments.append(EmailAttachment(
                    attachment_id=attachment_id,
                    filename=filename,
                    mime_type=mime_type,
                    size=size,
                ))
            parts = part.get("parts")
            if isinstance(parts, list):
                for sub in parts:
                    if isinstance(sub, dict):
                        stack.append(sub)
        return attachments

    async def fetch_attachments(self, message_id: str) -> List[EmailAttachment]:
        """Fetch list of attachments for a message."""
        return await asyncio.to_thread(self._fetch_attachments_sync, message_id)

    def _fetch_attachments_sync(self, message_id: str) -> List[EmailAttachment]:
        service = self._get_service()
        try:
            message = (
                service.users().messages().get(userId="me", id=message_id, format="full").execute()
            )
        except HttpError as exc:
            raise RuntimeError(f"Blad pobierania zalacznikow Gmail: {exc}") from exc
        payload = message.get("payload")
        if not isinstance(payload, dict):
            return []
        return self._extract_attachments(payload)

    async def download_attachment(self, message_id: str, attachment_id: str) -> bytes:
        """Download attachment content."""
        return await asyncio.to_thread(self._download_attachment_sync, message_id, attachment_id)

    def _download_attachment_sync(self, message_id: str, attachment_id: str) -> bytes:
        service = self._get_service()
        try:
            attachment = (
                service.users()
                .messages()
                .attachments()
                .get(userId="me", messageId=message_id, id=attachment_id)
                .execute()
            )
        except HttpError as exc:
            raise RuntimeError(f"Blad pobierania zalacznika: {exc}") from exc
        data = attachment.get("data", "")
        if not data:
            return b""
        return base64.urlsafe_b64decode(data.encode("utf-8"))

    def _load_message_cache(self) -> Dict[str, Tuple[float, List[EmailMessageSummary]]]:
        raw = self.tokens.get("message_cache")
        if not isinstance(raw, str) or not raw:
            return {}
        try:
            payload = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return {}
        cache: Dict[str, Tuple[float, List[EmailMessageSummary]]] = {}
        if isinstance(payload, dict):
            for folder, entry in payload.items():
                if not isinstance(entry, dict):
                    continue
                if folder not in self._FOLDER_LABELS:
                    continue
                timestamp = entry.get("timestamp")
                messages_raw = entry.get("messages", [])
                if not isinstance(timestamp, (int, float)):
                    continue
                messages: List[EmailMessageSummary] = []
                if isinstance(messages_raw, list):
                    for item in messages_raw:
                        if not isinstance(item, dict):
                            continue
                        message_id = str(item.get("message_id", "") or "")
                        subject = str(item.get("subject", "") or "")
                        sender = str(item.get("sender", "") or "")
                        snippet = str(item.get("snippet", "") or "")
                        if message_id:
                            messages.append(
                                EmailMessageSummary(message_id, subject, sender, snippet)
                            )
                cache[str(folder)] = (float(timestamp), messages)
        return cache

    def _persist_message_cache(self) -> None:
        if not self._messages_cache:
            self._remove_token_entry("message_cache")
            return
        payload: Dict[str, Any] = {}
        for folder, (timestamp, messages) in self._messages_cache.items():
            if folder not in self._FOLDER_LABELS:
                continue
            payload[folder] = {
                "timestamp": timestamp,
                "messages": [asdict(message) for message in messages],
            }
        if not payload:
            self._remove_token_entry("message_cache")
            return
        self._update_token_entries({"message_cache": json.dumps(payload)})


class MicrosoftProvider(BaseMailProvider):
    provider_id = "microsoft"
    display_name = "Microsoft 365 / Outlook"

    SCOPES = [
        "User.Read",
        "offline_access",
        "Mail.Read",
        "Mail.ReadWrite",
        "Mail.Send",
    ]

    _FOLDER_TARGETS = {
        "inbox": "inbox",
        "sent": "sentitems",
        "drafts": "drafts",
        "spam": "junkemail",
        "trash": "deleteditems",
    }

    def __init__(self, storage: TokenStorage) -> None:
        super().__init__(storage)
        self._active_folder: str = "inbox"
        self._body_cache: Dict[str, str] = {}
        self._token_cache = SerializableTokenCache()
        self._messages_cache: Dict[str, Tuple[float, List[EmailMessageSummary]]] = (
            self._load_message_cache()
        )
        self._cache_ttl = 60.0
        raw_cache = self.tokens.get("token_cache")
        if isinstance(raw_cache, str) and raw_cache:
            try:
                self._token_cache.deserialize(raw_cache)
            except Exception as exc:  # pragma: no cover - defensive
                logger.debug("Microsoft cache deserialize failed: %s", exc)
        self._account_id: str = str(self.tokens.get("account_id", "") or "")
        self._config = self._load_config()
        self._app: Optional[PublicClientApplication] = None
        if self._config:
            self._app = self._build_app(self._config)

    def set_active_folder(self, folder_id: str) -> None:
        target = self._FOLDER_TARGETS.get(folder_id, "inbox")
        if target != self._active_folder:
            self._body_cache.clear()
            self._active_folder = target
        else:
            self._active_folder = target

    async def authenticate(self) -> bool:
        tokens = await asyncio.to_thread(self._ensure_token)
        return bool(tokens)

    async def fetch_messages(self, force: bool = False) -> List[EmailMessageSummary]:
        return await asyncio.to_thread(self._fetch_messages_sync, force)

    async def fetch_message_body(self, message_id: str) -> str:
        return await asyncio.to_thread(self._fetch_message_body_sync, message_id)

    async def send_message(self, to: Iterable[str], subject: str, body: str) -> None:
        await asyncio.to_thread(self._send_message_sync, to, subject, body)

    # --- configuration & auth -------------------------------------------
    def is_configured(self) -> bool:
        return bool(self._config.get("client_id"))

    def _load_config(self) -> Dict[str, str]:
        env_path = os.getenv(MICROSOFT_CLIENT_CONFIG_ENV, "").strip()
        candidates: List[Path] = []
        if env_path:
            candidates.append(Path(env_path).expanduser())
        candidates.append(DEFAULT_MICROSOFT_CONFIG)
        for candidate in candidates:
            if candidate.exists():
                try:
                    with candidate.open("r", encoding="utf-8") as handle:
                        payload = json.load(handle)
                    client_id = str(payload.get("client_id", "")).strip()
                    tenant = str(payload.get("tenant", "common") or "common").strip()
                    redirect_uri = str(payload.get("redirect_uri", "") or "").strip()
                    if not client_id:
                        raise ValueError("client_id missing")
                    return {"client_id": client_id, "tenant": tenant, "redirect_uri": redirect_uri}
                except Exception as exc:  # pragma: no cover - defensive
                    logger.warning("Microsoft config load failed from %s: %s", candidate, exc)
        return {}

    def _build_app(self, config: Dict[str, str]) -> PublicClientApplication:
        authority = f"https://login.microsoftonline.com/{config.get('tenant', 'common')}"
        return PublicClientApplication(
            config["client_id"],
            authority=authority,
            token_cache=self._token_cache,
        )

    def _ensure_app(self) -> PublicClientApplication:
        if self._app is None:
            if not self._config:
                self._config = self._load_config()
            if not self._config:
                raise RuntimeError(
                    "Brak konfiguracji Microsoft OAuth. Dodaj plik microsoft_client.json do katalogu .env "
                    f"lub ustaw zmienna {MICROSOFT_CLIENT_CONFIG_ENV}."
                )
            self._app = self._build_app(self._config)
        return self._app

    def _ensure_token(self) -> Dict[str, Any]:
        app = self._ensure_app()
        account = self._resolve_account(app)

        result: Optional[Dict[str, Any]] = None
        if account is not None:
            result = app.acquire_token_silent(self.SCOPES, account=account)

        if not result or "access_token" not in result:
            try:
                result = app.acquire_token_interactive(
                    scopes=self.SCOPES,
                    redirect_uri=self._config.get("redirect_uri") or "http://localhost",
                )
            except Exception as exc:  # pragma: no cover - defensive
                raise RuntimeError(f"Logowanie do Microsoft nie powiodlo sie: {exc}") from exc
            if "access_token" not in result:
                error_desc = (
                    result.get("error_description") or result.get("error") or "brak dostepu"
                )
                raise RuntimeError(f"Logowanie do Microsoft nie powiodlo sie: {error_desc}")
            account = self._resolve_account(app, refresh=True)

        if account is not None:
            self._account_id = str(account.get("home_account_id", "") or "")

        self._store_auth_state()
        return result or {}

    def _resolve_account(
        self,
        app: PublicClientApplication,
        *,
        refresh: bool = False,
    ) -> Optional[Dict[str, Any]]:
        accounts = app.get_accounts()
        if not accounts:
            return None
        if refresh or not self._account_id:
            return accounts[0]
        for account in accounts:
            if account.get("home_account_id") == self._account_id:
                return account
        return accounts[0]

    def _store_auth_state(self) -> None:
        payload = {
            "token_cache": self._token_cache.serialize(),
            "account_id": self._account_id,
        }
        self._update_token_entries(payload)

    def _get_access_token(self) -> str:
        tokens = self._ensure_token()
        access_token = tokens.get("access_token")
        if not access_token:
            raise RuntimeError("Brak tokenu dostepu Microsoft Graph.")
        return str(access_token)

    # --- Graph helpers ---------------------------------------------------
    def _graph_headers(self) -> Dict[str, str]:
        access_token = self._get_access_token()
        return {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
        }

    def _graph_request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[Dict[str, str]] = None,
        json_payload: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        url = f"{GRAPH_BASE_URL}/{path.lstrip('/')}"
        try:
            response = requests.request(
                method,
                url,
                headers=self._graph_headers(),
                params=params,
                json=json_payload,
                timeout=20,
            )
        except requests.RequestException as exc:
            raise RuntimeError(f"Blad komunikacji z Microsoft Graph: {exc}") from exc
        if response.status_code >= 400:
            try:
                error_payload = response.json()
                message = error_payload.get("error", {}).get(
                    "message", f"HTTP {response.status_code}"
                )
            except Exception:
                message = f"HTTP {response.status_code}"
            raise RuntimeError(f"Microsoft Graph zwrocil blad: {message}")
        try:
            return response.json()
        except ValueError as exc:
            raise RuntimeError(f"Niepoprawna odpowiedz Microsoft Graph: {exc}") from exc

    def _folder_target(self) -> str:
        return self._FOLDER_TARGETS.get(self._active_folder, "inbox")

    # --- message operations ----------------------------------------------
    def cached_messages(self) -> List[EmailMessageSummary]:
        cache = self._messages_cache.get(self._active_folder)
        if not cache:
            return []
        timestamp, messages = cache
        if time.time() - timestamp > self._cache_ttl:
            return []
        return list(messages)

    def _fetch_messages_sync(self, force: bool = False) -> List[EmailMessageSummary]:
        cache = self._messages_cache.get(self._active_folder)
        now = time.time()
        if cache and not force and now - cache[0] < self._cache_ttl:
            return list(cache[1])
        params = {
            "$top": str(OUTLOOK_MAX_RESULTS),
            "$select": "id,subject,from,bodyPreview,receivedDateTime",
            "$orderby": "receivedDateTime DESC",
        }
        data = self._graph_request(
            "GET",
            f"me/mailFolders/{self._folder_target()}/messages",
            params=params,
        )
        messages_raw = data.get("value", [])
        summaries: List[EmailMessageSummary] = []
        if isinstance(messages_raw, list):
            for item in messages_raw:
                if not isinstance(item, dict):
                    continue
                summaries.append(self._build_summary(item))
        self._messages_cache[self._active_folder] = (time.time(), summaries)
        self._persist_message_cache()
        return summaries

    def _build_summary(self, payload: Dict[str, Any]) -> EmailMessageSummary:
        message_id = str(payload.get("id", ""))
        subject = str(payload.get("subject", "") or "")
        sender_info = payload.get("from", {})
        sender = ""
        if isinstance(sender_info, dict):
            email_data = sender_info.get("emailAddress", {})
            if isinstance(email_data, dict):
                address = str(email_data.get("address", "") or "")
                name = str(email_data.get("name", "") or "")
                sender = f"{name} <{address}>" if name and address else address or name
        snippet = str(payload.get("bodyPreview", "") or "")
        return EmailMessageSummary(message_id, subject, sender, snippet)

    def _fetch_message_body_sync(self, message_id: str) -> str:
        cached = self._body_cache.get(message_id)
        if cached is not None:
            return cached
        params = {"$select": "body"}
        data = self._graph_request("GET", f"me/messages/{message_id}", params=params)
        body_payload = data.get("body", {})
        content = ""
        if isinstance(body_payload, dict):
            content = str(body_payload.get("content", "") or "")
            content_type = str(body_payload.get("contentType", "") or "").lower()
            if content_type == "text":
                content = f"<pre>{html.escape(content)}</pre>"
        content = content or "<p>(Brak tresci wiadomosci)</p>"
        self._body_cache[message_id] = content
        return content

    def _send_message_sync(self, to: Iterable[str], subject: str, body: str) -> None:
        recipients = [
            {"emailAddress": {"address": address.strip()}}
            for address in to
            if address and address.strip()
        ]
        if not recipients:
            raise ValueError("Nie podano adresatow.")
        payload = {
            "message": {
                "subject": subject,
                "body": {
                    "contentType": "HTML",
                    "content": body,
                },
                "toRecipients": recipients,
            },
            "saveToSentItems": True,
        }
        self._graph_request("POST", "me/sendMail", json_payload=payload)
        self._messages_cache.pop(self._active_folder, None)
        self._messages_cache.pop("sent", None)
        self._persist_message_cache()

    def _load_message_cache(self) -> Dict[str, Tuple[float, List[EmailMessageSummary]]]:
        raw = self.tokens.get("message_cache")
        if not isinstance(raw, str) or not raw:
            return {}
        try:
            payload = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return {}
        cache: Dict[str, Tuple[float, List[EmailMessageSummary]]] = {}
        if isinstance(payload, dict):
            for folder, entry in payload.items():
                if not isinstance(entry, dict):
                    continue
                timestamp = entry.get("timestamp")
                messages_raw = entry.get("messages", [])
                if not isinstance(timestamp, (int, float)):
                    continue
                messages: List[EmailMessageSummary] = []
                if isinstance(messages_raw, list):
                    for item in messages_raw:
                        if not isinstance(item, dict):
                            continue
                        message_id = str(item.get("message_id", "") or "")
                        subject = str(item.get("subject", "") or "")
                        sender = str(item.get("sender", "") or "")
                        snippet = str(item.get("snippet", "") or "")
                        if message_id:
                            messages.append(
                                EmailMessageSummary(message_id, subject, sender, snippet)
                            )
                cache[str(folder)] = (float(timestamp), messages)
        return cache

    def _persist_message_cache(self) -> None:
        if not self._messages_cache:
            self._remove_token_entry("message_cache")
            return
        payload: Dict[str, Any] = {}
        for folder, (timestamp, messages) in self._messages_cache.items():
            payload[folder] = {
                "timestamp": timestamp,
                "messages": [asdict(message) for message in messages],
            }
        if not payload:
            self._remove_token_entry("message_cache")
            return
        self._update_token_entries({"message_cache": json.dumps(payload)})


class ImapProvider(BaseMailProvider):
    provider_id = "imap"
    display_name = "Inny (IMAP/SMTP)"

    _DEFAULT_FOLDER_MAP = {
        "inbox": "INBOX",
        "sent": "Sent",
        "drafts": "Drafts",
        "spam": "Junk",
        "trash": "Trash",
    }

    def __init__(self, storage: TokenStorage) -> None:
        super().__init__(storage)
        self._active_folder: str = "inbox"
        self._body_cache: Dict[str, str] = {}
        self._messages_cache: Dict[str, Tuple[float, List[EmailMessageSummary]]] = (
            self._load_message_cache()
        )
        self._cache_ttl = 60.0
        self._config = self._load_config_from_tokens(self.tokens)

    def set_active_folder(self, folder_id: str) -> None:
        mapping = self._config.get("folder_map", {})
        target = mapping.get(folder_id) or self._DEFAULT_FOLDER_MAP.get(folder_id, "INBOX")
        if target != self._active_folder:
            self._body_cache.clear()
            self._active_folder = target
        else:
            self._active_folder = target

    async def authenticate(self) -> bool:
        await asyncio.to_thread(self._test_connections)
        return True

    async def fetch_messages(self, force: bool = False) -> List[EmailMessageSummary]:
        return await asyncio.to_thread(self._fetch_messages_sync, force)

    async def fetch_message_body(self, message_id: str) -> str:
        return await asyncio.to_thread(self._fetch_message_body_sync, message_id)

    async def send_message(self, to: Iterable[str], subject: str, body: str) -> None:
        await asyncio.to_thread(self._send_message_sync, to, subject, body)

    # --- public helpers --------------------------------------------------
    def is_configured(self) -> bool:
        cfg = self._config
        required = [
            cfg.get("imap_host"),
            cfg.get("smtp_host"),
            cfg.get("username"),
            cfg.get("password"),
        ]
        return all(item for item in required)

    def get_config(self, *, include_secret: bool = False) -> Dict[str, Any]:
        config_copy = json.loads(json.dumps(self._config))
        if not include_secret:
            config_copy["password"] = ""
        return config_copy

    def update_config(self, payload: Dict[str, Any]) -> None:
        normalized = self._normalize_config(payload, require_password=True)
        self._config = normalized
        self._body_cache.clear()
        self._messages_cache.clear()
        self._update_token_entries({"config": json.dumps(normalized)})
        self._persist_message_cache()

    # --- configuration ---------------------------------------------------
    def _load_config_from_tokens(self, tokens: Dict[str, str]) -> Dict[str, Any]:
        raw = tokens.get("config")
        if isinstance(raw, str) and raw:
            try:
                data = json.loads(raw)
                return self._normalize_config(data)
            except Exception as exc:  # pragma: no cover - defensive
                logger.debug("IMAP config parse failed: %s", exc)
        return self._normalize_config({})

    def _normalize_config(
        self, payload: Dict[str, Any], *, require_password: bool = False
    ) -> Dict[str, Any]:
        def _to_bool(value: Any) -> bool:
            if isinstance(value, bool):
                return value
            if isinstance(value, str):
                return value.strip().lower() in {"1", "true", "yes", "on"}
            return bool(value)

        def _to_int(value: Any, default: int) -> int:
            try:
                return int(value)
            except (TypeError, ValueError):
                return default

        folder_map_raw = payload.get("folder_map", {}) or {}
        folder_map: Dict[str, str] = {}
        if isinstance(folder_map_raw, dict):
            for key, value in folder_map_raw.items():
                key_str = str(key).strip().lower()
                if not key_str:
                    continue
                folder_map[key_str] = str(value or "").strip() or self._DEFAULT_FOLDER_MAP.get(
                    key_str, ""
                )

        config = {
            "imap_host": str(payload.get("imap_host", "") or "").strip(),
            "imap_port": _to_int(payload.get("imap_port", 993), 993),
            "imap_ssl": _to_bool(payload.get("imap_ssl", True)),
            "imap_starttls": _to_bool(payload.get("imap_starttls", False)),
            "smtp_host": str(payload.get("smtp_host", "") or "").strip(),
            "smtp_port": _to_int(payload.get("smtp_port", 465), 465),
            "smtp_ssl": _to_bool(payload.get("smtp_ssl", True)),
            "smtp_starttls": _to_bool(payload.get("smtp_starttls", False)),
            "username": str(payload.get("username", "") or "").strip(),
            "password": str(payload.get("password", "") or "").strip(),
            "folder_map": {**self._DEFAULT_FOLDER_MAP, **folder_map},
        }

        if config["imap_ssl"]:
            config["imap_starttls"] = False
        if config["smtp_ssl"]:
            config["smtp_starttls"] = False

        if require_password and not config["password"]:
            raise ValueError("Podaj haslo do konta IMAP/SMTP.")
        if config["imap_starttls"] and config["imap_port"] == 993:
            config["imap_port"] = 143
        if config["smtp_starttls"] and config["smtp_port"] == 465:
            config["smtp_port"] = 587
        return config

    def _imap_folder_name(self) -> str:
        folder_map = self._config.get("folder_map", {}) or {}
        folder = folder_map.get(self._active_folder)
        if not folder:
            folder = self._DEFAULT_FOLDER_MAP.get(self._active_folder, "INBOX")
        return folder or "INBOX"

    # --- IMAP helpers ----------------------------------------------------
    def _test_connections(self) -> None:
        if not self.is_configured():
            raise RuntimeError("Brak konfiguracji IMAP/SMTP. Uzupelnij dane serwera.")
        self._test_imap()
        self._test_smtp()

    def _test_imap(self) -> None:
        with self._mailbox_context() as mailbox:
            mailbox.folder.list()  # ensure folder listing works

    def _test_smtp(self) -> None:
        config = self._config
        if not config.get("smtp_host"):
            raise RuntimeError("Brak konfiguracji serwera SMTP.")
        if config["smtp_ssl"]:
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(
                config["smtp_host"], config["smtp_port"], context=context, timeout=20
            ) as client:
                client.login(config["username"], config["password"])
        else:
            with smtplib.SMTP(config["smtp_host"], config["smtp_port"], timeout=20) as client:
                if config["smtp_starttls"]:
                    client.starttls(context=ssl.create_default_context())
                client.login(config["username"], config["password"])

    @contextlib.contextmanager
    def _mailbox_context(self, *, folder: Optional[str] = None):
        if not self.is_configured():
            raise RuntimeError("Brak konfiguracji IMAP.")
        config = self._config
        mailbox = MailBox(config["imap_host"], config["imap_port"])
        if config["imap_ssl"]:
            mailbox = mailbox.ssl()
        if config["imap_starttls"]:
            mailbox = mailbox.starttls()
        mailbox.login(config["username"], config["password"])
        try:
            target_folder = folder or self._imap_folder_name()
            if target_folder:
                mailbox.folder.set(target_folder)
            yield mailbox
        finally:
            try:
                mailbox.logout()
            except Exception:  # pragma: no cover - defensive
                pass

    # --- message operations ----------------------------------------------
    def cached_messages(self) -> List[EmailMessageSummary]:
        cache = self._messages_cache.get(self._active_folder)
        if not cache:
            return []
        timestamp, messages = cache
        if time.time() - timestamp > self._cache_ttl:
            return []
        return list(messages)

    def _fetch_messages_sync(self, force: bool = False) -> List[EmailMessageSummary]:
        cache = self._messages_cache.get(self._active_folder)
        now = time.time()
        if cache and not force and now - cache[0] < self._cache_ttl:
            return list(cache[1])
        summaries: List[EmailMessageSummary] = []
        with self._mailbox_context() as mailbox:
            for message in mailbox.fetch(
                AND(all=True), limit=IMAP_MAX_RESULTS, reverse=True, mark_seen=False
            ):
                message_id = self._compose_message_id(mailbox.folder.get_current(), message.uid)
                snippet = self._build_snippet(message)
                summaries.append(
                    EmailMessageSummary(
                        message_id,
                        message.subject or "(Brak tematu)",
                        message.from_ or "",
                        snippet,
                    )
                )
        self._messages_cache[self._active_folder] = (time.time(), summaries)
        self._persist_message_cache()
        return summaries

    def _build_snippet(self, message) -> str:
        source = message.text or message.html or ""
        if not source:
            return ""
        source = re.sub(r"<[^>]+>", " ", source)
        snippet = " ".join(source.split())
        return textwrap.shorten(snippet, width=160, placeholder="...")

    def _fetch_message_body_sync(self, message_id: str) -> str:
        cached = self._body_cache.get(message_id)
        if cached is not None:
            return cached
        folder, uid = self._parse_message_identity(message_id)
        with self._mailbox_context(folder=folder) as mailbox:
            for message in mailbox.fetch(AND(uid=uid), limit=1, mark_seen=False):
                body = message.html or ""
                if not body:
                    body = f"<pre>{html.escape(message.text or '')}</pre>"
                self._body_cache[message_id] = body
                return body
        return "<p>(Nie udalo sie pobrac tresci wiadomosci)</p>"

    def _send_message_sync(self, to: Iterable[str], subject: str, body: str) -> None:
        config = self._config
        recipients = [addr.strip() for addr in to if addr and addr.strip()]
        if not recipients:
            raise ValueError("Nie podano adresatow.")
        message = EmailMessage()
        message["From"] = config.get("username", "")
        message["To"] = ", ".join(recipients)
        message["Subject"] = subject
        message.set_content(body or "")
        if body:
            message.add_alternative(body, subtype="html")

        if config["smtp_ssl"]:
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(
                config["smtp_host"], config["smtp_port"], context=context, timeout=20
            ) as client:
                client.login(config["username"], config["password"])
                client.send_message(message)
        else:
            with smtplib.SMTP(config["smtp_host"], config["smtp_port"], timeout=20) as client:
                if config["smtp_starttls"]:
                    client.starttls(context=ssl.create_default_context())
                client.login(config["username"], config["password"])
                client.send_message(message)
        self._messages_cache.pop(self._active_folder, None)
        self._messages_cache.pop("sent", None)
        self._persist_message_cache()

    def _load_message_cache(self) -> Dict[str, Tuple[float, List[EmailMessageSummary]]]:
        raw = self.tokens.get("message_cache")
        if not isinstance(raw, str) or not raw:
            return {}
        try:
            payload = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return {}
        cache: Dict[str, Tuple[float, List[EmailMessageSummary]]] = {}
        if isinstance(payload, dict):
            for folder, entry in payload.items():
                if not isinstance(entry, dict):
                    continue
                timestamp = entry.get("timestamp")
                messages_raw = entry.get("messages", [])
                if not isinstance(timestamp, (int, float)):
                    continue
                messages: List[EmailMessageSummary] = []
                if isinstance(messages_raw, list):
                    for item in messages_raw:
                        if not isinstance(item, dict):
                            continue
                        message_id = str(item.get("message_id", "") or "")
                        subject = str(item.get("subject", "") or "")
                        sender = str(item.get("sender", "") or "")
                        snippet = str(item.get("snippet", "") or "")
                        if message_id:
                            messages.append(
                                EmailMessageSummary(message_id, subject, sender, snippet)
                            )
                cache[str(folder)] = (float(timestamp), messages)
        return cache

    def _persist_message_cache(self) -> None:
        if not self._messages_cache:
            self._remove_token_entry("message_cache")
            return
        payload: Dict[str, Any] = {}
        for folder, (timestamp, messages) in self._messages_cache.items():
            payload[folder] = {
                "timestamp": timestamp,
                "messages": [asdict(message) for message in messages],
            }
        self._update_token_entries({"message_cache": json.dumps(payload)})

    # --- utilities -------------------------------------------------------
    def _compose_message_id(self, folder: str, uid: str) -> str:
        return f"{folder}:{uid}"

    def _parse_message_identity(self, message_id: str) -> Tuple[str, str]:
        if ":" not in message_id:
            raise ValueError("Nieprawidlowe ID wiadomosci IMAP.")
        folder, uid = message_id.split(":", 1)
        return folder or "INBOX", uid


class EmailClient:
    def __init__(self) -> None:
        self.storage = TokenStorage()
        self.providers: Dict[str, BaseMailProvider] = {
            GmailProvider.provider_id: GmailProvider(self.storage),
            MicrosoftProvider.provider_id: MicrosoftProvider(self.storage),
            ImapProvider.provider_id: ImapProvider(self.storage),
        }
        self.current_provider: Optional[BaseMailProvider] = None
        self.current_folder: str = "inbox"

    def provider_choices(self) -> List[Tuple[str, str]]:
        return [(key, provider.display_name) for key, provider in self.providers.items()]

    def set_provider(self, provider_id: str) -> None:
        self.current_provider = self.providers.get(provider_id)
        if self.current_provider is not None:
            self.current_provider.set_active_folder(self.current_folder)

    async def authenticate(self) -> bool:
        if self.current_provider is None:
            raise RuntimeError("Provider not selected")
        return await self.current_provider.authenticate()

    async def fetch_messages(self, force: bool = False) -> List[EmailMessageSummary]:
        if self.current_provider is None:
            return []
        return await self.current_provider.fetch_messages(force=force)

    async def fetch_body(self, message_id: str) -> str:
        if self.current_provider is None:
            return ""
        return await self.current_provider.fetch_message_body(message_id)

    async def fetch_attachments(self, message_id: str) -> List[EmailAttachment]:
        if self.current_provider is None:
            return []
        return await self.current_provider.fetch_attachments(message_id)

    async def download_attachment(self, message_id: str, attachment_id: str) -> bytes:
        if self.current_provider is None:
            return b""
        return await self.current_provider.download_attachment(message_id, attachment_id)

    async def send(self, to: Iterable[str], subject: str, body: str) -> None:
        if self.current_provider is None:
            raise RuntimeError("Provider not selected")
        await self.current_provider.send_message(to, subject, body)

    def set_folder(self, folder_id: str) -> None:
        self.current_folder = folder_id or "inbox"
        if self.current_provider is not None:
            self.current_provider.set_active_folder(self.current_folder)

    def configure_imap(self, config: Dict[str, Any]) -> None:
        provider = self.providers.get(ImapProvider.provider_id)
        if isinstance(provider, ImapProvider):
            provider.update_config(config)
            provider.set_active_folder(self.current_folder)

    def cached_messages(self) -> List[EmailMessageSummary]:
        if self.current_provider is None:
            return []
        return self.current_provider.cached_messages()
