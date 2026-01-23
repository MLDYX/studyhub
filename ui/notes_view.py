from PyQt6.QtCore import Qt, QSize, QEvent, QRectF, QPropertyAnimation, QRect, QTimer
from PyQt6.QtWidgets import (
    QLabel,
    QVBoxLayout,
    QWidget,
    QFrame,
    QMessageBox,
    QHBoxLayout,
    QPushButton,
    QTextEdit,
    QSpacerItem,
    QSizePolicy,
    QLineEdit,
    QScrollArea,
    QListWidget,
    QListWidgetItem,
    QListView,
    QStyledItemDelegate,
    QStyle,
    QDialog,
    QComboBox,
    QDialogButtonBox,
    QFileDialog,
    QMenu,
    QInputDialog,
)
from PyQt6.QtGui import QIcon, QPainterPath, QRegion, QPainter, QColor, QFont, QPixmap, QPen
import json
import os
import shutil
import time
from functools import partial

from ui.folders_view import FolderView
from core.notes import get_all_favorites, get_all_notes, NOTES_DIR, _load_favorites, _save_favorites

PINNED_FOLDERS_FILE = os.path.join(os.path.dirname(NOTES_DIR), "pinned_folders.json")
from core.file_operations import (
    duplicate_file,
    move_file_to_folder,
    rename_file,
    delete_file,
    get_file_info,
)


CHIP_BUTTON_STYLE = """
    QPushButton[role="chip"] {
        background: transparent;
        border: none;
        padding: 8px 18px;
        border-radius: 18px;
        color: #3a3f63;
        font-weight: 600;
    }
    QPushButton[role="chip"]:enabled:hover {
        background: #dfe4ff;
        color: #1f2ad8;
    }
    QPushButton[role="chip"]:checked,
    QPushButton[role="chip"][aria-selected="true"] {
        background: #4c6ef5;
        color: white;
    }
    QPushButton[role="chip"]:disabled {
        background: #4c6ef5;
        color: white;
    }
"""

NEW_NOTE_BUTTON_STYLE = """
    QPushButton { 
        background:#3960f5; 
        color:white; 
        border:none; 
        border-radius:9px; 
        font-weight:bold; 
    } 
    QPushButton:hover { 
        background:#2e4fd0; 
    }
"""

ICON_BUTTON_STYLE = """
    QPushButton { 
        background: transparent; 
        border:1px solid rgba(0,0,0,0.04); 
        border-radius:9px; 
        color:#222; 
        font-weight:600; 
    } 
    QPushButton:hover { 
        background:#f2f5ff; 
    }
"""


def apply_rounded_mask(widget, radius):
    rect = widget.rect()
    path = QPainterPath()
    path.addRoundedRect(QRectF(rect), radius, radius)
    widget.setMask(QRegion(path.toFillPolygon().toPolygon()))


def clear_layout(layout):
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        if widget:
            widget.setParent(None)
        elif item.layout():
            clear_layout(item.layout())


class SaveNoteDialog(QDialog):
    
    def __init__(self, parent=None, folders=None):
        super().__init__(parent)
        self.setWindowTitle("Zapisz notatkę")
        self.setModal(True)
        self.setMinimumWidth(400)
        
        self.folders = folders or []
        self.selected_folder = None
        self.filename = ""
        self.extension = ".bgh"
        
        self.init_ui()
        
    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(24, 24, 24, 24)
        
        title = QLabel("Zapisz notatkę jako plik")
        title.setStyleSheet("font-size: 16px; font-weight: bold; color: #222;")
        layout.addWidget(title)
        
        folder_label = QLabel("Wybierz folder:")
        folder_label.setStyleSheet("font-size: 13px; font-weight: 600; color: #444;")
        layout.addWidget(folder_label)
        
        folder_row = QHBoxLayout()
        folder_row.setSpacing(8)
        
        self.folder_combo = QComboBox()
        self.folder_combo.setStyleSheet("""
            QComboBox {
                border: 1px solid rgba(0,0,0,0.12);
                border-radius: 6px;
                padding: 8px 12px;
                background: white;
                font-size: 13px;
            }
            QComboBox:hover {
                border: 1px solid #3960f5;
            }
            QComboBox::drop-down {
                border: none;
                width: 20px;
            }
        """)
        
        for folder in self.folders:
            label = folder.get("label", "")
            if label and label != "Wszystkie":
                self.folder_combo.addItem(label, folder)
        
        folder_row.addWidget(self.folder_combo, stretch=1)
        
        new_folder_btn = QPushButton("+ Nowy folder")
        new_folder_btn.setFixedHeight(36)
        new_folder_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        new_folder_btn.setStyleSheet("""
            QPushButton {
                background: #f3f6ff;
                border: 1px solid rgba(57,96,245,0.2);
                border-radius: 6px;
                padding: 8px 12px;
                font-size: 13px;
                font-weight: 600;
                color: #3960f5;
            }
            QPushButton:hover {
                background: #e6edff;
            }
        """)
        new_folder_btn.clicked.connect(self.create_new_folder)
        folder_row.addWidget(new_folder_btn)
        
        layout.addLayout(folder_row)
        
        name_label = QLabel("Nazwa pliku:")
        name_label.setStyleSheet("font-size: 13px; font-weight: 600; color: #444;")
        layout.addWidget(name_label)
        
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("np. moja-notatka")
        self.name_input.setStyleSheet("""
            QLineEdit {
                border: 1px solid rgba(0,0,0,0.12);
                border-radius: 6px;
                padding: 8px 12px;
                background: white;
                font-size: 13px;
            }
            QLineEdit:focus {
                border: 2px solid #3960f5;
            }
        """)
        layout.addWidget(self.name_input)
        
        ext_label = QLabel("Rozszerzenie:")
        ext_label.setStyleSheet("font-size: 13px; font-weight: 600; color: #444;")
        layout.addWidget(ext_label)
        
        self.ext_combo = QComboBox()
        self.ext_combo.addItems([".bgh", ".txt", ".md", ".note"])
        self.ext_combo.setStyleSheet("""
            QComboBox {
                border: 1px solid rgba(0,0,0,0.12);
                border-radius: 6px;
                padding: 8px 12px;
                background: white;
                font-size: 13px;
            }
            QComboBox:hover {
                border: 1px solid #3960f5;
            }
        """)
        layout.addWidget(self.ext_combo)
        
        layout.addSpacing(8)
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.button(QDialogButtonBox.StandardButton.Save).setText("Zapisz")
        button_box.button(QDialogButtonBox.StandardButton.Cancel).setText("Anuluj")
        button_box.setStyleSheet("""
            QPushButton {
                border: none;
                border-radius: 6px;
                padding: 8px 16px;
                font-size: 13px;
                font-weight: 600;
                min-width: 80px;
            }
            QPushButton[text="Zapisz"] {
                background: #3960f5;
                color: white;
            }
            QPushButton[text="Zapisz"]:hover {
                background: #2e4fd0;
            }
            QPushButton[text="Anuluj"] {
                background: #f0f0f0;
                color: #444;
            }
            QPushButton[text="Anuluj"]:hover {
                background: #e0e0e0;
            }
        """)
        button_box.accepted.connect(self.accept_dialog)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
        
    def create_new_folder(self):
        from PyQt6.QtWidgets import QInputDialog
        
        folder_name, ok = QInputDialog.getText(
            self,
            "Nowy folder",
            "Podaj nazwę folderu:",
            QLineEdit.EchoMode.Normal
        )
        
        if ok and folder_name.strip():
            from core.notes import NOTES_DIR
            
            # Utworz fizyczny folder
            folder_path = os.path.join(NOTES_DIR, folder_name.strip())
            try:
                os.makedirs(folder_path, exist_ok=True)
                
                new_folder = {"label": folder_name.strip(), "folder_path": None}
                self.folder_combo.addItem(folder_name.strip(), new_folder)
                self.folder_combo.setCurrentIndex(self.folder_combo.count() - 1)
                QMessageBox.information(self, "Sukces", f"Folder '{folder_name}' został utworzony!")
            except Exception as e:
                QMessageBox.critical(self, "Błąd", f"Nie można utworzyć folderu: {e}")
    
    def accept_dialog(self):
        self.filename = self.name_input.text().strip()
        self.extension = self.ext_combo.currentText()
        
        if not self.filename:
            QMessageBox.warning(self, "Błąd", "Podaj nazwę pliku!")
            return
        
        current_data = self.folder_combo.currentData()
        self.selected_folder = current_data if current_data else None
        
        self.accept()
    
    def get_full_filename(self):
        return f"{self.filename}{self.extension}"
    
    def get_folder_label(self):
        if self.selected_folder:
            return self.selected_folder.get("label", "")
        return ""


