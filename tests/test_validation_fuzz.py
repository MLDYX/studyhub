"""
Fuzz tests for data.validation.
"""

import atexit
import os
import random
import time
import unittest

import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from data import validation


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
        username_cases = self.stage_cases.get("username", 0)
        password_cases = self.stage_cases.get("password", 0)
        emails_cases = self.stage_cases.get("emails", 0)
        header_cases = self.stage_cases.get("header", 0)
        attach_cases = self.stage_cases.get("attachment", 0)
        lines = [
            "+----------------------------------------------------------------+",
            "| studyhub validation fuzz (test)                                 |",
            "+---------------------------+------------------------------------+",
            f"| process timing            | run time: {elapsed:<23} |",
            "+---------------------------+------------------------------------+",
            f"| overall results           | total cases : {self.total_cases:<17} |",
            f"|                           | total crashes: {self.total_crashes:<17} |",
            f"|                           | last crash  : {self.last_crash_stage or 'none':<17} |",
            "+---------------------------+------------------------------------+",
            f"| stage progress            | username: {username_cases:<17} |",
            f"|                           | password: {password_cases:<17} |",
            f"|                           | emails  : {emails_cases:<17} |",
            f"|                           | header  : {header_cases:<17} |",
            f"|                           | attachment: {attach_cases:<14} |",
            "+----------------------------------------------------------------+",
        ]
        return "\n".join(lines)

    def print_summary(self) -> None:
        print(self.render())


FUZZ_STATS = FuzzStats()
atexit.register(FUZZ_STATS.print_summary)


class ValidationFuzzBase(unittest.TestCase):
    def setUp(self):
        self.rng = random.Random(12345)

    def _rand_text(self, min_len=0, max_len=256):
        length = self.rng.randint(min_len, max_len)
        chars = [chr(self.rng.randint(32, 126)) for _ in range(length)]
        return "".join(chars)


class TestValidationFuzzUsername(ValidationFuzzBase):
    def test_validate_username_random(self):
        for _ in range(300):
            raw = self._rand_text(0, 40)
            FUZZ_STATS.note_case("username")
            try:
                result = validation.validate_username(raw)
                self.assertIsInstance(result, bool, "validate_username should return bool")
            except Exception:
                FUZZ_STATS.note_crash("username")
                raise

        self.assertTrue(validation.validate_username("abc"))
        self.assertFalse(validation.validate_username("ab"))
        self.assertFalse(validation.validate_username("a" * 33))
        self.assertFalse(validation.validate_username("UPPER"))


class TestValidationFuzzPassword(ValidationFuzzBase):
    def test_validate_password_random(self):
        for _ in range(300):
            raw = self._rand_text(0, 40)
            FUZZ_STATS.note_case("password")
            try:
                result = validation.validate_password(raw, min_len=4, max_len=12)
                self.assertIsInstance(result, bool, "validate_password should return bool")
            except Exception:
                FUZZ_STATS.note_crash("password")
                raise

        self.assertTrue(validation.validate_password("1234", min_len=4, max_len=12))
        self.assertFalse(validation.validate_password("123", min_len=4, max_len=12))
        self.assertFalse(validation.validate_password("x" * 13, min_len=4, max_len=12))


class TestValidationFuzzEmails(ValidationFuzzBase):
    def test_validate_emails_random(self):
        for _ in range(200):
            raw = self._rand_text(0, 60)
            try:
                FUZZ_STATS.note_case("emails")
                result = validation.validate_emails(raw)
                self.assertIsInstance(result, list, "validate_emails should return list")
            except ValueError:
                pass
            except Exception:
                FUZZ_STATS.note_crash("emails")
                raise

        self.assertEqual(validation.validate_emails("a@b.pl"), ["a@b.pl"])
        with self.assertRaises(ValueError):
            validation.validate_emails("bad-email")


class TestValidationFuzzSanitizeHeader(ValidationFuzzBase):
    def test_sanitize_header_random(self):
        for _ in range(200):
            raw = self._rand_text(0, 300)
            FUZZ_STATS.note_case("header")
            try:
                cleaned = validation.sanitize_header(raw)
                self.assertNotIn("\n", cleaned)
                self.assertNotIn("\r", cleaned)
                self.assertLessEqual(len(cleaned), 255)
            except Exception:
                FUZZ_STATS.note_crash("header")
                raise


class TestValidationFuzzAttachmentName(ValidationFuzzBase):
    def test_validate_attachment_name_random(self):
        for _ in range(200):
            raw = self._rand_text(0, 40)
            try:
                FUZZ_STATS.note_case("attachment")
                validation.validate_attachment_name(raw)
            except ValueError:
                pass
            except Exception:
                FUZZ_STATS.note_crash("attachment")
                raise

        with self.assertRaises(ValueError):
            validation.validate_attachment_name("bad.exe")


if __name__ == "__main__":
    unittest.main(verbosity=2)
