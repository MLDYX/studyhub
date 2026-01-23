from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import List, Optional

from data.credentials import UserCredentials
from data.supabase_client import SupabaseService


class NotePersistence:
    """Warstwa zapisu/odczytu notatek do Supabase (tytuł + treść + załączniki)."""

    def __init__(self, supabase: SupabaseService, user: UserCredentials) -> None:
        self.supabase = supabase
        self.user = user

    def create_note(self, title: str, content: str) -> str:
        row = self.supabase.create_note(self.user.user_id, title, content)
        return str(row["id"])

    def update_note(self, note_id: str, *, title: Optional[str] = None, content: Optional[str] = None) -> None:
        self.supabase.update_note(self.user.user_id, note_id, title=title, content=content)

    def list_notes(self) -> List[dict]:
        return self.supabase.list_notes(self.user.user_id)

    def search_notes(self, query: str) -> List[dict]:
        return self.supabase.search_notes_by_title(self.user.user_id, query)

    def soft_delete(self, note_id: str) -> None:
        self.supabase.soft_delete_note(self.user.user_id, note_id)

    def cleanup(self, *, hard_delete_older_than: datetime) -> None:
        self.supabase.hard_delete_notes_deleted_before(
            self.user.user_id,
            hard_delete_older_than.isoformat(),
        )

    def upload_attachment(
        self,
        note_id: str,
        *,
        file_path=None,
        file_bytes: Optional[bytes] = None,
        file_name: Optional[str] = None,
        mime_type: str = "application/octet-stream",
    ) -> dict:
        return self.supabase.upload_attachment_for_note(
            self.user,
            note_id,
            file_path=file_path,
            file_bytes=file_bytes,
            file_name=file_name,
            mime_type=mime_type,
        )

    def list_attachments(self, note_id: str) -> List[dict]:
        return self.supabase.list_note_attachments(note_id)
