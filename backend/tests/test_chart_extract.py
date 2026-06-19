"""Chart fact extraction for OR voice answers."""

from __future__ import annotations

import unittest
from pathlib import Path

from cases.bootstrap import SurgeryContext
from cases.chart_extract import extract_medications_spoken, try_chart_fact_answer

DEMO_CHART = (Path(__file__).resolve().parents[1] / "assets" / "demo" / "mock-patient-TKA-Donnelly.md").read_text(
    encoding="utf-8"
)


class ChartExtractTests(unittest.TestCase):
    def test_extract_medications_from_demo_chart(self) -> None:
        ctx = SurgeryContext(
            patient_id="001",
            procedure="TKA",
            summary=DEMO_CHART,
            raw={"context_window": {"prompt_block": DEMO_CHART}},
        )
        spoken = extract_medications_spoken(ctx)
        self.assertIsNotNone(spoken)
        self.assertIn("metformin", spoken.lower())
        self.assertNotIn("MISSING", spoken.upper())

    def test_try_chart_fact_answer_medications_query(self) -> None:
        ctx = SurgeryContext(
            patient_id="001",
            procedure="TKA",
            summary=DEMO_CHART,
            raw={"context_window": {"prompt_block": DEMO_CHART}},
        )
        spoken = try_chart_fact_answer("What are the patient's current medications?", ctx)
        self.assertTrue(spoken)
        self.assertIn("aspirin", spoken.lower())

    def test_try_chart_fact_answer_unrelated_query(self) -> None:
        ctx = SurgeryContext(
            patient_id="001",
            procedure="TKA",
            summary=DEMO_CHART,
            raw={},
        )
        self.assertIsNone(try_chart_fact_answer("What is the INR?", ctx))


if __name__ == "__main__":
    unittest.main()
