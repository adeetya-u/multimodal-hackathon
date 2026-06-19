from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Snippet:
    source: str
    text: str
    score: float = 0.0
    pages: str = ""
    title: str = ""
    chunk_id: str = ""
    doc_type: str = ""
    guideline_ref: str = ""
    date: str = ""

    def to_dict(self) -> dict[str, str]:
        return {
            "source": self.source,
            "text": self.text,
            "pages": self.pages,
            "title": self.title,
            "chunk_id": self.chunk_id,
            "doc_type": self.doc_type,
            "guideline_ref": self.guideline_ref,
            "date": self.date,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Snippet:
        return cls(
            source=str(data.get("source", "")),
            text=str(data.get("text", "")),
            score=float(data.get("score", 0)),
            pages=str(data.get("pages", "")),
            title=str(data.get("title", "")),
            chunk_id=str(data.get("chunk_id", "")),
            doc_type=str(data.get("doc_type", "")),
            guideline_ref=str(data.get("guideline_ref", "")),
            date=str(data.get("date", "")),
        )


@dataclass
class CompactPack:
    id: str
    title: str
    summary: str
    text: str
    chunk_type: str
    source: str
    procedure_step: str | None = None
    metadata: dict = field(default_factory=dict)
