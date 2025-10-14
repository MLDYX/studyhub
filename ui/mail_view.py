from __future__ import annotations

import asyncio
from typing import Optional, Tuple, List

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QMessageBox,
    QFrame,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from core.mail import EmailClient, EmailMessageSummary


class MailView(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("mailRoot")
        self.client = EmailClient()
        self._messages: list[EmailMessageSummary] = []

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(32, 32, 32, 32)
        root_layout.setSpacing(16)

        header = QLabel("Mail")
        header.setObjectName("h1")
        root_layout.addWidget(header)

        subheader = QLabel("Zarządzaj skrzynką odbiorczą z jednego miejsca")
        subheader.setObjectName("subtitle")
        root_layout.addWidget(subheader)

        container = QFrame()
        container.setObjectName("mailContainer")
        container.setFrameShape(QFrame.Shape.NoFrame)
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(20)

        controls = QHBoxLayout()
        controls.setSpacing(12)

        self.provider_combo = QComboBox()
        self.provider_combo.setObjectName("mailProviderCombo")
        for provider_id, display_name in self.client.provider_choices():
            self.provider_combo.addItem(display_name, provider_id)
        self.provider_combo.currentIndexChanged.connect(self._on_provider_changed)
        controls.addWidget(self.provider_combo, stretch=1)
        self.provider_combo.setCursor(Qt.CursorShape.PointingHandCursor)

        self.auth_button = QPushButton("Zaloguj")
        self.auth_button.setObjectName("mailAuthButton")
        self.auth_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.auth_button.clicked.connect(self._authenticate)
        controls.addWidget(self.auth_button)

        controls.addStretch(1)
        self.refresh_button = QPushButton("Odśwież")
        self.refresh_button.setObjectName("mailRefreshButton")
        self.refresh_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.refresh_button.clicked.connect(self._load_messages)
        controls.addWidget(self.refresh_button)

        self.compose_button = QPushButton("Wyślij wiadomość")
        self.compose_button.setObjectName("mailSendButton")
        self.compose_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.compose_button.clicked.connect(self._open_compose_dialog)
        controls.addWidget(self.compose_button)

        container_layout.addLayout(controls)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setMinimumHeight(520)
        splitter.setObjectName("mailSplitter")

        self.messages_list = QListWidget()
        self.messages_list.setObjectName("mailList")
        self.messages_list.itemSelectionChanged.connect(self._display_selected)
        splitter.addWidget(self.messages_list)
        self.messages_list.setCursor(Qt.CursorShape.PointingHandCursor)

        self.body_view = QTextEdit()
        self.body_view.setObjectName("mailBody")
        self.body_view.setReadOnly(True)
        splitter.addWidget(self.body_view)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)

        container_layout.addWidget(splitter)

        self.status_label = QLabel("Wybierz dostawcę i zaloguj się, aby wyświetlić wiadomości.")
        self.status_label.setObjectName("mailStatus")
        container_layout.addWidget(self.status_label)

        root_layout.addWidget(container)

        if self.provider_combo.count():
            self._on_provider_changed(0)

    def _run_async(self, coro):
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()

    def _on_provider_changed(self, index: int) -> None:
        provider_id = self.provider_combo.itemData(index)
        if provider_id:
            self.client.set_provider(provider_id)
            self.status_label.setText("Zaloguj się, aby pobrać wiadomości.")
            self.messages_list.clear()
            self.body_view.clear()

    def _authenticate(self) -> None:
        try:
            success = self._run_async(self.client.authenticate())
        except Exception as exc:
            self.status_label.setText(f"Błąd logowania: {exc}")
            return

        if success:
            self.status_label.setText("Pomyślnie zalogowano. Pobieram wiadomości…")
            self._load_messages()
        else:
            self.status_label.setText("Logowanie nie powiodło się.")

    def _load_messages(self) -> None:
        try:
            self._messages = self._run_async(self.client.fetch_messages())
        except Exception as exc:
            self.status_label.setText(f"Błąd pobierania: {exc}")
            return

        self.messages_list.clear()
        for message in self._messages:
            item = QListWidgetItem(f"{message.subject}\n{message.sender}")
            item.setData(Qt.ItemDataRole.UserRole, message.message_id)
            self.messages_list.addItem(item)

        if self._messages:
            self.status_label.setText(f"Załadowano {len(self._messages)} wiadomości.")
            self.messages_list.setCurrentRow(0)
        else:
            self.status_label.setText("Brak wiadomości do wyświetlenia.")
            self.body_view.clear()

    def _display_selected(self) -> None:
        item = self.messages_list.currentItem()
        if item is None:
            self.body_view.clear()
            return
        message_id = item.data(Qt.ItemDataRole.UserRole)
        try:
            body = self._run_async(self.client.fetch_body(message_id))
        except Exception as exc:
            self.body_view.setPlainText(f"Nie udało się pobrać treści: {exc}")
            return
        self.body_view.setHtml(body)

    def _open_compose_dialog(self) -> None:
        if self.client.current_provider is None:
            self.status_label.setText("Wybierz i zaloguj dostawcę, aby wysłać wiadomość.")
            return
        dialog = ComposeDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        recipients, subject, body = dialog.get_data()
        try:
            self._run_async(self.client.send(recipients, subject, body))
        except Exception as exc:
            self.status_label.setText(f"Nie udało się wysłać wiadomości: {exc}")
            return

        self.status_label.setText("Wysłano demonstracyjną wiadomość.")
        sent_summary = EmailMessageSummary("sent-demo", f"[Wysłano] {subject}", ", ".join(recipients))
        self._messages.insert(0, sent_summary)
        sent_item = QListWidgetItem(f"{sent_summary.subject}\n{sent_summary.sender}")
        sent_item.setData(Qt.ItemDataRole.UserRole, sent_summary.message_id)
        self.messages_list.insertItem(0, sent_item)
        self.messages_list.setCurrentRow(0)


class ComposeDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Wyślij wiadomość")
        self.setObjectName("mailComposeDialog")
        self.setMinimumWidth(420)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        form = QFormLayout()
        form.setSpacing(12)

        self.to_edit = QLineEdit()
        self.to_edit.setPlaceholderText("Adresat (oddziel przecinkami)")
        form.addRow("Do", self.to_edit)

        self.subject_edit = QLineEdit()
        self.subject_edit.setPlaceholderText("Temat")
        form.addRow("Temat", self.subject_edit)

        self.body_edit = QTextEdit()
        self.body_edit.setPlaceholderText("Treść wiadomości…")
        form.addRow("Treść", self.body_edit)

        layout.addLayout(form)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok
        )
        self.buttons.accepted.connect(self._on_accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

        self._result: Optional[Tuple[List[str], str, str]] = None

    def _on_accept(self) -> None:
        recipients_raw = self.to_edit.text().strip()
        subject = self.subject_edit.text().strip()
        body = self.body_edit.toPlainText().strip()

        recipients = [item.strip() for item in recipients_raw.split(",") if item.strip()]
        if not recipients or not subject or not body:
            QMessageBox.warning(self, "Brak danych", "Uzupełnij adresata, temat i treść.")
            return

        self._result = (recipients, subject, body)
        self.accept()

    def get_data(self) -> Tuple[List[str], str, str]:
        if self._result is None:
            return [], "", ""
        return self._result
