"""LangGraph 홍수→건물취약도→시나리오 순차 파이프라인 — HANDOVER.md §4.1 다이어그램.

지오코딩은 그래프 밖에서 처리한다(HANDOVER §4.2 "2.0 지오코딩 전처리, 에이전트 아님" —
"좌표 없이는 어떤 에이전트도 실행하지 않음"). 이 모듈은 이미 지오코딩된 좌표가 상태에
있다고 전제하고, 그 다음부터만 담당한다.

HANDOVER §⑧(층별 리스크 차등화, 2026-08-18 추가)로 building_node가 flood_node의 결과
(seg_code·tier)를 받아 floor_exposure를 계산해야 해서, 기존 flood∥building 병렬
fan-out을 flood→building 순차 실행으로 바꿨다(DEV_LOG 2026-08-18 "그래프/UI 연동은
다음 단계로 이월" 항목 후속 조치). flood는 프로세스당 1회 SHP 로딩(~75초) 이후로는
캐시로 즉시 처리되므로(DEV_LOG 2026-08-09) 순차화에 따른 상시 비용은 무시할 수
있는 수준이다.
"""

from __future__ import annotations

from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from climate_risk.agents.building_agent import BuildingAgentOutput, run_building_agent
from climate_risk.agents.flood_agent import FloodAgentOutput, run_flood_agent
from climate_risk.agents.scenario_agent import ScenarioAgentOutput, run_scenario_agent
from climate_risk.config import DEFAULT_EAL_ITERATIONS, DEFAULT_EAL_SEED
from climate_risk.geocoding.vworld import GeocodedAddress


class PipelineState(TypedDict, total=False):
    address: str
    collateral_value: float
    seed: int
    n_iterations: int
    target_floor: dict | None
    geocoded: GeocodedAddress
    flood: FloodAgentOutput
    building: BuildingAgentOutput
    scenario: ScenarioAgentOutput


def flood_node(state: PipelineState) -> dict:
    geocoded = state["geocoded"]
    return {"flood": run_flood_agent(geocoded.lat, geocoded.lon)}


def building_node(state: PipelineState) -> dict:
    geocoded = state["geocoded"]
    # lat/lon을 직접 넘겨 building_agent가 다시 도로명주소 지오코딩을 반복하지 않게 한다
    # (resolve_admin_codes는 lat/lon이 있으면 address 인자를 무시하고 바로 역지오코딩으로 간다).
    # target_floor 미입력 시 flood를 넘겨도 floor_exposure는 None으로 생략되므로(§⑧)
    # 기존(층수 미입력) 경로의 결과는 그대로다.
    return {
        "building": run_building_agent(
            lat=geocoded.lat,
            lon=geocoded.lon,
            target_floor=state.get("target_floor"),
            flood=state.get("flood"),
        )
    }


def scenario_node(state: PipelineState) -> dict:
    scenario = run_scenario_agent(
        state["flood"],
        state["building"],
        state["collateral_value"],
        seed=state.get("seed", DEFAULT_EAL_SEED),
        n_iterations=state.get("n_iterations", DEFAULT_EAL_ITERATIONS),
    )
    return {"scenario": scenario}


def build_graph():
    graph = StateGraph(PipelineState)
    graph.add_node("flood", flood_node)
    graph.add_node("building", building_node)
    graph.add_node("scenario", scenario_node)

    graph.add_edge(START, "flood")
    graph.add_edge("flood", "building")  # building이 floor_exposure 계산을 위해 flood 결과를 필요로 함(§⑧)
    graph.add_edge("building", "scenario")
    graph.add_edge("scenario", END)

    return graph.compile()
