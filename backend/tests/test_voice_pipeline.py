"""Vapi voice pipeline config stays within API limits."""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cases.voice.provider import voice_pipeline_config  # noqa: E402


class VoicePipelineConfigTests(unittest.TestCase):
    def test_on_no_punctuation_seconds_capped_at_three(self) -> None:
        with patch.dict(os.environ, {"VAPI_ENDPOINT_NO_PUNCT_SEC": "4.0"}, clear=False):
            plan = voice_pipeline_config()["startSpeakingPlan"]["transcriptionEndpointingPlan"]
            self.assertLessEqual(plan["onNoPunctuationSeconds"], 3.0)

    def test_default_on_no_punctuation_seconds_within_limit(self) -> None:
        env = os.environ.copy()
        env.pop("VAPI_ENDPOINT_NO_PUNCT_SEC", None)
        with patch.dict(os.environ, env, clear=True):
            plan = voice_pipeline_config()["startSpeakingPlan"]["transcriptionEndpointingPlan"]
            self.assertLessEqual(plan["onNoPunctuationSeconds"], 3.0)
            self.assertGreaterEqual(plan["onNoPunctuationSeconds"], 0.1)


if __name__ == "__main__":
    unittest.main()
