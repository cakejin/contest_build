"""agents/memo_agent.py — Week3 Done기준의 핵심 증거: "인용 없는 문장이 실제로
차단되는 컷"을 여기서 확정한다. 실제 claude CLI를 부르지 않고 `call_claude_structured`를
memo_agent 모듈 이름공간에서 monkeypatch한다."""

from climate_risk.agents import memo_agent
from climate_risk.agents.building_agent import BuildingAgentOutput
from climate_risk.agents.flood_agent import FloodAgentOutput
from climate_risk.agents.scenario_agent import ScenarioAgentOutput
from climate_risk.llm.claude_cli import ClaudeCliOutputError
from climate_risk.memo.schema import REASON_FORBIDDEN_PHRASE, REASON_NO_CITATION, REASON_UNKNOWN_SOURCE_ID
from climate_risk.scenario.eal import EALResult


def _agents(in_scope_flood):
    flood = FloodAgentOutput(flood=in_scope_flood, source_id="flood:a.shp", field_sources={"tier": "flood:a.shp"})
    building = BuildingAgentOutput(
        vulnerability_score=55.0,
        contributing_factors=[],
        source="test",
        source_id="building:123",
        missing_fields=[],
        status="OK",
        note=None,
    )
    eal = EALResult(
        EAL_mean=1000.0,
        EAL_p50=900.0,
        EAL_p95=2000.0,
        EAL_p99=2500.0,
        n_iterations=10000,
        seed=42,
        distribution_histogram_bins=None,
        methodology_note="test",
        status="OK",
        reason=None,
    )
    scenario = ScenarioAgentOutput(eal=eal, source_id="scenario:mc:seed=42")
    return flood, building, scenario


def test_all_valid_citations_pass_without_fallback(monkeypatch, in_scope_flood):
    flood, building, scenario = _agents(in_scope_flood)

    monkeypatch.setattr(
        memo_agent,
        "call_claude_structured",
        lambda prompt, schema_path, model="sonnet": {
            "sections": [
                {"text": "이 담보는 침수위험지도상 내부 tier입니다.", "citations": ["flood:a.shp"]},
                {"text": "건물취약도 점수는 55점입니다.", "citations": ["building:123"]},
            ]
        },
    )

    output = memo_agent.run_memo_agent(flood, building, scenario)

    assert output.fallback_used is False
    assert len(output.sections) == 2
    assert output.rejected_sentences == []
    assert output.citation_failure_rate == 0.0
    assert output.disclosure  # HITL 워터마크가 항상 붙어야 함


def test_no_citation_sentence_is_rejected_and_excluded_from_sections(monkeypatch, in_scope_flood):
    """Done 기준의 실물 증거 — 인용 없는 문장이 sections에서 실제로 빠지고
    rejected_sentences에 사유와 함께 남는지 확인한다. 정상 문장을 4개 넣어 실패율을
    threshold(0.30) 밑으로 유지 — "일부만 반려"와 "전체 폴백"은 별개 시나리오다."""
    flood, building, scenario = _agents(in_scope_flood)

    monkeypatch.setattr(
        memo_agent,
        "call_claude_structured",
        lambda prompt, schema_path, model="sonnet": {
            "sections": [
                {"text": "근거 있는 문장 1입니다.", "citations": ["flood:a.shp"]},
                {"text": "근거 있는 문장 2입니다.", "citations": ["building:123"]},
                {"text": "근거 있는 문장 3입니다.", "citations": ["scenario:mc:seed=42"]},
                {"text": "근거 있는 문장 4입니다.", "citations": ["flood:a.shp"]},
                {"text": "근거 없이 지어낸 문장입니다.", "citations": []},
            ]
        },
    )

    output = memo_agent.run_memo_agent(flood, building, scenario)

    assert output.fallback_used is False
    section_texts = [s.text for s in output.sections]
    assert "근거 있는 문장 1입니다." in section_texts
    assert "근거 없이 지어낸 문장입니다." not in section_texts
    assert len(output.rejected_sentences) == 1
    assert output.rejected_sentences[0].reason == REASON_NO_CITATION


