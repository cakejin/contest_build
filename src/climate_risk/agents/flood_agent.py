"""홍수 에이전트 — HANDOVER.md §4.2 2.1. gis/query.py 위에 source_id 태깅만 얹는다.

Week1이 이미 query_flood_risk()로 침수 판정 로직 전체(커버리지 게이트·tier·판정보류)를
구현했다 — 여기서는 새 판정 로직을 만들지 않는다. 이 얇은 래퍼의 유일한 책임은 Week3
인용검증 레이어가 "이 문장은 어느 source_id에서 왔는가"를 대조할 수 있도록 결과 필드마다
source_id를 붙이는 것뿐이다.
"""

from __future__ import annotations

from dataclasses import dataclass

from climate_risk.config import DEFAULT_SEARCH_RADIUS_M
from climate_risk.gis.loader import LoadedFloodRegion
from climate_risk.gis.query import FloodRiskResult, query_flood_risk

_OUT_OF_SCOPE_SOURCE_ID = "flood:out_of_scope"


@dataclass(frozen=True)
class FloodAgentOutput:
    flood: FloodRiskResult
    source_id: str
    field_sources: dict[str, str]


def run_flood_agent(
    lat: float,
    lon: float,
    radius_m: float = DEFAULT_SEARCH_RADIUS_M,
    regions: list[LoadedFloodRegion] | None = None,
) -> FloodAgentOutput:
    result = query_flood_risk(lat, lon, radius_m=radius_m, regions=regions)

    if result.coverage == "OUT_OF_SCOPE":
        source_id = _OUT_OF_SCOPE_SOURCE_ID
        field_sources = {"coverage": source_id}
        return FloodAgentOutput(flood=result, source_id=source_id, field_sources=field_sources)

    source_id = f"flood:{result.source_shp_file}"
    field_sources = {
        field: source_id
        for field in (
            "coverage",
            "in_polygon",
            "tier",
            "distance_to_polygon_m",
            "freq_label",
            "river_name",
            "region_name",
            "methodology_disclaimer",
        )
    }
    if result.uncertain is not None:
        # UncertainPoint가 이미 자기 출처(source_doc)를 갖고 있다 — 새로 만들 필요 없음
        # (gis/coverage.py KNOWN_UNCERTAIN_POINTS 참조).
        field_sources["uncertain"] = result.uncertain.source_doc

    return FloodAgentOutput(flood=result, source_id=source_id, field_sources=field_sources)
