"""Epoch timestamp helpers — tolerate ms vs seconds from browser and server."""

from __future__ import annotations

from datetime import UTC, datetime


def normalize_epoch_ts(ts: float | int | None) -> float | None:
    """Return Unix seconds; frontend Date.now() ms is converted automatically."""
    if ts is None:
        return None
    value = float(ts)
    if value <= 0:
        return None
    # Current epoch seconds are ~1.7e9; ms values are ~1.7e12.
    if value >= 1e11:
        value /= 1000.0
    return value


def format_epoch_ts(ts: float | int | None) -> str:
    normalized = normalize_epoch_ts(ts)
    if normalized is None:
        return ""
    try:
        return datetime.fromtimestamp(normalized, tz=UTC).strftime("%H:%M:%S")
    except (ValueError, OSError, OverflowError):
        return ""


def normalize_transcript_turns(transcript: list[dict]) -> list[dict]:
    """Normalize turn timestamps in place for summary generation."""
    normalized: list[dict] = []
    for turn in transcript:
        if not isinstance(turn, dict):
            continue
        item = dict(turn)
        ts = normalize_epoch_ts(item.get("ts"))
        if ts is not None:
            item["ts"] = ts
        normalized.append(item)
    return normalized
