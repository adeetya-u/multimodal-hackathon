"""Storage backend selection — Insforge or filesystem."""

from __future__ import annotations

import os

from ..store import CaseStore, EventedCaseStore


def storage_backend() -> str:
    return os.environ.get("STORAGE_BACKEND", "filesystem").strip().lower()


def get_case_store(*, on_change=None) -> CaseStore | EventedCaseStore:
    if storage_backend() == "insforge":
        from .insforge_repo import InsforgeCaseStore

        if on_change:
            return InsforgeEventedCaseStore(on_change=on_change)
        return InsforgeCaseStore()
    if on_change:
        return EventedCaseStore(on_change=on_change)
    return CaseStore()


class InsforgeEventedCaseStore:
    """Wraps InsforgeCaseStore with change notifications."""

    def __init__(self, *, on_change=None) -> None:
        from .insforge_repo import InsforgeCaseStore

        self._inner = InsforgeCaseStore()
        self._on_change = on_change

    def __getattr__(self, name: str):
        return getattr(self._inner, name)

    def update_stage(self, case_id, stage, error=None):
        meta = self._inner.update_stage(case_id, stage, error)
        if self._on_change:
            self._on_change(case_id)
        return meta

    def update_case_details(self, case_id, **kwargs):
        meta = self._inner.update_case_details(case_id, **kwargs)
        if self._on_change:
            self._on_change(case_id)
        return meta
