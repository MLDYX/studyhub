"""
Testy integracyjne dla notatek (core.notes).
"""

import json
import os
import tempfile
import unittest

from pathlib import Path

import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import core.notes as notes


class BaseNotesTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        notes.NOTES_DIR = os.path.join(self.temp_dir.name, "notes")
        notes.FAVORITES_PATH = os.path.join(self.temp_dir.name, "favorites.json")
        os.makedirs(notes.NOTES_DIR, exist_ok=True)

    def tearDown(self):
        self.temp_dir.cleanup()


def _print_suite_overview():
    lines = [
        "1. Konwersja TXT -> BGH z sanitacja",
        "2. Kopiowanie pliku z dozwolonym rozszerzeniem",
        "3. Odrzucenie niedozwolonego rozszerzenia",
        "4. Sortowanie i filtrowanie listy plikow",
        "5. Ulubione: dodanie i usuniecie",
        "-" * 62,
    ]
    print("\n".join(lines))


def load_tests(loader, tests, pattern):
    _print_suite_overview()
    return tests


class OkTestCase(unittest.TestCase):
    def run(self, result=None):
        result = super().run(result)
        failures = [test for test, _ in result.failures]
        errors = [test for test, _ in result.errors]
        skipped = [test for test, _ in result.skipped]
        if self not in failures and self not in errors and self not in skipped:
            name = self.id().split(".")[-2:]
            short = ".".join(name)
            print(f"{short} ... ok")
        return result


class Test1_AddExistingNoteTxtConverts(OkTestCase, BaseNotesTest):
    def test_txt_converts_to_bgh_and_sanitizes(self):
        folder = "FolderA"
        src_dir = Path(self.temp_dir.name) / "src"
        src_dir.mkdir(parents=True, exist_ok=True)
        src_path = src_dir / "note.txt"
        src_path.write_text("Hello\x00World", encoding="utf-8")

        result_path = notes.add_existing_note_file(folder, str(src_path))

        self.assertTrue(
            result_path.endswith(".bgh"),
            "add_existing_note_file should convert .txt to .bgh",
        )
        self.assertTrue(os.path.exists(result_path), "Converted note should exist on disk")
        data = json.loads(Path(result_path).read_text(encoding="utf-8"))
        self.assertEqual(data.get("oryginalny_format"), "txt")
        self.assertNotIn("\x00", data.get("tresc", ""), "_sanitize_text should remove null bytes")


class Test2_AddExistingNoteCopiesAllowed(OkTestCase, BaseNotesTest):
    def test_allowed_extension_without_reader_is_copied(self):
        folder = "FolderB"
        src_dir = Path(self.temp_dir.name) / "src"
        src_dir.mkdir(parents=True, exist_ok=True)
        src_path = src_dir / "note.md"
        src_path.write_text("abc", encoding="utf-8")

        result_path = notes.add_existing_note_file(folder, str(src_path))

        self.assertTrue(result_path.endswith("note.md"))
        self.assertTrue(os.path.exists(result_path), "File should be copied to notes folder")
        copied = Path(result_path).read_text(encoding="utf-8")
        self.assertEqual(copied, "abc", "Copied file content should match source")


class Test3_AddExistingNoteRejectsExtension(OkTestCase, BaseNotesTest):
    def test_rejects_disallowed_extension(self):
        folder = "FolderC"
        src_dir = Path(self.temp_dir.name) / "src"
        src_dir.mkdir(parents=True, exist_ok=True)
        src_path = src_dir / "bad.exe"
        src_path.write_text("data", encoding="utf-8")

        with self.assertRaises(ValueError, msg="Disallowed extensions should raise ValueError"):
            notes.add_existing_note_file(folder, str(src_path))


class Test4_GetNotesInFolderSorting(OkTestCase, BaseNotesTest):
    def test_sorting_and_extension_filter(self):
        folder = "Sort"
        folder_path = Path(notes.NOTES_DIR) / folder
        folder_path.mkdir(parents=True, exist_ok=True)
        (folder_path / "b.txt").write_text("b", encoding="utf-8")
        (folder_path / "a.txt").write_text("a", encoding="utf-8")
        (folder_path / "c.md").write_text("c", encoding="utf-8")

        files = notes.get_notes_in_folder(folder, extensions=["txt"])
        names = [Path(path).name for path in files]

        self.assertEqual(names, ["a.txt", "b.txt"], "get_notes_in_folder should sort names A-Z")


class Test6_FavoritesFlow(OkTestCase, BaseNotesTest):
    def test_toggle_and_list_favorites(self):
        folder = "Fav"
        folder_path = Path(notes.NOTES_DIR) / folder
        folder_path.mkdir(parents=True, exist_ok=True)
        note_path = folder_path / "fav.txt"
        note_path.write_text("fav", encoding="utf-8")

        added = notes.toggle_favorite(str(note_path))
        self.assertTrue(added, "toggle_favorite should add new favorite")
        self.assertTrue(notes.is_favorite(str(note_path)))

        favs = notes.get_favorites_in_folder(folder)
        self.assertIn(str(note_path), favs, "get_favorites_in_folder should include favorite")

        removed = notes.toggle_favorite(str(note_path))
        self.assertFalse(removed, "toggle_favorite should remove favorite")
        self.assertFalse(notes.is_favorite(str(note_path)))


class Test7_GetAllNotes(BaseNotesTest):
    def test_get_all_notes_aggregates(self):
        folder_a = Path(notes.NOTES_DIR) / "A"
        folder_b = Path(notes.NOTES_DIR) / "B"
        folder_a.mkdir(parents=True, exist_ok=True)
        folder_b.mkdir(parents=True, exist_ok=True)
        (folder_a / "one.txt").write_text("1", encoding="utf-8")
        (folder_b / "two.txt").write_text("2", encoding="utf-8")

        files = notes.get_all_notes(extensions=["txt"])
        names = sorted(Path(path).name for path in files)

        self.assertEqual(names, ["one.txt", "two.txt"], "get_all_notes should include all folders")


if __name__ == "__main__":
    _print_suite_overview()
    unittest.main(verbosity=2)
