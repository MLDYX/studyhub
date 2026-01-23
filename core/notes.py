import json
import os
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Set

MAX_CONTENT_LENGTH = 10 * 1024 * 1024
ALLOWED_EXTENSIONS = {
    '.txt', '.docx', '.pdf', '.bgh', '.md', '.log', '.ini', '.cfg', '.csv', '.json', '.xml', '.yml', '.yaml',
    '.png', '.jpg', '.jpeg', '.bmp', '.gif', '.webp', '.ico', '.svg',
    '.mp4', '.mov', '.mkv', '.avi', '.webm', '.m4v', '.flv', '.wmv',
    '.mp3', '.flac', '.m4a', '.ogg', '.opus', '.wav', '.aac'
}

try:
    from docx import Document
    HAS_DOCX = True
except ImportError:
    HAS_DOCX = False

try:
    from PyPDF2 import PdfReader
    HAS_PDF = True
except ImportError:
    HAS_PDF = False

NOTES_DIR = os.path.join(os.getcwd(), "data", "notes")
os.makedirs(NOTES_DIR, exist_ok=True)

FAVORITES_PATH = os.path.join(os.getcwd(), "data", "favorites.json")


def _load_favorites() -> Set[str]:
    try:
        if os.path.exists(FAVORITES_PATH):
            with open(FAVORITES_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                return set(data)
    except Exception:
        pass
    return set()


def _save_favorites(favs: Set[str]):
    try:
        os.makedirs(os.path.dirname(FAVORITES_PATH), exist_ok=True)
        with open(FAVORITES_PATH, "w", encoding="utf-8") as f:
            json.dump(sorted(list(favs)), f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def is_favorite(path: str) -> bool:
    if not path:
        return False
    try:
        favs = _load_favorites()
        return path in favs
    except Exception:
        return False


def toggle_favorite(path: str) -> bool:
    if not path:
        return False
    
    try:
        favs = _load_favorites()
        
        if path in favs:
            favs.discard(path)
            _save_favorites(favs)
            return False
        else:
            favs.add(path)
            _save_favorites(favs)
            return True
    except Exception:
        return False


def get_favorites_in_folder(folder_name):
    try:
        files = get_notes_in_folder(folder_name)
        favs = _load_favorites()
        
        if not favs:
            return []
        
        return [f for f in files if f in favs]
    except Exception:
        return []


def get_all_favorites():
    try:
        favs = _load_favorites()
        
        if not favs:
            return []
        
        result = []
        for fav_path in favs:
            if os.path.exists(fav_path):
                result.append(fav_path)
        
        return result
    except Exception:
        return []


def _is_safe_path(path, base_dir=None):
    """Sprawdz czy sciezka jest bezpieczna (bez path traversal)."""
    if not path:
        return False
    try:
        if base_dir:
            abs_base = os.path.abspath(base_dir)
            abs_path = os.path.abspath(path)
            return abs_path.startswith(abs_base)
        
        normalized = os.path.normpath(path)
        if ".." in normalized:
            return False
        return True
    except Exception:
        return False


def _sanitize_text(text, max_length=MAX_CONTENT_LENGTH):
    """Sanityzuj tekst usuwajac potencjalnie niebezpieczne tresci."""
    if not text:
        return ""
    if len(text) > max_length:
        text = text[:max_length]
    text = re.sub(r'[\x00-\x08\x0B-\x0C\x0E-\x1F\x7F]', '', text)
    return text


def read_txt(path):
    return Path(path).read_text(encoding="utf-8", errors="replace").strip()


def read_docx(path):
    if not HAS_DOCX:
        raise RuntimeError("Brak biblioteki python-docx. Zainstaluj: pip install python-docx")
    
    doc = Document(str(path))
    text_lines = [p.text for p in doc.paragraphs]
    return "\n".join(text_lines).strip()


def read_pdf(path):
    if not HAS_PDF:
        raise RuntimeError("Brak biblioteki PyPDF2. Zainstaluj: pip install PyPDF2")
    
    reader = PdfReader(str(path))
    text_parts = []
    
    for page in reader.pages:
        text = (page.extract_text() or "").strip()
        if text:
            text_parts.append(text)
    
    return "\n\n".join(text_parts).strip()


FILE_READERS = {
    ".txt": read_txt,
    ".docx": read_docx,
    ".pdf": read_pdf,
}


def get_notes_in_folder(folder_name, extensions=None):
    if not folder_name or ".." in folder_name or "/" in folder_name or "\\" in folder_name:
        return []
    
    folder_path = os.path.join(NOTES_DIR, folder_name)
    
    if not _is_safe_path(folder_path, NOTES_DIR):
        return []
    
    if not os.path.isdir(folder_path):
        return []
    
    allowed = None
    if extensions:
        allowed = {str(ext).lower().lstrip('.') for ext in extensions}

    files = []
    for filename in os.listdir(folder_path):
        full_path = os.path.join(folder_path, filename)
        if not os.path.isfile(full_path):
            continue
        if allowed is not None:
            file_ext = os.path.splitext(filename)[1].lower().lstrip('.')
            if file_ext not in allowed:
                continue
        files.append(full_path)

    return sorted(files, key=lambda p: os.path.basename(p).lower())


def add_existing_note_file(folder_name, file_path):
    """Dodaj plik do folderu notatek - sprobuj konwersji do JSON (.bgh)."""
    if not folder_name:
        raise ValueError("Nazwa folderu nie moze byc pusta")
    
    if ".." in folder_name or "/" in folder_name or "\\" in folder_name:
        raise ValueError("Nazwa folderu zawiera niedozwolone znaki")
    
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Plik nie istnieje: {file_path}")
    
    if not _is_safe_path(file_path):
        raise ValueError("Nieprawidlowa sciezka pliku")
    
    target_folder = os.path.join(NOTES_DIR, folder_name)
    os.makedirs(target_folder, exist_ok=True)
    
    src = Path(file_path)
    extension = src.suffix.lower()
    
    if extension and extension not in ALLOWED_EXTENSIONS:
        raise ValueError(f"Niedozwolone rozszerzenie pliku: {extension}")
    
    reader = FILE_READERS.get(extension)
    
    if reader is None:
        dest_path = os.path.join(target_folder, src.name)
        
        if os.path.exists(dest_path):
            base = src.stem
            counter = 1
            while os.path.exists(dest_path):
                new_name = f"{base}_{counter}{src.suffix}"
                dest_path = os.path.join(target_folder, new_name)
                counter += 1
        
        shutil.copy(file_path, dest_path)
        return dest_path
    
    try:
        content = reader(src)
        
        if not content or not content.strip():
            raise ValueError(f"Plik {src.name} jest pusty lub nie udalo sie odczytac zawartosci")
        
        safe_content = _sanitize_text(content)
        safe_title = _sanitize_text(src.stem, max_length=200)
        
        note_data = {
            "tytul": safe_title,
            "tresc": safe_content,
            "tagi": [],
            "data": datetime.now().strftime("%Y-%m-%d"),
            "oryginalny_format": extension.lstrip('.'),
        }
        
        dest_path = Path(target_folder) / f"{src.stem}.bgh"
        if dest_path.exists():
            base = src.stem
            counter = 1
            while dest_path.exists():
                dest_path = Path(target_folder) / f"{base}_{counter}.bgh"
                counter += 1
        
        dest_path.write_text(
            json.dumps(note_data, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
        
        return str(dest_path)
        
    except Exception as error:
        dest_path = os.path.join(target_folder, src.name)
        
        if os.path.exists(dest_path):
            base = src.stem
            counter = 1
            while os.path.exists(dest_path):
                new_name = f"{base}_{counter}{src.suffix}"
                dest_path = os.path.join(target_folder, new_name)
                counter += 1
        
        shutil.copy(file_path, dest_path)
        raise Exception(f"Blad konwersji {src.name}: {error}. Plik zostal skopiowany bez konwersji.") from error


def get_all_notes(extensions=None):
    if not os.path.isdir(NOTES_DIR):
        return []
    
    all_files = []
    for folder_name in os.listdir(NOTES_DIR):
        folder_path = os.path.join(NOTES_DIR, folder_name)
        if os.path.isdir(folder_path):
            folder_files = get_notes_in_folder(folder_name, extensions)
            all_files.extend(folder_files)
    
    return all_files


def ensure_notes_subfolders(folder_labels):
    for label in folder_labels:
        if not label or str(label).strip().lower() == "wszystkie":
            continue
        folder_path = os.path.join(NOTES_DIR, label)
        os.makedirs(folder_path, exist_ok=True)