def test_unknown_source_id_citation_is_rejected(monkeypatch, in_scope_flood):
    flood, building, scenario = _agents(in_scope_flood)

    monkeypatch.setattr(
        memo_agent,
        "call_claude_structured",
        lambda prompt, schema_path, model="sonnet": {
            "sections": [
                {"text": "정상 문장 1입니다.", "citations": ["flood:a.shp"]},
                {"text": "정상 문장 2입니다.", "citations": ["building:123"]},
                {"text": "정상 문장 3입니다.", "citations": ["scenario:mc:seed=42"]},
                {"text": "정상 문장 4입니다.", "citations": ["flood:a.shp"]},
                {"text": "존재하지 않는 출처를 인용한 문장입니다.", "citations": ["flood:nonexistent.shp"]},
            ]
        },
    )

    output = memo_agent.run_memo_agent(flood, building, scenario)

    assert output.fallback_used is False
    assert len(output.rejected_sentences) == 1
    assert output.rejected_sentences[0].reason == REASON_UNKNOWN_SOURCE_ID


def test_high_citation_failure_rate_triggers_fallback(monkeypatch, in_scope_flood):
    flood, building, scenario = _agents(in_scope_flood)

    # 4문장 중 3문장이 인용 없음 → 실패율 75% > CITATION_FAILURE_FALLBACK_THRESHOLD(0.30)
    monkeypatch.setattr(
        memo_agent,
        "call_claude_structured",
        lambda prompt, schema_path, model="sonnet": {
            "sections": [
                {"text": "유효한 문장", "citations": ["flood:a.shp"]},
                {"text": "무효1", "citations": []},
                {"text": "무효2", "citations": []},
                {"text": "무효3", "citations": []},
            ]
        },
    )

    output = memo_agent.run_memo_agent(flood, building, scenario)

    assert output.fallback_used is True
    assert output.source_id == "memo:fallback_template"
    assert len(output.sections) == 3  # fallback_template은 3에이전트당 1섹션


def test_claude_cli_error_triggers_immediate_fallback(monkeypatch, in_scope_flood):
    flood, building, scenario = _agents(in_scope_flood)

    def raise_error(prompt, schema_path, model="sonnet"):
        raise ClaudeCliOutputError("boom")

    monkeypatch.setattr(memo_agent, "call_claude_structured", raise_error)

    output = memo_agent.run_memo_agent(flood, building, scenario)

    assert output.fallback_used is True
    assert output.source_id == "memo:fallback_template"


def test_valid_citation_but_forbidden_phrase_is_still_rejected(monkeypatch, in_scope_flood):
    """인용이 유효해도 금지어(블루라이닝 표현)가 있으면 반려되는지 확인 — 인용 유효성과
    보호규율 준수는 독립된 검증축이라는 것의 증거."""
    flood, building, scenario = _agents(in_scope_flood)

    monkeypatch.setattr(
        memo_agent,
        "call_claude_structured",
        lambda prompt, schema_path, model="sonnet": {
            "sections": [
                {"text": "정상 문장 1입니다.", "citations": ["flood:a.shp"]},
                {"text": "정상 문장 2입니다.", "citations": ["building:123"]},
                {"text": "정상 문장 3입니다.", "citations": ["scenario:mc:seed=42"]},
                {"text": "정상 문장 4입니다.", "citations": ["flood:a.shp"]},
                {"text": "이 담보는 금리 인상 대상입니다.", "citations": ["flood:a.shp"]},
            ]
        },
    )

    output = memo_agent.run_memo_agent(flood, building, scenario)

    assert output.fallback_used is False
    section_texts = [s.text for s in output.sections]
    assert "이 담보는 금리 인상 대상입니다." not in section_texts
    assert any(r.reason == REASON_FORBIDDEN_PHRASE for r in output.rejected_sentences)
