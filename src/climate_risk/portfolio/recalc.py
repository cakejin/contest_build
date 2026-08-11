"""지역필터링 서브셋 재계산 — HANDOVER.md §4.1 "추출된 서브셋만 위 그래프(홍수·건물취약도·
시나리오 에이전트)로 재계산". 기존 graph/pipeline.py 노드가 부르는 것과 동일한 3개
에이전트 함수를 직접 호출한다 — 파이프라인 로직을 새로 만들지 않는다. lat/lon은
geocode_cache가 이미 채워둔 값을 재사용하므로 재지오코딩하지 않는다.
"""

from __future__ import annotations

from dataclasses import dataclass

from climate_risk.agents.building_agent import BuildingAgentOutput, run_building_agent
from climate_risk.agents.flood_agent import FloodAgentOutput, run_flood_agent
from climate_risk.agents.scenario_agent import ScenarioAgentOutput, run_scenario_agent
from climate_risk.config import DEFAULT_EAL_ITERATIONS, DEFAULT_EAL_SEED
from climate_risk.portfolio.schema import PortfolioRecord


@dataclass(frozen=True)
class PortfolioRecalcResult:
    collateral_id: str
    flood: FloodAgentOutput
    building: BuildingAgentOutput
    scenario: ScenarioAgentOutput
    geocode_confidence: str | None


def recalc_subset(
    records: list[PortfolioRecord],
    seed: int = DEFAULT_EAL_SEED,
    n_iterations: int = DEFAULT_EAL_ITERATIONS,
) -> list[PortfolioRecalcResult]:
    results: list[PortfolioRecalcResult] = []
    for record in records:
        flood = run_flood_agent(record.lat, record.lon)
        building = run_building_agent(lat=record.lat, lon=record.lon)
        scenario = run_scenario_agent(
            flood, building, record.collateral_value, seed=seed, n_iterations=n_iterations
        )
        results.append(
            PortfolioRecalcResult(
                collateral_id=record.collateral_id,
                flood=flood,
                building=building,
                scenario=scenario,
                geocode_confidence=record.geocode_confidence,
            )
        )
    return results
