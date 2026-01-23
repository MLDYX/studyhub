"""
Fuzz tests for core.calendar.
"""

import atexit
import os
import random
import tempfile
import time
import unittest

from datetime import date, datetime, timedelta
from pathlib import Path

import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.calendar import CalendarStore, WARSAW_TZ, _as_datetime


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
        add_cases = self.stage_cases.get("add", 0)
        import_cases = self.stage_cases.get("import", 0)
        as_dt_cases = self.stage_cases.get("as_datetime", 0)
        lines = [
            "+----------------------------------------------------------------+",
            "| studyhub calendar fuzz (test)                                   |",
            "+---------------------------+------------------------------------+",
            f"| process timing            | run time: {elapsed:<23} |",
            "+---------------------------+------------------------------------+",
            f"| overall results           | total cases : {self.total_cases:<17} |",
            f"|                           | total crashes: {self.total_crashes:<17} |",
            f"|                           | last crash  : {self.last_crash_stage or 'none':<17} |",
            "+---------------------------+------------------------------------+",
            f"| stage progress            | add     : {add_cases:<18} |",
            f"|                           | import  : {import_cases:<18} |",
            f"|                           | as_dt   : {as_dt_cases:<18} |",
            "+----------------------------------------------------------------+",
        ]
        return "\n".join(lines)

    def print_summary(self) -> None:
        print(self.render())


FUZZ_STATS = FuzzStats()
atexit.register(FUZZ_STATS.print_summary)


class CalendarFuzzBase(unittest.TestCase):
    def setUp(self):
        self.store = CalendarStore()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.rng = random.Random(12345)

    def tearDown(self):
        self.temp_dir.cleanup()

    def _rand_text(self, min_len=0, max_len=80):
        length = self.rng.randint(min_len, max_len)
        chars = [chr(self.rng.randint(32, 126)) for _ in range(length)]
        return "".join(chars)

    def _rand_datetime(self):
        base = datetime(2025, 1, 1, tzinfo=WARSAW_TZ)
        delta = timedelta(minutes=self.rng.randint(-10000, 10000))
        return base + delta


class TestCalendarFuzzAdd(CalendarFuzzBase):
    def test_add_event_random(self):
        for _ in range(200):
            title = self._rand_text(0, 100)
            start = self._rand_datetime()
            end = start + timedelta(minutes=self.rng.randint(0, 240))
            FUZZ_STATS.note_case("add")
            try:
                self.store.add_event(title, start, end, "Niebieski", persist=False)
            except Exception:
                FUZZ_STATS.note_crash("add")
                raise


class TestCalendarFuzzImport(CalendarFuzzBase):
    def _write_ics(self, content: str) -> str:
        path = Path(self.temp_dir.name) / "input.ics"
        path.write_text(content, encoding="utf-8", errors="replace")
        return str(path)

    def test_import_ics_random_payloads(self):
        for _ in range(80):
            summary = self._rand_text(0, 40)
            ics = (
                "BEGIN:VCALENDAR\n"
                "VERSION:2.0\n"
                "PRODID:-//StudyHub//EN\n"
                "BEGIN:VEVENT\n"
                f"UID:{self._rand_text(1, 12)}\n"
                f"DTSTAMP:20250101T120000Z\n"
                f"DTSTART:20250101T{self.rng.randint(0,23):02d}{self.rng.randint(0,59):02d}00Z\n"
                f"DTEND:20250101T{self.rng.randint(0,23):02d}{self.rng.randint(0,59):02d}00Z\n"
                f"SUMMARY:{summary}\n"
                "END:VEVENT\n"
                "END:VCALENDAR\n"
            )
            path = self._write_ics(ics)
            FUZZ_STATS.note_case("import")
            try:
                imported = self.store.import_ics(path)
                self.assertIsInstance(imported, int)
            except Exception:
                FUZZ_STATS.note_crash("import")
                raise


class TestCalendarFuzzAsDatetime(CalendarFuzzBase):
    def test_as_datetime_random(self):
        for _ in range(200):
            value = self.rng.choice(
                [
                    self._rand_datetime(),
                    self._rand_datetime().date(),
                ]
            )
            FUZZ_STATS.note_case("as_datetime")
            try:
                result = _as_datetime(value)
                self.assertIsInstance(result, datetime)
            except Exception:
                FUZZ_STATS.note_crash("as_datetime")
                raise


if __name__ == "__main__":
    unittest.main(verbosity=2)
