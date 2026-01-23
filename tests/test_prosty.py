"""
Testy jednostkowe dla aplikacji StudyHub
Autor: Marcin
"""

import unittest
import sys
import os
import tempfile
import shutil
import json

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from ui.folders_view import FolderView
from core.notes import (
    read_txt,
    toggle_favorite,
    get_notes_in_folder,
    ensure_notes_subfolders,
    add_existing_note_file,
    get_all_notes,
    NOTES_DIR,
    _save_favorites,
    is_favorite
)
from core.file_operations import duplicate_file, get_file_info, move_file_to_folder


class Test1_SanitizeFilename(unittest.TestCase):
    """Test 1: Walidacja nazw plików"""
    
    def test_usuwa_niebezpieczne_znaki(self):
        """Usuwa znaki < > : " | ? * z nazwy pliku"""
        wynik = FolderView._sanitize_filename("plik<test>.txt")
        self.assertEqual(wynik, "pliktest.txt")


class Test2_ReadTxt(unittest.TestCase):
    """Test 2: Czytanie plików TXT"""
    
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
    
    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_czyta_polskie_znaki(self):
        """Czyta pliki z polskimi znakami (UTF-8)"""
        test_file = os.path.join(self.temp_dir, "test.txt")
        
        with open(test_file, "w", encoding="utf-8") as f:
            f.write("Zażółć gęślą jaźń")
        
        wynik = read_txt(test_file)
        self.assertIn("ą", wynik)


class Test3_DuplicateFile(unittest.TestCase):
    """Test 3: Duplikowanie plików"""
    
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
    
    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_tworzy_kopie_z_unikalna_nazwa(self):
        """Tworzy kopię pliku z suffixem _kopia"""
        oryginal = os.path.join(self.temp_dir, "test.txt")
        with open(oryginal, "w") as f:
            f.write("zawartość")
        
        kopia = duplicate_file(oryginal)
        
        self.assertIn("_kopia", kopia)
        self.assertTrue(os.path.exists(kopia))


class Test4_GetFileInfo(unittest.TestCase):
    """Test 4: Pobieranie informacji o pliku"""
    
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
    
    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_zwraca_metadata(self):
        """Zwraca nazwę, rozszerzenie i rozmiar pliku"""
        test_file = os.path.join(self.temp_dir, "raport.xlsx")
        
        with open(test_file, "w") as f:
            f.write("test")
        
        info = get_file_info(test_file)
        
        self.assertEqual(info["name_without_ext"], "raport")
        self.assertEqual(info["extension"], ".xlsx")


class Test5_FolderViewSwitch(unittest.TestCase):
    """Test 5: Zmiana widoku folderu"""
    
    def setUp(self):
        """Utwórz dwa foldery z różnymi plikami"""
        self.folder_a = "TestViewA"
        self.folder_b = "TestViewB"
        
        self.path_a = os.path.join(NOTES_DIR, self.folder_a)
        self.path_b = os.path.join(NOTES_DIR, self.folder_b)
        
        os.makedirs(self.path_a, exist_ok=True)
        os.makedirs(self.path_b, exist_ok=True)
        
        # Dodaj pliki do Folder A
        for i in range(2):
            with open(os.path.join(self.path_a, f"plikA{i}.txt"), "w") as f:
                f.write(f"Folder A - plik {i}")
        
        # Dodaj pliki do Folder B
        for i in range(3):
            with open(os.path.join(self.path_b, f"plikB{i}.txt"), "w") as f:
                f.write(f"Folder B - plik {i}")
    
    def tearDown(self):
        """Usuń foldery testowe"""
        for path in [self.path_a, self.path_b]:
            if os.path.exists(path):
                shutil.rmtree(path)
    
    def test_widok_folderu_pokazuje_wlasciwe_pliki(self):
        """Po wyborze folderu widok pokazuje tylko jego pliki"""
        # Sprawdź Folder A
        pliki_a = get_notes_in_folder(self.folder_a)
        nazwy_a = [os.path.basename(p) for p in pliki_a]
        
        self.assertEqual(len(pliki_a), 2, "Folder A powinien mieć 2 pliki")
        self.assertTrue(all("plikA" in n for n in nazwy_a))
        
        # Sprawdź Folder B
        pliki_b = get_notes_in_folder(self.folder_b)
        nazwy_b = [os.path.basename(p) for p in pliki_b]
        
        self.assertEqual(len(pliki_b), 3, "Folder B powinien mieć 3 pliki")
        self.assertTrue(all("plikB" in n for n in nazwy_b))
        
        # Sprawdź że foldery mają różne pliki
        self.assertNotEqual(set(pliki_a), set(pliki_b))


class Test6_ToggleFavorite(unittest.TestCase):
    """Test 6: System ulubionych"""
    
    def tearDown(self):
        _save_favorites(set())
    
    def test_dodaje_i_usuwa_ulubione(self):
        """Toggle dodaje i usuwa plik z ulubionych"""
        plik = "/test/plik.txt"
        
        wynik1 = toggle_favorite(plik)
        self.assertTrue(wynik1)
        
        wynik2 = toggle_favorite(plik)
        self.assertFalse(wynik2)


