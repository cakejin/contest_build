"""Week3 통합 데모 엔트리포인트 — HANDOVER.md Week3 Done기준
"주소입력→힌남노리플레이→심사메모"를 실제로 호출 가능한 함수 하나로 노출한다.

graph/run.py의 run_pipeline()과 달리 flood/building/scenario를 dict가 아니라 타입
있는 dataclass로 유지한다 — memo_agent가 field_sources/source_id를 그대로 읽어야
하기 때문에(portfolio/recalc.py와 동일한 이유로 run_pipeline을 재사용하지 않는다).

포트폴리오 배치 재계산은 `advisory.trigger_event`가 True일 때만 실행한다(HANDOVER §4.1
"전체 재계산과 트리거 재계산을 분리한다" — 특보가 없는데 배치를 도는 것은 이 트리거
경로의 책임이 아니다, 정기 배치의 몫).
"""

from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Any

from climate_risk.agents.advisory_agent import run_advisory_agent
from climate_risk.agents.building_agent import run_building_agent
from climate_risk.agents.flood_agent import run_flood_agent
from climate_risk.agents.memo_agent import run_memo_agent
from climate_risk.agents.portfolio_agent import run_portfolio_agent
from climate_risk.agents.scenario_agent import run_scenario_agent
from climate_risk.config import (
    DEFAULT_EAL_ITERATIONS,
    DEFAULT_EAL_SEED,
    HINNAMNO_TIMELINE_PATH,
    PORTFOLIO_DATA_PATH,
)
from climate_risk.geocoding.vworld import geocode_road_address
from climate_risk.policy.coverage_labels import label_for_flood_result


def run_week3_demo(
    address: str,
    collateral_value: float,
    region_code: str = "47111",
    portfolio_path: Path = PORTFOLIO_DATA_PATH,
    timeline_path: Path = HINNAMNO_TIMELINE_PATH,
    seed: int = DEFAULT_EAL_SEED,
    n_iterations: int = DEFAULT_EAL_ITERATIONS,
) -> dict[str, Any]:
    advisory = run_advisory_agent(region_code=region_code, mode="replay", timeline_path=timeline_path)

    geocoded = geocode_road_address(address)
    if geocoded is None:
        return {"error": "주소 인식 실패 — 주소 수정 요청", "address": address}

    flood = run_flood_agent(geocoded.lat, geocoded.lon)
    building = run_building_agent(lat=geocoded.lat, lon=geocoded.lon)
    scenario = run_scenario_agent(
        flood, building, collateral_value, seed=seed, n_iterations=n_iterations
    )
    memo = run_memo_agent(flood, building, scenario, advisory=advisory)

    portfolio_batch = None
    if advisory.trigger_event:
        portfolio_batch = run_portfolio_agent(
            advisory, portfolio_path=portfolio_path, seed=seed, n_iterations=n_iterations
        )

    return {
        "address": address,
        "geocoded": dataclasses.asdict(geocoded),
        "advisory": dataclasses.asdict(advisory),
        "flood": dataclasses.asdict(flood),
        "building": dataclasses.asdict(building),
        "scenario": dataclasses.asdict(scenario),
        "memo": dataclasses.asdict(memo),
        "portfolio_batch": dataclasses.asdict(portfolio_batch) if portfolio_batch else None,
        "coverage_label": label_for_flood_result(flood.flood),
    }
