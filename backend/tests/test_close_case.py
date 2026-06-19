"""Close-case voice phrase detection."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cases.mode_controller import wants_close_case  # noqa: E402


class CloseCasePhraseTests(unittest.TestCase):
    def test_end_surgery(self) -> None:
        self.assertTrue(wants_close_case("end surgery"))

    def test_surgery_is_complete(self) -> None:
        self.assertTrue(wants_close_case("surgery is complete"))

    def test_close_the_case(self) -> None:
        self.assertTrue(wants_close_case("close the case"))

    def test_regular_question_is_not_close(self) -> None:
        self.assertFalse(wants_close_case("what are the patient's allergies"))


if __name__ == "__main__":
    unittest.main()
