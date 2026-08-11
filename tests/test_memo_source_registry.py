from climate_risk.agents.building_agent import BuildingAgentOutput
from climate_risk.agents.flood_agent import FloodAgentOutput
from climate_risk.agents.scenario_agent import ScenarioAgentOutput
from climate_risk.memo.source_registry import build_source_registry
from climate_risk.scenario.eal import EALResult


def _flood_output(in_scope_flood):
    return FloodAgentOutput(
        flood=in_scope_flood,
        source_id="flood:test.shp",
        field_sources={"coverage": "flood:test.shp", "tier": "flood:test.shp"},
    )


def _building_output():
    return BuildingAgentOutput(
        vulnerability_score=55.0,
        contributing_factors=[],
        source="test",
        source_id="building:test123",
        missing_fields=[],
        status="OK",
        note=None,
    )


def _scenario_output():
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
    return ScenarioAgentOutput(eal=eal, source_id="scenario:mc:seed=42")


def test_registry_includes_all_three_agent_source_ids(in_scope_flood):
    flood = _flood_output(in_scope_flood)
    building = _building_output()
    scenario = _scenario_output()

    registry = build_source_registry(flood, building, scenario)

    assert flood.source_id in registry
    assert building.source_id in registry
    assert scenario.source_id in registry


def test_registry_includes_advisory_events_when_given(in_scope_flood):
    from climate_risk.agents.advisory_agent import run_advisory_agent
    from climate_risk.config import HINNAMNO_TIMELINE_PATH

    flood = _flood_output(in_scope_flood)
    building = _building_output()
    scenario = _scenario_output()
    advisory = run_advisory_agent(region_code="47111", mode="replay", timeline_path=HINNAMNO_TIMELINE_PATH)

    registry = build_source_registry(flood, building, scenario, advisory)

    for event in advisory.timeline:
        assert event.source_id in registry


def test_registry_omits_advisory_when_none(in_scope_flood):
    flood = _flood_output(in_scope_flood)
    building = _building_output()
    scenario = _scenario_output()

    registry = build_source_registry(flood, building, scenario, advisory=None)

    assert all(r.origin != "advisory" for r in registry.values())