class TileGridDelegate(QStyledItemDelegate):
    def __init__(
        self,
        parent: QListWidget,
        preview_size: QSize,
        radius: float = 12.0,
        outer_margin: int = 4,
        inner_left_right: int = 8,
        inner_top: int = 10,
        inner_bottom: int = 10,
        footer_h: int = 24,
    ):
        super().__init__(parent)
        self.preview_size = preview_size
        self.radius = radius
        self.outer_margin = outer_margin
        self.inner_left_right = inner_left_right
        self.inner_top = inner_top
        self.inner_bottom = inner_bottom
        self.footer_h = footer_h

        self.title_font = QFont("Segoe UI", 9)
        self.title_font.setBold(True)

    def sizeHint(self, option, index):
        w = option.widget.gridSize().width() if option.widget else (self.preview_size.width() + 28)
        h = option.widget.gridSize().height() if option.widget else (self.preview_size.height() + 44)
        return QSize(w, h)

    def paint(self, painter: QPainter, option, index):
        painter.save()

        outer = option.rect.adjusted(
            self.outer_margin,
            self.outer_margin,
            -self.outer_margin,
            -self.outer_margin,
        )

        bg = QColor("white")
        border = QColor(225, 230, 245)
        if option.state & QStyle.StateFlag.State_Selected:
            bg = QColor(230, 237, 255)
            border = QColor(57, 96, 245)
        elif option.state & QStyle.StateFlag.State_MouseOver:
            bg = QColor(247, 250, 255)
            border = QColor(212, 219, 239)

        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        path = QPainterPath()
        path.addRoundedRect(QRectF(outer), self.radius, self.radius)
        painter.fillPath(path, bg)

        pen = QPen(border)
        pen.setWidthF(1.0)
        painter.setPen(pen)
        painter.drawPath(path)

        content = outer.adjusted(
            self.inner_left_right,
            self.inner_top,
            -self.inner_left_right,
            -self.inner_bottom,
        )
        preview_rect = QRect(
            content.x(),
            content.y(),
            content.width(),
            max(1, content.height() - self.footer_h - 6),
        )

        deco = index.data(Qt.ItemDataRole.DecorationRole)
        pm = deco if isinstance(deco, QPixmap) and not deco.isNull() else None
        if pm and not pm.isNull() and preview_rect.width() > 2 and preview_rect.height() > 2:
            target = preview_rect.adjusted(2, 2, -2, -2)
            scaled = pm.scaled(
                target.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            ix = target.x() + (target.width() - scaled.width()) // 2
            iy = target.y() + (target.height() - scaled.height()) // 2
            painter.drawPixmap(ix, iy, scaled)

        name = index.data(Qt.ItemDataRole.DisplayRole) or ""
        footer_top = outer.bottom() - self.footer_h - 2
        painter.setPen(QColor(25, 25, 25))
        painter.setFont(self.title_font)
        metrics = painter.fontMetrics()
        elided_name = metrics.elidedText(name, Qt.TextElideMode.ElideRight, max(1, int(content.width())))
        name_rect = QRectF(content.x(), footer_top, content.width(), self.footer_h)
        painter.drawText(name_rect, int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter), elided_name)
        painter.restore()


class TileHitList(QListWidget):
    def __init__(self, parent=None, outer_margin: int = 4):
        super().__init__(parent)
        self._outer_margin = outer_margin

    def _hit_item(self, pos):
        item = self.itemAt(pos)
        if item is None:
            return None, False
        r = self.visualItemRect(item)
        return item, r.contains(pos)

    def mousePressEvent(self, event):
        item, hit = self._hit_item(event.pos())
        if item is None or not hit:
            # Klik w tło listy nie powinien odznaczać aktualnie zaznaczonego elementu.
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        item, hit = self._hit_item(event.pos())
        if item is None or not hit:
            event.accept()
            return
        super().mouseReleaseEvent(event)


