from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QLabel, QVBoxLayout, QWidget


class FlashcardsView(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("flashcardsRoot")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 32, 32, 32)
        layout.setSpacing(16)

        title = QLabel("Fiszki")
        title.setObjectName("h1")
        layout.addWidget(title)

        placeholder = QLabel("Funkcja dostępna wkrótce")
        placeholder.setObjectName("comingSoon")
        placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        placeholder.setEnabled(False)
        layout.addWidget(placeholder, alignment=Qt.AlignmentFlag.AlignCenter)

        layout.addStretch(1)
