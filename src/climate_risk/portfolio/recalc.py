"""지역필터링 서브셋 재계산 — HANDOVER.md §4.1 "추출된 서브셋만 위 그래프(홍수·건물취약도·
시나리오 에이전트)로 재계산". 기존 graph/pipeline.py 노드가 부르는 것과 동일한 3개
에이전트 함수를 직접 호출한다 — 파이프라인 로직을 새로 만들지 않는다. lat/lon은
geocode_cache가 이미 채워둔 값을 재사용하므로 재지오코딩하지 않는다.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from climate_risk.agents.building_agent import BuildingAgentOutput, run_building_agent
from climate_risk.agents.flood_agent import FloodAgentOutput, run_flood_agent
from climate_risk.agents.scenario_agent import ScenarioAgentOutput, run_scenario_agent
from climate_risk.config import DEFAULT_EAL_ITERATIONS, DEFAULT_EAL_SEED
from climate_risk.portfolio.schema import PortfolioRecord

_MAX_WORKERS = 8


@dataclass(frozen=True)
class PortfolioRecalcResult:
    collateral_id: str
    flood: FloodAgentOutput
    building: BuildingAgentOutput
    scenario: ScenarioAgentOutput
    geocode_confidence: str | None


def _recalc_one(record: PortfolioRecord, seed: int, n_iterations: int) -> PortfolioRecalcResult:
    flood = run_flood_agent(record.lat, record.lon)
    building = run_building_agent(lat=record.lat, lon=record.lon)
    scenario = run_scenario_agent(
        flood, building, record.collateral_value, seed=seed, n_iterations=n_iterations
    )
    return PortfolioRecalcResult(
        collateral_id=record.collateral_id,
        flood=flood,
        building=building,
        scenario=scenario,
        geocode_confidence=record.geocode_confidence,
    )


def recalc_subset(
    records: list[PortfolioRecord],
    seed: int = DEFAULT_EAL_SEED,
    n_iterations: int = DEFAULT_EAL_ITERATIONS,
) -> list[PortfolioRecalcResult]:
    """레코드별 재계산은 서로 독립적이다(각자 다른 좌표를 건축HUB/SHP에 조회) —
    핫패스(특보 트리거마다 실행)에서 순차 블로킹 I/O로 수십 초씩 쌓이지 않도록
    스레드풀로 병렬화한다. seed는 레코드마다 run_monte_carlo_eal이 만드는 로컬
    np.random.default_rng(seed) 인스턴스에서만 쓰여 스레드 간 공유 상태가 없다."""
    if not records:
        return []
    with ThreadPoolExecutor(max_workers=min(_MAX_WORKERS, len(records))) as executor:
        return list(executor.map(lambda r: _recalc_one(r, seed, n_iterations), records))
