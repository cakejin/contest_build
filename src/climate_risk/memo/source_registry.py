"""메모 에이전트가 참조할 수 있는 source_id 전체 목록 — Week1·2가 이미 태깅해둔
`field_sources`/`source_id`를 그대로 모을 뿐, 새 출처를 만들지 않는다.

인용검증 게이트(memo/citation_gate.py)는 이 레지스트리의 키 집합(known_source_ids)과
LLM이 낸 citations를 대조한다 — 여기 없는 source_id를 인용하면 무조건 반려된다.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from typing import Any

from climate_risk.agents.advisory_agent import AdvisoryAgentOutput
from climate_risk.agents.building_agent import BuildingAgentOutput
from climate_risk.agents.flood_agent import FloodAgentOutput
from climate_risk.agents.scenario_agent import ScenarioAgentOutput


@dataclass(frozen=True)
class SourceRecord:
    source_id: str
    label: str
    value_repr: str
    origin: str  # "flood" | "building" | "scenario" | "advisory"


def _flood_records(flood: FloodAgentOutput) -> dict[str, SourceRecord]:
    by_source_id: dict[str, list[str]] = {}
    for field, source_id in flood.field_sources.items():
        by_source_id.setdefault(source_id, []).append(field)

    flood_values = dataclasses.asdict(flood.flood)
    records: dict[str, SourceRecord] = {}
    for source_id, fields in by_source_id.items():
        value_repr = ", ".join(f"{f}={flood_values.get(f)!r}" for f in fields)
        records[source_id] = SourceRecord(
            source_id=source_id,
            label="홍수위험지도 점대점 판정" if source_id != "flood:out_of_scope" else "홍수위험지도 커버리지 밖",
            value_repr=value_repr,
            origin="flood",
        )
    return records


def _building_records(building: BuildingAgentOutput) -> dict[str, SourceRecord]:
    value_repr = (
        f"vulnerability_score={building.vulnerability_score!r}, "
        f"status={building.status!r}, missing_fields={building.missing_fields!r}"
    )
    label = "건축HUB 건축물대장정보 건물취약도"
    # HANDOVER §⑧(층별 리스크 차등화) — target_floor 입력 시 building.floor_exposure에
    # 층 단위 판정이 담긴다. 별도 source_id를 새로 만들지 않고 같은 building.source_id
    # 아래에 병기한다 — 이 값도 결국 flood(seg_code/tier)+건축HUB 데이터에서 결정론적으로
    # 파생된 것이라 건물취약도 레코드의 연장선이지 새 원자료가 아니다.
    if building.floor_exposure is not None:
        fe = building.floor_exposure
        value_repr += (
            f", floor_risk_tier={fe.floor_risk_tier!r}, floor_unassessed={fe.floor_unassessed!r}"
            f", basis={fe.basis!r}, reason={fe.reason!r}"
        )
        label = "건축HUB 건축물대장정보 건물취약도(층별 리스크 반영)"
    return {
        building.source_id: SourceRecord(
            source_id=building.source_id,
            label=label,
            value_repr=value_repr,
            origin="building",
        )
    }


def _scenario_records(scenario: ScenarioAgentOutput) -> dict[str, SourceRecord]:
    eal = scenario.eal
    value_repr = (
        f"EAL_mean={eal.EAL_mean!r}, EAL_p50={eal.EAL_p50!r}, "
        f"EAL_p95={eal.EAL_p95!r}, EAL_p99={eal.EAL_p99!r}, status={eal.status!r}"
    )
    return {
        scenario.source_id: SourceRecord(
            source_id=scenario.source_id,
            label="몬테카를로 EAL 시뮬레이션",
            value_repr=value_repr,
            origin="scenario",
        )
    }


def _advisory_records(advisory: AdvisoryAgentOutput) -> dict[str, SourceRecord]:
    records: dict[str, SourceRecord] = {}
    for event in advisory.timeline:
        records[event.source_id] = SourceRecord(
            source_id=event.source_id,
            label=f"특보 리플레이 이벤트({event.event_type})",
            value_repr=f"{event.issued_at} {event.description} (source={event.source_url})",
            origin="advisory",
        )
    return records


def build_source_registry(
    flood: FloodAgentOutput,
    building: BuildingAgentOutput,
    scenario: ScenarioAgentOutput,
    advisory: AdvisoryAgentOutput | None = None,
) -> dict[str, SourceRecord]:
    registry: dict[str, SourceRecord] = {}
    registry.update(_flood_records(flood))
    registry.update(_building_records(building))
    registry.update(_scenario_records(scenario))
    if advisory is not None:
        registry.update(_advisory_records(advisory))
    return registry


def registry_to_prompt_facts(registry: dict[str, SourceRecord]) -> list[dict[str, Any]]:
    """LLM 프롬프트에 넣을 수 있는 평문 사실 목록으로 변환(정렬 고정 — 프롬프트 재현성)."""
    return [
        {"source_id": r.source_id, "label": r.label, "value": r.value_repr}
        for r in sorted(registry.values(), key=lambda r: r.source_id)
    ]
