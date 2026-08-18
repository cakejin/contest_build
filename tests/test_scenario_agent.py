"""agents/scenario_agent.py — HANDOVER §⑧ 옵션A(floor_exposure -> EAL 반영) 회귀 테스트.

시나리오 에이전트 자체의 EAL 계산 로직은 scenario/eal.py가 이미 커버한다(seed
재현성 등) — 여기서는 "floor_exposure가 있으면 vulnerability_score가 조정돼 EAL에
반영되는가, 없으면 기존과 동일한가"만 검증한다.
"""

from climate_risk.agents.building_agent import BuildingAgentOutput
from climate_risk.agents.flood_agent import FloodAgentOutput
from climate_risk.agents.scenario_agent import run_scenario_agent
from climate_risk.gis.query import FloodRiskResult
from climate_risk.scenario.floor_exposure import determine_floor_flood_exposure

_FLOOD = FloodAgentOutput(
    flood=FloodRiskResult(
        coverage="IN_SCOPE", in_polygon=True, tier="내부", distance_to_polygon_m=0.0,
        freq_label="MAX", river_name="냉천", region_name="포항시 남구",
        source_shp_file="test.shp", license="공공누리4유형",
        methodology_disclaimer="test", uncertain=None, seg_code="N331",
    ),
    source_id="flood:test.shp", field_sources={},
)


def _building(vulnerability_score, floor_exposure=None):
    return BuildingAgentOutput(
        vulnerability_score=vulnerability_score, contributing_factors=[], source="test",
        source_id="building:test", missing_fields=[], status="OK", note=None,
        floor_exposure=floor_exposure,
    )


def test_no_floor_exposure_matches_baseline_eal():
    without = run_scenario_agent(_FLOOD, _building(20.0), collateral_value=1_000_000_000, seed=42, n_iterations=500)
    baseline = run_scenario_agent(_FLOOD, _building(20.0, None), collateral_value=1_000_000_000, seed=42, n_iterations=500)
    assert without.eal.EAL_mean == baseline.eal.EAL_mean


def test_underground_floor_exposure_increases_eal_vs_ground_low_tier():
    """지하층(HIGH 강제) 담보와 고층(LOW) 담보를 같은 건물 취약도 점수로 비교하면,
    지하층 쪽 EAL이 더 커야 한다 — floor_exposure가 실제로 EAL에 영향을 주는지 확인."""
    high = determine_floor_flood_exposure("지하", 1, None, None, "IN_SCOPE")
    low = determine_floor_flood_exposure("지상", 5, "N330", "내부", "IN_SCOPE")  # 5층, 얕은 침수등급 -> LOW

    result_high = run_scenario_agent(
        _FLOOD, _building(20.0, high), collateral_value=1_000_000_000, seed=42, n_iterations=2000
    )
    result_low = run_scenario_agent(
        _FLOOD, _building(20.0, low), collateral_value=1_000_000_000, seed=42, n_iterations=2000
    )

    assert result_high.eal.EAL_mean > result_low.eal.EAL_mean
