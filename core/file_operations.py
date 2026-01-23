# -*- coding: utf-8 -*-
"""
Operacje na plikach notatek - duplikowanie, przenoszenie, zmiana nazwy, usuwanie.
"""
import os
import shutil
from typing import Optional, List


def create_folder_selection_dialog(parent, folders: List[str], title: str = "Wybierz folder") -> Optional[str]:
    """
    Utworz ladny dialog wyboru folderu.
    
    Args:
        parent: Widget rodzic
        folders: Lista nazw folderow
        title: Tytul dialogu
        
    Returns:
        Wybrana nazwa folderu lub None
    """
    try:
        from PyQt6.QtWidgets import QDialog, QVBoxLayout, QLabel, QPushButton, QScrollArea, QWidget, QFrame
        from PyQt6.QtCore import Qt
        
        dialog = QDialog(parent)
        dialog.setWindowTitle(title)
        dialog.setModal(True)
        dialog.setMinimumWidth(350)
        dialog.setStyleSheet("background: white;")
        
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)
        
        # Tytul
        title_label = QLabel(title)
        title_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #222;")
        layout.addWidget(title_label)
        
        # Scroll area z folderami
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("""
            QScrollArea {
                border: 1px solid #e0e0e0;
                border-radius: 8px;
                background: white;
            }
        """)
        
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(8, 8, 8, 8)
        content_layout.setSpacing(4)
        
        selected_folder = [None]  # Mutable container for selection
        
        def make_select_handler(folder_name):
            def handler():
                selected_folder[0] = folder_name
                dialog.accept()
            return handler
        
        # Przyciski folderow
        for folder in folders:
            btn = QPushButton(f" {folder}")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet("""
                QPushButton {
                    text-align: left;
                    padding: 12px 16px;
                    border: 1px solid #e0e0e0;
                    border-radius: 6px;
                    background: white;
                    color: #222;
                    font-size: 14px;
                }
                QPushButton:hover {
                    background: #f0f4ff;
                    border: 1px solid #3960f5;
                    color: #3960f5;
                }
            """)
            btn.clicked.connect(make_select_handler(folder))
            content_layout.addWidget(btn)
        
        scroll.setWidget(content)
        scroll.setMinimumHeight(min(400, len(folders) * 50 + 20))
        layout.addWidget(scroll)
        
        # Przycisk anuluj
        cancel_btn = QPushButton("Anuluj")
        cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_btn.setStyleSheet("""
            QPushButton {
                padding: 10px 20px;
                border: none;
                border-radius: 6px;
                background: #f0f0f0;
                color: #444;
                font-size: 14px;
                font-weight: 600;
            }
            QPushButton:hover {
                background: #e0e0e0;
            }
        """)
        cancel_btn.clicked.connect(dialog.reject)
        layout.addWidget(cancel_btn)
        
        if dialog.exec() == QDialog.DialogCode.Accepted:
            return selected_folder[0]
        return None
        
    except Exception:
        # Fallback do standardowego dialogu
        from PyQt6.QtWidgets import QInputDialog
        folder, ok = QInputDialog.getItem(parent, title, "Wybierz folder:", folders, 0, False)
        return folder if ok else None


def duplicate_file(file_path: str) -> Optional[str]:
    """
    Duplikuj plik, zwroc sciezke nowego pliku lub None w przypadku bledu.
    
    Args:
        file_path: Sciezka do pliku do zduplikowania
        
    Returns:
        Sciezka do nowego pliku lub None
    """
    try:
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Plik nie istnieje: {file_path}")
        
        # Wygeneruj nowa nazwe
        directory = os.path.dirname(file_path)
        filename = os.path.basename(file_path)
        name, ext = os.path.splitext(filename)
        
        counter = 1
        new_path = os.path.join(directory, f"{name}_kopia{ext}")
        while os.path.exists(new_path):
            new_path = os.path.join(directory, f"{name}_kopia_{counter}{ext}")
            counter += 1
        
        # Kopiuj plik
        shutil.copy2(file_path, new_path)
        return new_path
        
    except Exception as e:
        raise Exception(f"Nie udalo sie zduplikowac pliku: {str(e)}")


