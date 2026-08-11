"""인용검증 게이트 — HANDOVER.md §4.2 2.6 "각 문장의 citations가 실제 소스 레지스트리에
존재하는지 런타임 대조 → 미존재/빈 배열 문장은 렌더링 차단".

이 모듈은 LLM이 "인용을 지켰다"는 주장을 신뢰하지 않는다 — memo/prompt.py의 지시와는
완전히 독립적으로, 순수 규칙기반 문자열 대조만 한다(설계원칙4 "모델 출력만으로 판단하지
말고 별도 검증 레이어로 이중화"). 프롬프트 인젝션으로 LLM이 존재하지 않는 source_id를
그럴듯하게 지어내도 여기서 걸린다.
"""

from __future__ import annotations

from dataclasses import dataclass

from climate_risk.memo.schema import REASON_NO_CITATION, REASON_UNKNOWN_SOURCE_ID, MemoSection, RejectedSentence


@dataclass(frozen=True)
class CitationGateResult:
    accepted: list[MemoSection]
    rejected: list[RejectedSentence]
    citation_failure_rate: float


def verify_citations(
    sections: list[MemoSection], known_source_ids: set[str]
) -> CitationGateResult:
    if not sections:
        return CitationGateResult(accepted=[], rejected=[], citation_failure_rate=0.0)

    accepted: list[MemoSection] = []
    rejected: list[RejectedSentence] = []

    for section in sections:
        if not section.citations:
            rejected.append(RejectedSentence(text=section.text, reason=REASON_NO_CITATION))
            continue

        unknown = [c for c in section.citations if c not in known_source_ids]
        if unknown:
            rejected.append(RejectedSentence(text=section.text, reason=REASON_UNKNOWN_SOURCE_ID))
            continue

        accepted.append(section)

    failure_rate = len(rejected) / len(sections)
    return CitationGateResult(accepted=accepted, rejected=rejected, citation_failure_rate=failure_rate)
