from PyQt6.QtCore import (
    Qt,
    QFileSystemWatcher,
    QRectF,
    QLineF,
    QSize,
    QFileInfo,
)
from PyQt6.QtCore import QUrl
from PyQt6.QtWidgets import (
    QWidget,
    QLabel,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QFileDialog,
    QMessageBox,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QStyledItemDelegate,
    QStyle,
    QSizePolicy,
    QListWidget,
    QListWidgetItem,
    QListView,
    QFileIconProvider,
    QSpacerItem,
    QToolButton,
    QFrame,
)
from PyQt6.QtGui import (
    QDesktopServices,
    QPainterPath,
    QRegion,
    QColor,
    QPen,
    QIcon,
    QPixmap,
    QPixmapCache,
    QImage,
    QPainter,
    QFont,
)
import os
import datetime
import time
import re

# Maksymalny rozmiar pliku (100 MB)
MAX_FILE_SIZE = 100 * 1024 * 1024

# Opcjonalne biblioteki do miniaturek
try:
    import fitz  # PyMuPDF dla PDF
    HAS_PYMUPDF = True
except ImportError:
    HAS_PYMUPDF = False

try:
    import cv2  # OpenCV dla wideo
    HAS_OPENCV = True
except ImportError:
    HAS_OPENCV = False

try:
    from mutagen import File as MutagenFile  # Mutagen dla okładek audio
    HAS_MUTAGEN = True
except ImportError:
    HAS_MUTAGEN = False

from core.notes import add_existing_note_file, get_notes_in_folder, NOTES_DIR, is_favorite, toggle_favorite
from core.file_operations import duplicate_file, move_file_to_folder, rename_file, delete_file, get_file_info
from PyQt6.QtWidgets import QMenu
from PyQt6.QtWidgets import QInputDialog


def safe_font(family: str = "Segoe UI", size: int = 10, bold: bool = False) -> QFont:
    """Utwórz bezpieczną czcionkę z gwarancją, że rozmiar jest > 0"""
    safe_size = max(6, size)  # Minimalna wartość 6
    font = QFont(family, safe_size)
    if bold:
        font.setBold(True)
    return font


