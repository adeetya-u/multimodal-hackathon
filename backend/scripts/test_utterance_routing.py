#!/usr/bin/env python3
"""Smoke tests for question vs log vs checklist routing."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cases.checklist import ChecklistState, infer_step_update_scored  # noqa: E402
from cases.utterance_intent import (  # noqa: E402
    SegmentIntentKind,
    classify_intent_for_utterance,
    classify_segment_intent,
)
from cases.workers import (  # noqa: E402
    LoggerOutput,
    OperationMode,
    SessionState,
    run_logger,
)

FIXTURE = ROOT / "tests" / "fixtures" / "case-001-checklist.json"


def load_fixture() -> ChecklistState:
    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return ChecklistState.from_dict(raw)


INTENT_CASES: list[tuple[str, SegmentIntentKind, str | None]] = [
    ("is there any allergies I should know about", SegmentIntentKind.QUESTION, None),
    ("what antibiotic should we give", SegmentIntentKind.QUESTION, None),
    ("what is the DVT prophylaxis", SegmentIntentKind.QUESTION, None),
    ("allergy check is done", SegmentIntentKind.CHECKLIST, "Pre-op safety and medication review"),
    ("we did the timeout", SegmentIntentKind.CHECKLIST, "Surgical timeout and site verification"),
    ("time out complete", SegmentIntentKind.CHECKLIST, "Surgical timeout and site verification"),
    ("starting the femoral resection", SegmentIntentKind.CHECKLIST, "Femoral preparation and resection"),
    ("trials look good", SegmentIntentKind.CHECKLIST, "Implant trialing and balancing"),
    ("patient has no known allergies", SegmentIntentKind.LOG, None),
    ("patient is prepped and draped", SegmentIntentKind.CHECKLIST, "Patient positioning and surgical prep"),
]


async def test_intent_classification() -> None:
    checklist = load_fixture()
    failures: list[str] = []
    for utterance, expected_kind, expected_step in INTENT_CASES:
        intent = classify_segment_intent(utterance, checklist)
        if intent.kind != expected_kind:
            failures.append(f"intent {utterance!r}: expected {expected_kind}, got {intent.kind}")
            continue
        if expected_step:
            scored = infer_step_update_scored(checklist, utterance)
            if not scored or scored.step_label != expected_step:
                got = scored.step_label if scored else None
                failures.append(f"checklist {utterance!r}: expected {expected_step!r}, got {got!r}")
    if failures:
        raise AssertionError("\n".join(failures))


async def test_run_logger_heuristic() -> None:
    """run_logger with LLM disabled should route questions to retrieval."""
    checklist = load_fixture()
    state = SessionState(session_id="test", patient_id="p1")

    with patch("cases.workers.converse_text", return_value=None):
        with patch.dict("os.environ", {"VOICE_INTENT_LLM": "0"}):
            q = await run_logger(state=state, checklist=checklist, segment="is there any allergies")
            assert q.needs_retrieval and q.mode == "query", q

            log = await run_logger(
                state=state,
                checklist=checklist,
                segment="allergy check is done",
            )
            assert not log.needs_retrieval, log
            assert log.step_update and log.step_update.get("status") in {"completed", "complete"}, log


async def test_run_logger_reconcile_overrides_wrong_llm() -> None:
    """Heuristic intent (LLM off) should still route explicit questions to retrieval."""
    checklist = load_fixture()
    state = SessionState(session_id="test", patient_id="p1")

    with patch.dict("os.environ", {"VOICE_INTENT_LLM": "0"}):
        out = await run_logger(
            state=state,
            checklist=checklist,
            segment="what antibiotic should we use",
        )
        assert out.mode == "query" and out.needs_retrieval, out


async def test_every_utterance_uses_intent_llm() -> None:
    """Every finalized utterance goes through intent LLM when VOICE_INTENT_LLM=1."""
    checklist = load_fixture()
    state = SessionState(session_id="test", patient_id="p1")
    calls: list[str] = []

    def fake_classify(segment, cl, *, current_mode="logging", dialogue_context=""):
        calls.append(segment)
        from cases.utterance_intent import SegmentIntent, SegmentIntentKind

        return SegmentIntent(
            kind=SegmentIntentKind.LOG,
            confidence=0.8,
            is_log=True,
        )

    with patch("cases.workers.classify_intent_for_utterance", side_effect=fake_classify):
        with patch.dict("os.environ", {"VOICE_INTENT_LLM": "1"}):
            await run_logger(state=state, checklist=checklist, segment="hello there")
            await run_logger(state=state, checklist=checklist, segment="Patient's allergies.")
    assert calls == ["hello there", "Patient's allergies."]


async def test_allergy_phrases_via_llm_mock() -> None:
    checklist = load_fixture()
    state = SessionState(session_id="test", patient_id="p1")

    def fake_llm(segment, cl, *, current_mode="logging", dialogue_context=""):
        from cases.utterance_intent import SegmentIntent, SegmentIntentKind, infer_step_update_scored

        if "verified" in segment.lower():
            scored = infer_step_update_scored(cl, segment)
            return SegmentIntent(
                kind=SegmentIntentKind.CHECKLIST,
                confidence=0.9,
                is_checklist=True,
                is_log=True,
                checklist=scored,
            )
        return SegmentIntent(
            kind=SegmentIntentKind.QUESTION,
            confidence=0.9,
            is_question=True,
            extracted_query=segment,
        )

    with patch("cases.workers.classify_intent_for_utterance", side_effect=fake_llm):
        q = await run_logger(state=state, checklist=checklist, segment="Patient's allergies.")
        assert q.needs_retrieval and q.mode == "query", q
        log = await run_logger(
            state=SessionState(session_id="test2", patient_id="p1"),
            checklist=load_fixture(),
            segment="I have verified the patients allergies",
        )
        assert not log.needs_retrieval, log
        assert log.step_update and log.step_update.get("status") in {"completed", "complete"}, log


async def main() -> None:
    if not FIXTURE.exists():
        raise SystemExit(f"Missing fixture: {FIXTURE}")
    await test_intent_classification()
    print(f"PASS intent + checklist ({len(INTENT_CASES)} cases)")
    await test_run_logger_heuristic()
    print("PASS run_logger heuristic routing")
    await test_run_logger_reconcile_overrides_wrong_llm()
    print("PASS run_logger intent overrides bad LLM")
    await test_every_utterance_uses_intent_llm()
    print("PASS every utterance uses intent LLM when enabled")
    await test_allergy_phrases_via_llm_mock()
    print("PASS LLM resolves allergy question vs checklist log")
    print("\nAll utterance routing tests passed.")


if __name__ == "__main__":
    asyncio.run(main())
