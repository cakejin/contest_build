"""블루라이닝 방어 금지어 필터 — HANDOVER.md §⑥ item7 "코드 상수 템플릿으로 고정, 금지어
("LTV 하향"·"금리 인상"·"회수" 등) 필터링"의 실체 구현.

LLM 프롬프트로 "이런 표현 쓰지 마라"고 지시하는 것만으로는 프롬프트 인젝션·모델 오류에
취약하다(HANDOVER §⑥ 레드팀 시나리오3·9) — 이 모듈은 메모 에이전트 출력·사람이 입력한
감사로그 메모 등, 외부로 노출될 수 있는 모든 텍스트에 대해 프롬프트와 무관하게 별도로
돌리는 규칙기반 이중 검증이다.
"""

from __future__ import annotations

from dataclasses import dataclass

# HANDOVER §⑥ item7 명시 금지어 + 근접 변형. "인상"만 단독으로 넣지 않는다 — "물가 인상" 같은
# 무관한 문맥까지 오탐하므로 "금리 인상"처럼 구체 문구 단위로 유지한다(정밀도 우선).
FORBIDDEN_PHRASES: list[str] = [
    "LTV 하향",
    "LTV하향",
    "담보인정비율 하향",
    "금리 인상",
    "금리인상",
    "이자율 인상",
    "여신 회수",
    "대출 회수",
    "회수 조치",
    "만기 연장 거절",
    "재계약 거절",
    "대출을 줄여",
    "여신 축소",
    "대출 축소",
]


@dataclass(frozen=True)
class ForbiddenPhraseMatch:
    phrase: str
    start: int
    end: int
    matched_text: str


def scan_forbidden_phrases(text: str) -> list[ForbiddenPhraseMatch]:
    """text 안에서 FORBIDDEN_PHRASES에 등록된 문구를 전부 찾아 반환한다(단순 부분문자열
    탐지 — 오탐보다 누락이 더 위험한 성격이라 형태소분석 없이 넓게 잡는다)."""
    matches: list[ForbiddenPhraseMatch] = []
    for phrase in FORBIDDEN_PHRASES:
        start = 0
        while True:
            idx = text.find(phrase, start)
            if idx == -1:
                break
            matches.append(
                ForbiddenPhraseMatch(
                    phrase=phrase, start=idx, end=idx + len(phrase), matched_text=phrase
                )
            )
            start = idx + len(phrase)
    return matches


def contains_forbidden_phrase(text: str) -> bool:
    return bool(scan_forbidden_phrases(text))
