from __future__ import annotations

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from data.credentials import CredentialsStore, UserCredentials
from data.supabase_client import SupabaseAuthError, SupabaseConfigError, SupabaseService


@dataclass
class AuthResult:
    credentials: UserCredentials
    is_new: bool


class AuthService:
    """Handles loading/saving credentials and validating tokens with Supabase."""

    def __init__(self, supabase: SupabaseService, store: CredentialsStore | None = None) -> None:
        self.supabase = supabase
        self.store = store or CredentialsStore()

    def load_saved_credentials(self, max_age_days: int = 7) -> Optional[UserCredentials]:
        creds = self.store.load()
        if not creds:
            return None
        try:
            # sprawdz waznosc sesji
            last_login = datetime.fromisoformat(creds.last_login_iso)
            if last_login < datetime.now(timezone.utc) - timedelta(days=max_age_days):
                return None
        except Exception:
            return None
        try:
            validated = self.supabase.get_user_by_token(creds.secret_token)
            # zachowaj ostatnie logowanie
            validated.last_login_iso = _now_iso()
            self.store.save(validated)
            return validated
        except SupabaseAuthError:
            return None

    def login_or_register(self, username: str, password: str) -> AuthResult:
        creds = self.supabase.login_or_register_username_password(username, password)
        self.store.save(creds)
        return AuthResult(credentials=creds, is_new=False)

    def clear(self) -> None:
        self.store.clear()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
