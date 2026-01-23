from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


DEFAULT_CREDENTIALS_PATH = Path(__file__).resolve().parent / "user_credentials.json"


@dataclass
class UserCredentials:
    user_id: str
    secret_token: str
    username: str
    last_login_iso: str


class CredentialsStore:
    """Proste przechowywanie user_id/secret_token/username w pliku JSON."""

    def __init__(self, path: Path = DEFAULT_CREDENTIALS_PATH) -> None:
        self.path = path

    def load(self) -> Optional[UserCredentials]:
        if not self.path.exists():
            return None
        try:
            with self.path.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, json.JSONDecodeError):
            return None
        user_id = str(data.get("user_id", "")).strip()
        token = str(data.get("secret_token", "")).strip()
        username = str(data.get("username", "")).strip()
        last_login = str(data.get("last_login_iso", "")).strip()
        if not user_id or not token or not username or not last_login:
            return None
        return UserCredentials(
            user_id=user_id,
            secret_token=token,
            username=username,
            last_login_iso=last_login,
        )

    def save(self, creds: UserCredentials) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "user_id": creds.user_id,
            "secret_token": creds.secret_token,
            "username": creds.username,
            "last_login_iso": creds.last_login_iso,
        }
        with self.path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)

    def clear(self) -> None:
        if self.path.exists():
            try:
                self.path.unlink()
            except OSError:
                return
