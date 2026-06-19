"""Tests for spoken output sanitization."""

from __future__ import annotations

import unittest

from cases.workers import clamp_spoken_text, sanitize_spoken_output


class SpokenSanitizeTests(unittest.TestCase):
    def test_strips_thinking_tags(self) -> None:
        raw = (
            '<think>The user says: "Knee orthopedics assistant. '
            'One or two short spoken sentences. Never refuse.</think>'
            "Typical TKA rehab is about twelve weeks for return to daily activities."
        )
        cleaned = sanitize_spoken_output(raw)
        self.assertIn("Typical TKA rehab", cleaned)
        self.assertNotIn("Knee orthopedics assistant", cleaned)
        self.assertNotIn("redacted_thinking", cleaned)

    def test_strips_unclosed_thinking(self) -> None:
        raw = '<think>The user says: "Knee orthopedics assistant. One or two short spoken sentences.'
        self.assertEqual(sanitize_spoken_output(raw), "")

    def test_strips_prompt_echo(self) -> None:
        raw = "Knee orthopedics assistant. One or two short spoken sentences. Never refuse."
        self.assertEqual(sanitize_spoken_output(raw), "")

    def test_clamp_applies_sanitize(self) -> None:
        raw = "GROUNDED: [c1] Early mobilization reduces DVT risk after knee surgery."
        spoken = clamp_spoken_text(raw)
        self.assertIn("Early mobilization", spoken)
        self.assertNotIn("GROUNDED:", spoken)


if __name__ == "__main__":
    unittest.main()
