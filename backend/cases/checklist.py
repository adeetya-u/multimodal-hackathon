from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

from .store import IngestionStage

StepStatus = Literal["pending", "in_progress", "complete"]

_STATUS_RANK: dict[StepStatus, int] = {"pending": 0, "in_progress": 1, "complete": 2}

INFERENCE_CONFIDENCE_THRESHOLD = 0.48

logger = logging.getLogger(__name__)

_STOP_WORDS = frozenset({
    "a", "an", "the", "i", "we", "am", "is", "are", "was", "were", "be", "been",
    "with", "for", "on", "to", "of", "in", "at", "and", "or", "it", "this", "that",
    "my", "our", "now", "just", "have", "has", "had", "do", "does", "did",
})

_SPOKEN_NUMBERS: dict[str, int] = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
}


def merge_checklist_progress(current: ChecklistState, incoming: ChecklistState) -> ChecklistState:
    """Keep the furthest step status — bootstrap/API must not revert live OR progress."""
    cur_by_id = {step.id: step for step in current.steps}
    merged: list[ChecklistStep] = []
    for inc in incoming.steps:
        cur = cur_by_id.get(inc.id)
        if cur is None:
            merged.append(inc)
            continue
        if _STATUS_RANK[cur.status] > _STATUS_RANK[inc.status]:
            merged.append(
                ChecklistStep(
                    id=inc.id,
                    label=inc.label,
                    aliases=inc.aliases or cur.aliases,
                    status=cur.status,
                    completed_at=cur.completed_at,
                )
            )
        else:
            merged.append(inc)
    return ChecklistState(
        procedure=incoming.procedure,
        mode=incoming.mode,
        steps=merged,
        updated_at=max(current.updated_at, incoming.updated_at),
    )


@dataclass
class ChecklistStep:
    id: str
    label: str
    aliases: list[str] = field(default_factory=list)
    status: StepStatus = "pending"
    completed_at: float | None = None


