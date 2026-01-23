from __future__ import annotations

from PyQt6.QtCore import Qt
from pathlib import Path

from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from data.auth_service import AuthResult, AuthService
from data.supabase_client import SupabaseAuthError
from data.validation import validate_password, validate_username


class LoginOverlay(QWidget):
    """Pełnoekranowy ekran logowania/rejestracji (jeden formularz)."""

    def __init__(self, auth_service: AuthService, on_success, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.auth_service = auth_service
        self.on_success = on_success
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        container = QFrame()
        container.setObjectName("loginContainer")
        container.setFixedWidth(820)

        outer = QVBoxLayout(container)
        outer.setContentsMargins(64, 64, 64, 64)
        outer.setSpacing(26)

        # Logo
        logo_row = QHBoxLayout()
        logo_row.setContentsMargins(0, 0, 0, 0)
        logo_row.setSpacing(0)
        logo = QLabel()
        logo.setObjectName("loginLogo")
        logo_path = Path(__file__).resolve().parent.parent / "assets" / "icons" / "logo.png"
        pix = QPixmap(str(logo_path))
        if not pix.isNull():
            logo.setPixmap(pix.scaledToWidth(260, Qt.TransformationMode.SmoothTransformation))
        logo_row.addStretch(1)
        logo_row.addWidget(logo, alignment=Qt.AlignmentFlag.AlignCenter)
        logo_row.addStretch(1)
        outer.addLayout(logo_row)
        outer.addSpacing(12)

        title = QLabel("Zaloguj się")
        title.setObjectName("loginTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        outer.addWidget(title)

        subtitle = QLabel("Podaj nazwę użytkownika i hasło. Nowe konto zostanie utworzone automatycznie.")
        subtitle.setWordWrap(True)
        subtitle.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        outer.addWidget(subtitle)

        form = QGridLayout()
        form.setVerticalSpacing(12)
        form.setHorizontalSpacing(10)

        user_label = QLabel("Nazwa użytkownika")
        self.user_input = QLineEdit()
        self.user_input.setPlaceholderText("np. jan")
        self.user_input.setClearButtonEnabled(True)

        pass_label = QLabel("Hasło")
        self.pass_input = QLineEdit()
        self.pass_input.setPlaceholderText("Hasło")
        self.pass_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.pass_input.setClearButtonEnabled(True)

        form.addWidget(user_label, 0, 0)
        form.addWidget(self.user_input, 1, 0)
        form.addWidget(pass_label, 2, 0)
        form.addWidget(self.pass_input, 3, 0)

        outer.addLayout(form)

        self.error_label = QLabel("")
        self.error_label.setObjectName("errorLabel")
        outer.addWidget(self.error_label)

        btn_row = QHBoxLayout()
        self.login_btn = QPushButton("Zaloguj się")
        self.login_btn.setObjectName("loginButton")
        self.login_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.login_btn.clicked.connect(self._handle_login)
        btn_row.addStretch(1)
        btn_row.addWidget(self.login_btn, alignment=Qt.AlignmentFlag.AlignCenter)
        btn_row.addStretch(1)
        outer.addLayout(btn_row)

        layout.addStretch(1)
        layout.addWidget(container, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addStretch(1)

    def _handle_login(self) -> None:
        if self.auth_service is None:
            self._set_error("Brak usługi logowania.")
            return
        username = self.user_input.text().strip()
        password = self.pass_input.text().strip()
        if not username or not password:
            self._set_error("Podaj nazwę użytkownika i hasło.")
            return
        if not validate_username(username):
            self._set_error("Nazwa użytkownika musi mieć 3-32 znaki (a-z, 0-9, _.-).")
            return
        if not validate_password(password, min_len=4, max_len=12):
            self._set_error("Hasło musi mieć 4-12 znaków.")
            return
        try:
            result: AuthResult = self.auth_service.login_or_register(username, password)
            self._set_error("")
            self.on_success(result.credentials)
        except SupabaseAuthError as exc:
            self._set_error(str(exc))
        except Exception as exc:
            self._set_error(str(exc))

    def _set_error(self, msg: str) -> None:
        self.error_label.setText(msg)
