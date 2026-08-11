from climate_risk.agents.building_agent import BuildingAgentOutput
from climate_risk.agents.flood_agent import FloodAgentOutput
from climate_risk.agents.scenario_agent import ScenarioAgentOutput
from climate_risk.memo.fallback_template import build_fallback_memo
from climate_risk.scenario.eal import EALResult


def test_fallback_memo_citations_are_always_subset_of_real_source_ids(in_scope_flood):
    flood = FloodAgentOutput(flood=in_scope_flood, source_id="flood:a.shp", field_sources={})
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

    real_source_ids = {flood.source_id, building.source_id, scenario.source_id}
    sections = build_fallback_memo(flood, building, scenario)

    assert len(sections) == 3
    for section in sections:
        assert set(section.citations).issubset(real_source_ids)
        assert section.citations  # 폴백은 항상 인용이 존재해야 함


def test_fallback_memo_handles_out_of_scope_flood_without_crashing(out_of_scope_flood):
    flood = FloodAgentOutput(
        flood=out_of_scope_flood, source_id="flood:out_of_scope", field_sources={}
    )
    building = BuildingAgentOutput(
        vulnerability_score=None,
        contributing_factors=[],
        source="",
        source_id="building:resolution_failed",
        missing_fields=["전체"],
        status="FAILED",
        note="건물 정보 미확인",
    )
    insufficient_eal = EALResult(
        EAL_mean=None,
        EAL_p50=None,
        EAL_p95=None,
        EAL_p99=None,
        n_iterations=10000,
        seed=42,
        distribution_histogram_bins=None,
        methodology_note="test",
        status="INSUFFICIENT_INPUT",
        reason="입력 데이터 불충분",
    )
    scenario = ScenarioAgentOutput(eal=insufficient_eal, source_id="scenario:mc:seed=42")

    sections = build_fallback_memo(flood, building, scenario)

    assert len(sections) == 3
    assert all(section.citations for section in sections)