@dataclass
class ChecklistState:
    procedure: str
    mode: str
    steps: list[ChecklistStep]
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "procedure": self.procedure,
            "mode": self.mode,
            "updated_at": self.updated_at,
            "steps": [asdict(step) for step in self.steps],
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict())

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> ChecklistState:
        steps = [
            ChecklistStep(
                id=str(s["id"]),
                label=str(s["label"]),
                aliases=list(s.get("aliases") or []),
                status=s.get("status", "pending"),
                completed_at=s.get("completed_at"),
            )
            for s in raw.get("steps", [])
            if isinstance(s, dict) and s.get("id") and s.get("label")
        ]
        return cls(
            procedure=str(raw.get("procedure", "Surgery")),
            mode=str(raw.get("mode", "logger")),
            steps=steps,
            updated_at=float(raw.get("updated_at") or time.time()),
        )

    def apply_step_update(self, step_id: str, status: StepStatus) -> ChecklistStep | None:
        index = self.step_index(step_id)
        if status == "complete":
            return self._complete_step(index)
        if status == "in_progress":
            return self._mark_in_progress(index)
        return None

    def step_index(self, step_id: str) -> int:
        for index, step in enumerate(self.steps):
            if step.id == step_id:
                return index
        raise KeyError(f"Unknown checklist step: {step_id}")

    def first_incomplete_index(self) -> int | None:
        for index, step in enumerate(self.steps):
            if step.status != "complete":
                return index
        return None

    def current_in_progress_index(self) -> int | None:
        for index, step in enumerate(self.steps):
            if step.status == "in_progress":
                return index
        return None

    def forward_min_index(self) -> int:
        """Earliest step index that may receive progress — no going backward."""
        in_progress = self.current_in_progress_index()
        if in_progress is not None:
            return in_progress
        first = self.first_incomplete_index()
        return first if first is not None else len(self.steps)

    def _complete_prior_steps(self, index: int) -> None:
        """When jumping forward, assume all earlier milestones are done."""
        if index <= 0:
            return
        now = time.time()
        for i in range(index):
            step = self.steps[i]
            if step.status != "complete":
                step.status = "complete"
                step.completed_at = now

    def _complete_step(self, index: int) -> ChecklistStep | None:
        step = self.steps[index]
        if step.status == "complete":
            self.updated_at = time.time()
            return step
        if index < self.forward_min_index():
            return None
        self._complete_prior_steps(index)
        now = time.time()
        step.status = "complete"
        step.completed_at = now
        next_index = index + 1
        while next_index < len(self.steps) and self.steps[next_index].status == "complete":
            next_index += 1
        if next_index < len(self.steps):
            self._set_single_in_progress(next_index)
        else:
            self._clear_in_progress()
        self.updated_at = time.time()
        return step

    def _mark_in_progress(self, index: int) -> ChecklistStep | None:
        step = self.steps[index]
        if step.status == "complete":
            return None
        if index < self.forward_min_index():
            return None
        self._complete_prior_steps(index)
        self._set_single_in_progress(index)
        self.updated_at = time.time()
        return step

    def _set_single_in_progress(self, index: int) -> None:
        for step_index, step in enumerate(self.steps):
            if step_index == index:
                step.status = "in_progress"
                step.completed_at = None
            elif step.status == "in_progress":
                step.status = "pending"
                step.completed_at = None

    def _clear_in_progress(self) -> None:
        for step in self.steps:
            if step.status == "in_progress":
                step.status = "pending"
                step.completed_at = None

    def resolve_step_id(self, hint: str) -> str | None:
        normalized = hint.strip().lower()
        if not normalized:
            return None
        candidates: list[tuple[int, int, str]] = []
        for index, step in enumerate(self.steps):
            label = step.label.lower()
            if normalized == step.id or normalized == label:
                candidates.append((900, index, step.id))
            elif normalized in label and len(normalized) >= 4:
                candidates.append((500 + len(normalized), index, step.id))
            for alias in step.aliases:
                alias_lower = alias.lower()
                if alias_lower in normalized or normalized in alias_lower:
                    candidates.append((100 + len(alias_lower), index, step.id))
        if not candidates:
            return None
        min_index = self.forward_min_index()
        candidates = [
            item
            for item in candidates
            if item[1] >= min_index and self.steps[item[1]].status != "complete"
        ]
        if not candidates:
            return None
        if len(candidates) > 1 and re.search(
            r"\b(?:skip(?:ping)?|jump(?:ing)?|straight to|go(?:ing)? to|move(?:d)? to)\b",
            normalized,
        ):
            candidates.sort(key=lambda item: (-item[1], -item[0]))
            return candidates[0][2]
        expected = min_index if min_index < len(self.steps) else 0
        candidates.sort(key=lambda item: (-item[0], abs(item[1] - expected), item[1]))
        return candidates[0][2]

    def resolve_step_id_from_labels(self, segment: str) -> str | None:
        """Match spoken text against this case's step labels and aliases only."""
        text = segment.lower()
        min_index = self.forward_min_index()
        best: tuple[float, int, str] | None = None
        for index, step in enumerate(self.steps):
            if index < min_index or step.status == "complete":
                continue
            phrases = [step.label, *[alias.replace("_", " ") for alias in step.aliases]]
            for phrase in phrases:
                score = _phrase_overlap_score(phrase, segment)
                if score < 0.42:
                    if len(phrase) >= 3 and phrase.lower() in text:
                        score = 0.55 + min(len(phrase) / 100, 0.15)
                    else:
                        continue
                if best is None or score > best[0] or (score == best[0] and index < best[1]):
                    best = (score, index, step.id)
        return best[2] if best else None


_SKIP_TARGET_RE = re.compile(
    r"\b(?:skip(?:ping)?|jump(?:ing)?|move(?:d)?|moving|proceed(?:ing)?|go(?:ing)?)\s+"
    r"(?:(?:to|on to|ahead to|straight to|past)\s+)?(.+?)(?:[,.]|$|\band\b)",
    re.IGNORECASE,
)

_STEP_NUM_RE = re.compile(
    r"\b(?:step|number|#)\s*(?:(\d+)|(" + "|".join(_SPOKEN_NUMBERS) + r"))\b",
    re.IGNORECASE,
)
_MARK_STEP_RE = re.compile(
    r"\b(?:mark|check|complete)\s+step\s*(?:(\d+)|(" + "|".join(_SPOKEN_NUMBERS) + r"))\b",
    re.IGNORECASE,
)

