from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from data.auth_service import AuthResult, AuthService
from data.supabase_client import SupabaseAuthError, SupabaseConfigError, SupabaseStorageError


class AuthDialog(QDialog):
    """Blokujacy dialog logowania/rejestracji przed uruchomieniem aplikacji."""

    def __init__(self, auth_service: AuthService, parent=None) -> None:
        super().__init__(parent)
        self.setModal(True)
        self.setWindowTitle("Logowanie do bazy")
        self.auth_service = auth_service
        self.result_data: AuthResult | None = None
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(14)

        info = QLabel(
            "Utworz konto (generuje token) albo podaj istniejacy token.\n"
            "Tokeny i dane zapisywane sa lokalnie w data/user_credentials.json."
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        form = QGridLayout()
        form.setVerticalSpacing(10)

        name_label = QLabel("Nazwa uzytkownika (opcjonalnie przy rejestracji)")
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("np. Jan")

        token_label = QLabel("Token")
        self.token_input = QLineEdit()
        self.token_input.setPlaceholderText("wklej token albo zostaw puste przy rejestracji")
        self.token_input.setClearButtonEnabled(True)

        form.addWidget(name_label, 0, 0)
        form.addWidget(self.name_input, 1, 0)
        form.addWidget(token_label, 2, 0)
        form.addWidget(self.token_input, 3, 0)

        layout.addLayout(form)

        btn_row = QHBoxLayout()
        self.register_btn = QPushButton("Utworz konto")
        self.login_btn = QPushButton("Zaloguj tokenem")
        btn_row.addWidget(self.register_btn)
        btn_row.addWidget(self.login_btn)
        layout.addLayout(btn_row)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        layout.addWidget(buttons)

        self.register_btn.clicked.connect(self._register)
        self.login_btn.clicked.connect(self._login)
        buttons.rejected.connect(self.reject)

    def _register(self) -> None:
        display_name = self.name_input.text().strip() or None
        try:
            self.result_data = self.auth_service.register_new_user(display_name)
        except (SupabaseAuthError, SupabaseConfigError, SupabaseStorageError, Exception) as exc:
            self._show_error(str(exc))
            return
        self.accept()

    def _login(self) -> None:
        token = self.token_input.text().strip()
        if not token:
            self._show_error("Podaj token aby sie zalogowac.")
            return
        try:
            self.result_data = self.auth_service.login_with_token(token)
        except SupabaseAuthError as exc:
            self._show_error(str(exc))
            return
        except SupabaseConfigError as exc:
            self._show_error(str(exc))
            return
        self.accept()

    def _show_error(self, message: str) -> None:
        QMessageBox.critical(self, "Blad logowania", message, QMessageBox.StandardButton.Ok)
