"""시나리오 에이전트 — HANDOVER.md §4.2 2.4. scenario/eal.py 위 얇은 오케스트레이션.

flood_agent·building_agent의 출력을 그대로 받아 run_monte_carlo_eal()에 넘기고,
결과에 source_id만 붙인다 — 새 계산 로직은 없다(그건 scenario/eal.py의 책임).
"""

from __future__ import annotations

from dataclasses import dataclass

from climate_risk.agents.building_agent import BuildingAgentOutput
from climate_risk.agents.flood_agent import FloodAgentOutput
from climate_risk.config import (
    ADAPTATION_ASSUMPTION_NOTE,
    ADAPTATION_BARRIER_HEIGHTS_M,
    DEFAULT_EAL_ITERATIONS,
    DEFAULT_EAL_SEED,
)
from climate_risk.scenario.eal import EALResult, run_monte_carlo_eal
from climate_risk.scenario.floor_exposure import apply_floor_adjustment


# 2026-09-08 추가(DEV_LOG.md 참조) — 적응 투자(차수판) 설치 후 EAL. 결정론 규칙은
# config.ADAPTATION_ASSUMPTION_NOTE 그대로. 화면의 "우대 조건 안내" 참고치이며 금전 조건에 연결하지 않는다.
@dataclass(frozen=True)
class AdaptationScenario:
    barrier_height_m: float
    EAL_mean: float
    change_pct: float  # (after - before) / before, before가 0이면 0.0


@dataclass(frozen=True)
class AdaptationResult:
    assumption_note: str
    baseline_EAL_mean: float
    scenarios: list[AdaptationScenario]


@dataclass(frozen=True)
class ScenarioAgentOutput:
    eal: EALResult
    source_id: str
    adaptation: AdaptationResult | None = None


def run_scenario_agent(
    flood: FloodAgentOutput,
    building: BuildingAgentOutput,
    collateral_value: float,
    seed: int = DEFAULT_EAL_SEED,
    n_iterations: int = DEFAULT_EAL_ITERATIONS,
) -> ScenarioAgentOutput:
    # HANDOVER §⑧ 옵션A — target_floor를 넣지 않은 기존 호출(building.floor_exposure
    # is None)은 apply_floor_adjustment()가 building.vulnerability_score를 그대로
    # 반환하므로 이 줄을 추가해도 기존 동작이 바뀌지 않는다.
    vulnerability_score = apply_floor_adjustment(building.vulnerability_score, building.floor_exposure)
    eal = run_monte_carlo_eal(
        flood=flood.flood,
        vulnerability_score=vulnerability_score,
        collateral_value=collateral_value,
        seed=seed,
        n_iterations=n_iterations,
    )
    adaptation = None
    if eal.EAL_mean is not None:
        base = eal.EAL_mean
        scenarios = []
        for h in ADAPTATION_BARRIER_HEIGHTS_M:
            after = run_monte_carlo_eal(
                flood=flood.flood,
                vulnerability_score=vulnerability_score,
                collateral_value=collateral_value,
                seed=seed,
                n_iterations=n_iterations,
                barrier_height_m=h,
            )
            after_mean = after.EAL_mean if after.EAL_mean is not None else 0.0
            change = (after_mean - base) / base if base > 0 else 0.0
            scenarios.append(AdaptationScenario(barrier_height_m=h, EAL_mean=after_mean, change_pct=change))
        adaptation = AdaptationResult(
            assumption_note=ADAPTATION_ASSUMPTION_NOTE, baseline_EAL_mean=base, scenarios=scenarios
        )
    return ScenarioAgentOutput(eal=eal, source_id=f"scenario:mc:seed={seed}", adaptation=adaptation)