class Test7_GetNotesInFolder(unittest.TestCase):
    """Test 7: Listowanie plików"""
    
    def setUp(self):
        self.folder = "TestSortFolder"
        self.path = os.path.join(NOTES_DIR, self.folder)
        os.makedirs(self.path, exist_ok=True)
    
    def tearDown(self):
        if os.path.exists(self.path):
            shutil.rmtree(self.path)
    
    def test_sortuje_alfabetycznie(self):
        """Sortuje pliki alfabetycznie A-Z"""
        for nazwa in ["zebra.txt", "alfa.txt"]:
            with open(os.path.join(self.path, nazwa), "w") as f:
                f.write("test")
        
        pliki = get_notes_in_folder(self.folder)
        nazwy = [os.path.basename(p) for p in pliki]
        
        self.assertEqual(nazwy, ["alfa.txt", "zebra.txt"])


class Test8_AddExistingNote(unittest.TestCase):
    """Test 8: Konwersja TXT na JSON"""
    
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.folder = "TestFolder"
        self.path = os.path.join(NOTES_DIR, self.folder)
        os.makedirs(self.path, exist_ok=True)
    
    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)
        if os.path.exists(self.path):
            shutil.rmtree(self.path)
    
    def test_konwertuje_txt_na_json(self):
        """Konwertuje plik TXT na format JSON (.bgh)"""
        txt = os.path.join(self.temp_dir, "test.txt")
        
        with open(txt, "w", encoding="utf-8") as f:
            f.write("Test notatki")
        
        wynik = add_existing_note_file(self.folder, txt)
        
        self.assertTrue(wynik.endswith(".bgh"))


class Test9_SanitizacjaZnakow(unittest.TestCase):
    """Test 9: Sanityzacja znaków kontrolnych"""
    
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.folder = "TestFolder"
        self.path = os.path.join(NOTES_DIR, self.folder)
        os.makedirs(self.path, exist_ok=True)
    
    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)
        if os.path.exists(self.path):
            shutil.rmtree(self.path)
    
    def test_usuwa_null_byte(self):
        """Usuwa znaki kontrolne (NULL byte) z tekstu"""
        txt = os.path.join(self.temp_dir, "test.txt")
        
        with open(txt, "w", encoding="utf-8") as f:
            f.write("Hello\x00World")
        
        wynik = add_existing_note_file(self.folder, txt)
        
        with open(wynik, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        self.assertNotIn("\x00", data["tresc"])


class Test10_MoveFile(unittest.TestCase):
    """Test 10: Przenoszenie plików"""
    
    def setUp(self):
        self.temp_base = tempfile.mkdtemp()
        self.folder1 = os.path.join(self.temp_base, "Folder1")
        self.folder2 = os.path.join(self.temp_base, "Folder2")
        os.makedirs(self.folder1)
        os.makedirs(self.folder2)
    
    def tearDown(self):
        shutil.rmtree(self.temp_base, ignore_errors=True)
        _save_favorites(set())
    
    def test_przenosi_plik_i_aktualizuje_ulubione(self):
        """Przenosi plik i aktualizuje ścieżkę w ulubionych"""
        plik = os.path.join(self.folder1, "test.txt")
        
        with open(plik, "w") as f:
            f.write("test")
        
        toggle_favorite(plik)
        
        nowa_sciezka = move_file_to_folder(plik, "Folder2", self.temp_base)
        
        self.assertTrue(is_favorite(nowa_sciezka))


class Test11_EdgeCases(unittest.TestCase):
    """Test 11: Przypadki brzegowe"""
    
    def test_nieistniejacy_folder(self):
        """Zwraca pustą listę dla nieistniejącego folderu"""
        pliki = get_notes_in_folder("NieistniejacyFolder")
        self.assertEqual(pliki, [])


class Test12_PathSecurity(unittest.TestCase):
    """Test 12: Bezpieczeństwo ścieżek"""
    
    def test_blokuje_path_traversal(self):
        """Blokuje próby path traversal (../)"""
        wynik = FolderView._is_safe_path("../../../etc/passwd")
        self.assertFalse(wynik)


if __name__ == "__main__":
    print("\n" + "="*60)
    print("TESTY JEDNOSTKOWE - STUDYHUB")
    print("="*60)
    print("\n12 testów dla kluczowych funkcji:")
    print("  1. Walidacja nazw plików")
    print("  2. Czytanie plików TXT")
    print("  3. Duplikowanie plików")
    print("  4. Metadata pliku")
    print("  5. Zmiana widoku folderu")
    print("  6. System ulubionych")
    print("  7. Sortowanie plików")
    print("  8. Konwersja TXT->JSON")
    print("  9. Sanityzacja znaków")
    print(" 10. Przenoszenie plików")
    print(" 11. Przypadki brzegowe")
    print(" 12. Bezpieczeństwo")
    print("="*60 + "\n")
    
    unittest.main(verbosity=2)