_STEP_COMPLETE_HINTS = [
    r"\b(?:done|finished|complete|completed|checked off)(?: with| the)?\b",
    r"\b(?:that's|that is|it's|it is)\s+(?:done|complete|completed|finished)\b",
    r"^(?:done|complete|completed|finished|check)\.?$",
    r"\b(?:wrapped up|wrap(?:ped)? up)\b",
    r"\b(?:check(?:ed)?|mark(?:ed)?)\s+(?:off|complete|done)?\b",
    r"\b(?:check|checked)\s*$",
    r"\bcheck(?:ed)?\s+off\b",
]

_STEP_IN_PROGRESS_HINTS = [
    r"\b(?:starting|beginning|working on|now doing|moving to|proceeding to)\b",
]

_CHECKLIST_PROGRESS_CUES = _STEP_COMPLETE_HINTS + _STEP_IN_PROGRESS_HINTS + [
    r"\b(?:mark|check)\s+(?:off|complete|done)\b",
    r"\b(?:step|milestone)\s+(?:done|complete)\b",
    r"\b(?:mark|check|complete|finish|done with|skip(?:ping)? to|move(?:d)? to)\b",
    r"\b(?:step|number|#)\s*\d+\b",
]


@dataclass
class StepInference:
    step_id: str
    step_label: str
    status: str
    confidence: float


def _matches_any(text: str, patterns: list[str]) -> bool:
    return any(re.search(p, text) for p in patterns)


def _stem(word: str) -> str:
    if len(word) > 4 and word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


def _tokenize(text: str) -> set[str]:
    tokens = {
        word
        for word in re.findall(r"[a-z0-9]+", text.lower())
        if len(word) >= 2 and word not in _STOP_WORDS
    }
    return tokens | {_stem(word) for word in tokens}


def _parse_step_number(segment: str) -> int | None:
    for pattern in (_MARK_STEP_RE, _STEP_NUM_RE):
        match = pattern.search(segment.lower())
        if not match:
            continue
        digit, spoken = match.group(1), match.group(2)
        if digit:
            return int(digit)
        if spoken:
            return _SPOKEN_NUMBERS.get(spoken.lower())
    return None


def _resolve_step_by_number(checklist: ChecklistState, segment: str) -> tuple[str, float] | None:
    step_num = _parse_step_number(segment)
    if step_num is None:
        return None
    min_index = checklist.forward_min_index()
    index = step_num - 1
    if index < 0 or index >= len(checklist.steps):
        return None
    if index < min_index or checklist.steps[index].status == "complete":
        return None
    return checklist.steps[index].id, 0.92


def _phrase_overlap_score(phrase: str, segment: str) -> float:
    phrase_l = phrase.lower().strip()
    seg_l = segment.lower()
    if len(phrase_l) >= 4 and phrase_l in seg_l:
        return min(0.92, 0.78 + len(phrase_l) / 200)
    phrase_tokens = _tokenize(phrase)
    speech_tokens = _tokenize(segment)
    if not phrase_tokens or not speech_tokens:
        return 0.0
    overlap = phrase_tokens & speech_tokens
    if not overlap:
        for token in phrase_tokens:
            if len(token) < 4:
                continue
            if any(token in word or word in token for word in speech_tokens):
                overlap.add(token)
    if not overlap:
        return 0.0
    ratio = len(overlap) / len(phrase_tokens)
    score = ratio * 0.72 + min(len(overlap), 5) * 0.05
    overlap_stems = {_stem(w) for w in overlap}
    if len(overlap_stems) >= 2:
        score = max(score, 0.55)
    return score


