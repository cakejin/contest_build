"""메모 에이전트 — HANDOVER.md §4.2 2.5. "절대 축소 금지" 인용검증 게이트의 오케스트레이션.

호출 순서: 소스 레지스트리 구축 → 프롬프트 → `call_claude_structured`(실패 시 즉시
폴백) → `verify_citations`(인용 없음/미등록 source_id 반려) → **금지어 2차 검사**
(citations가 유효해도 블루라이닝 금지어가 있으면 반려, HANDOVER §⑥ item7) → 반려율이
`CITATION_FAILURE_FALLBACK_THRESHOLD` 초과 시 전체 폐기하고 규칙기반 폴백으로 대체.

`call_claude_structured`는 이 모듈 이름공간으로 임포트해둔다 — 테스트가
`monkeypatch.setattr(memo_agent, "call_claude_structured", ...)`로 실제 CLI 호출 없이
검증할 수 있는 단일 seam이다.
"""

from __future__ import annotations

from climate_risk.agents.advisory_agent import AdvisoryAgentOutput
from climate_risk.agents.building_agent import BuildingAgentOutput
from climate_risk.agents.flood_agent import FloodAgentOutput
from climate_risk.agents.scenario_agent import ScenarioAgentOutput
from climate_risk.config import CITATION_FAILURE_FALLBACK_THRESHOLD, MEMO_SCHEMA_PATH
from climate_risk.llm.claude_cli import ClaudeCliError, call_claude_structured
from climate_risk.memo.citation_gate import verify_citations
from climate_risk.memo.fallback_template import build_fallback_memo
from climate_risk.memo.prompt import build_memo_prompt
from climate_risk.memo.schema import REASON_FORBIDDEN_PHRASE, MemoAgentOutput, MemoSection, RejectedSentence
from climate_risk.memo.source_registry import build_source_registry
from climate_risk.policy.disclosures import HITL_WATERMARK_TEXT
from climate_risk.policy.forbidden_phrases import contains_forbidden_phrase

_FALLBACK_SOURCE_ID = "memo:fallback_template"


def _llm_source_id(model: str) -> str:
    return f"memo:llm:{model}"


def _apply_forbidden_phrase_check(
    sections: list[MemoSection],
) -> tuple[list[MemoSection], list[RejectedSentence]]:
    """인용이 전부 유효해도 금지어가 섞인 문장은 별도로 반려한다 — 인용 유효성과
    보호규율 준수는 독립된 검증축이다(하나가 통과했다고 다른 하나도 통과한 게 아님)."""
    clean: list[MemoSection] = []
    newly_rejected: list[RejectedSentence] = []
    for section in sections:
        if contains_forbidden_phrase(section.text):
            newly_rejected.append(RejectedSentence(text=section.text, reason=REASON_FORBIDDEN_PHRASE))
        else:
            clean.append(section)
    return clean, newly_rejected


def _fallback_output(
    flood: FloodAgentOutput, building: BuildingAgentOutput, scenario: ScenarioAgentOutput
) -> MemoAgentOutput:
    fallback_sections = build_fallback_memo(flood, building, scenario)
    return MemoAgentOutput(
        sections=fallback_sections,
        rejected_sentences=[],
        citation_failure_rate=0.0,
        fallback_used=True,
        source_id=_FALLBACK_SOURCE_ID,
        disclosure=HITL_WATERMARK_TEXT,
    )


def run_memo_agent(
    flood: FloodAgentOutput,
    building: BuildingAgentOutput,
    scenario: ScenarioAgentOutput,
    advisory: AdvisoryAgentOutput | None = None,
    model: str = "sonnet",
) -> MemoAgentOutput:
    registry = build_source_registry(flood, building, scenario, advisory)
    known_source_ids = set(registry.keys())

    prompt = build_memo_prompt(registry)
    try:
        raw = call_claude_structured(prompt, MEMO_SCHEMA_PATH, model=model)
    except ClaudeCliError:
        return _fallback_output(flood, building, scenario)

    raw_sections = [
        MemoSection(text=s["text"], citations=list(s.get("citations", []))) for s in raw.get("sections", [])
    ]

    gate_result = verify_citations(raw_sections, known_source_ids)
    accepted, forbidden_rejected = _apply_forbidden_phrase_check(gate_result.accepted)
    all_rejected = gate_result.rejected + forbidden_rejected

    total = len(raw_sections)
    if total == 0:
        # 빈 sections는 문장이 하나도 없으므로 반려율로 판단할 수 없다 —
        # "0/0 = 0.0"으로 계산하면 인용 실패율이 0%로 위장돼 폴백을 우회하므로
        # 무조건 폴백으로 취급한다(HANDOVER §4.2 "절대 축소 금지" 게이트).
        return _fallback_output(flood, building, scenario)

    failure_rate = len(all_rejected) / total

    if failure_rate > CITATION_FAILURE_FALLBACK_THRESHOLD:
        return _fallback_output(flood, building, scenario)

    return MemoAgentOutput(
        sections=accepted,
        rejected_sentences=all_rejected,
        citation_failure_rate=failure_rate,
        fallback_used=False,
        source_id=_llm_source_id(model),
        disclosure=HITL_WATERMARK_TEXT,
    )
