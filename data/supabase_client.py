from __future__ import annotations

import os
import secrets
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

from dotenv import load_dotenv
from supabase import Client, create_client
import bcrypt

from data.credentials import UserCredentials


class SupabaseConfigError(Exception):
    """Raised when Supabase configuration is missing or invalid."""


class SupabaseAuthError(Exception):
    """Raised when authentication or token lookup fails."""


class SupabaseStorageError(Exception):
    """Raised when file upload or storage validation fails."""


BLOCKED_EXTENSIONS = {".exe", ".bat", ".cmd", ".sh", ".ps1", ".psm1", ".com"}
MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024  # 10 MB
SESSION_MAX_AGE_DAYS = 7
logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class SupabaseService:
    """Lightweight wrapper around Supabase client for app data."""

    def __init__(self, env_path: str | Path = ".env/local.env") -> None:
        load_dotenv(env_path)
        url = os.getenv("SUPABASE_URL")
        # Prefer service key if provided (backend context), otherwise anon/public
        key = os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_ANON_KEY")
        if not url or not key:
            raise SupabaseConfigError(
                "Brak SUPABASE_URL oraz klucza (SUPABASE_SERVICE_KEY lub SUPABASE_ANON_KEY). "
                "Upewnij się, że używasz klucza 'anon' (legacy) lub service_key, a nie nowego publishable sb_…"
            )
        try:
            self.client: Client = create_client(url, key)
        except Exception as exc:
            raise SupabaseConfigError(
                "Niepoprawny klucz API. Użyj klucza 'anon' (Legacy API Keys) albo service_role."
            ) from exc

    # --- auth ----------------------------------------------------------
    def register_user(self, display_name: str | None = None) -> UserCredentials:
        token = secrets.token_urlsafe(32)
        payload: Dict[str, Any] = {"secret_token": token}
        if display_name:
            payload["display_name"] = display_name.strip()
        response = self.client.table("users").insert(payload).execute()
        data = self._first_row(response.data)
        return UserCredentials(
            user_id=str(data["id"]),
            secret_token=token,
            username=str(data.get("username", "")),
            last_login_iso=_now_iso(),
        )

    # --- username/password auth ---------------------------------------
    def login_or_register_username_password(self, username: str, password: str) -> UserCredentials:
        normalized = self._normalize_username(username)
        existing = self._get_user_by_username(normalized)
        if existing:
            stored_hash = existing.get("password_hash") or ""
            if not self._verify_password(password, stored_hash):
                raise SupabaseAuthError("Błędne hasło")
            return UserCredentials(
                user_id=str(existing["id"]),
                secret_token=str(existing["secret_token"]),
                username=normalized,
                last_login_iso=_now_iso(),
            )
        password_hash = self._hash_password(password)
        token = secrets.token_urlsafe(32)
        payload = {
            "secret_token": token,
            "username": normalized,
            "password_hash": password_hash.decode("utf-8"),
        }
        try:
            response = self.client.table("users").insert(payload).execute()
        except Exception as exc:
            raise SupabaseAuthError("Taki użykownik już istnieje.") from exc
        data = self._first_row(response.data)
        return UserCredentials(
            user_id=str(data["id"]),
            secret_token=token,
            username=normalized,
            last_login_iso=_now_iso(),
        )

    def get_user_by_token(self, token: str) -> UserCredentials:
        token = token.strip()
        if not token:
            raise SupabaseAuthError("Brak tokenu.")
        response = (
            self.client.table("users")
            .select("id, secret_token, username")
            .eq("secret_token", token)
            .limit(1)
            .execute()
        )
        if not response.data:
            raise SupabaseAuthError("Niepoprawny token.")
        row = response.data[0]
        return UserCredentials(
            user_id=str(row["id"]),
            secret_token=str(row["secret_token"]),
            username=str(row.get("username", "")),
            last_login_iso=_now_iso(),
        )

    # --- calendar ------------------------------------------------------
    def create_calendar_event(
        self,
        user_id: str,
        title: str,
        starts_at: datetime,
        ends_at: datetime,
        *,
        event_id: str | None = None,
        location: str = "",
        description: str = "",
        color_key: str = "Niebieski",
        source_id: str | None = None,
        source_type: str | None = None,
    ) -> Dict[str, Any]:
        payload = {
            "id": event_id,
            "user_id": user_id,
            "title": title.strip() or "Bez tytulu",
            "starts_at": starts_at.isoformat(),
            "ends_at": ends_at.isoformat(),
            "location": location.strip(),
            "description": description.strip(),
            "color_key": color_key,
            "source_id": source_id,
            "source_type": source_type,
            "updated_at": _now_iso(),
            "deleted_at": None,
        }
        response = self.client.table("calendar_events").insert(payload).execute()
        return self._first_row(response.data)

    def create_calendar_events_bulk(
        self,
        user_id: str,
        events: List[Any],
        *,
        source_id: str | None = None,
        source_type: str | None = None,
    ) -> None:
        if not events:
            return
        payload = []
        for ev in events:
            payload.append(
                {
                    "id": ev.id,
                    "user_id": user_id,
                    "title": ev.title,
                    "starts_at": ev.start.isoformat(),
                    "ends_at": ev.end.isoformat(),
                    "location": "",
                    "description": ev.description,
                    "color_key": ev.color_key,
                    "source_id": source_id,
                    "source_type": source_type,
                    "updated_at": _now_iso(),
                    "deleted_at": None,
                }
            )
        self.client.table("calendar_events").upsert(payload).execute()
        logger.info(
            "calendar_bulk_upsert",
            extra={
                "event": "calendar_bulk_upsert",
                "count": len(events),
                "user_id": user_id,
                "source_id": source_id,
                "source_type": source_type,
            },
        )

    def list_calendar_events(self, user_id: str) -> List[Dict[str, Any]]:
        response = (
            self.client.table("calendar_events")
            .select("*")
            .eq("user_id", user_id)
            .is_("deleted_at", "null")
            .order("starts_at")
            .execute()
        )
        return list(response.data or [])

    def update_calendar_event(
        self,
        user_id: str,
        event_id: str,
        **updates: Any,
    ) -> Dict[str, Any]:
        if not updates:
            raise ValueError("Brak danych do aktualizacji.")
        updates["updated_at"] = _now_iso()
        response = (
            self.client.table("calendar_events")
            .update(updates)
            .eq("id", event_id)
            .eq("user_id", user_id)
            .execute()
        )
        return self._first_row(response.data)

    def delete_calendar_event(self, user_id: str, event_id: str) -> None:
        self.client.table("calendar_events").update({"deleted_at": _now_iso()}).eq("id", event_id).eq("user_id", user_id).execute()

    def soft_delete_events_by_source(self, user_id: str, source_id: str) -> None:
        self.client.table("calendar_events").update({"deleted_at": _now_iso()}).eq("user_id", user_id).eq("source_id", source_id).is_("deleted_at", "null").execute()

    def soft_delete_events_past(self, user_id: str, before_iso: str) -> None:
        # Zaznacz jako usunięte wszystko co zakończyło się przed podaną datą
        self.client.table("calendar_events").update({"deleted_at": _now_iso()}).eq("user_id", user_id).lt("ends_at", before_iso).is_("deleted_at", "null").execute()
        logger.info(
            "calendar_soft_delete_past",
            extra={"event": "calendar_soft_delete_past", "user_id": user_id, "before": before_iso},
        )

    def hard_delete_old_deleted(self, user_id: str, older_than_iso: str) -> None:
        # Trwale usuwaj rekordy usunięte ponad zadany czas
        self.client.table("calendar_events").delete().eq("user_id", user_id).lt("deleted_at", older_than_iso).execute()
        logger.info(
            "calendar_hard_delete_old",
            extra={"event": "calendar_hard_delete_old", "user_id": user_id, "older_than": older_than_iso},
        )

    # --- mail metadata -------------------------------------------------
    def add_mail_message(
        self,
        user_id: str,
        subject: str,
        snippet: str,
        sender: str,
        received_at: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        payload = {
            "user_id": user_id,
            "subject": subject.strip() or "(bez tematu)",
            "snippet": snippet.strip(),
            "sender": sender.strip(),
            "received_at": received_at.isoformat() if received_at else None,
        }
        response = self.client.table("mail_messages").insert(payload).execute()
        return self._first_row(response.data)

    def list_mail_messages(self, user_id: str) -> List[Dict[str, Any]]:
        response = (
            self.client.table("mail_messages")
            .select("*")
            .eq("user_id", user_id)
            .order("received_at", desc=True)
            .execute()
        )
        return list(response.data or [])

    # --- notes CRUD ----------------------------------------------------
    def create_note(
        self,
        user_id: str,
        title: str,
        content: str,
        *,
        note_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        payload = {
            "id": note_id,
            "user_id": user_id,
            "title": title,
            "content": content,
            "deleted_at": None,
            "updated_at": _now_iso(),
        }
        response = self.client.table("notes").insert(payload).execute()
        return self._first_row(response.data)

    def update_note(
        self,
        user_id: str,
        note_id: str,
        *,
        title: Optional[str] = None,
        content: Optional[str] = None,
    ) -> Dict[str, Any]:
        updates: Dict[str, Any] = {"updated_at": _now_iso()}
        if title is not None:
            updates["title"] = title
        if content is not None:
            updates["content"] = content
        if len(updates) == 1:
            raise ValueError("Brak danych do aktualizacji.")
        response = (
            self.client.table("notes")
            .update(updates)
            .eq("id", note_id)
            .eq("user_id", user_id)
            .execute()
        )
        return self._first_row(response.data)

    def list_notes(self, user_id: str) -> List[Dict[str, Any]]:
        response = (
            self.client.table("notes")
            .select("*")
            .eq("user_id", user_id)
            .is_("deleted_at", "null")
            .order("updated_at", desc=True)
            .execute()
        )
        return list(response.data or [])

    def search_notes_by_title(self, user_id: str, query: str) -> List[Dict[str, Any]]:
        response = (
            self.client.table("notes")
            .select("id, title, updated_at, created_at")
            .eq("user_id", user_id)
            .is_("deleted_at", "null")
            .like("title", f"%{query}%")
            .order("updated_at", desc=True)
            .execute()
        )
        return list(response.data or [])

    def soft_delete_note(self, user_id: str, note_id: str) -> None:
        self.client.table("notes").update({"deleted_at": _now_iso()}).eq("id", note_id).eq("user_id", user_id).execute()

    def hard_delete_notes_deleted_before(self, user_id: str, older_than_iso: str) -> None:
        self.client.table("notes").delete().eq("user_id", user_id).lt("deleted_at", older_than_iso).execute()
        logger.info(
            "notes_hard_delete_old",
            extra={"event": "notes_hard_delete_old", "user_id": user_id, "older_than": older_than_iso},
        )

    # --- notes attachments ---------------------------------------------
    def upload_attachment_for_note(
        self,
        user: UserCredentials,
        note_id: str,
        *,
        file_path: Optional[Path] = None,
        file_bytes: Optional[bytes] = None,
        file_name: Optional[str] = None,
        mime_type: str = "application/octet-stream",
    ) -> Dict[str, Any]:
        if file_path is None and file_bytes is None:
            raise SupabaseStorageError("Brak pliku do wyslania.")
        data, resolved_name = self._resolve_file_payload(file_path, file_bytes, file_name)
        self._validate_attachment(resolved_name, data)

        storage_path = f"{user.secret_token}/{_now_iso()}_{resolved_name}"
        try:
            self.client.storage.from_("attachments").upload(
                storage_path,
                data,
                {"content-type": mime_type},
            )
        except Exception as exc:
            raise SupabaseStorageError(f"Blad uploadu: {exc}") from exc

        response = (
            self.client.table("note_attachments")
            .insert(
                {
                    "note_id": note_id,
                    "blob_path": storage_path,
                    "file_name": resolved_name,
                    "mime_type": mime_type,
                    "size_bytes": len(data),
                }
            )
            .execute()
        )
        logger.info(
            "note_attachment_uploaded",
            extra={
                "event": "note_attachment_uploaded",
                "note_id": note_id,
                "size": len(data),
                "file_name": resolved_name,
            },
        )
        return self._first_row(response.data)

    def list_note_attachments(self, note_id: str) -> List[Dict[str, Any]]:
        response = (
            self.client.table("note_attachments")
            .select("*")
            .eq("note_id", note_id)
            .order("created_at")
            .execute()
        )
        return list(response.data or [])

    # --- helpers -------------------------------------------------------
    @staticmethod
    def _first_row(data: List[Dict[str, Any]] | None) -> Dict[str, Any]:
        if not data:
            raise ValueError("Brak danych z Supabase.")
        return data[0]

    @staticmethod
    def _resolve_file_payload(
        file_path: Optional[Path],
        file_bytes: Optional[bytes],
        file_name: Optional[str],
    ) -> Tuple[bytes, str]:
        if file_path:
            content = file_path.read_bytes()
            name = file_path.name
        else:
            if file_bytes is None:
                raise SupabaseStorageError("Brak danych pliku.")
            content = file_bytes
            name = file_name or f"upload_{uuid4().hex}"
        return content, name

    @staticmethod
    def _validate_attachment(file_name: str, content: bytes) -> None:
        ext = Path(file_name).suffix.lower()
        if ext in BLOCKED_EXTENSIONS:
            raise SupabaseStorageError("Ten typ pliku jest zablokowany.")
        if len(content) > MAX_ATTACHMENT_BYTES:
            raise SupabaseStorageError("Plik jest wiekszy niz 10 MB.")

    @staticmethod
    def _normalize_username(username: str) -> str:
        return username.strip().lower()

    def _get_user_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        response = (
            self.client.table("users")
            .select("id, secret_token, username, password_hash")
            .eq("username", username)
            .limit(1)
            .execute()
        )
        if not response.data:
            return None
        return response.data[0]

    @staticmethod
    def _hash_password(password: str) -> bytes:
        salt = bcrypt.gensalt()
        return bcrypt.hashpw(password.encode("utf-8"), salt)

    @staticmethod
    def _verify_password(password: str, stored_hash: str) -> bool:
        if not stored_hash:
            return False
        try:
            return bcrypt.checkpw(password.encode("utf-8"), stored_hash.encode("utf-8"))
        except ValueError:
            return False