# Speech keywords that should prefer a specific step when multiple share generic aliases.
_STEP_KEYWORD_HINTS: dict[str, tuple[str, ...]] = {
    "femoral": ("femoral", "femur"),
    "femur": ("femoral", "femur"),
    "tibial": ("tibial", "tibia"),
    "tibia": ("tibial", "tibia"),
    "trial": ("trialing", "trial"),
    "trials": ("trialing", "trial"),
    "trialing": ("trialing", "trial"),
    "allergy": ("pre_op", "allergy", "allerg", "antibiotic", "penicillin"),
    "allergies": ("pre_op", "allergy", "allerg", "antibiotic", "penicillin"),
    "penicillin": ("pre_op", "allergy", "allerg", "antibiotic", "penicillin"),
    "verified": ("allergy", "allerg", "penicillin"),
    "timeout": ("timeout", "site verification"),
    "prep": ("positioning", "prep", "draping"),
    "draped": ("positioning", "prep", "draping"),
    "closure": ("closure", "dressing"),
    "pacu": ("pacu", "handoff"),
}


def segment_reports_checklist_progress(segment: str) -> bool:
    """True when speech clearly reports starting or completing a milestone."""
    text = segment.strip().lower()
    if not text:
        return False
    return _matches_any(text, _CHECKLIST_PROGRESS_CUES)


def segment_reports_completion(segment: str) -> bool:
    """True when speech clearly marks a step done (not merely started)."""
    text = segment.strip().lower()
    if not text:
        return False
    return _matches_any(text, _STEP_COMPLETE_HINTS)


def _step_keyword_boost(step: ChecklistStep, segment: str) -> float:
    seg_lower = segment.lower()
    if re.search(r"\bno known allergies\b|\bnkda\b|\bno allergies\b", seg_lower):
        return 0.0
    step_text = f"{step.id} {step.label} {' '.join(step.aliases)}".lower()
    boost = 0.0
    for keyword, hints in _STEP_KEYWORD_HINTS.items():
        if keyword not in seg_lower:
            continue
        if any(hint in step_text for hint in hints):
            boost = max(boost, 0.38)
    return boost


def _fuzzy_step_match(checklist: ChecklistState, segment: str) -> tuple[str, float] | None:
    speech_tokens = _tokenize(segment)
    if not speech_tokens:
        return None
    min_index = checklist.forward_min_index()
    completion_utterance = _matches_any(segment.lower(), _STEP_COMPLETE_HINTS)
    skip_forward = bool(_SKIP_TARGET_RE.search(segment)) or completion_utterance
    best: tuple[float, int, str] | None = None
    for index, step in enumerate(checklist.steps):
        keyword_boost = _step_keyword_boost(step, segment)
        if index < min_index and keyword_boost < 0.35:
            continue
        # Never jump multiple steps ahead on a weak token overlap (prevents mass auto-complete).
        if index > min_index + 1 and not skip_forward and keyword_boost < 0.35:
            continue
        if step.status == "complete" and not completion_utterance and keyword_boost < 0.35:
            continue
        phrases = [step.label, *step.aliases]
        best_phrase_score = max((_phrase_overlap_score(phrase, segment) for phrase in phrases), default=0.0)
        score = best_phrase_score + keyword_boost
        if keyword_boost >= 0.35 and best_phrase_score < 0.42:
            score = max(score, 0.48 + keyword_boost * 0.15)
        if score < 0.42:
            continue
        if best is None or score > best[0] or (score == best[0] and index < best[1]):
            best = (score, index, step.id)
    if best is None:
        return None
    return best[2], min(best[0], 0.95)


def _resolve_step_id_layered(checklist: ChecklistState, target: str) -> tuple[str | None, float]:
    by_num = _resolve_step_by_number(checklist, target)
    if by_num:
        return by_num
    fuzzy = _fuzzy_step_match(checklist, target)
    if fuzzy:
        return fuzzy
    step_id = checklist.resolve_step_id(target)
    if step_id:
        return step_id, 0.7
    step_id = checklist.resolve_step_id_from_labels(target)
    if step_id:
        return step_id, 0.65
    return None, 0.0


_ING_WORD_RE = re.compile(r"\b\w{4,}ing\b")
_ED_WORD_RE = re.compile(r"\b\w{4,}ed\b")


