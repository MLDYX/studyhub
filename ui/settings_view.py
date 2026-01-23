from __future__ import annotations

from pathlib import Path
from typing import Dict, List

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.mail import EmailClient
from core.settings import SettingsManager
from ui.calendar_view import ImportCalendarDialog


class SettingsView(QWidget):
    calendar_sources_changed = pyqtSignal()

    def __init__(self, settings: SettingsManager, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("settingsRoot")

        self.settings = settings
        self._mail_client = EmailClient()
        provider_choices = self._mail_client.provider_choices()
        self._provider_display: Dict[str, str] = {
            provider_id: display for provider_id, display in provider_choices
        }

        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 32, 32, 32)
        layout.setSpacing(24)

        header = QLabel("Ustawienia")
        header.setObjectName("settingsTitle")
        layout.addWidget(header)

        subtitle = QLabel("Dostosuj sposob dzialania StudyHub.")
        subtitle.setObjectName("settingsSubtitle")
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)

        layout.addWidget(self._build_mail_card(provider_choices))
        layout.addWidget(self._build_calendar_card())
        layout.addStretch(1)

        self._load_mail_provider()
        self._load_calendar_sources()

    def _build_mail_card(self, provider_choices) -> QFrame:
        card = QFrame()
        card.setObjectName("settingsCard")
        wrapper = QVBoxLayout(card)
        wrapper.setContentsMargins(20, 20, 20, 20)
        wrapper.setSpacing(16)

        title = QLabel("Domyslne konto pocztowe")
        title.setObjectName("settingsCardTitle")
        wrapper.addWidget(title)

        description = QLabel(
            "Wybierz domyslnego dostawce poczty, aby szybciej otwierac skrzynke mailowa."
        )
        description.setObjectName("settingsCardDescription")
        description.setWordWrap(True)
        wrapper.addWidget(description)

        controls = QHBoxLayout()
        controls.setSpacing(10)

        self.mail_combo = QComboBox()
        self.mail_combo.setObjectName("settingsMailCombo")
        self.mail_combo.addItem("Nie zapamietuj", "")
        for provider_id, display in provider_choices:
            self.mail_combo.addItem(display, provider_id)
        controls.addWidget(self.mail_combo, stretch=1)

        self.clear_mail_button = QPushButton("Wyczysc")
        self.clear_mail_button.setObjectName("settingsClearMailButton")
        self.clear_mail_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.clear_mail_button.clicked.connect(self._clear_mail_provider)
        controls.addWidget(self.clear_mail_button)

        wrapper.addLayout(controls)

        self.mail_feedback = QLabel("")
        self.mail_feedback.setObjectName("settingsFeedback")
        self.mail_feedback.setWordWrap(True)
        wrapper.addWidget(self.mail_feedback)

        self.mail_combo.currentIndexChanged.connect(self._on_mail_provider_changed)

        return card

    def _build_calendar_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("settingsCard")
        wrapper = QVBoxLayout(card)
        wrapper.setContentsMargins(20, 20, 20, 20)
        wrapper.setSpacing(16)

        title = QLabel("Kalendarze zewnetrzne")
        title.setObjectName("settingsCardTitle")
        wrapper.addWidget(title)

        description = QLabel(
            "Dodaj lub usun pliki ICS, ktore maja byc ladowane w module Kalendarz. "
            "Zmiany zostana zastosowane po ponownym otwarciu kalendarza."
        )
        description.setObjectName("settingsCardDescription")
        description.setWordWrap(True)
        wrapper.addWidget(description)

        self.calendar_list = QListWidget()
        self.calendar_list.setObjectName("settingsCalendarList")
        self.calendar_list.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self.calendar_list.setUniformItemSizes(True)
        wrapper.addWidget(self.calendar_list)

        actions = QHBoxLayout()
        actions.setSpacing(10)

        self.add_calendar_button = QPushButton("Dodaj kalendarz")
        self.add_calendar_button.setObjectName("settingsAddCalendarButton")
        self.add_calendar_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.add_calendar_button.clicked.connect(self._add_calendar_source)
        actions.addWidget(self.add_calendar_button)

        self.remove_calendar_button = QPushButton("Usun zaznaczony")
        self.remove_calendar_button.setObjectName("settingsRemoveCalendarButton")
        self.remove_calendar_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.remove_calendar_button.clicked.connect(self._remove_calendar_source)
        actions.addWidget(self.remove_calendar_button)

        actions.addStretch(1)
        wrapper.addLayout(actions)

        self.calendar_feedback = QLabel("")
        self.calendar_feedback.setObjectName("settingsFeedback")
        self.calendar_feedback.setWordWrap(True)
        wrapper.addWidget(self.calendar_feedback)

        return card

    # --- mail handlers --------------------------------------------------
    def _load_mail_provider(self) -> None:
        saved_provider = self.settings.get_mail_provider()
        if saved_provider:
            index = self.mail_combo.findData(saved_provider)
            if index >= 0:
                self.mail_combo.setCurrentIndex(index)
        if saved_provider and saved_provider in self._provider_display:
            self.mail_feedback.setText(
                f"Domyslna skrzynka: {self._provider_display[saved_provider]}."
            )
        else:
            self.mail_feedback.setText("Brak ustawionej domyslnej skrzynki.")

    def _on_mail_provider_changed(self, index: int) -> None:
        provider_id = self.mail_combo.itemData(index)
        if provider_id:
            self.settings.set_mail_provider(provider_id)
            display = self.mail_combo.currentText()
            self.mail_feedback.setText(f"Domyslna skrzynka ustawiona na {display}.")
        else:
            self.settings.clear_mail_provider()
            self.mail_feedback.setText("Domyslna skrzynka zostala wyczyszczona.")

    def _clear_mail_provider(self) -> None:
        self.settings.clear_mail_provider()
        self.mail_combo.blockSignals(True)
        self.mail_combo.setCurrentIndex(0)
        self.mail_combo.blockSignals(False)
        self.mail_feedback.setText("Domyslna skrzynka zostala wyczyszczona.")

    # --- calendar handlers ----------------------------------------------
    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._load_calendar_sources()

    def _load_calendar_sources(self) -> None:
        self.calendar_list.clear()
        sources = self.settings.get_calendar_sources()
        if not sources:
            placeholder = QListWidgetItem("Brak zapisanych kalendarzy. Dodaj plik ICS, aby zaczac.")
            placeholder.setFlags(Qt.ItemFlag.NoItemFlags)
            self.calendar_list.addItem(placeholder)
            self.remove_calendar_button.setEnabled(False)
            self.calendar_feedback.setText("Brak skonfigurowanych kalendarzy zewnetrznych.")
            return

        for entry in sources:
            name = entry.get("name") or Path(entry["path"]).stem
            path = entry["path"]
            source_type = entry.get("type", "file")
            label = f"{name}\n{path}"
            if source_type == "url":
                label = f"{name} [URL]\n{path}"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, entry)
            self.calendar_list.addItem(item)

        self.remove_calendar_button.setEnabled(True)
        self.calendar_feedback.setText(f"Zapisane kalendarze: {len(sources)}.")

    def _add_calendar_source(self) -> None:
        dialog = ImportCalendarDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        result = dialog.get_result()
        if result is None:
            return

        mode, value = result
        source_type = "file"
        source_ref = value.strip()
        name = ""

        if mode == "url":
            source_type = "url"
            source_ref = source_ref or value.strip()
            if not source_ref:
                return
            name = source_ref
        else:
            path_obj = Path(source_ref).expanduser()
            if not path_obj.exists():
                QMessageBox.warning(self, "Nie znaleziono pliku", "Wybrany plik nie istnieje.")
                return
            path_obj = path_obj.resolve()
            source_ref = str(path_obj)
            name = path_obj.stem

        if not source_ref:
            return

        existing = self.settings.get_calendar_sources()
        if any(
            entry.get("path") == source_ref and (entry.get("type", "file") or "file") == source_type
            for entry in existing
        ):
            QMessageBox.information(
                self,
                "Kalendarz juz dodany",
                "Ten kalendarz znajduje sie juz na liscie.",
            )
            return

        self.settings.add_calendar_source(name or source_ref, source_ref, source_type=source_type)
        self._load_calendar_sources()
        self.calendar_feedback.setText(f"Dodano kalendarz: {name or source_ref}.")
        self.calendar_sources_changed.emit()

    def _remove_calendar_source(self) -> None:
        item = self.calendar_list.currentItem()
        if item is None:
            return
        payload = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(payload, dict):
            return

        confirm = QMessageBox.question(
            self,
            "Usun kalendarz",
            "Czy na pewno chcesz usunac wybrany kalendarz z ustawien?",
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        self.settings.remove_calendar_source(payload.get("path", ""))
        self._load_calendar_sources()
        self.calendar_feedback.setText("Kalendarz zostal usuniety.")
        self.calendar_sources_changed.emit()
