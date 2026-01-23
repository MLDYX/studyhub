from __future__ import annotations

import re
from typing import Iterable, List


USERNAME_PATTERN = re.compile(r"^[a-z0-9_.-]{3,32}$")
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
BLOCKED_EXTENSIONS = {".exe", ".bat", ".cmd", ".sh", ".ps1", ".psm1", ".com"}


def validate_username(value: str) -> bool:
    return bool(USERNAME_PATTERN.fullmatch(value.strip()))


def validate_password(value: str, *, min_len: int = 4, max_len: int = 12) -> bool:
    return min_len <= len(value) <= max_len


def validate_emails(raw: str) -> List[str]:
    emails: List[str] = []
    for part in raw.replace("\r", "").replace("\n", "").split(","):
        addr = part.strip()
        if not addr:
            continue
        if not EMAIL_PATTERN.fullmatch(addr):
            raise ValueError(f"Niepoprawny adres e-mail: {addr}")
        emails.append(addr)
    if not emails:
        raise ValueError("Podaj co najmniej jeden adres e-mail.")
    return emails


def trim_length(text: str, max_len: int) -> str:
    text = text or ""
    if len(text) > max_len:
        return text[:max_len]
    return text


def sanitize_header(value: str, max_len: int = 255) -> str:
    cleaned = (value or "").replace("\r", "").replace("\n", "").strip()
    return trim_length(cleaned, max_len)


def validate_attachment_name(name: str, *, max_len: int = 255) -> None:
    from pathlib import Path

    ext = Path(name).suffix.lower()
    if ext in BLOCKED_EXTENSIONS:
        raise ValueError("Ten typ pliku jest zablokowany.")
    if len(name) > max_len:
        raise ValueError("Nazwa pliku jest za dluga.")
