"""규칙기반 폴백 메모 — HANDOVER.md §4.2 2.5 "인용 실패율이 임계치 초과 시 LLM 생성 전체를
폐기하고 4개 에이전트 output을 규칙기반 정형 템플릿(표)으로 자동 대체".

LLM을 전혀 호출하지 않는다 — 3개 에이전트 output에서 결정론적으로 문장을 조립하고,
각 문장의 citation은 그 문장이 실제로 참조한 필드의 source_id 그대로다. 구성상 인용
실패율이 항상 0%다(citation_gate.verify_citations를 통과할 필요조차 없다).
"""

from __future__ import annotations

from climate_risk.agents.building_agent import BuildingAgentOutput
from climate_risk.agents.flood_agent import FloodAgentOutput
from climate_risk.agents.scenario_agent import ScenarioAgentOutput
from climate_risk.memo.schema import MemoSection


def _flood_section(flood: FloodAgentOutput) -> MemoSection:
    f = flood.flood
    if f.coverage == "OUT_OF_SCOPE":
        text = "이 담보는 홍수위험지도 SHP 커버리지 밖이라 침수 판정을 보류합니다(데이터 없음 — 위험 낮음 아님)."
    elif f.uncertain is not None:
        text = f"이 담보는 침수 판정이 확정되지 않아 판정보류 상태입니다({f.uncertain.note})."
    else:
        text = (
            f"이 담보는 {f.river_name} 홍수위험지도상 {f.tier} 등급"
            f"(폴리곤까지 거리 {f.distance_to_polygon_m}m, {f.freq_label} 빈도)입니다."
        )
    return MemoSection(text=text, citations=[flood.source_id])


def _building_section(building: BuildingAgentOutput) -> MemoSection:
    if building.vulnerability_score is None:
        text = f"건물취약도 정보가 불충분합니다({building.note})."
    else:
        text = (
            f"건물취약도 점수는 {building.vulnerability_score}점"
            f"({building.status}, 결측항목 {building.missing_fields or '없음'})입니다."
        )
    return MemoSection(text=text, citations=[building.source_id])


def _scenario_section(scenario: ScenarioAgentOutput) -> MemoSection:
    eal = scenario.eal
    if eal.status != "OK":
        text = f"연간기대손실(EAL)을 산출하지 못했습니다({eal.reason})."
    else:
        text = (
            f"연간기대손실(EAL) 평균은 {eal.EAL_mean:,.0f}원, p95는 {eal.EAL_p95:,.0f}원입니다"
            f"(시드 {eal.seed}, {eal.n_iterations}회 시뮬레이션)."
        )
    return MemoSection(text=text, citations=[scenario.source_id])


def build_fallback_memo(
    flood: FloodAgentOutput,
    building: BuildingAgentOutput,
    scenario: ScenarioAgentOutput,
) -> list[MemoSection]:
    return [
        _flood_section(flood),
        _building_section(building),
        _scenario_section(scenario),
    ]
