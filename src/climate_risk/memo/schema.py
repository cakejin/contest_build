"""심사메모 데이터 형태 — HANDOVER.md §4.2 2.5 출력 스키마
`{sections: [{text, citations}], rejected_sentences: [{text, reason}]}`."""

from __future__ import annotations

from dataclasses import dataclass, field

REASON_NO_CITATION = "NO_CITATION"
REASON_UNKNOWN_SOURCE_ID = "UNKNOWN_SOURCE_ID"
REASON_FORBIDDEN_PHRASE = "FORBIDDEN_PHRASE"


@dataclass(frozen=True)
class MemoSection:
    text: str
    citations: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class RejectedSentence:
    text: str
    reason: str  # REASON_* 상수 중 하나


@dataclass(frozen=True)
class MemoAgentOutput:
    sections: list[MemoSection]
    rejected_sentences: list[RejectedSentence]
    citation_failure_rate: float
    fallback_used: bool
    source_id: str
    disclosure: str
