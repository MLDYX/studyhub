from __future__ import annotations

import logging
import sys
import os
from pathlib import Path

from PyQt6.QtWidgets import QApplication, QMessageBox

from data.auth_service import AuthService
from data.credentials import UserCredentials
from data.logger import configure_logging, install_global_excepthook, set_app_version, set_user_context
from data.supabase_client import SupabaseConfigError, SupabaseService
from ui.main_window import MainWindow

try:  # tomllib jest wbudowane od Pythona 3.11
    import tomllib  # type: ignore
except Exception:  # pragma: no cover - fallback, jeśli nie ma tomllib
    tomllib = None


class SafeApplication(QApplication):
    """QApplication z globalnym try/except dla zdarzeń UI (graceful failure + log)."""

    def __init__(self, argv, logger: logging.Logger):
        super().__init__(argv)
        self.logger = logger

    def notify(self, receiver, event):
        try:
            return super().notify(receiver, event)
        except Exception as exc:
            self.logger.error(
                "Unhandled UI exception",
                exc_info=exc,
                extra={"event": "ui_exception"},
            )
            QMessageBox.critical(None, "Błąd", f"Wystąpił nieoczekiwany błąd:\n{exc}")
            return False


def main() -> None:
    logger = configure_logging(debug=False)
    set_app_version(_load_app_version())
    install_global_excepthook(logger)

    # Opcjonalny test krytycznego loga: ustaw zmienną środowiskową DEMO_CRITICAL=1
    if os.getenv("DEMO_CRITICAL") == "1":
        # Tylko log (bez dialogu), żeby uniknąć błędu "QWidget: Must construct a QApplication..."
        logger.critical("Demo critical triggered for alert test", extra={"event": "demo_critical"})

    app = SafeApplication(sys.argv, logger)

    # Demo CRITICAL przeniesione po utworzeniu QApplication, aby QMessageBox działał poprawnie
    if os.getenv("DEMO_CRITICAL") == "1":
        logger.critical("Demo critical triggered for alert test", extra={"event": "demo_critical"})
        QMessageBox.critical(None, "Demo CRITICAL", "Wygenerowano CRITICAL dla testu alertów.")

    credentials, supabase, auth_service = _authenticate(app, logger)
    if supabase is None or auth_service is None:
        sys.exit(1)

    if credentials:
        set_user_context(credentials.user_id, credentials.username)

    try:
        window = MainWindow(
            supabase_service=supabase,
            auth_service=auth_service,
            user_credentials=credentials,
        )
    except Exception as exc:  # Graceful failure na starcie
        logger.critical(
            "Failed to start main window",
            exc_info=exc,
            extra={"event": "startup_error"},
        )
        QMessageBox.critical(None, "Błąd krytyczny", f"Nie udało się uruchomić aplikacji:\n{exc}")
        sys.exit(1)

    window.show()
    sys.exit(app.exec())


def _authenticate(app: QApplication, logger: logging.Logger) -> tuple[UserCredentials | None, SupabaseService | None, AuthService | None]:
    try:
        supabase = SupabaseService()
    except SupabaseConfigError as exc:
        logger.critical(
            "Supabase configuration missing or invalid",
            exc_info=exc,
            extra={"event": "supabase_config_error"},
        )
        QMessageBox.critical(None, "Brak konfiguracji", str(exc))
        return None, None, None

    auth_service = AuthService(supabase)
    saved = auth_service.load_saved_credentials()
    if saved:
        set_user_context(saved.user_id, saved.username)
    return saved, supabase, auth_service


def _load_app_version() -> str:
    pyproject = Path(__file__).resolve().parent / "pyproject.toml"
    if not tomllib or not pyproject.exists():
        return "dev"
    try:
        with pyproject.open("rb") as handle:
            data = tomllib.load(handle)
        return str(data.get("project", {}).get("version", "dev"))
    except Exception:
        return "dev"


if __name__ == "__main__":
    main()
