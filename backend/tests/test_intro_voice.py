"""Intro demo voice — reference corpus only, no patient chart."""

from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, patch

from cases.intro_voice import (
    answer_intro_question,
    clamp_intro_spoken,
    format_intro_candidates,
    intro_snippet_fallback,
)
from cases.search import load_demo_reference_knowledge
from cases.types import Snippet
from cases.voice.provider import intro_assistant_overrides, assistant_overrides


class IntroVoiceTests(unittest.TestCase):
    def test_load_demo_reference_knowledge_has_snippets(self) -> None:
        knowledge = load_demo_reference_knowledge()

        async def run() -> None:
            hits = await knowledge.search("DVT knee surgery", k=3)
            self.assertGreater(len(hits), 0)

        import asyncio

        asyncio.run(run())

    def test_intro_assistant_overrides_differs_from_or(self) -> None:
        intro = intro_assistant_overrides()
        or_cfg = assistant_overrides("test-case")
        self.assertEqual(intro["metadata"], {"mode": "intro"})
        self.assertNotEqual(intro["firstMessage"], or_cfg["firstMessage"])
        content = intro["model"]["messages"][0]["content"]
        self.assertIn("stay silent", content.lower())
        self.assertNotIn("respond ONLY with Checking.", content)

    def test_format_intro_candidates(self) -> None:
        snip = Snippet(
            chunk_id="c1",
            source="ref",
            doc_type="evidence",
            text="DVT prophylaxis after TKA includes early mobilization.",
        )
        formatted = format_intro_candidates([snip])
        self.assertIn("c1", formatted)
        self.assertIn("DVT", formatted)

    def test_answer_intro_question_uses_corpus(self) -> None:
        async def run() -> None:
            spoken = await answer_intro_question("How do you prevent DVT after knee surgery?")
            self.assertTrue(spoken.strip())
            self.assertNotIn("Checking.", spoken)

        import asyncio

        asyncio.run(run())

    def test_clamp_intro_spoken_limits_length(self) -> None:
        long = " ".join(["Word"] * 80) + "."
        spoken = clamp_intro_spoken(long)
        self.assertLessEqual(len(spoken), 181)

    def test_answer_intro_question_rejects_prompt_leak(self) -> None:
        async def run() -> None:
            leak = (
                '<think>The user says: "Knee orthopedics assistant. '
                'One or two short spoken sentences. Never refuse.'
            )
            with patch("cases.intro_voice.converse_intro", return_value=leak):
                spoken = await answer_intro_question("What is typical rehab after TKA?")
            self.assertNotIn("Knee orthopedics assistant", spoken)
            self.assertNotIn("redacted_thinking", spoken)
            self.assertTrue(spoken.strip())

        import asyncio

        asyncio.run(run())

    def test_answer_intro_question_fallback_without_llm(self) -> None:
        async def run() -> None:
            with patch("cases.intro_voice.converse_intro", return_value=None):
                spoken = await answer_intro_question("What is TKA?")
            self.assertTrue(spoken.strip())
            self.assertNotIn("Continue to prep", spoken)

        import asyncio

        asyncio.run(run())

    def test_intro_snippet_fallback_recovery_question(self) -> None:
        knowledge = load_demo_reference_knowledge()

        async def run() -> None:
            hits = await knowledge.search("recovery after knee surgery", k=4)
            spoken = intro_snippet_fallback("how long to recover after surgery?", hits)
            self.assertTrue(spoken.strip())
            self.assertNotIn("Continue to prep", spoken)

        import asyncio

        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
