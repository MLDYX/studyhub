"""
Fuzz tests for core.notes.
"""

import atexit
import os
import random
import tempfile
import time
import unittest

from pathlib import Path

import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import core.notes as notes


class FuzzStats:
    def __init__(self) -> None:
        self.start_time = time.time()
        self.total_cases = 0
        self.total_crashes = 0
        self.last_crash_stage = ""
        self.stage_cases = {}

    def note_case(self, stage: str) -> None:
        self.total_cases += 1
        self.stage_cases[stage] = self.stage_cases.get(stage, 0) + 1

    def note_crash(self, stage: str) -> None:
        self.total_crashes += 1
        self.last_crash_stage = stage

    def _format_elapsed(self) -> str:
        elapsed = int(time.time() - self.start_time)
        hours = elapsed // 3600
        minutes = (elapsed % 3600) // 60
        seconds = elapsed % 60
        return f"{hours}h {minutes}m {seconds}s"

    def render(self) -> str:
        elapsed = self._format_elapsed()
        sanitize_cases = self.stage_cases.get("sanitize", 0)
        add_cases = self.stage_cases.get("add", 0)
        get_cases = self.stage_cases.get("get", 0)
        lines = [
            "+----------------------------------------------------------------+",
            "| studyhub notes fuzz (test)                                      |",
            "+---------------------------+------------------------------------+",
            f"| process timing            | run time: {elapsed:<23} |",
            "+---------------------------+------------------------------------+",
            f"| overall results           | total cases : {self.total_cases:<17} |",
            f"|                           | total crashes: {self.total_crashes:<17} |",
            f"|                           | last crash  : {self.last_crash_stage or 'none':<17} |",
            "+---------------------------+------------------------------------+",
            f"| stage progress            | sanitize: {sanitize_cases:<18} |",
            f"|                           | add     : {add_cases:<18} |",
            f"|                           | get     : {get_cases:<18} |",
            "+----------------------------------------------------------------+",
        ]
        return "\n".join(lines)

    def print_summary(self) -> None:
        print(self.render())


FUZZ_STATS = FuzzStats()
atexit.register(FUZZ_STATS.print_summary)


class NotesFuzzBase(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        notes.NOTES_DIR = os.path.join(self.temp_dir.name, "notes")
        notes.FAVORITES_PATH = os.path.join(self.temp_dir.name, "favorites.json")
        os.makedirs(notes.NOTES_DIR, exist_ok=True)
        self.rng = random.Random(12345)

    def tearDown(self):
        self.temp_dir.cleanup()

    def _rand_text(self, min_len=0, max_len=256):
        length = self.rng.randint(min_len, max_len)
        chars = [chr(self.rng.randint(0, 127)) for _ in range(length)]
        return "".join(chars)


class TestNotesFuzzSanitize(NotesFuzzBase):
    def test_sanitize_text_random_inputs(self):
        control_chars = {chr(code) for code in range(0x00, 0x09)}
        control_chars.update({chr(0x0B), chr(0x0C)})
        control_chars.update({chr(code) for code in range(0x0E, 0x20)})
        control_chars.add(chr(0x7F))

        for _ in range(200):
            raw = self._rand_text(0, 1024)
            FUZZ_STATS.note_case("sanitize")
            try:
                cleaned = notes._sanitize_text(raw)
                self.assertLessEqual(
                    len(cleaned),
                    notes.MAX_CONTENT_LENGTH,
                    "_sanitize_text should not exceed MAX_CONTENT_LENGTH",
                )
                self.assertTrue(
                    all(ch not in control_chars for ch in cleaned),
                    "_sanitize_text should remove control characters",
                )
            except Exception:
                FUZZ_STATS.note_crash("sanitize")
                raise


class TestNotesFuzzAddExisting(NotesFuzzBase):
    def test_add_existing_note_file_random_txt(self):
        folder = "FuzzFolder"
        src_dir = Path(self.temp_dir.name) / "src"
        src_dir.mkdir(parents=True, exist_ok=True)

        for i in range(50):
            payload = self._rand_text(1, 2048)
            src_path = src_dir / f"note_{i}.txt"
            src_path.write_text(payload, encoding="utf-8", errors="replace")

            FUZZ_STATS.note_case("add")
            try:
                result_path = notes.add_existing_note_file(folder, str(src_path))
            except Exception:
                FUZZ_STATS.note_crash("add")
                raise

            self.assertTrue(
                os.path.exists(result_path),
                "add_existing_note_file should create output file",
            )
            self.assertTrue(
                result_path.endswith(".bgh"),
                "add_existing_note_file should convert .txt to .bgh",
            )

    def test_add_existing_note_file_invalid_folder(self):
        src_dir = Path(self.temp_dir.name) / "src"
        src_dir.mkdir(parents=True, exist_ok=True)
        src_path = src_dir / "note.txt"
        src_path.write_text("content", encoding="utf-8")

        with self.assertRaises(ValueError):
            notes.add_existing_note_file("../bad", str(src_path))


class TestNotesFuzzGetNotes(NotesFuzzBase):
    def test_get_notes_in_folder_random_names(self):
        folder = "FolderA"
        folder_path = Path(notes.NOTES_DIR) / folder
        folder_path.mkdir(parents=True, exist_ok=True)
        (folder_path / "a.txt").write_text("a", encoding="utf-8")

        for _ in range(100):
            name = self._rand_text(0, 20)
            # Filter out path separators to keep within allowed space
            name = name.replace("/", "").replace("\\", "")
            FUZZ_STATS.note_case("get")
            try:
                result = notes.get_notes_in_folder(name)
            except Exception:
                FUZZ_STATS.note_crash("get")
                raise
            self.assertIsInstance(
                result,
                list,
                "get_notes_in_folder should always return a list",
            )

        self.assertEqual(
            notes.get_notes_in_folder("../bad"),
            [],
            "get_notes_in_folder should reject path traversal",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
