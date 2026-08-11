from climate_risk.agents.building_agent import BuildingAgentOutput
from climate_risk.agents.flood_agent import FloodAgentOutput
from climate_risk.agents.scenario_agent import ScenarioAgentOutput
from climate_risk.portfolio import recalc
from climate_risk.portfolio.schema import PortfolioRecord
from climate_risk.scenario.eal import EALResult


def _record(collateral_id):
    return PortfolioRecord(
        collateral_id=collateral_id,
        address="테스트",
        collateral_type="아파트",
        balance=100.0,
        collateral_value=200.0,
        ltv=0.5,
        score_before=50.0,
        eal_before=1000.0,
        lat=35.0,
        lon=129.0,
        region_code="47111",
        geocode_confidence="OK",
    )


def test_recalc_subset_calls_three_agents_directly_no_reheocoding(monkeypatch, in_scope_flood):
    flood_calls = []
    building_calls = []
    scenario_calls = []

    def fake_flood(lat, lon, **kwargs):
        flood_calls.append((lat, lon))
        return FloodAgentOutput(flood=in_scope_flood, source_id="flood:test.shp", field_sources={})

    def fake_building(**kwargs):
        building_calls.append(kwargs)
        return BuildingAgentOutput(
            vulnerability_score=60.0,
            contributing_factors=[],
            source="test",
            source_id="building:test",
            missing_fields=[],
            status="OK",
            note=None,
        )

    def fake_scenario(flood, building, collateral_value, seed, n_iterations):
        scenario_calls.append(collateral_value)
        eal = EALResult(
            EAL_mean=1500.0,
            EAL_p50=1200.0,
            EAL_p95=3000.0,
            EAL_p99=4000.0,
            n_iterations=n_iterations,
            seed=seed,
            distribution_histogram_bins=None,
            methodology_note="test",
            status="OK",
            reason=None,
        )
        return ScenarioAgentOutput(eal=eal, source_id=f"scenario:mc:seed={seed}")

    monkeypatch.setattr(recalc, "run_flood_agent", fake_flood)
    monkeypatch.setattr(recalc, "run_building_agent", fake_building)
    monkeypatch.setattr(recalc, "run_scenario_agent", fake_scenario)

    records = [_record("COL-001"), _record("COL-002")]
    results = recalc.recalc_subset(records, seed=42, n_iterations=100)

    assert len(results) == 2
    assert flood_calls == [(35.0, 129.0), (35.0, 129.0)]  # 캐시된 lat/lon 재사용, 재지오코딩 없음
    assert [r.collateral_id for r in results] == ["COL-001", "COL-002"]
    assert results[0].scenario.eal.EAL_mean == 1500.0
