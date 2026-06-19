from __future__ import annotations

import re
import time
from enum import Enum


class AgentMode(str, Enum):
    LOGGER = "logger"
    SITUATION = "situation"
    SUMMARY = "summary"


COMPLICATION_PATTERNS = [
    r"\bbleeding\b",
    r"\bcomplication\b",
    r"\bwhat (?:do|should) i do\b",
    r"\bhelp me\b",
    r"\bproblem\b",
    r"\bunexpected\b",
]

RESOLVED_PATTERNS = [
    r"\bresolved\b",
    r"\bcomplication resolved\b",
    r"\bback to log(?:ging)?\b",
    r"\ball clear\b",
]

CLOSE_CASE_PATTERNS = [
    r"\bclose (?:the )?case\b",
    r"\bend (?:the )?(?:surgery|case|procedure|operation)\b",
    r"\bfinish (?:the )?(?:surgery|case|procedure|operation)\b",
    r"\bwrap(?:ping)? (?:up|it up)\b",
    r"\bcase complete\b",
    # "surgery is complete/done" (+ common STT mishearings of "surgery")
    r"\b(?:surgery|suregry|sergery)'?s?(?: is)? (?:done|complete|over|finished)\b",
    r"\b(?:the )?(?:surgery|procedure|operation|case) (?:is )?(?:done|complete|over|finished)\b",
    # -ing forms: "closing is done", "operating is complete", "finishing is done"
    r"\b(?:closing|operating|finishing|wrapping)(?: (?:the )?(?:case|surgery|procedure|operation))?(?: is)? (?:done|complete|finished)\b",
    r"\b(?:we'?re?|i'?m?) done(?: with)?(?: the)? (?:surgery|case|procedure|operation)\b",
]


def wants_close_case(text: str) -> bool:
    normalized = text.lower().strip()
    if not normalized:
        return False
    return _matches_any(normalized, CLOSE_CASE_PATTERNS)


class ModeController:
    def __init__(self) -> None:
        self.mode = AgentMode.LOGGER
        self.updated_at = time.time()

    def evaluate_transcript(self, text: str) -> AgentMode | None:
        normalized = text.lower().strip()
        if not normalized:
            return None
        if wants_close_case(normalized):
            self._set(AgentMode.SUMMARY)
            return AgentMode.SUMMARY
        if self.mode == AgentMode.SITUATION and _matches_any(normalized, RESOLVED_PATTERNS):
            self._set(AgentMode.LOGGER)
            return AgentMode.LOGGER
        if self.mode == AgentMode.LOGGER and _matches_any(normalized, COMPLICATION_PATTERNS):
            self._set(AgentMode.SITUATION)
            return AgentMode.SITUATION
        return None

    def _set(self, mode: AgentMode) -> None:
        self.mode = mode
        self.updated_at = time.time()


def _matches_any(text: str, patterns: list[str]) -> bool:
    return any(re.search(p, text) for p in patterns)
