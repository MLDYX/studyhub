from __future__ import annotations

import json
import logging
import os
import platform
import sys
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Dict, Optional
from uuid import uuid4
from urllib import request

from dotenv import load_dotenv
from opencensus.ext.azure.log_exporter import AzureLogHandler


# Domyślna ścieżka: data/logs/app.log (tworzona automatycznie)
DEFAULT_LOG_DIR = Path("data") / "logs"
DEFAULT_LOG_FILE = DEFAULT_LOG_DIR / "app.log"
ENV_PATH = (Path(__file__).resolve().parent.parent / ".env" / "local.env").resolve()
AZURE_JSON_PATH = (Path(__file__).resolve().parent.parent / ".env" / "azure.json").resolve()

MAX_BYTES = 5 * 1024 * 1024  # 5 MB
BACKUP_COUNT = 5


@dataclass
class LogContext:
    session_id: str = field(default_factory=lambda: uuid4().hex)
    user_id: Optional[str] = None
    username: Optional[str] = None
    app_version: str = "dev"
    os_info: str = field(default_factory=lambda: f"{platform.system()} {platform.release()}")


class ContextFilter(logging.Filter):
    """Wstrzykuje kontekst (session_id, user_id itp.) do każdego rekordu."""

    def __init__(self, context: LogContext):
        super().__init__()
        self.context = context

    def set_user(self, user_id: str, username: str | None) -> None:
        self.context.user_id = user_id
        self.context.username = username

    def filter(self, record: logging.LogRecord) -> bool:
        record.session_id = self.context.session_id
        record.user_id = self.context.user_id
        record.username = self.context.username
        record.app_version = self.context.app_version
        record.os_info = self.context.os_info
        return True


class JsonFormatter(logging.Formatter):
    """Formatter zwracający jeden wiersz JSON na wpis."""

    def format(self, record: logging.LogRecord) -> str:
        payload: Dict[str, Any] = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "event": getattr(record, "event", None),
            "component": getattr(record, "component", None),
            "action": getattr(record, "action", None),
            "session_id": getattr(record, "session_id", None),
            "user_id": getattr(record, "user_id", None),
            "username": getattr(record, "username", None),
            "app_version": getattr(record, "app_version", None),
            "os": getattr(record, "os_info", None),
        }
        if record.exc_info:
            etype, value, tb = record.exc_info
            payload["exception"] = {
                "type": etype.__name__ if etype else None,
                "message": str(value),
            }
        # Usuń pola None, żeby log był zwięzły
        payload = {k: v for k, v in payload.items() if v is not None}
        return json.dumps(payload, ensure_ascii=False)


class AlertHandler(logging.Handler):
    """
    Handler opcjonalnie wysyłający alerty (np. do webhooka) dla ERROR/CRITICAL.
    Minimalny throttling, by nie spamować.
    """

    def __init__(self, webhook_url: str | None, min_interval_seconds: int = 300):
        super().__init__(level=logging.ERROR)
        self.webhook_url = webhook_url
        self.min_interval = min_interval_seconds
        self._lock = threading.Lock()
        self._last_sent: Dict[str, float] = {}

    def emit(self, record: logging.LogRecord) -> None:
        if not self.webhook_url:
            return
        level = record.levelname
        now = time.time()
        with self._lock:
            last = self._last_sent.get(level, 0)
            if now - last < self.min_interval:
                return
            self._last_sent[level] = now
        try:
            payload = {
                "level": level,
                "message": record.getMessage(),
                "ts": datetime.now(timezone.utc).isoformat(),
                "session_id": getattr(record, "session_id", None),
                "user_id": getattr(record, "user_id", None),
                "username": getattr(record, "username", None),
            }
            data = json.dumps(payload).encode("utf-8")
            req = request.Request(
                self.webhook_url,
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            request.urlopen(req, timeout=5)  # nosec - świadomie wywołanie HTTP
        except Exception:
            # Nie przerywamy logowania w razie błędu alertu
            return


_context = LogContext()
_context_filter = ContextFilter(_context)


def configure_logging(debug: bool = False) -> logging.Logger:
    """Konfiguruje root logger: JSON, rotacja plików, opcjonalne alerty."""
    _ensure_env_loaded()

    log_dir = DEFAULT_LOG_DIR
    log_dir.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(logging.DEBUG if debug else logging.INFO)

    file_handler = RotatingFileHandler(DEFAULT_LOG_FILE, maxBytes=MAX_BYTES, backupCount=BACKUP_COUNT, encoding="utf-8")
    file_handler.lock = threading.RLock()
    file_handler.setFormatter(JsonFormatter())
    file_handler.addFilter(_context_filter)
    root.addHandler(file_handler)

    # Wysyłka do Azure Application Insights (jeśli podano connection string)
    connection_string = os.getenv("AZURE_LOG_CONNECTION_STRING", "")
    if connection_string:
        azure_handler = AzureLogHandler(connection_string=connection_string)
        azure_handler.lock = threading.RLock()
        azure_handler.addFilter(_context_filter)
        root.addHandler(azure_handler)
        root.info("azure_handler_attached", extra={"event": "azure_handler_attached"})

    # Alerty przez webhook (jeśli ustawiono LOG_ALERT_WEBHOOK)
    webhook_url = os.getenv("LOG_ALERT_WEBHOOK")
    alert_handler = AlertHandler(webhook_url)
    alert_handler.lock = threading.RLock()
    alert_handler.addFilter(_context_filter)
    root.addHandler(alert_handler)

    root.info("logger_initialized", extra={"event": "logger_initialized"})
    return root


def set_user_context(user_id: str, username: str | None) -> None:
    _context_filter.set_user(user_id, username)


def set_app_version(version: str) -> None:
    _context.app_version = version


def install_global_excepthook(logger: logging.Logger) -> None:
    """Przechwytuje nieobsłużone wyjątki, loguje jako CRITICAL i próbuje zakończyć elegancko."""

    def _hook(exc_type, exc_value, exc_tb):
        logger.critical(
            "Uncaught exception",
            exc_info=(exc_type, exc_value, exc_tb),
            extra={"event": "uncaught_exception"},
        )
        # Pozwalamy defaultowemu hookowi wyświetlić trace jeśli jest w dev
        sys.__excepthook__(exc_type, exc_value, exc_tb)

    sys.excepthook = _hook


def log_exception(logger: logging.Logger, message: str, exc: BaseException, *, level: int = logging.ERROR, **extra: Any) -> None:
    logger.log(level, message, exc_info=exc, extra=extra)


def _ensure_env_loaded() -> None:
    """Ładuje zmienne z .env/local.env; jeśli dotenv nie ustawi, robi ręczny parse."""
    if ENV_PATH.exists():
        load_dotenv(ENV_PATH, override=False)
        if not os.getenv("AZURE_LOG_CONNECTION_STRING"):
            try:
                content = ENV_PATH.read_text(encoding="utf-8").splitlines()
                for line in content:
                    if "=" not in line:
                        continue
                    key, val = line.split("=", 1)
                    key = key.strip()
                    if key == "AZURE_LOG_CONNECTION_STRING" and val.strip():
                        os.environ[key] = val.strip()
                        break
            except Exception:
                pass
    if not os.getenv("AZURE_LOG_CONNECTION_STRING") and AZURE_JSON_PATH.exists():
        try:
            data = json.loads(AZURE_JSON_PATH.read_text(encoding="utf-8"))
            conn = data.get("AZURE_LOG_CONNECTION_STRING")
            if conn:
                os.environ["AZURE_LOG_CONNECTION_STRING"] = str(conn).strip()
        except Exception:
            pass
