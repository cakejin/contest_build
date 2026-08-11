"""시나리오 에이전트 — HANDOVER.md §4.2 2.4. scenario/eal.py 위 얇은 오케스트레이션.

flood_agent·building_agent의 출력을 그대로 받아 run_monte_carlo_eal()에 넘기고,
결과에 source_id만 붙인다 — 새 계산 로직은 없다(그건 scenario/eal.py의 책임).
"""

from __future__ import annotations

from dataclasses import dataclass

from climate_risk.agents.building_agent import BuildingAgentOutput
from climate_risk.agents.flood_agent import FloodAgentOutput
from climate_risk.config import DEFAULT_EAL_ITERATIONS, DEFAULT_EAL_SEED
from climate_risk.scenario.eal import EALResult, run_monte_carlo_eal


@dataclass(frozen=True)
class ScenarioAgentOutput:
    eal: EALResult
    source_id: str


def run_scenario_agent(
    flood: FloodAgentOutput,
    building: BuildingAgentOutput,
    collateral_value: float,
    seed: int = DEFAULT_EAL_SEED,
    n_iterations: int = DEFAULT_EAL_ITERATIONS,
) -> ScenarioAgentOutput:
    eal = run_monte_carlo_eal(
        flood=flood.flood,
        vulnerability_score=building.vulnerability_score,
        collateral_value=collateral_value,
        seed=seed,
        n_iterations=n_iterations,
    )
    return ScenarioAgentOutput(eal=eal, source_id=f"scenario:mc:seed={seed}")