def move_file_to_folder(file_path: str, target_folder_label: str, base_notes_path: str, overwrite: bool = False) -> Optional[str]:
    """
    Przenies plik do innego folderu notatek.
        
    Args:
        file_path: Sciezka do pliku do przeniesienia
        target_folder_label: Nazwa folderu docelowego (np. "Folder 1")
        base_notes_path: Bazowa sciezka do folderow notatek (np. "data/notes")
        overwrite: Czy nadpisac jesli plik juz istnieje
            
    Returns:
        Nowa sciezka do pliku lub None
    """
    try:
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Plik nie istnieje: {file_path}")
            
        # Sciezka docelowa
        target_dir = os.path.join(base_notes_path, target_folder_label)
        os.makedirs(target_dir, exist_ok=True)
            
        filename = os.path.basename(file_path)
        target_path = os.path.join(target_dir, filename)
            
        # Sprawdz czy plik juz istnieje
        if os.path.exists(target_path) and not overwrite:
            raise FileExistsError(f"Plik '{filename}' juz istnieje w folderze '{target_folder_label}'")
            
        # Sprawdz czy plik byl ulubiony PRZED przeniesieniem
        was_favorite = False
        try:
            from core.notes import is_favorite, toggle_favorite, _load_favorites, _save_favorites
            was_favorite = is_favorite(file_path)
        except Exception:
            pass
            
        # Przenies plik
        shutil.move(file_path, target_path)
            
        # Jesli byl ulubiony, zaktualizuj ulubione na nowa sciezke
        if was_favorite:
            try:
                favs = _load_favorites()
                # Usun stara sciezke
                favs.discard(file_path)
                # Dodaj nowa sciezke
                favs.add(target_path)
                _save_favorites(favs)
            except Exception:
                pass
            
        return target_path
            
    except Exception as e:
        raise Exception(f"Nie udalo sie przeniesc pliku: {str(e)}")


def rename_file(file_path: str, new_name: str, keep_extension: bool = True) -> Optional[str]:
    """
    Zmien nazwe pliku.
            
    Returns:
        Nowa sciezka do pliku lub None
    """
    try:
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Plik nie istnieje: {file_path}")
            
        directory = os.path.dirname(file_path)
            
        if keep_extension:
            ext = os.path.splitext(file_path)[1]
            new_filename = new_name.strip() + ext
        else:
            new_filename = new_name.strip()
            
        new_path = os.path.join(directory, new_filename)
            
        if os.path.exists(new_path):
            raise FileExistsError("Plik o tej nazwie juz istnieje!")
            
        # Sprawdz czy plik byl ulubiony PRZED zmiana nazwy
        was_favorite = False
        try:
            from core.notes import is_favorite, _load_favorites, _save_favorites
            was_favorite = is_favorite(file_path)
        except Exception:
            pass
            
        # Zmien nazwe
        os.rename(file_path, new_path)
            
        # Jesli byl ulubiony, zaktualizuj ulubione na nowa sciezke
        if was_favorite:
            try:
                favs = _load_favorites()
                # Usun stara sciezke
                favs.discard(file_path)
                # Dodaj nowa sciezke
                favs.add(new_path)
                _save_favorites(favs)
            except Exception:
                pass
            
        return new_path
            
    except Exception as e:
        raise Exception(f"Nie udalo sie zmienic nazwy: {str(e)}")


def delete_file(file_path: str, permanent: bool = True) -> bool:
    """
    Usun plik.    
    Returns:
        True jesli sukces, False w przypadku bledu
    """
    try:
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Plik nie istnieje: {file_path}")
        
        os.remove(file_path)
        return True
        
    except Exception as e:
        raise Exception(f"Nie udalo sie usunac pliku: {str(e)}")


def get_file_info(file_path: str) -> dict:
    """
    Pobierz informacje o pliku.
    
    Returns:
        Dict z kluczami: name, name_without_ext, extension, size, modified, created
    """
    try:
        stat = os.stat(file_path)
        filename = os.path.basename(file_path)
        name_without_ext = os.path.splitext(filename)[0]
        extension = os.path.splitext(filename)[1]
        
        return {
            "name": filename,
            "name_without_ext": name_without_ext,
            "extension": extension,
            "size": stat.st_size,
            "modified": stat.st_mtime,
            "created": getattr(stat, "st_ctime", stat.st_mtime),
            "path": file_path,
            "directory": os.path.dirname(file_path)
        }
    except Exception:
        return {}
