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
from typing import Any, Callable

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
from climate_risk.gis import query as gis_query
from climate_risk.policy.coverage_labels import label_for_flood_result

OnStage = Callable[[str, str], None]


def _notify(on_stage: OnStage | None, stage: str, message: str) -> None:
    """진행상황 훅 — 기본값 None이면 아무 동작 없음(기존 CLI/테스트 100% 동일 동작).
    웹 데모(webapp/app.py)가 SSE로 실제 단계 진행상황을 중계하는 데 쓴다 — 타이머로
    흉내낸 가짜 시퀀스가 아니라 이 함수가 실제로 불리는 시점 그대로를 전달한다."""
    if on_stage is not None:
        on_stage(stage, message)


def run_week3_demo(
    address: str,
    collateral_value: float,
    region_code: str = "47111",
    portfolio_path: Path = PORTFOLIO_DATA_PATH,
    timeline_path: Path = HINNAMNO_TIMELINE_PATH,
    mode: str = "replay",
    seed: int = DEFAULT_EAL_SEED,
    n_iterations: int = DEFAULT_EAL_ITERATIONS,
    on_stage: OnStage | None = None,
    # HANDOVER §⑧(층별 리스크 차등화) — 선택 입력. 미입력(None) 시 building_agent가
    # floor_exposure를 계산하지 않아 기존 건물 전체 스코어링 경로와 100% 동일하다.
    target_floor: dict | None = None,
) -> dict[str, Any]:
    _notify(on_stage, "advisory", "기상특보 이력을 조회하고 있어요")
    advisory = run_advisory_agent(region_code=region_code, mode=mode, timeline_path=timeline_path)

    _notify(on_stage, "geocode", "주소를 좌표로 변환하고 있어요")
    geocoded = geocode_road_address(address)
    if geocoded is None:
        return {"error": "주소 인식 실패 — 주소 수정 요청", "address": address}

    shp_cache_warm = gis_query._cached_default_regions.cache_info().currsize > 0
    flood_message = (
        "침수위험 지도를 조회하고 있어요"
        if shp_cache_warm
        else "침수위험 지도 데이터를 최초로 불러오고 있어요 (약 75초 소요, 이후엔 즉시 처리돼요)"
    )
    _notify(on_stage, "flood", flood_message)
    flood = run_flood_agent(geocoded.lat, geocoded.lon)

    _notify(on_stage, "building", "건축물대장에서 건물 정보를 가져오고 있어요")
    building = run_building_agent(
        lat=geocoded.lat, lon=geocoded.lon, target_floor=target_floor, flood=flood
    )

    _notify(on_stage, "scenario", "몬테카를로 시뮬레이션으로 예상 손실액을 계산하고 있어요")
    scenario = run_scenario_agent(
        flood, building, collateral_value, seed=seed, n_iterations=n_iterations
    )

    _notify(on_stage, "memo", "근거를 인용한 심사메모를 작성하고 있어요")
    memo = run_memo_agent(flood, building, scenario, advisory=advisory)

    portfolio_batch = None
    if advisory.trigger_event:
        _notify(on_stage, "portfolio", "발효된 특보에 따라 포트폴리오를 재계산하고 있어요")
        portfolio_batch = run_portfolio_agent(
            advisory, portfolio_path=portfolio_path, seed=seed, n_iterations=n_iterations
        )

    _notify(on_stage, "done", "완료됐어요")

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