class FolderView(QWidget):
    def __init__(self, parent=None, folders=None, on_open_folder=None, on_back=None):
        super().__init__(parent)
        self.setObjectName("folderView")
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(8, 12, 8, 12)
        self.main_layout.setSpacing(8)
        
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        self.on_open_folder = on_open_folder
        self.on_back = on_back
        self.current_label = None
        self._fs_watcher = None
        self.view_mode = "grid"
        self._icon_provider = QFileIconProvider()
        self._sort_desc = False
        self._view_created_at = 0.0

        # Ustawienia miniaturek
        self._icon_size = QSize(96, 96)
        self._icon_cache = {}
        self._pdf_dpi = 200

        if folders is None:
            folders = [
                {"label": "Zeszyt", "folder_path": os.path.join(os.path.expanduser("~"), "Desktop")},
                {"label": "Zdjęcia", "folder_path": os.path.join(os.path.expanduser("~"), "Pictures")},
                {"label": "Inne", "folder_path": os.path.join(os.path.expanduser("~"), "Desktop")},
            ]
        self.folders = folders
        self.init_view()

    # --- Widok startowy z przyciskami folderów ---
    def init_view(self):
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(16)
        for f in self.folders:
            row.addWidget(self.create_folder_button(f["label"], f.get("folder_path")))
        self.main_layout.addLayout(row)

    def create_folder_button(self, label, folder_path):
        btn = QPushButton(label)
        btn.setObjectName("folderButton")
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setFlat(True)
        btn.setFixedSize(140, 40)
        btn.setToolTip(folder_path or "")
        btn.setStyleSheet("""
            QPushButton#folderButton {
                background: transparent;
                color:#222;
                border-radius:10px;
                padding:6px 10px;
                font-size:14px;
                font-weight:600;
            }
            QPushButton#folderButton:hover {
                background:#f2f5ff;
                color:#3960f5;
            }
        """)

        def on_click():
            if callable(self.on_open_folder):
                self.on_open_folder(folder_path, label)
            else:
                self.show_folder_view(folder_path, label)
        btn.clicked.connect(on_click)
        return btn

    # --- Główny widok folderu ---
    def show_folder_view(self, folder_path, label):
        self.setUpdatesEnabled(False)
        try:
            self.clear_layout(self.main_layout)
            self.current_label = label

            # Nagłówek z powrotem i nazwą folderu
            header_row = QHBoxLayout()
            header_row.setContentsMargins(8, 0, 8, 0)
            
            # Przycisk powrót
            back_btn = QPushButton("← Powrót")
            back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            back_btn.setFlat(True)
            back_btn.setStyleSheet(
                "QPushButton { background:transparent; border:none; font-size:15px; color:#3960f5; } "
                "QPushButton:hover { text-decoration:underline; }"
            )
            back_btn.clicked.connect(self.handle_back)
            header_row.addWidget(back_btn, alignment=Qt.AlignmentFlag.AlignLeft)
            
            # Nazwa folderu (wyśrodkowana)
            folder_label = QLabel(label)
            folder_label.setStyleSheet("font-size: 20px; font-weight: 600; color: #1f2a4a;")
            folder_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            header_row.addWidget(folder_label, stretch=1, alignment=Qt.AlignmentFlag.AlignCenter)
            
            # Spacer po prawej dla symetrii
            header_row.addSpacerItem(QSpacerItem(back_btn.sizeHint().width(), 0, QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Minimum))
            
            self.main_layout.addLayout(header_row)

            # Pasek akcji
            actions_row = QHBoxLayout()
            actions_row.setContentsMargins(8, 0, 8, 0)
            actions_row.setSpacing(12)

            # Kontener na przyciski toggle (prosty, własny styl)
            toggle_container = QFrame()
            toggle_container.setStyleSheet("""
                QFrame {
                    background-color: rgba(57, 96, 245, 0.08);
                    border-radius: 12px;
                    padding: 4px;
                }
            """)
            toggle_layout = QHBoxLayout(toggle_container)
            toggle_layout.setContentsMargins(4, 4, 4, 4)
            toggle_layout.setSpacing(4)

            # Proste przyciski QPushButton
            self.btn_grid = QPushButton("Miniatury")
            self.btn_grid.setCheckable(True)
            self.btn_grid.setChecked(self.view_mode == "grid")
            self.btn_grid.setCursor(Qt.CursorShape.PointingHandCursor)
            self.btn_grid.setFlat(True)
            self.btn_grid.setMinimumWidth(90)
            self.btn_grid.clicked.connect(lambda: self.switch_view("grid"))

            self.btn_list = QPushButton("Lista")
            self.btn_list.setCheckable(True)
            self.btn_list.setChecked(self.view_mode == "table")
            self.btn_list.setCursor(Qt.CursorShape.PointingHandCursor)
            self.btn_list.setFlat(True)
            self.btn_list.setMinimumWidth(70)
            self.btn_list.clicked.connect(lambda: self.switch_view("table"))

            # Prosty, czytelny styl
            btn_style = """
                QPushButton {
                    background-color: transparent;
                    color: #415165;
                    border: none;
                    border-radius: 10px;
                    padding: 6px 14px;
                    font-size: 14px;
                    font-weight: 600;
                    min-height: 32px;
                }
                QPushButton:hover:!checked {
                    background-color: rgba(57, 96, 245, 0.12);
                }
                QPushButton:checked {
                    background-color: #4c6ef5;
                    color: #ffffff;
                }
            """
            self.btn_grid.setStyleSheet(btn_style)
            self.btn_list.setStyleSheet(btn_style)

            toggle_layout.addWidget(self.btn_grid)
            toggle_layout.addWidget(self.btn_list)

            actions_row.addWidget(toggle_container)
            actions_row.addStretch(1)
            
            # Kontener na przyciski akcji (taki sam styl jak toggle)
            actions_container = QFrame()
            actions_container.setStyleSheet("""
                QFrame {
                    background-color: rgba(57, 96, 245, 0.08);
                    border-radius: 12px;
                    padding: 4px;
                }
            """)
            actions_layout = QHBoxLayout(actions_container)
            actions_layout.setContentsMargins(4, 4, 4, 4)
            actions_layout.setSpacing(4)
            
            # Przycisk dodawania pliku
            add_btn = QPushButton("+ Dodaj")
            add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            add_btn.setFlat(True)
            add_btn.setMinimumWidth(75)
            add_btn.setStyleSheet("""
                QPushButton {
                    background-color: transparent;
                    color: #415165;
                    border: none;
                    border-radius: 10px;
                    padding: 6px 12px;
                    font-size: 13px;
                    font-weight: 600;
                    min-height: 32px;
                }
                QPushButton:hover {
                    background-color: rgba(57, 96, 245, 0.12);
                }
            """)
            add_btn.clicked.connect(lambda: self.add_file_to_folder_delayed(folder_path))
            
            # Przycisk sortowania
            sort_btn = QPushButton("↑↓ Sortuj")
            sort_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            sort_btn.setFlat(True)
            sort_btn.setMinimumWidth(80)
            sort_btn.setStyleSheet("""
                QPushButton {
                    background-color: transparent;
                    color: #415165;
                    border: none;
                    border-radius: 10px;
                    padding: 6px 12px;
                    font-size: 13px;
                    font-weight: 600;
                    min-height: 32px;
                }
                QPushButton:hover {
                    background-color: rgba(57, 96, 245, 0.12);
                }
            """)
            sort_btn.clicked.connect(self.toggle_sort_direction_delayed)
            
            actions_layout.addWidget(add_btn)
            actions_layout.addWidget(sort_btn)
            
            actions_row.addWidget(actions_container)
            self.main_layout.addLayout(actions_row)

            # Kontenery widoków
            self.view_container = QVBoxLayout()
            self.view_container.setContentsMargins(0, 0, 0, 0)
            self.files_table = self.create_files_table()
            self.files_grid = self.create_files_grid()

            if self.view_mode == "grid":
                self.files_table.hide()
            else:
                self.files_grid.hide()

            self.view_container.addWidget(self.files_table, 1)
            self.view_container.addWidget(self.files_grid, 1)
            self.main_layout.addLayout(self.view_container)

            self._view_created_at = time.monotonic()
            self.refresh_current_view()
            self._setup_fs_watcher()
        finally:
            self.setUpdatesEnabled(True)

    def handle_back(self):
        if callable(self.on_back):
            self.on_back()

    # --- Interakcja myszką poza elementami selekcji ---
    def mousePressEvent(self, event):
        try:
            if hasattr(self, "files_table") and self.files_table.isVisible():
                self.files_table.clearSelection()
            if hasattr(self, "files_grid") and self.files_grid.isVisible():
                self.files_grid.clearSelection()
        except Exception:
            pass
        super().mousePressEvent(event)
    
    def toggle_sort_direction(self):
        self._sort_desc = not self._sort_desc
        self.refresh_current_view()
    
    def toggle_sort_direction_delayed(self):
        """Sortowanie z opóźnieniem aby uniknąć podwójnego kliknięcia"""
        if time.monotonic() - self._view_created_at < 0.15:
            return
        self.toggle_sort_direction()
    
    def add_file_to_folder_delayed(self, folder_path):
        """Dodawanie pliku z opóźnieniem aby uniknąć podwójnego kliknięcia"""
        if time.monotonic() - self._view_created_at < 0.25:
            return
        self.add_file_to_folder(folder_path)

    @staticmethod
    def _is_safe_path(path):
        """Sprawdz czy sciezka jest bezpieczna (bez path traversal)"""
        if not path:
            return False
        try:
            normalized = os.path.normpath(path)
            if ".." in normalized:
                return False
            dangerous_chars = ['<', '>', '"', '|', '?', '*', '\x00']
            if any(char in path for char in dangerous_chars):
                return False
            return True
        except Exception:
            return False

    @staticmethod
    def _sanitize_filename(filename):
        """Sanityzuj nazwę pliku usuwając niebezpieczne znaki"""
        if not filename:
            return "untitled"
        # Usuń niebezpieczne znaki
        safe_name = re.sub(r'[<>:"|?*\x00-\x1f]', '', filename)
        # Usuń wielokrotne spacje
        safe_name = re.sub(r'\s+', ' ', safe_name).strip()
        # Ogranicz długość
        if len(safe_name) > 200:
            name, ext = os.path.splitext(safe_name)
            safe_name = name[:200-len(ext)] + ext
        return safe_name or "untitled"

    def _sorted_files(self, files):
        """Sortuj pliki: najpierw ulubione, potem alfabetycznie."""
        try:
            def key(p):
                return (0 if is_favorite(p) else 1, os.path.basename(p).lower())
            sorted_files = sorted(files, key=key)
            return list(reversed(sorted_files)) if self._sort_desc else sorted_files
        except Exception:
            return files

    # --- Dodawanie istniejącego pliku ---
    def add_file_to_folder(self, folder_path):
        start_dir = folder_path if folder_path and os.path.isdir(folder_path) else os.path.expanduser("~")
        file_path, _ = QFileDialog.getOpenFileName(
            self, 
            "Wybierz plik do dodania", 
            start_dir, 
            "Wszystkie pliki (*.*);;Dokumenty tekstowe (*.txt *.docx *.pdf);;Obrazy (*.png *.jpg *.jpeg *.bmp *.gif);;Wideo (*.mp4 *.mov *.mkv *.avi);;Audio (*.mp3 *.flac *.m4a *.ogg)"
        )
        if not file_path:
            return
        
        # Walidacja bezpieczeństwa
        if not self._is_safe_path(file_path):
            QMessageBox.critical(self, "Błąd", "Nieprawidłowa ścieżka pliku.")
            return
        
        if not os.path.exists(file_path):
            QMessageBox.critical(self, "Błąd", "Wybrany plik nie istnieje.")
            return
        
        # Sprawdź rozmiar pliku
        try:
            file_size = os.path.getsize(file_path)
            if file_size > MAX_FILE_SIZE:
                QMessageBox.critical(
                    self, 
                    "Błąd", 
                    f"Plik jest zbyt duży ({file_size // (1024*1024)} MB).\nMaksymalny rozmiar: {MAX_FILE_SIZE // (1024*1024)} MB"
                )
                return
        except Exception as e:
            QMessageBox.critical(self, "Błąd", f"Nie można odczytać rozmiaru pliku: {e}")
            return
        
        label = self.current_label or "Inne"
        
        # Sanityzuj nazwę pliku
        original_filename = os.path.basename(file_path)
        safe_filename = self._sanitize_filename(original_filename)
        if safe_filename != original_filename:
            reply = QMessageBox.question(
                self,
                "Zmiana nazwy pliku",
                f"Nazwa pliku zawiera niedozwolone znaki.\n\nOryginalna nazwa: {original_filename}\nBezpieczna nazwa: {safe_filename}\n\nKontynuować?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes
            )
            if reply == QMessageBox.StandardButton.No:
                return
        
        ext = os.path.splitext(file_path)[1].lower()
        
        # Sprawdź czy plik może zawierać obrazy (Word, PDF)
        if ext in {".docx", ".pdf"}:
            reply = QMessageBox.question(
                self,
                "Konwersja pliku",
                f"Wykryto plik {ext.upper()}.\n\n"
                "Czy chcesz skonwertować plik do wersji tekstowej (bez obrazów)?\n\n"
                "• TAK - konwertuj do formatu JSON (tylko tekst)\n"
                "• NIE - zachowaj oryginalny plik bez zmian",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes
            )
            
            if reply == QMessageBox.StandardButton.No:
                # Użytkownik wybrał zachowanie oryginału - skopiuj bez konwersji
                try:
                    import shutil
                    from pathlib import Path
                    target_folder = os.path.join(NOTES_DIR, label)
                    os.makedirs(target_folder, exist_ok=True)
                    
                    src = Path(file_path)
                    dest_path = os.path.join(target_folder, src.name)
                    
                    # Sprawdź czy plik już istnieje
                    if os.path.exists(dest_path):
                        base = src.stem
                        counter = 1
                        while os.path.exists(dest_path):
                            new_name = f"{base}_{counter}{src.suffix}"
                            dest_path = os.path.join(target_folder, new_name)
                            counter += 1
                    
                    shutil.copy(file_path, dest_path)
                    self._invalidate_icon(dest_path)
                    
                    QMessageBox.information(
                        self, 
                        "Dodano plik", 
                        f"Oryginalny plik '{os.path.basename(dest_path)}' został dodany do folderu '{label}'"
                    )
                    
                    self.refresh_current_view()
                    self._setup_fs_watcher()
                    return
                    
                except Exception as e:
                    QMessageBox.critical(self, "Błąd", f"Nie udało się skopiować pliku:\n{e}")
                    return
        
        # Standardowa konwersja
        try:
            saved_path = add_existing_note_file(label, file_path)
            self._invalidate_icon(saved_path)
            
            original_name = os.path.basename(file_path)
            saved_name = os.path.basename(saved_path)
            
            if saved_name.endswith('.bgh'):
                msg = f"Plik '{original_name}' został przekonwertowany i dodany jako '{saved_name}'"
            else:
                msg = f"Plik '{saved_name}' został dodany do folderu '{label}'"
            
            QMessageBox.information(self, "Dodano plik", msg)
            
            self.refresh_current_view()
            self._setup_fs_watcher()
            
        except Exception as e:
            error_msg = str(e)
            if "Błąd konwersji" in error_msg:
                QMessageBox.warning(
                    self, 
                    "Ostrzeżenie", 
                    f"{error_msg}\n\nPlik został dodany, ale nie udało się go przekonwertować na format JSON."
                )
                self.refresh_current_view()
                self._setup_fs_watcher()
            else:
                QMessageBox.critical(self, "Błąd", f"Nie udało się dodać pliku:\n{error_msg}")

    # --- Klasy pomocnicze dla tabeli ---
    class FilesTable(QTableWidget):
        def focusOutEvent(self, event):
            try:
                self.clearSelection()
            except Exception:
                pass
            super().focusOutEvent(event)
        def mousePressEvent(self, event):
            idx = self.indexAt(event.pos())
            if not idx.isValid():
                self.clearSelection()
            super().mousePressEvent(event)
        def resizeEvent(self, event):
            try:
                rect = self.rect()
                path = QPainterPath()
                path.addRoundedRect(QRectF(rect), 12.0, 12.0)
                self.setMask(QRegion(path.toFillPolygon().toPolygon()))
            except Exception:
                pass
            super().resizeEvent(event)

    class ColumnDividerDelegate(QStyledItemDelegate):
        def __init__(self, parent=None, last_column_index=None, color=QColor(0, 0, 0, 40)):
            super().__init__(parent)
            self.last_column_index = last_column_index
            self.pen = QPen(color)
            self.pen.setCosmetic(True)
        def paint(self, painter, option, index):
            super().paint(painter, option, index)
            if self.last_column_index is None or index.column() < self.last_column_index:
                old_pen = painter.pen()
                painter.setPen(self.pen)
                x = float(option.rect.right()) - 0.5
                painter.drawLine(QLineF(x, option.rect.top(), x, option.rect.bottom()))
                painter.setPen(old_pen)

    class HeaderView(QHeaderView):
        def __init__(self, parent=None, color=QColor(0, 0, 0, 40)):
            super().__init__(Qt.Orientation.Horizontal, parent)
            self._pen = QPen(color)
            self._pen.setCosmetic(True)
        def paintSection(self, painter, rect, logicalIndex):
            super().paintSection(painter, rect, logicalIndex)
            if logicalIndex < (self.model().columnCount() - 1):
                old = painter.pen()
                painter.setPen(self._pen)
                x = float(rect.right()) - 0.5
                painter.drawLine(QLineF(x, rect.top(), x, rect.bottom()))
                painter.setPen(old)

    # --- Tabela plików ---
    def create_files_table(self):
        table = self.FilesTable()
        table.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        table.setColumnCount(5)
        table.setHorizontalHeaderLabels(["★", "Nazwa", "Rozszerzenie", "Dodano", "Zmodyfikowano"])
        table.verticalHeader().setVisible(False)
        table.setShowGrid(False)
        table.setAlternatingRowColors(True)
        table.setSelectionBehavior(table.SelectionBehavior.SelectRows)
        table.setSelectionMode(table.SelectionMode.SingleSelection)
        table.setEditTriggers(table.EditTrigger.NoEditTriggers)
        table.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        table.setStyleSheet("""
            QTableWidget {
                background:white;
                border:0.5px solid rgba(0,0,0,0.08);
                border-radius:12px;
                outline:none;
            }
            QHeaderView::section {
                background:#f3f6ff;
                border:none;
                padding:8px;
                font-weight:600;
            }
            QHeaderView::section:first { border-top-left-radius:12px; }
            QHeaderView::section:last  { border-top-right-radius:12px; }
            QTableWidget::item {
                padding:6px 8px;
                border:none;
            }
            QTableWidget::item:selected {
                background:#e6edff;
                color:#3960f5;
            }
            QTableCornerButton::section { background:#f3f6ff; border:none; }
        """)
        header = self.HeaderView(parent=table)
        table.setHorizontalHeader(header)
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Interactive)
        header.setMinimumSectionSize(100)
        table.setColumnWidth(2, 120)
        table.setColumnWidth(3, 170)
        table.setColumnWidth(4, 170)
        table.setItemDelegate(self.ColumnDividerDelegate(parent=table, last_column_index=4))
        table.cellClicked.connect(self.on_table_cell_clicked)
        table.itemDoubleClicked.connect(self.on_table_item_double_clicked)
        
        # Context menu dla tabeli
        table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        table.customContextMenuRequested.connect(lambda pos: self._handle_table_context_menu(pos, table))
        
        return table

    # --- Widok miniatur (grid) ---
    def create_files_grid(self):
        grid = QListWidget()
        grid.setObjectName("filesGrid")
        grid.setViewMode(QListView.ViewMode.IconMode)
        grid.setMovement(QListView.Movement.Static)
        grid.setResizeMode(QListView.ResizeMode.Adjust)
        grid.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        # Rozmiar kafelków - mniejsza wysokość
        self._tile_preview_size = QSize(140, 160)
        grid.setIconSize(self._tile_preview_size)
        # Kompaktowa stopka
        grid.setGridSize(QSize(self._tile_preview_size.width() + 16, self._tile_preview_size.height() + 28))
        grid.setSpacing(8)
        
        grid.setUniformItemSizes(True)
        grid.setMouseTracking(True)
        grid.setStyleSheet("""
            QListWidget#filesGrid {
                background:white;
                border:0.5px solid rgba(0,0,0,0.08);
                border-radius:12px;
                padding:12px;
                outline:none;
            }
            QListWidget#filesGrid::item {
                background:white;
                border:0.5px solid #e1e6f5;
                border-radius:12px;
                margin:4px;
                padding:6px 4px 8px 4px;
            }
            QListWidget#filesGrid::item:hover {
                background:#f7faff;
                border:0.5px solid #d4dbef;
            }
            QListWidget#filesGrid::item:selected {
                background:#e6edff;
                border:0.5px solid #3960f5;
                color:#3960f5;
            }
        """)
        
        class GridTileDelegate(QStyledItemDelegate):
            def __init__(self, parent: QListWidget, preview_size: QSize):
                super().__init__(parent)
                self.preview_size = preview_size
                self.title_font = safe_font("Segoe UI", 9, bold=True)
                self.star_font = safe_font("Segoe UI", 12)
                
            def sizeHint(self, option, index):
                base = super().sizeHint(option, index)
                return QSize(max(base.width(), self.preview_size.width()+24), max(base.height(), self.preview_size.height()+40))
                
            def paint(self, painter: QPainter, option, index):
                painter.save()
                rect = option.rect.adjusted(6, 6, -6, -6)
                
                # Kolor tła
                bg = QColor("white")
                if option.state & QStyle.StateFlag.State_Selected:
                    bg = QColor(230, 237, 255)
                elif option.state & QStyle.StateFlag.State_MouseOver:
                    bg = QColor(247, 250, 255)
                painter.fillRect(rect, bg)
                
                # Stopka na nazwę
                footer_h = 22
                preview_rect = rect.adjusted(0, 4, 0, -footer_h - 4)
                
                # Pobierz podgląd
                deco = index.data(Qt.ItemDataRole.DecorationRole)
                ext = (index.data(Qt.ItemDataRole.UserRole + 1) or "").lower()
                pm = None
                
                if isinstance(deco, QIcon):
                    bigger = QSize(int(self.preview_size.width()*1.4), int(self.preview_size.height()*1.4))
                    pm = deco.pixmap(bigger)
                    pm = FolderView._scale_crop_pixmap(pm, self.preview_size)
                elif isinstance(deco, QPixmap):
                    pm = deco
                    pm = FolderView._scale_crop_pixmap(pm, self.preview_size)
                
                # Narysuj podgląd
                if pm and not pm.isNull():
                    shrink = 0.92
                    dw = max(1, int(pm.width() * shrink))
                    dh = max(1, int(pm.height() * shrink))
                    draw_pm = pm.scaled(dw, dh, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
                    ix = preview_rect.x() + (preview_rect.width() - draw_pm.width())//2  
                    iy = preview_rect.y() + (preview_rect.height() - draw_pm.height())//2 
                    painter.drawPixmap(ix, iy, draw_pm)
                
                # Ikona ulubione (gwiazdka w prawym górnym rogu)
                file_path = index.data(Qt.ItemDataRole.UserRole)
                fav = bool(file_path and is_favorite(file_path))
                star_rect = QRectF(rect.right()-22, rect.top()+6, 16, 16)
                painter.setFont(self.star_font)
                painter.setPen(QColor(240, 180, 0) if fav else QColor(160, 160, 160))
                painter.drawText(star_rect, int(Qt.AlignmentFlag.AlignCenter), "★")

                # Narysuj nazwę
                name = index.data(Qt.ItemDataRole.DisplayRole) or ""
                footer_top = rect.bottom() - footer_h
                painter.setPen(QColor(25,25,25))
                painter.setFont(self.title_font)
                
                available_width = rect.width() - 16
                metrics = painter.fontMetrics()
                elided_name = metrics.elidedText(name, Qt.TextElideMode.ElideRight, int(available_width))
                
                name_rect = QRectF(rect.x()+8, footer_top+4, rect.width()-16, 18)
                painter.drawText(
                    name_rect,
                    int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
                    elided_name
                )
                painter.restore()
        grid.setItemDelegate(GridTileDelegate(grid, self._tile_preview_size))
        grid.mousePressEvent = self._grid_mouse_press_wrapper(grid.mousePressEvent)
        grid.itemDoubleClicked.connect(self.on_file_double_clicked)
        
        # Context menu dla grid
        grid.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        grid.customContextMenuRequested.connect(lambda pos: self._handle_grid_context_menu(pos, grid))
        
        return grid

    def _grid_mouse_press_wrapper(self, original):
        def handler(event):
            pos = event.pos()
            item = self.files_grid.itemAt(pos)
            if item:
                rect = self.files_grid.visualItemRect(item).adjusted(6, 6, -6, -6)
                star_rect = QRectF(rect.right()-22, rect.top()+6, 16, 16)
                
                from PyQt6.QtCore import QPointF
                if star_rect.contains(QPointF(pos)):
                    path = item.data(Qt.ItemDataRole.UserRole)
                    now_fav = toggle_favorite(path)
                    # Odśwież tylko pozycję
                    self._update_grid_item(path)
                    return
            return original(event)
        return handler

    # --- Odświeżenie tabeli ---
    def refresh_files_table(self):
        if not hasattr(self, "files_table"):
            return
        try:
            files = get_notes_in_folder(self.current_label or "")
        except Exception:
            files = []
        files = self._sorted_files(files)
        self.files_table.setRowCount(len(files))
        for row, fpath in enumerate(files):
            fname = os.path.basename(fpath)
            stem, ext = os.path.splitext(fname)
            ext = ext.lstrip(".")
            try:
                stat = os.stat(fpath)
                created = datetime.datetime.fromtimestamp(getattr(stat, "st_ctime", stat.st_mtime))
                modified = datetime.datetime.fromtimestamp(stat.st_mtime)
                created_str = created.strftime("%Y-%m-%d %H:%M")
                modified_str = modified.strftime("%Y-%m-%d %H:%M")
            except Exception:
                created_str = "-"; modified_str = "-"
            fav_item = QTableWidgetItem("★" if is_favorite(fpath) else "☆")
            fav_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            fav_item.setData(Qt.ItemDataRole.UserRole, fpath)
            self.files_table.setItem(row, 0, fav_item)
            name_item = QTableWidgetItem(stem)
            name_item.setData(Qt.ItemDataRole.UserRole, fpath)
            self.files_table.setItem(row, 1, name_item)
            ext_item = QTableWidgetItem(ext or "-")
            ext_item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            self.files_table.setItem(row, 2, ext_item)
            c_item = QTableWidgetItem(created_str)
            c_item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            self.files_table.setItem(row, 3, c_item)
            m_item = QTableWidgetItem(modified_str)
            m_item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            self.files_table.setItem(row, 4, m_item)
        try:
            self.files_table.setColumnWidth(3, max(self.files_table.columnWidth(3), 170))
            self.files_table.setColumnWidth(4, max(self.files_table.columnWidth(4), 170))
        except Exception:
            pass
        self.files_table.resizeRowsToContents()
        self._setup_fs_watcher(files)

    def on_table_cell_clicked(self, row, column):
        if column == 0:
            item = self.files_table.item(row, 0)
            if not item:
                return
            path = item.data(Qt.ItemDataRole.UserRole)
            now_fav = toggle_favorite(path)
            item.setText("★" if now_fav else "☆")
            # Przesortuj i odśwież
            self.refresh_current_view()

    # --- Odświeżenie gridu ---
    def refresh_files_grid(self):
        if not hasattr(self, "files_grid"):
            return
        try:
            files = get_notes_in_folder(self.current_label or "")
        except Exception:
            files = []
        files = self._sorted_files(files)
        self.files_grid.setUpdatesEnabled(False)
        self.files_grid.clear()
        for fpath in files:
            # Wyświetl nazwę bez rozszerzenia
            full_name = os.path.basename(fpath)
            name_without_ext = os.path.splitext(full_name)[0]
            ext = os.path.splitext(fpath)[1].lower()
            
            item = QListWidgetItem()
            # Ustaw dekorację jako QPixmap w rozmiarze kafelka, aby wypełniał ramkę
            preview_pm = self._get_preview_pixmap(fpath, self._tile_preview_size)
            if preview_pm and not preview_pm.isNull():
                item.setData(Qt.ItemDataRole.DecorationRole, preview_pm)
            else:
                # fallback
                item.setIcon(self._get_icon(fpath))
            
            # Wyświetl tylko nazwę bez rozszerzenia
            item.setText(name_without_ext)
            item.setData(Qt.ItemDataRole.UserRole, fpath)
            # zapisz rozszerzenie do różnicowania skalowania w delegacie
            item.setData(Qt.ItemDataRole.UserRole + 1, ext)
            # Tooltip z pełną nazwą (bez ścieżki)
            item.setToolTip(full_name)
            # Rozmiar zgodny z delegatem
            item.setSizeHint(self.files_grid.gridSize())
            self.files_grid.addItem(item)
        self.files_grid.setUpdatesEnabled(True)
        self._setup_fs_watcher(files)

    def _get_preview_pixmap(self, path, size):
        """Wygeneruj podgląd pliku"""
        ext = os.path.splitext(path)[1].lower()
        try:
            # Pliki BGH (notatki)
            if ext == ".bgh":
                try:
                    import json
                    with open(path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    content = data.get("tresc", "")
                    if not content:
                        content = data.get("tytul", os.path.basename(path))
                    lines = content.split("\n")[:120]
                    text = "\n".join(lines)
                    W = max(100, int(size.width() * 3))
                    H = max(100, int(size.height() * 3))
                    if W <= 0 or H <= 0:
                        return QPixmap()
                    img = QImage(W, H, QImage.Format.Format_ARGB32)
                    img.fill(QColor("white"))
                    p = QPainter(img)
                    p.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
                    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
                    title_font = safe_font("Segoe UI", 8, bold=True)
                    body_font = safe_font("Segoe UI", 7)
                    p.setFont(title_font)
                    p.setPen(QColor(0, 0, 0))
                    p.drawText(QRectF(10, 5, W - 20, 22), int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter), data.get("tytul", os.path.basename(path)))
                    p.setFont(body_font)
                    p.setPen(QColor(35, 35, 35))
                    p.drawText(QRectF(10, 28, W - 20, H - 36), int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop | Qt.TextFlag.TextWordWrap), text)
                    p.end()
                    pm = QPixmap.fromImage(img)
                    return FolderView._scale_crop_pixmap_left(pm, size)
                except Exception:
                    pass
            
            # Obrazy
            if ext in {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp"}:
                original = QPixmap(path)
                if original.isNull():
                    return QPixmap()
                return FolderView._scale_crop_pixmap(original, size)
            
            # Pliki tekstowe
            if ext in {".txt", ".md", ".log", ".ini", ".cfg", ".csv"}:
                try:
                    lines = []
                    with open(path, "r", encoding="utf-8", errors="replace") as f:
                        for _ in range(120):
                            line = f.readline()
                            if not line:
                                break
                            lines.append(line.rstrip("\n\r"))
                    text = "\n".join(lines)
                    W = max(100, int(size.width() * 3))
                    H = max(100, int(size.height() * 3))
                    if W <= 0 or H <= 0:
                        return QPixmap()
                    img = QImage(W, H, QImage.Format.Format_ARGB32)
                    img.fill(QColor("white"))
                    p = QPainter(img)
                    p.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
                    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
                    title_font = safe_font("Segoe UI", 8, bold=True)
                    body_font = safe_font("Segoe UI", 7)
                    p.setFont(title_font)
                    p.setPen(QColor(0, 0, 0))
                    p.drawText(QRectF(10, 5, W - 20, 22), int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter), os.path.basename(path))
                    p.setFont(body_font)
                    p.setPen(QColor(35, 35, 35))
                    p.drawText(QRectF(10, 28, W - 20, H - 36), int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop | Qt.TextFlag.TextWordWrap), text)
                    p.end()
                    pm = QPixmap.fromImage(img)
                    return FolderView._scale_crop_pixmap_left(pm, size)
                except Exception:
                    pass
            
            # PDF
            if ext == ".pdf" and HAS_PYMUPDF:
                doc = None
                try:
                    doc = fitz.open(path)
                    if doc.page_count == 0:
                        return QPixmap()
                    page = doc.load_page(0)
                    scale = self._pdf_dpi / 72.0
                    mat = fitz.Matrix(scale, scale)
                    pix = page.get_pixmap(matrix=mat, alpha=True)
                    fmt = getattr(QImage.Format, "Format_RGBA8888", None) or QImage.Format.Format_ARGB32
                    img = QImage(pix.samples, pix.width, pix.height, pix.stride, fmt)
                    if img.isNull():
                        return QPixmap()
                    img = img.copy()
                    pm = QPixmap.fromImage(img)
                    pm = FolderView._crop_horizontal_whitespace(pm)
                    return FolderView._scale_crop_pixmap_center(pm, size)
                finally:
                    if doc:
                        try:
                            doc.close()
                        except Exception:
                            pass
            
            # Wideo
            if ext in {".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v"} and HAS_OPENCV:
                try:
                    cap = cv2.VideoCapture(path)
                    ok, frame = cap.read()
                    cap.release()
                    if not ok or frame is None:
                        return QPixmap()
                    frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    h, w, ch = frame.shape
                    bytes_per_line = ch * w
                    img = QImage(frame.data, w, h, bytes_per_line, QImage.Format.Format_RGB888).copy()
                    pm = QPixmap.fromImage(img)
                    return FolderView._scale_crop_pixmap(pm, size)
                except Exception:
                    return QPixmap()
            
            # Audio
            if ext in {".mp3", ".flac", ".m4a", ".ogg", ".opus"} and HAS_MUTAGEN:
                try:
                    mf = MutagenFile(path)
                    cover_data = None
                    if mf and hasattr(mf, "tags") and mf.tags:
                        for k, v in mf.tags.items():
                            if str(k).startswith("APIC"):
                                cover_data = v.data
                                break
                    if not cover_data and mf and hasattr(mf, "pictures"):
                        pics = mf.pictures or []
                        if pics:
                            cover_data = pics[0].data
                    if cover_data:
                        img = QImage.fromData(cover_data)
                        if not img.isNull():
                            pm = QPixmap.fromImage(img)
                            return FolderView._scale_crop_pixmap(pm, size)
                except Exception:
                    return QPixmap()
            
            # Inne - systemowa ikona
            sys_icon = self._get_system_icon(path)
            pm = sys_icon.pixmap(size)
            return FolderView._scale_crop_pixmap(pm, size)
        except Exception:
            return QPixmap()

    @staticmethod
    def _scale_crop_pixmap(pm, target):
        """Skaluj i przytnij obraz - wyśrodkowany"""
        if pm.isNull() or target.isEmpty():
            return QPixmap()
        tw, th = target.width(), target.height()
        sw, sh = pm.width(), pm.height()
        if sw == 0 or sh == 0:
            return QPixmap()
        scale = max(tw / sw, th / sh)
        nw, nh = int(sw * scale), int(sh * scale)
        scaled = pm.scaled(nw, nh, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
        x = max(0, (nw - tw) // 2)
        y = max(0, (nh - th) // 2)
        return scaled.copy(x, y, min(tw, scaled.width()-x), min(th, scaled.height()-y))

    @staticmethod
    def _scale_crop_pixmap_left(pm, target):
        """Skaluj i przytnij - wyrównanie do lewej"""
        if pm.isNull() or target.isEmpty():
            return QPixmap()
        tw, th = target.width(), target.height()
        sw, sh = pm.width(), pm.height()
        if sw == 0 or sh == 0:
            return QPixmap()
        scale = max(tw / sw, th / sh)
        nw, nh = int(sw * scale), int(sh * scale)
        scaled = pm.scaled(nw, nh, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
        x = 0
        y = max(0, (nh - th) // 2)
        return scaled.copy(x, y, min(tw, scaled.width()-x), min(th, scaled.height()-y))

    @staticmethod
    def _scale_crop_pixmap_center(pm, target):
        """Skaluj i przytnij - wyśrodkowany pionowo"""
        if pm.isNull() or target.isEmpty():
            return QPixmap()
        tw, th = target.width(), target.height()
        sw, sh = pm.width(), pm.height()
        if sw == 0 or sh == 0:
            return QPixmap()
        scale = max(tw / sw, th / sh)
        nw, nh = int(sw * scale), int(sh * scale)
        scaled = pm.scaled(nw, nh, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
        x = max(0, (nw - tw) // 2)
        y = max(0, (nh - th) // 2)
        return scaled.copy(x, y, min(tw, scaled.width()-x), min(th, scaled.height()-y))

    @staticmethod
    def _crop_horizontal_whitespace(pm, threshold=245):
        """Usuń białe marginesy po bokach"""
        if pm.isNull():
            return pm
        img = pm.toImage().convertToFormat(QImage.Format.Format_RGB32)
        w = img.width()
        h = img.height()
        if w == 0 or h == 0:
            return pm
        
        # Funkcja sprawdza czy kolumna ma treść (nie jest biała)
        def col_has_content(x: int) -> bool:
            for y in range(0, h, max(1, h // 200)):
                c = QColor(img.pixel(x, y))
                if c.red() < threshold or c.green() < threshold or c.blue() < threshold:
                    return True
            return False
        
        # Znajdź lewa krawędź
        left = 0
        while left < w and not col_has_content(left):
            left += 1
        
        # Znajdź prawą krawędź
        right = w - 1
        while right > left and not col_has_content(right):
            right -= 1
        
        if right <= left:
            return pm
        return pm.copy(left, 0, right - left + 1, h)

    def _get_icon(self, path):
        """Zwróć ikonę dla pliku"""
        ext = os.path.splitext(path)[1].lower()
        if ext in {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp"}:
            return self._thumbnail_icon(path)
        if ext == ".pdf":
            return self._pdf_thumbnail_icon(path)
        if ext in {".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v"}:
            return self._video_thumbnail_icon(path)
        if ext in {".txt", ".md", ".csv", ".json", ".xml", ".yml", ".yaml", ".log", ".ini", ".cfg", ".bgh"}:
            return self._text_thumbnail_icon(path)
        if ext in {".mp3", ".flac", ".m4a", ".ogg", ".opus"}:
            return self._audio_thumbnail_icon(path)
        return self._get_system_icon(path)

    def _get_system_icon(self, path):
        """Pobierz systemową ikonę pliku"""
        if path in self._icon_cache:
            return self._icon_cache[path]
        icon = self._icon_provider.icon(QFileInfo(path))
        self._icon_cache[path] = icon
        return icon

    def _thumbnail_icon(self, path):
        """Miniatura obrazu"""
        cache_key = f"thumb::{path}::{self._icon_size.width()}x{self._icon_size.height()}"
        pix = QPixmapCache.find(cache_key)
        if pix and not pix.isNull():
            return QIcon(pix)
        original = QPixmap(path)
        if original.isNull():
            return self._get_system_icon(path)
        scaled = original.scaled(self._icon_size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        QPixmapCache.insert(cache_key, scaled)
        return QIcon(scaled)

    def _pdf_thumbnail_icon(self, path):
        """Miniatura PDF"""
        if not HAS_PYMUPDF:
            return self._get_system_icon(path)
        cache_key = f"pdfthumb::{path}::{self._icon_size.width()}x{self._icon_size.height()}::dpi{self._pdf_dpi}"
        cached = QPixmapCache.find(cache_key)
        if cached and not cached.isNull():
            return QIcon(cached)
        doc = None
        try:
            doc = fitz.open(path)
            if doc.page_count == 0:
                return self._get_system_icon(path)
            page = doc.load_page(0)
            scale = self._pdf_dpi / 72.0
            mat = fitz.Matrix(scale, scale)
            pix = page.get_pixmap(matrix=mat, alpha=True)
            fmt = getattr(QImage.Format, "Format_RGBA8888", None) or QImage.Format.Format_ARGB32
            img = QImage(pix.samples, pix.width, pix.height, pix.stride, fmt)
            if img.isNull():
                return self._get_system_icon(path)
            img = img.copy()
            scaled = img.scaled(self._icon_size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            qpx = QPixmap.fromImage(scaled)
            QPixmapCache.insert(cache_key, qpx)
            return QIcon(qpx)
        except Exception:
            return self._get_system_icon(path)
        finally:
            if doc:
                try:
                    doc.close()
                except Exception:
                    pass

    def _video_thumbnail_icon(self, path):
        """Miniatura wideo"""
        if not HAS_OPENCV:
            return self._get_system_icon(path)
        cache_key = f"vidthumb::{path}::{self._icon_size.width()}x{self._icon_size.height()}"
        cached = QPixmapCache.find(cache_key)
        if cached and not cached.isNull():
            return QIcon(cached)
        try:
            cap = cv2.VideoCapture(path)
            ok, frame = cap.read()
            cap.release()
            if not ok or frame is None:
                return self._get_system_icon(path)
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            h, w, ch = frame.shape
            bytes_per_line = ch * w
            img = QImage(frame.data, w, h, bytes_per_line, QImage.Format.Format_RGB888).copy()
            scaled = img.scaled(self._icon_size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            qpx = QPixmap.fromImage(scaled)
            QPixmapCache.insert(cache_key, qpx)
            return QIcon(qpx)
        except Exception:
            return self._get_system_icon(path)

    def _text_thumbnail_icon(self, path):
        """Miniatura tekstu"""
        cache_key = f"textthumb::{path}::{self._icon_size.width()}x{self._icon_size.height()}"
        cached = QPixmapCache.find(cache_key)
        if cached and not cached.isNull():
            return QIcon(cached)
        try:
            ext = os.path.splitext(path)[1].lower()
            if ext == ".bgh":
                import json
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                content = data.get("tresc", "")
                if not content:
                    content = data.get("tytul", os.path.basename(path))
                lines = content.split("\n")[:40]
                title = data.get("tytul", os.path.basename(path))
            else:
                lines = []
                with open(path, "r", encoding="utf-8", errors="replace") as f:
                    for _ in range(40):
                        line = f.readline()
                        if not line:
                            break
                        lines.append(line.rstrip("\n\r"))
                title = os.path.basename(path)
            if not lines:
                return self._get_system_icon(path)
            text = "\n".join(lines)
            W = max(100, int(self._icon_size.width() * 2))
            H = max(100, int(self._icon_size.height() * 2))
            if W <= 0 or H <= 0:
                return self._get_system_icon(path)
            img = QImage(W, H, QImage.Format.Format_ARGB32)
            img.fill(QColor("white"))
            p = QPainter(img)
            p.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
            title_font = safe_font("Segoe UI", 11, bold=True)
            body_font = safe_font("Segoe UI", 10)
            p.setFont(title_font)
            p.setPen(QColor(30, 30, 30))
            p.drawText(QRectF(12, 10, W - 24, 24), int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter), title)
            p.setFont(body_font)
            p.setPen(QColor(60, 60, 60))
            p.drawText(QRectF(12, 36, W - 24, H - 48), int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop | Qt.TextFlag.TextWordWrap), text)
            p.end()
            scaled = img.scaled(self._icon_size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            qpx = QPixmap.fromImage(scaled)
            QPixmapCache.insert(cache_key, qpx)
            return QIcon(qpx)
        except Exception:
            return self._get_system_icon(path)

    def _audio_thumbnail_icon(self, path):
        """Miniatura audio (okładka)"""
        if not HAS_MUTAGEN:
            return self._get_system_icon(path)
        cache_key = f"audiothumb::{path}::{self._icon_size.width()}x{self._icon_size.height()}"
        cached = QPixmapCache.find(cache_key)
        if cached and not cached.isNull():
            return QIcon(cached)
        try:
            mf = MutagenFile(path)
            cover_data = None
            if mf is None:
                return self._get_system_icon(path)
            if hasattr(mf, "tags") and mf.tags:
                for k, v in mf.tags.items():
                    if str(k).startswith("APIC"):
                        cover_data = v.data
                        break
            if not cover_data and hasattr(mf, "pictures"):
                pics = mf.pictures or []
                if pics:
                    cover_data = pics[0].data
            if not cover_data:
                return self._get_system_icon(path)
            img = QImage.fromData(cover_data)
            if img.isNull():
                return self._get_system_icon(path)
            scaled = img.scaled(self._icon_size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            qpx = QPixmap.fromImage(scaled)
            QPixmapCache.insert(cache_key, qpx)
            return QIcon(qpx)
        except Exception:
            return self._get_system_icon(path)

    def _invalidate_icon(self, path):
        """Usuń ikonę z cache"""
        self._icon_cache.pop(path, None)

    def _update_grid_item(self, path):
        """Zaktualizuj element w siatce"""
        if not hasattr(self, "files_grid"):
            return
        for i in range(self.files_grid.count()):
            it = self.files_grid.item(i)
            if it.data(Qt.ItemDataRole.UserRole) == path:
                if not os.path.exists(path):
                    self.files_grid.takeItem(i)
                    return
                # Ustaw podgląd miniatury lub ikonę systemową
                preview_pm = self._get_preview_pixmap(path, self._tile_preview_size)
                if preview_pm and not preview_pm.isNull():
                    it.setData(Qt.ItemDataRole.DecorationRole, preview_pm)
                else:
                    it.setIcon(self._get_icon(path))

                # Nazwa bez rozszerzenia + tooltip z pełną nazwą
                full_name = os.path.basename(path)
                name_without_ext = os.path.splitext(full_name)[0]
                it.setToolTip(full_name)
                it.setText(name_without_ext)

                # Zapisz rozszerzenie (używane przez delegata do skalowania)
                ext = os.path.splitext(path)[1].lower()
                it.setData(Qt.ItemDataRole.UserRole + 1, ext)
                return
                
        if os.path.exists(path):
            full_name = os.path.basename(path)
            name_without_ext = os.path.splitext(full_name)[0]
            preview_pm = self._get_preview_pixmap(path, self._tile_preview_size)
            it = QListWidgetItem()
            if preview_pm and not preview_pm.isNull():
                it.setData(Qt.ItemDataRole.DecorationRole, preview_pm)
            else:
                it.setIcon(self._get_icon(path))
            it.setText(name_without_ext)
            it.setData(Qt.ItemDataRole.UserRole, path)
            it.setToolTip(full_name)
            it.setData(Qt.ItemDataRole.UserRole + 1, os.path.splitext(path)[1].lower())
            it.setSizeHint(self.files_grid.gridSize())
            self.files_grid.addItem(it)

    def _update_table_row(self, path):
        """Zaktualizuj wiersz w tabeli"""
        if not hasattr(self, "files_table"):
            return
        for row in range(self.files_table.rowCount()):
            item0 = self.files_table.item(row, 0)
            if item0 and item0.data(Qt.ItemDataRole.UserRole) == path:
                if not os.path.exists(path):
                    self.refresh_files_table()
                    return
                try:
                    stat = os.stat(path)
                    created = datetime.datetime.fromtimestamp(getattr(stat, "st_ctime", stat.st_mtime)).strftime("%Y-%m-%d %H:%M")
                    modified = datetime.datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M")
                except Exception:
                    created = "-"; modified = "-"
                fname = os.path.basename(path)
                stem, ext = os.path.splitext(fname)
                ext = ext.lstrip(".")
                item0.setText(stem)
                ext_item = self.files_table.item(row, 1)
                if ext_item:
                    ext_item.setText(ext or "-")
                self.files_table.item(row, 2).setText(created)
                self.files_table.item(row, 3).setText(modified)
                return
        if os.path.exists(path):
            self.refresh_files_table()

    def refresh_current_view(self):
        """Odśwież aktualny widok (grid lub tabela)"""
        if self.view_mode == "grid":
            if hasattr(self, "files_grid"):
                self.refresh_files_grid()
        else:
            if hasattr(self, "files_table"):
                self.refresh_files_table()

    def switch_view(self, mode):
        """Przełącz między widokiem siatki a tabelą"""
        if mode not in ("table", "grid") or mode == self.view_mode:
            return
        self.view_mode = mode
        self.btn_list.setChecked(self.view_mode == "table")
        self.btn_grid.setChecked(self.view_mode == "grid")
        self.files_table.setVisible(self.view_mode == "table")
        self.files_grid.setVisible(self.view_mode == "grid")
        self.refresh_current_view()

    # --- Watcher systemu plików ---
    def _ensure_fs_watcher(self):
        if self._fs_watcher is None:
            self._fs_watcher = QFileSystemWatcher(self)
            self._fs_watcher.directoryChanged.connect(self._on_fs_changed)
            self._fs_watcher.fileChanged.connect(self._on_fs_changed)

    def _setup_fs_watcher(self, files=None):
        if not self.current_label:
            return
        folder_path = os.path.join(NOTES_DIR, self.current_label)
        if not os.path.isdir(folder_path):
            return
        self._ensure_fs_watcher()
        try:
            all_paths = self._fs_watcher.files() + self._fs_watcher.directories()
            if all_paths:
                self._fs_watcher.removePaths(all_paths)
        except Exception:
            pass
        try:
            self._fs_watcher.addPath(folder_path)
            if files is None:
                files = get_notes_in_folder(self.current_label or "")
            if files:
                self._fs_watcher.addPaths(files)
        except Exception:
            pass

    def _on_fs_changed(self, path):
        if not path:
            return
        if os.path.isdir(path):
            self.refresh_current_view()
            return
        if not os.path.exists(path):
            self._invalidate_icon(path)
            if self.view_mode == "grid":
                self._update_grid_item(path)
            else:
                self.refresh_files_table()
            return
        self._invalidate_icon(path)
        if self.view_mode == "grid":
            self._update_grid_item(path)
        else:
            self._update_table_row(path)

    def on_file_double_clicked(self, item):
        """Obsługa dwukliknięcia na pliku"""
        file_path = item.data(Qt.ItemDataRole.UserRole)
        if not file_path or not os.path.exists(file_path):
            return
        
        ext = os.path.splitext(file_path)[1].lower()
        
        # Pliki .bgh (JSON) - otwórz w wbudowanym edytorze
        if ext == ".bgh":
            self.open_file_in_viewer(file_path)
        else:
            # Inne pliki - otwórz w systemowym programie
            try:
                QDesktopServices.openUrl(QUrl.fromLocalFile(file_path))
            except Exception as e:
                QMessageBox.warning(self, "Błąd", f"Nie można otworzyć pliku: {e}")
    
    def open_file_in_viewer(self, file_path):
        """Otwórz plik w wbudowanym podglądzie/edytorze"""
        from PyQt6.QtWidgets import QDialog, QTextEdit
        import json
        
        if not os.path.exists(file_path):
            QMessageBox.warning(self, "Błąd", "Plik nie istnieje.")
            return
        
        ext = os.path.splitext(file_path)[1].lower()
        file_name = os.path.basename(file_path)
        
        dialog = QDialog(self)
        dialog.setWindowTitle(f"Podgląd: {file_name}")
        dialog.resize(900, 700)
        dialog.setStyleSheet("background: white;")
        
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Przyciski górne
        top_bar = QHBoxLayout()
        top_bar.setContentsMargins(12, 12, 12, 12)
        
        title_label = QLabel(file_name)
        title_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #222;")
        top_bar.addWidget(title_label)
        top_bar.addStretch()
        
        close_btn = QPushButton("✕ Zamknij")
        close_btn.setStyleSheet("""
            QPushButton { 
                background: #f44336; 
                color: white; 
                border: none; 
                border-radius: 6px; 
                padding: 8px 16px; 
                font-weight: bold;
            }
            QPushButton:hover { background: #d32f2f; }
        """)
        close_btn.clicked.connect(dialog.close)
        top_bar.addWidget(close_btn)
        
        layout.addLayout(top_bar)
        
        try:
            # Plik JSON (.bgh) - edytowalny tekst
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            text_edit = QTextEdit()
            text_edit.setPlainText(data.get("tresc", ""))
            text_edit.setStyleSheet("""
                QTextEdit {
                    font-family: 'Segoe UI', Arial;
                    font-size: 14px;
                    padding: 16px;
                    border: none;
                    background: #fafafa;
                    color: #1f1f24;
                }
            """)
            layout.addWidget(text_edit)
            
            # Przycisk zapisz
            save_btn = QPushButton("💾 Zapisz zmiany")
            save_btn.setStyleSheet("""
                QPushButton { 
                    background: #4CAF50; 
                    color: white; 
                    border: none; 
                    border-radius: 6px; 
                    padding: 10px 20px; 
                    font-weight: bold;
                    margin: 12px;
                }
                QPushButton:hover { background: #45a049; }
            """)
            
            def save_changes():
                try:
                    new_content = text_edit.toPlainText()
                    data["tresc"] = new_content
                    data["ostatnia_modyfikacja"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    
                    with open(file_path, "w", encoding="utf-8") as f:
                        json.dump(data, f, ensure_ascii=False, indent=2)
                    
                    # Wyczyść cache ikony po zapisie
                    self._invalidate_icon(file_path)
                    
                    QMessageBox.information(dialog, "Zapisano", "Zmiany zostały zapisane!")
                    
                    # Odśwież widok
                    self.refresh_current_view()
                    
                except json.JSONDecodeError as e:
                    QMessageBox.critical(dialog, "Błąd JSON", f"Nieprawidłowa struktura JSON: {e}")
                except Exception as e:
                    QMessageBox.critical(dialog, "Błąd", f"Nie można zapisać: {e}")
            
            save_btn.clicked.connect(save_changes)
            layout.addWidget(save_btn)
        
        except json.JSONDecodeError as e:
            error_label = QLabel(f"Błąd odczytu pliku JSON:\n{e}\n\nPlik może być uszkodzony.")
            error_label.setStyleSheet("color: red; padding: 20px; font-size: 14px;")
            error_label.setWordWrap(True)
            layout.addWidget(error_label)
        except Exception as e:
            error_label = QLabel(f"Błąd odczytu pliku:\n{e}")
            error_label.setStyleSheet("color: red; padding: 20px; font-size: 14px;")
            error_label.setWordWrap(True)
            layout.addWidget(error_label)
        
        dialog.exec()

    def on_table_item_double_clicked(self, item: QTableWidgetItem):
        """Otwórz tylko gdy dwuklik wykonano na kolumnie nazwy (kolumna 1)."""
        try:
            idx = self.files_table.indexFromItem(item)
            if not idx.isValid():
                return
            if idx.column() != 1:
                # Ignoruj dwuklik na kolumnie gwiazdki i innych
                return
        except Exception:
            # Fallback: jeśli nie uda się pobrać kolumny, nie otwieraj
            return
        self.on_file_double_clicked(item)
    
    def _handle_grid_context_menu(self, pos, grid):
        """Obsluga context menu dla grid view"""
        item = grid.itemAt(pos)
        if item:
            file_path = item.data(Qt.ItemDataRole.UserRole)
            if file_path and os.path.exists(file_path):
                global_pos = grid.mapToGlobal(pos)
                self._show_file_context_menu(file_path, global_pos)
    
    def _handle_table_context_menu(self, pos, table):
        """Obsluga context menu dla table view"""
        item = table.itemAt(pos)
        if item:
            row = item.row()
            name_item = table.item(row, 1)
            if name_item:
                file_path = name_item.data(Qt.ItemDataRole.UserRole)
                if file_path and os.path.exists(file_path):
                    global_pos = table.mapToGlobal(pos)
                    self._show_file_context_menu(file_path, global_pos)
    
    def _show_file_context_menu(self, file_path: str, position):
        """Pokaz menu kontekstowe dla pliku"""
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background: white;
                border: 1px solid #e0e4f6;
                border-radius: 8px;
                padding: 4px;
            }
            QMenu::item {
                padding: 8px 24px 8px 12px;
                border-radius: 4px;
                margin: 2px 4px;
            }
            QMenu::item:selected {
                background: #f0f4ff;
                color: #3960f5;
            }
        """)
        
        # Ikony emoji jak w notes_view
        fav_text = "⭐ Usun z ulubionych" if is_favorite(file_path) else "⭐ Dodaj do ulubionych"
        
        fav_action = menu.addAction(fav_text)
        menu.addSeparator()
        duplicate_action = menu.addAction("📋 Duplikuj")
        move_action = menu.addAction("📁 Przenies do...")
        rename_action = menu.addAction("✏️ Zmien nazwe")
        menu.addSeparator()
        delete_action = menu.addAction("🗑️ Usun")
        
        action = menu.exec(position)
        
        if action == fav_action:
            self._toggle_favorite_file(file_path)
        elif action == duplicate_action:
            self._duplicate_file_op(file_path)
        elif action == move_action:
            self._move_file_to_folder_op(file_path)
        elif action == rename_action:
            self._rename_file_op(file_path)
        elif action == delete_action:
            self._delete_file_op(file_path)
    
    def _toggle_favorite_file(self, file_path: str):
        """Przelacz status ulubionego"""
        try:
            now_fav = toggle_favorite(file_path)
            status = "dodany do" if now_fav else "usuniety z"
            QMessageBox.information(self, "Ulubione", f"Plik zostal {status} ulubionych!")
            self.refresh_current_view()
        except Exception as e:
            QMessageBox.critical(self, "Blad", str(e))
    
    def _duplicate_file_op(self, file_path: str):
        """Duplikuj plik"""
        try:
            new_path = duplicate_file(file_path)
            self._invalidate_icon(new_path)
            QMessageBox.information(
                self, 
                "Sukces", 
                f"Plik zostal zduplikowany jako:\n{os.path.basename(new_path)}"
            )
            self.refresh_current_view()
        except Exception as e:
            QMessageBox.critical(self, "Blad", str(e))
    
    def _move_file_to_folder_op(self, file_path: str):
        """Przenies plik do innego folderu"""
        from core.file_operations import create_folder_selection_dialog
        
        folder_names = [f["label"] for f in self.folders if f.get("label") and f["label"] != "Wszystkie"]
        
        if not folder_names:
            QMessageBox.warning(self, "Blad", "Brak dostepnych folderow!")
            return
        
        # Wybierz folder docelowy za pomoca ladnego dialogu
        folder_name = create_folder_selection_dialog(self, folder_names, "Przenies plik do folderu")
        
        if folder_name:
            try:
                filename = os.path.basename(file_path)
                target_path = os.path.join(NOTES_DIR, folder_name, filename)
                overwrite = False
                
                if os.path.exists(target_path):
                    reply = QMessageBox.question(
                        self,
                        "Plik istnieje",
                        f"Plik '{filename}' juz istnieje w folderze '{folder_name}'.\nCzy nadpisac?",
                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                    )
                    if reply == QMessageBox.StandardButton.No:
                        return
                    overwrite = True
                
                # Przenies uzywajac funkcji z core (automatycznie aktualizuje ulubione!)
                new_path = move_file_to_folder(file_path, folder_name, NOTES_DIR, overwrite)
                self._invalidate_icon(new_path)
                
                QMessageBox.information(self, "Sukces", f"Plik przeniesiony do folderu:\n{folder_name}")
                self.refresh_current_view()
            except Exception as e:
                QMessageBox.critical(self, "Blad", str(e))
    
    def _rename_file_op(self, file_path: str):
        """Zmien nazwe pliku"""
        from PyQt6.QtWidgets import QLineEdit
        
        file_info = get_file_info(file_path)
        name_without_ext = file_info.get("name_without_ext", "")
        ext = file_info.get("extension", "")
        
        new_name, ok = QInputDialog.getText(
            self,
            "Zmien nazwe",
            "Nowa nazwa (bez rozszerzenia):",
            QLineEdit.EchoMode.Normal,
            name_without_ext
        )
        
        if ok and new_name.strip():
            try:
                new_path = rename_file(file_path, new_name.strip(), keep_extension=True)
                self._invalidate_icon(new_path)
                QMessageBox.information(
                    self, 
                    "Sukces", 
                    f"Nazwa zmieniona na:\n{new_name.strip() + ext}"
                )
                self.refresh_current_view()
            except Exception as e:
                QMessageBox.critical(self, "Blad", str(e))
    
    def _delete_file_op(self, file_path: str):
        """Usun plik"""
        filename = os.path.basename(file_path)
        
        reply = QMessageBox.question(
            self,
            "Potwierdzenie usuniecia",
            f"Czy na pewno chcesz usunac plik?\n\n{filename}\n\nTej operacji nie mozna cofnac!",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            try:
                delete_file(file_path, permanent=True)
                self._invalidate_icon(file_path)
                QMessageBox.information(self, "Sukces", "Plik zostal usuniety!")
                self.refresh_current_view()
            except Exception as e:
                QMessageBox.critical(self, "Blad", str(e))
    
    def clear_layout(self, layout):
        """Wyczyść wszystkie elementy z layoutu"""
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.setParent(None)
            elif item.layout():
                self.clear_layout(item.layout())