def _step_update_status(segment: str) -> str | None:
    text = segment.lower()
    if re.search(r"\b(?:verified|confirmed|checked off)\b", text) and re.search(r"\ballerg", text):
        return "completed"
    if _matches_any(text, _STEP_COMPLETE_HINTS):
        return "completed"
    if _matches_any(text, _STEP_IN_PROGRESS_HINTS):
        return "in_progress"
    if _parse_step_number(segment) and re.search(r"\b(?:check|complete|done|mark)\b", text):
        return "completed"
    if _ING_WORD_RE.search(text):
        return "in_progress"
    if _ED_WORD_RE.search(text):
        return "completed"
    return None


def infer_step_update_scored(checklist: ChecklistState, segment: str) -> StepInference | None:
    """Detect checklist progress with confidence for deterministic routing."""
    normalized = segment.strip()
    if not normalized:
        return None
    target = normalized
    skip_match = _SKIP_TARGET_RE.search(normalized)
    if skip_match:
        target = skip_match.group(1).strip()
    step_id, confidence = _resolve_step_id_layered(checklist, target)
    if not step_id and target != normalized:
        step_id, confidence = _resolve_step_id_layered(checklist, normalized)
    if not step_id and segment_reports_checklist_progress(normalized):
        idx = checklist.current_in_progress_index()
        if idx is None:
            idx = checklist.first_incomplete_index()
        if idx is not None:
            step = checklist.steps[idx]
            step_id = step.id
            confidence = 0.58 if _matches_any(normalized.lower(), _STEP_COMPLETE_HINTS) else 0.52
    if not step_id:
        return None
    step = next(s for s in checklist.steps if s.id == step_id)
    status = _step_update_status(normalized)
    if status is None:
        # Topic-only mention ("planning") without done/starting cues — not a checklist update.
        if not segment_reports_checklist_progress(normalized):
            return None
        status = "in_progress"
    if skip_match:
        confidence = max(confidence, 0.85)
        # Skip forward: checkmark all skipped milestones; land on the target step.
        if not _matches_any(normalized.lower(), _STEP_COMPLETE_HINTS):
            status = "in_progress"
    return StepInference(
        step_id=step_id,
        step_label=step.label,
        status=status,
        confidence=confidence,
    )


def infer_step_update_from_transcript(checklist: ChecklistState, segment: str) -> dict[str, str] | None:
    """Detect checklist progress from surgeon speech when the router omits step_update."""
    scored = infer_step_update_scored(checklist, segment)
    if not scored:
        return None
    return {"step": scored.step_label, "status": scored.status}


def empty_checklist(procedure: str = "Surgery") -> ChecklistState:
    """No static template — milestones come from case prep (Bedrock) only."""
    return ChecklistState(procedure=procedure, mode="logger", steps=[])


def load_checklist(path: Path) -> ChecklistState:
    """Load checklist JSON from an explicit path (tests/fixtures only)."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    return ChecklistState.from_dict(raw)


def load_case_checklist(case_id: str | None) -> ChecklistState:
    if case_id:
        from .store import case_data_root

        case_dir = case_data_root() / case_id
        path = case_dir / "checklist.json"
        if path.exists():
            raw = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                return ChecklistState.from_dict(raw)
        procedure = "Surgery"
        meta_path = case_dir / "metadata.json"
        if meta_path.exists():
            try:
                procedure = str(json.loads(meta_path.read_text(encoding="utf-8")).get("procedure") or procedure)
            except json.JSONDecodeError:
                pass
        return empty_checklist(procedure)
    return empty_checklist()


def ensure_case_checklist(store, case_id: str) -> tuple[ChecklistState, bool]:
    """Return checklist for a case. Do not seed generic defaults — wait for prep LLM."""
    checklist = load_case_checklist(case_id)
    if checklist.steps:
        return checklist, False
    meta = store.get_metadata(case_id)
    if meta.stage not in {IngestionStage.READY, IngestionStage.INDEXING}:
        return empty_checklist(meta.procedure or "Surgery"), False
    from .checklist_gen import default_checklist

    seeded = default_checklist(meta.procedure, reason="default_tka_fallback")
    store.write_json(case_id, "checklist.json", seeded)
    logger.warning(
        "seeded default TKA checklist (%d steps) for case_id=%s — prep LLM did not produce steps",
        len(seeded["steps"]),
        case_id,
    )
    return ChecklistState.from_dict(seeded), True