class FolderPopup(QFrame):
    def __init__(self, parent, folders, on_select, on_close=None, on_rename=None, on_delete=None, on_toggle_pin=None, is_pinned=None):
        flags = Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint
        if hasattr(Qt.WindowType, "NoDropShadowWindowHint"):
            flags |= Qt.WindowType.NoDropShadowWindowHint
        super().__init__(parent, flags)
        self.setObjectName("folderPopup")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._on_select = on_select
        self._on_close = on_close
        self._on_rename_folder = on_rename
        self._on_delete_folder = on_delete
        self._on_toggle_pin = on_toggle_pin
        self._is_pinned = is_pinned or (lambda folder: False)

        self.setStyleSheet("""
            QFrame#folderPopup {
                background: white;
                border: 1px solid #e0e4f6;
                border-radius: 24px;
            }
            QPushButton.folderItem {
                text-align: left;
                padding: 8px 12px;
                border: none;
                background: transparent;
                color: #222;
                font-size: 13px;
                min-height: 36px;
            }
            QPushButton.folderItem:hover { background: #f2f5ff; }
        """)

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        content = QWidget(self)
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)

        for f in folders:
            label = f.get("label") or "Folder"
            path = f.get("folder_path")
            btn = QPushButton(label, content)
            btn.setObjectName("folderItem")
            btn.setProperty("class", "folderItem")
            btn.setFlat(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(partial(self._select, path, label))
            btn.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            btn.customContextMenuRequested.connect(
                lambda pos, info=f, button=btn: self._show_context_menu(button, info, pos)
            )
            content_layout.addWidget(btn)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(content)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        scroll.setContentsMargins(0, 0, 0, 0)
        scroll.setFixedHeight(min(240, max(120, len(folders) * 40 + 8)))
        root_layout.addWidget(scroll)
        self._scroll = scroll
        self.installEventFilter(self)
        self._scroll.installEventFilter(self)
        self._drag_active = False
        self._drag_start_pos = None
        self._drag_start_value = None

    def _can_manage_folder(self, folder):
        label = (folder.get("label") or "").strip().lower()
        if not label or label == "wszystkie":
            return False
        path = folder.get("folder_path")
        if not path or not os.path.isdir(path):
            return False
        try:
            return os.path.commonpath([os.path.abspath(path), os.path.abspath(NOTES_DIR)]) == os.path.abspath(NOTES_DIR)
        except ValueError:
            return False

    def _show_context_menu(self, button, folder, pos):
        if not self._can_manage_folder(folder):
            return
        menu = QMenu(button)
        menu.setStyleSheet(
            """
            QMenu { background: white; border: 1px solid #e0e4f6; border-radius: 8px; }
            QMenu::item { padding: 6px 16px; border-radius: 4px; margin: 2px; }
            QMenu::item:selected { background: #eef3ff; color: #3960f5; }
            """
        )
        pin_action = None
        rename_action = delete_action = None
        if callable(self._on_toggle_pin):
            pinned = bool(self._is_pinned(folder))
            text = "📌 Zdejmij z paska" if pinned else "📌 Dodaj do paska"
            pin_action = menu.addAction(text)
            menu.addSeparator()
        if callable(self._on_rename_folder):
            rename_action = menu.addAction("✏️ Zmień nazwę")
        if callable(self._on_delete_folder):
            delete_action = menu.addAction("🗑️ Usuń")
        if not (pin_action or rename_action or delete_action):
            return
        action = menu.exec(button.mapToGlobal(pos))
        if action == pin_action:
            self._on_toggle_pin(folder)
            self.close()
        elif action == rename_action:
            self._on_rename_folder(folder)
            self.close()
        elif action == delete_action:
            self._on_delete_folder(folder)
            self.close()

    def eventFilter(self, obj, event):
        # Utrzymuj zaokrąglenie podczas zmiany rozmiaru i przewijania
        if event.type() in (QEvent.Type.Resize, QEvent.Type.Paint, QEvent.Type.Scroll):
            apply_rounded_mask(self, 24.0)
        if obj is self._scroll:
            bar = self._scroll.verticalScrollBar()
            if event.type() in (QEvent.Type.MouseButtonPress, QEvent.Type.MouseMove, QEvent.Type.MouseButtonRelease):
                pos = event.position().toPoint() if hasattr(event, "position") else event.pos()
                if bar.geometry().contains(pos):
                    return False
            if event.type() == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
                self._drag_active = True
                self._drag_start_pos = event.position().y()
                self._drag_start_value = self._scroll.verticalScrollBar().value()
                return True
            elif event.type() == QEvent.Type.MouseMove and self._drag_active:
                delta = event.position().y() - self._drag_start_pos
                self._scroll.verticalScrollBar().setValue(self._drag_start_value - int(delta))
                return True
            elif event.type() == QEvent.Type.MouseButtonRelease and event.button() == Qt.MouseButton.LeftButton:
                self._drag_active = False
                return True
        return super().eventFilter(obj, event)

    def _select(self, folder_path, label):
        if callable(self._on_select):
            self._on_select(folder_path, label)
        self.close()

    def focusOutEvent(self, event):
        if not self.isAncestorOf(self.focusWidget()):
            self.close()
        super().focusOutEvent(event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(event)

    def closeEvent(self, event):
        if callable(self._on_close):
            self._on_close()
        super().closeEvent(event)

    def show_near(self, anchor_widget, prefer_width=None):
        w = min(max(prefer_width or 220, 160), 320)
        self.setFixedWidth(w)
        self.adjustSize()
        rect = anchor_widget.rect()
        global_bl = anchor_widget.mapToGlobal(rect.bottomLeft())
        x = max(global_bl.x() + anchor_widget.width() - self.width(), 4)
        y = global_bl.y() + 6
        self.move(x, y)
        self.show()
        self.setFocus()


class NotesView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("notesRoot")
        self.setStyleSheet("background: white;")

        self.frame_extra_width = 24
        self.sidebar_width = 300
        self.sidebar_collapsed_width = 64
        self.sidebar_expanded = False
        self.sidebar_overlay_mode = False
        self._sidebar_anim = None
        self._sidebar_prev_visible = True

        self.notesSidebarFrame = QFrame(self)
        self.notesSidebarFrame.setObjectName("notesSidebarFrame")
        self._frame_style_with_border = (
            """
            QFrame#notesSidebarFrame {
                background: #fff;
                border: 1px solid #e0e4f6;
                border-radius: 32px;
            }
            """
        )
        self._frame_style_no_border = (
            """
            QFrame#notesSidebarFrame {
                background: #fff;
                border: none;
                border-radius: 32px;
            }
            """
        )
        self.notesSidebarFrame.setStyleSheet(self._frame_style_with_border)
        self.notesSidebarFrame.setGeometry(0, 0, self.width(), self.height())

        self.root_layout = QHBoxLayout(self.notesSidebarFrame)
        self.root_layout.setContentsMargins(0, 0, 0, 0)
        self.root_layout.setSpacing(0)

        self.main_content_widget = QWidget()
        self.main_layout = QVBoxLayout(self.main_content_widget)
        # Mniejsze marginesy pionowe, żeby UI nie wymuszało zbyt wysokiego okna
        self.main_layout.setContentsMargins(24, 16, 24, 16)
        self.main_layout.setSpacing(12)

        self.init_notes_sidebar()

        self.root_layout.addWidget(self.main_content_widget, stretch=1)
        self._layout_spacing = QSpacerItem(2, 0, QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Minimum)
        self.root_layout.addItem(self._layout_spacing)
        self.root_layout.addWidget(self.notes_sidebar, stretch=0)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.notesSidebarFrame)

        self._folders_popup = None
        self._popup_closed_at = 0.0
        self._folder_view = None
        self._pinned_labels = self._load_pinned_folders()
        
        self._search_popup = None
        self._search_query = ""
        self._search_timer = QTimer()
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(300)
        self._search_timer.timeout.connect(self._perform_search)

        os.makedirs(NOTES_DIR, exist_ok=True)
        self.folders = []
        self.refresh_folder_list()

        self.installEventFilter(self)

        self.init_main_view()

    def set_notes_frame_border_visible(self, visible):
        style = self._frame_style_with_border if visible else self._frame_style_no_border
        self.notesSidebarFrame.setStyleSheet(style)

    def _open_path(self, path: str):
        if not path or not os.path.exists(path):
            return
        ext = os.path.splitext(path)[1].lower()
        if ext == ".bgh":
            fv = self._folder_view or FolderView(self)
            fv.open_file_in_viewer(path)
            return
        from PyQt6.QtCore import QUrl
        from PyQt6.QtGui import QDesktopServices
        try:
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))
        except Exception:
            pass
    
    def _show_file_context_menu(self, file_path: str, position):
        """Pokaż menu kontekstowe dla pliku"""
        from PyQt6.QtWidgets import QMenu
        from core.notes import is_favorite, toggle_favorite
        
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
        
        # Ikony dla akcji
        fav_text = "⭐ Usuń z ulubionych" if is_favorite(file_path) else "⭐ Dodaj do ulubionych"
        
        # Akcje menu
        fav_action = menu.addAction(fav_text)
        menu.addSeparator()
        duplicate_action = menu.addAction("📋 Duplikuj")
        move_action = menu.addAction("📁 Przenieś do...")
        rename_action = menu.addAction("✏️ Zmień nazwę")
        menu.addSeparator()
        delete_action = menu.addAction("🗑️ Usuń")
        
        # Pokaż menu i obsłuż wybór
        action = menu.exec(position)
        
        if action == fav_action:
            self._toggle_favorite(file_path)
        elif action == duplicate_action:
            self._duplicate_file(file_path)
        elif action == move_action:
            self._move_file_to_folder(file_path)
        elif action == rename_action:
            self._rename_file(file_path)
        elif action == delete_action:
            self._delete_file(file_path)
    
    def _toggle_favorite(self, file_path: str):
        """Przełącz status ulubionego"""
        from core.notes import toggle_favorite, is_favorite
        
        try:
            toggle_favorite(file_path)
            status = "dodany do" if is_favorite(file_path) else "usunięty z"
            QMessageBox.information(self, "Ulubione", f"Plik został {status} ulubionych!")
            self.init_main_view()  # Odśwież widok
        except Exception as e:
            QMessageBox.critical(self, "Błąd", f"Nie udało się zmienić statusu:\n{str(e)}")
    
    def _duplicate_file(self, file_path: str):
        try:
            new_path = duplicate_file(file_path)
            QMessageBox.information(
                self, 
                "Sukces", 
                f"Plik został zduplikowany jako:\n{os.path.basename(new_path)}"
            )
            self.init_main_view()  # Odśwież widok
        except Exception as e:
            QMessageBox.critical(self, "Błąd", str(e))
    
    def _move_file_to_folder(self, file_path: str):
        from core.file_operations import create_folder_selection_dialog
        
        # Pobierz liste folderow (bez "Wszystkie")
        folder_names = [f["label"] for f in self.folders if f["label"] != "Wszystkie"]
        
        if not folder_names:
            QMessageBox.warning(self, "Blad", "Brak dostepnych folderow!")
            return
        
        # Wybierz folder docelowy za pomoca ladnego dialogu
        folder_name = create_folder_selection_dialog(self, folder_names, "Przenies plik do folderu")
        
        if folder_name:
            try:
                filename = os.path.basename(file_path)
                base_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "notes")
                
                # Sprawdz czy plik juz istnieje
                target_path = os.path.join(base_path, folder_name, filename)
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
                new_path = move_file_to_folder(file_path, folder_name, base_path, overwrite)
                
                
                
                QMessageBox.information(self, "Sukces", f"Plik przeniesiony do folderu:\n{folder_name}")
                self.init_main_view()
            except Exception as e:
                QMessageBox.critical(self, "Blad", str(e))
    
    def _rename_file(self, file_path: str):
        """Zmień nazwę pliku (UI wrapper)"""
        from PyQt6.QtWidgets import QInputDialog
        
        file_info = get_file_info(file_path)
        name_without_ext = file_info.get("name_without_ext", "")
        ext = file_info.get("extension", "")
        
        new_name, ok = QInputDialog.getText(
            self,
            "Zmień nazwę",
            "Nowa nazwa (bez rozszerzenia):",
            QLineEdit.EchoMode.Normal,
            name_without_ext
        )
        
        if ok and new_name.strip():
            try:
                new_path = rename_file(file_path, new_name.strip(), keep_extension=True)
                QMessageBox.information(
                    self, 
                    "Sukces", 
                    f"Nazwa zmieniona na:\n{new_name.strip() + ext}"
                )
                self.init_main_view()  # Odśwież widok
            except Exception as e:
                QMessageBox.critical(self, "Błąd", str(e))
    
    def _delete_file(self, file_path: str):
        """Usuń plik (UI wrapper)"""
        filename = os.path.basename(file_path)
        
        reply = QMessageBox.question(
            self,
            "Potwierdzenie usunięcia",
            f"Czy na pewno chcesz usunąć plik?\n\n{filename}\n\nTej operacji nie można cofnąć!",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            try:
                delete_file(file_path, permanent=True)
                QMessageBox.information(self, "Sukces", "Plik został usunięty!")
                self.init_main_view()  # Odśwież widok
            except Exception as e:
                QMessageBox.critical(self, "Błąd", str(e))

    def _update_favorites_for_folder(self, old_path, new_path=None):
        try:
            favs = _load_favorites()
        except Exception:
            return
        updated = set()
        changed = False
        old_abs = os.path.abspath(old_path)
        for fav in favs:
            fav_abs = os.path.abspath(fav)
            if fav_abs.startswith(old_abs + os.sep):
                changed = True
                if new_path:
                    updated.add(os.path.abspath(new_path) + fav_abs[len(old_abs):])
            else:
                updated.add(fav_abs)
        if changed:
            _save_favorites(updated)

    def _rename_notes_folder(self, folder):
        label = folder.get("label") or ""
        folder_path = folder.get("folder_path")
        if not folder_path or not os.path.isdir(folder_path):
            return
        new_label, ok = QInputDialog.getText(
            self,
            "Zmień nazwę folderu",
            "Nowa nazwa folderu:",
            QLineEdit.EchoMode.Normal,
            label,
        )
        if not ok:
            return
        new_label = FolderView._sanitize_filename(new_label.strip())
        if not new_label:
            QMessageBox.warning(self, "Błąd", "Nazwa folderu nie może być pusta.")
            return
        if new_label == label:
            return
        new_path = os.path.join(NOTES_DIR, new_label)
        if os.path.exists(new_path):
            QMessageBox.warning(self, "Błąd", "Folder o takiej nazwie już istnieje.")
            return
        try:
            os.rename(folder_path, new_path)
            self._update_favorites_for_folder(folder_path, new_path)
            QMessageBox.information(self, "Sukces", "Folder został przemianowany.")
            self.refresh_folder_list()
            self.init_main_view()
        except Exception as e:
            QMessageBox.critical(self, "Błąd", f"Nie udało się zmienić nazwy folderu:\n{e}")

    def _delete_notes_folder(self, folder):
        label = folder.get("label") or ""
        folder_path = folder.get("folder_path")
        if not folder_path or not os.path.isdir(folder_path):
            return
        reply = QMessageBox.question(
            self,
            "Usuń folder",
            f"Czy na pewno chcesz usunąć folder '{label}' wraz z zawartością?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            shutil.rmtree(folder_path)
            self._update_favorites_for_folder(folder_path)
            QMessageBox.information(self, "Sukces", "Folder został usunięty.")
            self.refresh_folder_list()
            self.init_main_view()
        except Exception as e:
            QMessageBox.critical(self, "Błąd", f"Nie udało się usunąć folderu:\n{e}")

    def _load_pinned_folders(self):
        try:
            with open(PINNED_FOLDERS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                return [str(label) for label in data if isinstance(label, str)]
        except Exception:
            pass
        return []

    def _save_pinned_folders(self):
        try:
            os.makedirs(os.path.dirname(PINNED_FOLDERS_FILE), exist_ok=True)
            with open(PINNED_FOLDERS_FILE, "w", encoding="utf-8") as f:
                json.dump(self._pinned_labels, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _sync_pinned_with_existing(self):
        available = {f.get("label") for f in self.folders if f.get("label")}
        filtered = [label for label in self._pinned_labels if label in available and label.lower() != "wszystkie"]
        if filtered != self._pinned_labels:
            self._pinned_labels = filtered
            self._save_pinned_folders()

    def _is_folder_pinned(self, label: str) -> bool:
        label = (label or "").strip()
        if not label or label.lower() == "wszystkie":
            return False
        return label in self._pinned_labels

    def _set_folder_pinned(self, label: str, pinned: bool):
        label = (label or "").strip()
        if not label or label.lower() == "wszystkie":
            return
        currently = self._is_folder_pinned(label)
        if pinned and not currently:
            self._pinned_labels.append(label)
            self._save_pinned_folders()
            self.init_main_view()
        elif not pinned and currently:
            self._pinned_labels = [l for l in self._pinned_labels if l != label]
            self._save_pinned_folders()
            self.init_main_view()

    def _toggle_pin_from_popup(self, folder):
        label = folder.get("label") if isinstance(folder, dict) else folder
        if not label:
            return
        self._set_folder_pinned(label, not self._is_folder_pinned(label))

    def refresh_folder_list(self):
        """Zsynchronizuj liste folderów z aktualnym katalogiem notatek."""
        folders = [{"label": "Wszystkie", "folder_path": None}]
        if os.path.isdir(NOTES_DIR):
            try:
                names = sorted(
                    [name for name in os.listdir(NOTES_DIR) if os.path.isdir(os.path.join(NOTES_DIR, name))],
                    key=lambda s: s.lower(),
                )
                for name in names:
                    folders.append({"label": name, "folder_path": os.path.join(NOTES_DIR, name)})
            except Exception:
                pass
        self.folders = folders
        self._sync_pinned_with_existing()
        if self._folder_view is not None:
            self._folder_view.folders = self.folders

    def _resolve_folder_path(self, label):
        if not label or label.strip().lower() == "wszystkie":
            return None
        for info in self.folders:
            if info.get("label") == label:
                return info.get("folder_path")
        return os.path.join(NOTES_DIR, label)

    def init_main_view(self):
        self.set_notes_frame_border_visible(True)
        self.set_sidebar_overlay_mode(False)
        self.notes_sidebar.show()
        self.toggle_btn.setEnabled(True)

        clear_layout(self.main_layout)
        self.init_top_header()
        self.main_layout.addSpacing(8)

        # Sekcja: Ulubione pliki
        favorites_section = QFrame()
        favorites_section.setObjectName("favoritesSection")
        favorites_section.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        favorites_section.setStyleSheet("""
            QFrame#favoritesSection {
                background: white;
                border-radius: 12px;
                border: 1px solid rgba(0,0,0,0.08);
            }
        """)
        fav_layout = QVBoxLayout(favorites_section)
        fav_layout.setContentsMargins(16, 12, 16, 12)
        fav_layout.setSpacing(0)
        
        # Tytuł sekcji ulubionych
        fav_title = QLabel("Ulubione pliki")
        fav_title.setStyleSheet("font-size:15px; font-weight:600; color:#222;")
        fav_layout.addWidget(fav_title)
        fav_layout.addSpacing(12)
        
        # Kontener na kafelki ulubionych z przewijaniem
        fav_scroll = QScrollArea()
        fav_scroll.setObjectName("favScroll")
        fav_scroll.setWidgetResizable(True)
        fav_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        fav_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        fav_scroll.setFrameShape(QFrame.Shape.NoFrame)
        fav_scroll.setStyleSheet("""
            QScrollArea#favScroll {
                background: transparent;
                border: none;
            }
            QScrollBar:horizontal {
                height: 8px;
                background: #f0f0f0;
                border-radius: 4px;
            }
            QScrollBar::handle:horizontal {
                background: #c0c0c0;
                border-radius: 4px;
                min-width: 40px;
            }
            QScrollBar::handle:horizontal:hover {
                background: #a0a0a0;
            }
        """)
        
        fav_content = QFrame()
        fav_content.setObjectName("favContent")
        fav_content.setStyleSheet("""
            QFrame#favContent {
                background: #f8faff;
                border: 1px dashed rgba(0,0,0,0.12);
                border-radius: 8px;
                min-height: 165px;
            }
        """)
        fav_content_layout = QHBoxLayout(fav_content)
        fav_content_layout.setContentsMargins(12, 10, 12, 10)
        fav_content_layout.setSpacing(12)
        fav_content_layout.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        
        # Pobierz ulubione pliki
        try:
            favs = get_all_favorites()
        except Exception:
            favs = []
        
        if favs:
            # Dodaj kafelki dla ulubionych (max 10 z przewijaniem)
            self._add_tiles_to_layout(fav_content_layout, favs[:10], QSize(90, 105), 110, 145)
            fav_scroll.setWidget(fav_content)
            fav_layout.addWidget(fav_scroll)
        else:
            # Placeholder gdy brak
            fav_placeholder = QLabel("Brak ulubionych plików")
            fav_placeholder.setStyleSheet("color:#888; font-size:13px;")
            fav_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
            fav_content_layout.addWidget(fav_placeholder)
            fav_scroll.setWidget(fav_content)
            fav_layout.addWidget(fav_scroll)
        self.main_layout.addWidget(favorites_section)
        self.main_layout.addSpacing(12)

        # Sekcja: Ostatnio zmodyfikowane
        recent_section = QFrame()
        recent_section.setObjectName("recentSection")
        recent_section.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        recent_section.setStyleSheet("""
            QFrame#recentSection {
                background: white;
                border-radius: 12px;
                border: 1px solid rgba(0,0,0,0.08);
            }
        """)
        recent_layout = QVBoxLayout(recent_section)
        recent_layout.setContentsMargins(16, 12, 16, 12)
        recent_layout.setSpacing(0)
        
        # Tytuł sekcji ostatnio zmodyfikowanych
        recent_title = QLabel("Ostatnio zmodyfikowane")
        recent_title.setStyleSheet("font-size:15px; font-weight:600; color:#222;")
        recent_layout.addWidget(recent_title)
        recent_layout.addSpacing(12)
        
        # Kontener na kafelki ostatnio zmodyfikowanych z przewijaniem
        recent_scroll = QScrollArea()
        recent_scroll.setObjectName("recentScroll")
        recent_scroll.setWidgetResizable(True)
        recent_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        recent_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        recent_scroll.setFrameShape(QFrame.Shape.NoFrame)
        recent_scroll.setStyleSheet("""
            QScrollArea#recentScroll {
                background: transparent;
                border: none;
            }
            QScrollBar:horizontal {
                height: 8px;
                background: #f0f0f0;
                border-radius: 4px;
            }
            QScrollBar::handle:horizontal {
                background: #c0c0c0;
                border-radius: 4px;
                min-width: 40px;
            }
            QScrollBar::handle:horizontal:hover {
                background: #a0a0a0;
            }
        """)
        
        recent_content = QFrame()
        recent_content.setObjectName("recentContent")
        recent_content.setStyleSheet("""
            QFrame#recentContent {
                background: #f8faff;
                border: 1px dashed rgba(0,0,0,0.12);
                border-radius: 8px;
                min-height: 165px;
            }
        """)
        recent_content_layout = QHBoxLayout(recent_content)
        recent_content_layout.setContentsMargins(12, 10, 12, 10)
        recent_content_layout.setSpacing(12)
        recent_content_layout.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        
        # Pobierz ostatnio zmodyfikowane pliki
        try:
            all_notes = get_all_notes()
        except Exception:
            all_notes = []
        
        try:
            all_notes = sorted(all_notes, key=lambda p: os.path.getmtime(p), reverse=True)[:8]
        except Exception:
            pass
        
        if all_notes:
            
            self._add_tiles_to_layout(recent_content_layout, all_notes, QSize(90, 105), 110, 145)
            recent_scroll.setWidget(recent_content)
            recent_layout.addWidget(recent_scroll)
        else:
            # Placeholder gdy brak
            recent_placeholder = QLabel("Brak ostatnio zmodyfikowanych plików")
            recent_placeholder.setStyleSheet("color:#888; font-size:13px;")
            recent_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
            recent_content_layout.addWidget(recent_placeholder)
            recent_scroll.setWidget(recent_content)
            recent_layout.addWidget(recent_scroll)
        self.main_layout.addWidget(recent_section)

        self.notesSidebarFrame.raise_()
    
    def _add_tiles_to_layout(self, layout: QHBoxLayout, paths: list[str], preview_size: QSize, tile_w: int, tile_h: int):
        """Dodaj kafelki plików do layoutu"""
        helper = self._folder_view or FolderView(self)
        
        for path in paths:
            tile_frame = self._create_tile_widget(path, preview_size, tile_w, tile_h, helper)
            layout.addWidget(tile_frame)
    
    def _create_tile_widget(self, path: str, preview_size: QSize, tile_w: int, tile_h: int, helper) -> QFrame:
        """Utwórz pojedynczy kafelek z plikiem"""
        tile = QFrame()
        tile.setObjectName("tileFrame")
        tile.setFixedSize(tile_w, tile_h)
        tile.setCursor(Qt.CursorShape.PointingHandCursor)
        tile.setStyleSheet("""
            QFrame#tileFrame {
                background: white;
                border: 1px solid rgba(0,0,0,0.08);
                border-radius: 8px;
            }
            QFrame#tileFrame:hover {
                background: #f0f4ff;
                border: 1px solid rgba(57,96,245,0.3);
            }
        """)
        
        tile_layout = QVBoxLayout(tile)
        tile_layout.setContentsMargins(6, 6, 6, 6)
        tile_layout.setSpacing(4)
        
        # Podgląd pliku
        preview_label = QLabel()
        preview_label.setFixedSize(preview_size)
        preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        preview_label.setStyleSheet("background: #f5f5f5; border-radius: 4px;")
        
        preview_pm = helper._get_preview_pixmap(path, preview_size)
        if preview_pm and not preview_pm.isNull():
            preview_label.setPixmap(preview_pm)
        
        tile_layout.addWidget(preview_label)
        
        # Nazwa pliku
        full_name = os.path.basename(path)
        name_without_ext = os.path.splitext(full_name)[0]
        
        name_label = QLabel(name_without_ext)
        name_label.setStyleSheet("font-size:11px; color:#222; background: transparent;")
        name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        name_label.setWordWrap(True)
        name_label.setMaximumHeight(28)
        name_label.setToolTip(full_name)
        
        # Skróć tekst jeśli za długi
        font_metrics = name_label.fontMetrics()
        elided_text = font_metrics.elidedText(name_without_ext, Qt.TextElideMode.ElideRight, tile_w - 12)
        name_label.setText(elided_text)
        
        tile_layout.addWidget(name_label)
        
        # Obsługa kliknięcia
        def handle_mouse_press(event):
            if event.button() == Qt.MouseButton.LeftButton:
                self._open_path(path)
            elif event.button() == Qt.MouseButton.RightButton:
                self._show_file_context_menu(path, event.globalPosition().toPoint())
        
        tile.mousePressEvent = handle_mouse_press
        
        return tile

    def init_top_header(self):
        header_frame = QFrame()
        header_frame.setObjectName("topHeader")
        header_frame.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        header_frame.setStyleSheet("""
            QFrame#topHeader {
                background: white;
                border-radius:12px;
                border:1px solid rgba(0,0,0,0.04);
                padding:12px;
            }
        """)
        header_frame.installEventFilter(self)

        self.header_vlayout = QVBoxLayout(header_frame)
        self.header_vlayout.setContentsMargins(0, 0, 0, 0)
        self.header_vlayout.setSpacing(8)

        chips_row = QWidget()
        chips_layout = QHBoxLayout(chips_row)
        chips_layout.setContentsMargins(0, 0, 0, 0)
        chips_layout.setSpacing(8)

        chips_container = QWidget()
        chips_container.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        chips_container.setStyleSheet("background: transparent;")
        chips_inner = QHBoxLayout(chips_container)
        chips_inner.setContentsMargins(0, 0, 0, 0)
        chips_inner.setSpacing(4)

        self.chip_buttons = []
        display_labels = ["Wszystkie"] + list(self._pinned_labels)
        for label in display_labels:
            info = next((f for f in self.folders if f.get("label") == label), None)
            if not info:
                continue
            display_text = "Strona główna" if label.lower() == "wszystkie" else label
            btn = QPushButton(display_text)
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor if label.lower() != "wszystkie" else Qt.CursorShape.ArrowCursor)
            btn.setProperty("role", "chip")
            btn.setProperty("folder_label", label)
            btn.setFlat(True)
            btn.setMinimumHeight(36)
            btn.setStyleSheet(CHIP_BUTTON_STYLE)
            btn.setToolTip(display_text)
            if label.lower() != "wszystkie":
                btn.clicked.connect(self.on_chip_clicked)
            else:
                btn.setEnabled(False)
                btn.setChecked(True)
            chips_inner.addWidget(btn)
            self.chip_buttons.append(btn)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        scroll.setFixedHeight(56)
        scroll.setWidget(chips_container)
        chips_layout.addWidget(scroll, stretch=1)

        self.header_vlayout.addWidget(chips_row)

        # Wiersz z polem wyszukiwania i przyciskami
        btns_row = QWidget()
        btns_layout = QHBoxLayout(btns_row)
        btns_layout.setContentsMargins(0, 0, 0, 0)
        btns_layout.setSpacing(8)
        
        # Pole wyszukiwania
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Wyszukaj notatki...")
        self.search_input.setStyleSheet("""
            QLineEdit {
                border: 1px solid rgba(0,0,0,0.12);
                border-radius: 9px;
                padding: 8px 14px;
                background: white;
                font-size: 13px;
                min-height: 20px;
            }
            QLineEdit:focus {
                border: 1px solid rgba(57,96,245,0.4);
                background: #f8faff;
            }
        """)
        self.search_input.textChanged.connect(self.on_search_text_changed)
        btns_layout.addWidget(self.search_input, stretch=1)

        self.add_folder_btn = QPushButton("+")
        self.add_folder_btn.setFixedSize(36, 36)
        self.add_folder_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.add_folder_btn.setFlat(True)
        self.add_folder_btn.setToolTip("Dodaj nowy folder")
        self.add_folder_btn.setStyleSheet(NEW_NOTE_BUTTON_STYLE)
        self.add_folder_btn.clicked.connect(self.on_new_note)
        btns_layout.addWidget(self.add_folder_btn)

        self.more_btn = QPushButton("▾")
        self.more_btn.setFixedSize(36, 36)
        self.more_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.more_btn.setFlat(True)
        self.more_btn.setStyleSheet(ICON_BUTTON_STYLE)
        self.more_btn.clicked.connect(self.show_more_folders)
        btns_layout.addWidget(self.more_btn)

        self.header_vlayout.addWidget(btns_row)

        self.main_layout.addWidget(header_frame)
        self.header_frame = header_frame

    def adjust_header_right_margin(self):
        """Dostosuj margines nagłówka do szerokości sidebaru"""
        if not hasattr(self, "header_frame"):
            return
        
        sidebar_w = self.sidebar_width if self.sidebar_expanded else self.sidebar_collapsed_width
        # Add right padding when sidebar overlays to avoid borders overlapping
        padding = max(0, sidebar_w - 8) if self.sidebar_overlay_mode else 0
        self.header_frame.setContentsMargins(0, 0, padding, 0)
        # Also pad the main content layout so borders don't touch sidebar
        try:
            left, top, _, bottom = self.main_layout.getContentsMargins()
            self.main_layout.setContentsMargins(left, top, padding, bottom)
        except Exception:
            pass

    def _on_popup_closed(self):
        self._popup_closed_at = time.monotonic()
        self.more_btn.setText("▾")
        self._folders_popup = None

    def show_more_folders(self):
        # Prosty debounce dla zamkniętego popupu
        if time.monotonic() - getattr(self, "_popup_closed_at", 0) < 0.20:
            return
        if self._folders_popup and self._folders_popup.isVisible():
            self._folders_popup.close()
            return

        self.refresh_folder_list()

        def on_select(folder_path, label):
            if not label or label.strip().lower() == "wszystkie":
                self.init_main_view()
                return
            resolved = folder_path or self._resolve_folder_path(label)
            self.show_folder_view(resolved, label)

        popup_folders = [f for f in self.folders if (f.get("label") or "").strip().lower() != "wszystkie"]

        self._folders_popup = FolderPopup(
            self.window() or self,
            popup_folders,
            on_select,
            on_close=self._on_popup_closed,
            on_rename=self._rename_notes_folder,
            on_delete=self._delete_notes_folder,
            on_toggle_pin=self._toggle_pin_from_popup,
            is_pinned=lambda folder: self._is_folder_pinned((folder or {}).get("label")) if isinstance(folder, dict) else self._is_folder_pinned(folder),
        )
        prefer_width = 220
        self.more_btn.setText("▴")
        self._folders_popup.show_near(self.more_btn, prefer_width=prefer_width)

    def eventFilter(self, obj, event):
        name = obj.objectName() if hasattr(obj, "objectName") else ""
        if name in ("topHeader", "bottomHeader", "bottomFrame") and event.type() == QEvent.Type.Resize:
            apply_rounded_mask(obj, 12.0)
        
        return super().eventFilter(obj, event)
    
    def _search_files(self, query: str):
        """Wyszukaj pliki pasujące do zapytania"""
        query_lower = query.lower().strip()
        if not query_lower:
            return []
        
        try:
            all_files = get_all_notes()
        except Exception:
            return []
        
        results = []
        for file_path in all_files:
            filename = os.path.basename(file_path)
            name_without_ext = os.path.splitext(filename)[0]
            
            # Wyszukiwanie po fragmencie nazwy (case-insensitive)
            if query_lower in name_without_ext.lower():
                # Znajdź folder
                folder_name = "Główny"
                try:
                    parent_dir = os.path.basename(os.path.dirname(file_path))
                    # Jeśli parent_dir to 'notes', to jest w katalogu głównym
                    if parent_dir and parent_dir.lower() != 'notes':
                        folder_name = parent_dir
                except Exception:
                    pass
                
                results.append({
                    "path": file_path,
                    "name": name_without_ext,
                    "folder": folder_name
                })
        
        return results[:3]  # Maksymalnie 3 wyniki
    
    def on_search_text_changed(self, text):
        """Obsługa zmiany tekstu w polu wyszukiwania """
        # Zatrzymaj poprzedni timer
        self._search_timer.stop()
        
        query = text.strip()
        self._search_query = query
        
        # Jeśli pole puste, zamknij popup
        if not query:
            if self._search_popup and self._search_popup.isVisible():
                self._search_popup.close()
                self._search_popup = None
            return
        
        # Uruchom timer - wyszukiwanie nastąpi po 300ms
        self._search_timer.start()
    
    def _perform_search(self):
        """Wykonaj wyszukiwanie po opóźnieniu """
        if not self._search_query:
            return
        
        # Wyszukaj pliki
        results = self._search_files(self._search_query)
        if results:
            self._show_search_popup(results)
        else:
            # Brak wyników - zamknij popup
            if self._search_popup and self._search_popup.isVisible():
                self._search_popup.close()
                self._search_popup = None
    
    def _show_search_popup(self, files):
        """Wyświetl popup z wynikami wyszukiwania pod polem tekstowym"""
        if self._search_popup:
            try:
                self._search_popup.close()
                self._search_popup.deleteLater()
            except Exception:
                pass
        
        self._search_popup = QFrame(
            self.window() or self, 
            Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint
        )
        self._search_popup.setObjectName("searchPopup")
        self._search_popup.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._search_popup.setStyleSheet("""
            QFrame#searchPopup {
                background: white;
                border: 1px solid rgba(0,0,0,0.12);
                border-radius: 8px;
            }
            QPushButton.searchItem {
                text-align: left;
                padding: 8px 12px;
                border: none;
                background: transparent;
                color: #222;
                font-size: 13px;
                min-height: 36px;
            }
            QPushButton.searchItem:hover {
                background: #f0f4ff;
                border-radius: 6px;
            }
        """)
        
        popup_layout = QVBoxLayout(self._search_popup)
        popup_layout.setContentsMargins(8, 8, 8, 8)
        popup_layout.setSpacing(2)
        
        # Wyniki
        for file_info in files:
            btn = QPushButton()
            btn.setProperty("class", "searchItem")
            btn.setFlat(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            
            # Layout dla przycisku
            btn_layout = QHBoxLayout(btn)
            btn_layout.setContentsMargins(8, 6, 8, 6)
            btn_layout.setSpacing(12)
            
            # Nazwa pliku (po lewej)
            name_label = QLabel(file_info["name"])
            name_label.setStyleSheet("font-weight: 600; color: #222; font-size: 13px;")
            btn_layout.addWidget(name_label, stretch=1)
            
            # Folder (po prawej, mniejszy tekst)
            folder_label = QLabel(file_info['folder'])
            folder_label.setStyleSheet("color: #888; font-size: 11px;")
            folder_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            btn_layout.addWidget(folder_label)
            
            file_path = file_info["path"]
            btn.clicked.connect(lambda checked=False, path=file_path: self._open_from_search(path))
            
            popup_layout.addWidget(btn)
        
        # Pozycjonowanie popup pod polem wyszukiwania
        search_rect = self.search_input.rect()
        global_pos = self.search_input.mapToGlobal(search_rect.bottomLeft())
        
        self._search_popup.setFixedWidth(self.search_input.width())
        self._search_popup.adjustSize()
        
        self._search_popup.move(global_pos.x(), global_pos.y() + 6)
        self._search_popup.show()
        self._search_popup.raise_()
        self._search_popup.setFocus()
    
    def _open_from_search(self, file_path):
        """Otwórz plik z popupu wyszukiwania"""
        # Zamknij popup
        if self._search_popup:
            self._search_popup.close()
            self._search_popup = None
        
        # Otwórz plik
        self._open_path(file_path)

    def on_chip_clicked(self):
        sender = self.sender()
        if sender is None:
            return

        for b in self.chip_buttons:
            b.setChecked(b is sender)

        label = (sender.property("folder_label") or sender.text() or "").strip()
        if label.lower() == "wszystkie":
            self.init_main_view()
            return

        self.show_folder_view(None, label)

    def on_new_note(self):
        """Utworz nowy folder notatek"""
        from PyQt6.QtWidgets import QInputDialog
        
        folder_name, ok = QInputDialog.getText(
            self,
            "Nowy folder",
            "Podaj nazwe nowego folderu:",
            QLineEdit.EchoMode.Normal
        )
        
        if ok and folder_name.strip():
            # Sprawdz czy folder juz istnieje
            if any(f["label"] == folder_name.strip() for f in self.folders):
                QMessageBox.warning(self, "Blad", f"Folder '{folder_name.strip()}' juz istnieje!")
                return
            
            try:
                # Utworz fizyczny folder
                folder_path = os.path.join(NOTES_DIR, folder_name.strip())
                os.makedirs(folder_path, exist_ok=True)
                
                # Odswiez liste folderow i widok
                self.refresh_folder_list()
                self.init_main_view()
                
                QMessageBox.information(
                    self, 
                    "Sukces", 
                    f"Folder '{folder_name.strip()}' zostal utworzony!"
                )
                
            except Exception as e:
                QMessageBox.critical(self, "Blad", f"Nie udalo sie utworzyc folderu:\n{str(e)}")

    def init_notes_sidebar(self):
        self.notes_sidebar = QFrame(self.notesSidebarFrame)
        self.notes_sidebar.setObjectName("notesSidebar")
        self.notes_sidebar.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.notes_sidebar.setStyleSheet("""
            QFrame#notesSidebar {
                background-color: rgba(255,255,255,180);
                border-top-left-radius: 32px;
                border-bottom-left-radius: 32px;
                border-top-right-radius: 0px;
                border-bottom-right-radius: 0px;
            }
        """)
        self.notes_sidebar.setMinimumWidth(self.sidebar_collapsed_width)
        self.notes_sidebar.setMaximumWidth(self.sidebar_width)
        self.notes_sidebar.raise_()

        self.toggle_btn = QPushButton("<", self.notes_sidebar)
        self.toggle_btn.setFixedSize(36, 36)
        self.toggle_btn.setStyleSheet("""
            QPushButton {
                background:#e6edff;
                border:none;
                border-top-left-radius:18px;
                border-bottom-left-radius:18px;
                border-top-right-radius:0px;
                border-bottom-right-radius:0px;
                font-size:16px;
                color:#3960f5;
            }
            QPushButton:hover { background:#d0e0ff; }
        """)
        self.toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.toggle_btn.clicked.connect(self.toggle_notes_sidebar)

        self.calc_btn = QPushButton()
        candidates_dirs = [
            os.path.join(os.path.dirname(__file__), "assets", "icons"),
            os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "assets", "icons")),
            os.path.abspath(os.path.join(os.getcwd(), "assets", "icons")),
        ]
        chosen_path = None
        for d in candidates_dirs:
            if os.path.isdir(d):
                try:
                    for fn in os.listdir(d):
                        if "calculator" in fn.lower():
                            chosen_path = os.path.join(d, fn)
                            break
                except Exception:
                    chosen_path = None
            if chosen_path:
                break

        if chosen_path and os.path.exists(chosen_path):
            self.calc_btn.setIcon(QIcon(chosen_path))
        else:
            self.calc_btn.setIcon(QIcon.fromTheme("accessories-calculator"))

        if self.calc_btn.icon().isNull():
            self.calc_btn.setText("C")
            self.calc_btn.setStyleSheet(
                "border: none; background: transparent; font-weight: bold; color: #3960f5;"
            )
        else:
            self.calc_btn.setStyleSheet("border: none; background: transparent;")
        self.calc_btn.setIconSize(QSize(40, 40))
        self.calc_btn.setFixedSize(56, 56)
        self.calc_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.calc_btn.clicked.connect(self.show_calculator)

        self.notes_content = QWidget()
        nc_layout = QVBoxLayout(self.notes_content)
        nc_layout.setContentsMargins(16, 16, 16, 16)
        nc_layout.setSpacing(12)
        
        # Nagłówek z przyciskiem zapisu
        header_row = QHBoxLayout()
        header_row.setSpacing(8)
        nc_label = QLabel("Twoje notatki")
        nc_label.setStyleSheet("font-size:18px; font-weight:bold;")
        header_row.addWidget(nc_label)
        header_row.addStretch()
        
        self.save_note_btn = QPushButton("Zapisz")
        self.save_note_btn.setFixedHeight(32)
        self.save_note_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.save_note_btn.setStyleSheet("""
            QPushButton {
                background: #3960f5;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 6px 12px;
                font-size: 13px;
                font-weight: 600;
            }
            QPushButton:hover {
                background: #2e4fd0;
            }
            QPushButton:pressed {
                background: #1e3db0;
            }
        """)
        self.save_note_btn.clicked.connect(self.show_save_note_dialog)
        header_row.addWidget(self.save_note_btn)
        
        nc_layout.addLayout(header_row)
        
        self.notes_edit = QTextEdit()
        self.notes_edit.setPlaceholderText("Zapisz tutaj swoje notatki...")
        self.notes_edit.setStyleSheet(
            "font-size:15px; border:2px solid rgba(57,96,245,0.3); border-radius:8px; background:#f8faff; margin-left:8px; min-height:180px; min-width:180px; padding:14px;"
        )
        nc_layout.addWidget(self.notes_edit, stretch=1)

        self.sidebar_layout = QVBoxLayout(self.notes_sidebar)
        self.sidebar_layout.setContentsMargins(0, 0, 0, 0)
        self.sidebar_layout.setSpacing(0)
        self.set_sidebar_state(False)

    def bring_sidebar_front(self):
        self.notesSidebarFrame.raise_()
        self.notes_sidebar.raise_()
        for w in self.findChildren(QWidget):
            if w not in (self.notes_sidebar, self.notesSidebarFrame):
                w.stackUnder(self.notesSidebarFrame)

    def set_sidebar_state(self, expanded):
        self.sidebar_expanded = expanded
        clear_layout(self.sidebar_layout)

        target_width = self.sidebar_width if expanded else self.sidebar_collapsed_width

        if self.sidebar_overlay_mode:
            start_geom = self.notes_sidebar.geometry()
            end_geom = QRectF(max(self.width() - target_width, 0), 0, target_width, self.height()).toRect()
            anim = QPropertyAnimation(self.notes_sidebar, b"geometry")
            anim.setDuration(220)
            anim.setStartValue(start_geom)
            anim.setEndValue(end_geom)
            anim.start()
            self._sidebar_anim = anim
        else:
            self.notes_sidebar.setFixedWidth(target_width)

        if expanded:
            content_row = QHBoxLayout()
            content_row.setContentsMargins(0, 0, 0, 0)
            content_row.setSpacing(0)
            content_row.addWidget(self.notes_content, stretch=1)
            btn_col = QVBoxLayout()
            spacer = QSpacerItem(20, 334, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
            btn_col.addItem(spacer)
            btn_col.addWidget(self.toggle_btn, alignment=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            btn_col.addStretch(1)
            content_row.addLayout(btn_col)
            self.sidebar_layout.addLayout(content_row)
            self.calc_btn.hide()
            self.notes_content.show()
            self.toggle_btn.setText(">")
            self.bring_sidebar_front()
        else:
            col = QVBoxLayout()
            col.setContentsMargins(0, 0, 0, 0)
            col.setSpacing(0)
            spacer = QSpacerItem(20, 334, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
            col.addItem(spacer)
            toggle_row = QHBoxLayout()
            toggle_row.setContentsMargins(6, 0, 0, 0)
            toggle_row.addWidget(self.toggle_btn, alignment=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            col.addLayout(toggle_row)
            col.addStretch(1)
            bottom_h = QHBoxLayout()
            bottom_h.setContentsMargins(4, 0, 0, 0)
            bottom_h.addWidget(self.calc_btn, alignment=Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom)
            col.addLayout(bottom_h)
            self.sidebar_layout.addLayout(col)
            self.calc_btn.show()
            self.notes_content.hide()
            self.toggle_btn.setText("<")
            self.bring_sidebar_front()
        self.adjust_header_right_margin()

    def set_sidebar_overlay_mode(self, enabled: bool):
        if enabled == self.sidebar_overlay_mode:
            return
        self.sidebar_overlay_mode = enabled
        if enabled:
            self.root_layout.removeWidget(self.notes_sidebar)
            w = self.sidebar_width if self.sidebar_expanded else self.sidebar_collapsed_width
            self.notes_sidebar.setParent(self.notesSidebarFrame)
            self.notes_sidebar.setGeometry(max(self.width() - w, 0), 0, w, self.height())
            self.notes_sidebar.raise_()
        else:
            self.root_layout.addWidget(self.notes_sidebar, stretch=0)
            self.notes_sidebar.setFixedWidth(self.sidebar_width if self.sidebar_expanded else self.sidebar_collapsed_width)

    def resizeEvent(self, event):
        self.notesSidebarFrame.setGeometry(0, 0, self.width(), self.height())
        if self.sidebar_overlay_mode:
            current_width = self.sidebar_width if self.sidebar_expanded else self.sidebar_collapsed_width
            self.notes_sidebar.setGeometry(max(self.width() - current_width, 0), 0, current_width, self.height())
        self.adjust_header_right_margin()
        super().resizeEvent(event)

    def toggle_notes_sidebar(self):
        self.set_sidebar_state(not self.sidebar_expanded)

    def show_calculator(self):
        from ui.calculator_view import CalculatorDialog
        dlg = CalculatorDialog(self)
        dlg.exec()
    
    def show_save_note_dialog(self):
        
        text = self.notes_edit.toPlainText().strip()
        
        if not text:
            QMessageBox.warning(self, "Pusta notatka", "Notatka jest pusta. Wpisz coś przed zapisaniem!")
            return
        
        dialog = SaveNoteDialog(self, self.folders)
        
        if dialog.exec() == QDialog.DialogCode.Accepted:
            filename = dialog.get_full_filename()
            folder_label = dialog.get_folder_label()
            
            if not folder_label:
                QMessageBox.warning(self, "Błąd", "Wybierz folder!")
                return
            
            try:
                # Zapisz tymczasowo jako plik tekstowy
                import tempfile
                with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', delete=False, suffix='.txt') as tmp:
                    tmp.write(text)
                    tmp_path = tmp.name
                
                # Użyj add_existing_note_file() - konwertuje TXT → BGH (JSON)
                from core.notes import add_existing_note_file
                
                # Zapisz używając istniejącej funkcji (jak przy dodawaniu pliku z komputera)
                saved_path = add_existing_note_file(folder_label, tmp_path)
                
                # Usuń tymczasowy plik
                try:
                    os.unlink(tmp_path)
                except Exception:
                    pass
                
                # Zmień nazwę na żądaną (jeśli inna niż domyślna)
                target_name = os.path.splitext(filename)[0] + ".bgh"
                target_path = os.path.join(os.path.dirname(saved_path), target_name)
                
                if saved_path != target_path and not os.path.exists(target_path):
                    os.rename(saved_path, target_path)
                    saved_path = target_path
                
                QMessageBox.information(
                    self,
                    "Sukces",
                    f"Notatka została zapisana!\n\nFolder: {folder_label}\nPlik: {os.path.basename(saved_path)}"
                )
                
                # Wyczyść pole tekstowe
                self.notes_edit.clear()
                
                # Odśwież widok główny żeby pokazać nowy plik na kafelkach
                self.refresh_folder_list()
                self.init_main_view()
                
            except Exception as e:
                QMessageBox.critical(self, "Błąd", f"Nie udało się zapisać pliku:\n{str(e)}")
    
    
    def show_folder_view(self, folder_path, label):
        """Pokaż widok folderu z plikami (dla notatek folder_path nie ma znaczenia, używany jest label)"""
        self.set_notes_frame_border_visible(False)
        self._sidebar_prev_visible = self.notes_sidebar.isVisible()
        self.notes_sidebar.hide()
        self.toggle_btn.setEnabled(False)

        clear_layout(self.main_layout)
        if self._folder_view is None:
            self._folder_view = FolderView(
                self,
                folders=self.folders,
                on_open_folder=lambda p, l: self.show_folder_view(p, l),
                on_back=self.init_main_view,
            )
        
        resolved = folder_path or self._resolve_folder_path(label)
        self._folder_view.show_folder_view(resolved, label)
        self.main_layout.addWidget(self._folder_view)
        self.notesSidebarFrame.raise_()
        