"""평가 대시보드 최소셋 회귀 테스트 — evaluation/metrics.py."""

from climate_risk.agents.building_agent import BuildingAgentOutput
from climate_risk.agents.flood_agent import FloodAgentOutput
from climate_risk.evaluation.metrics import (
    citation_metric,
    coverage_gate_metric,
    coverage_uncertain_point_metric,
    eal_reproducibility_metric,
    forbidden_phrase_absence_metric,
)
from climate_risk.memo.schema import MemoAgentOutput, MemoSection, RejectedSentence


def test_citation_metric_reads_memo_fields_without_recomputing():
    memo = MemoAgentOutput(
        sections=[MemoSection(text="a", citations=["s1"]), MemoSection(text="b", citations=["s2"])],
        rejected_sentences=[RejectedSentence(text="c", reason="NO_CITATION")],
        citation_failure_rate=1 / 3,
        fallback_used=False,
        source_id="memo:llm:sonnet",
        disclosure="d",
    )
    metric = citation_metric(memo)
    assert metric == {"accepted": 2, "rejected": 1, "rate": 1 - 1 / 3}


def test_coverage_gate_metric_golden_set_all_pass():
    result = coverage_gate_metric()
    assert result["failed"] == 0
    assert result["pass_rate"] == 1.0
    assert result["total"] == 8  # 냉천3 + 신천5


def test_coverage_uncertain_point_metric_clean():
    result = coverage_uncertain_point_metric()
    assert result["clean"] is True
    assert result["mismatches"] == []


def test_eal_reproducibility_metric_true_for_same_seed(in_scope_flood):
    flood = FloodAgentOutput(flood=in_scope_flood, source_id="flood:test", field_sources={})
    building = BuildingAgentOutput(
        vulnerability_score=55.0,
        contributing_factors=[],
        source="building:test",
        source_id="building:test",
        missing_fields=[],
        status="OK",
        note=None,
    )
    metric = eal_reproducibility_metric(flood, building, collateral_value=500_000_000)
    assert metric["reproducible"] is True
    assert metric["EAL_mean"] is not None


def test_forbidden_phrase_absence_metric_clean_when_no_forbidden_text():
    memo = MemoAgentOutput(
        sections=[MemoSection(text="침수 위험이 확인되었습니다", citations=["s1"])],
        rejected_sentences=[],
        citation_failure_rate=0.0,
        fallback_used=False,
        source_id="memo:llm:sonnet",
        disclosure="d",
    )
    metric = forbidden_phrase_absence_metric(memo)
    assert metric == {"clean": True, "matches": []}
