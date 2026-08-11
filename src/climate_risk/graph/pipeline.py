"""LangGraph fan-out(홍수∥건물취약도)/fan-in(시나리오) 골격 — HANDOVER.md §4.1 다이어그램.

지오코딩은 그래프 밖에서 처리한다(HANDOVER §4.2 "2.0 지오코딩 전처리, 에이전트 아님" —
"좌표 없이는 어떤 에이전트도 실행하지 않음"). 이 모듈은 이미 지오코딩된 좌표가 상태에
있다고 전제하고, 그 다음부터의 fan-out/fan-in만 담당한다.
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
    return {"building": run_building_agent(lat=geocoded.lat, lon=geocoded.lon)}


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
    graph.add_edge(START, "building")  # flood/building은 geocoded만 있으면 독립 실행 가능 — 병렬 fan-out
    graph.add_edge("flood", "scenario")
    graph.add_edge("building", "scenario")  # scenario는 둘 다 끝나야 실행 — LangGraph superstep이 fan-in 보장
    graph.add_edge("scenario", END)

    return graph.compile()
