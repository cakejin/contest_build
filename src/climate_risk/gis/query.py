"""query_flood_risk — HANDOVER.md §4.3 point-in-polygon 질의 인터페이스.

2차 경로(로컬/오프라인): pyshp로 로딩한 shapely geometry + STRtree.
HANDOVER §4.2 홍수 에이전트 출력 스키마를 그대로 따른다.
"""

from __future__ import annotations

from dataclasses import dataclass

import shapely.geometry
from shapely import STRtree

from climate_risk.config import DEFAULT_SEARCH_RADIUS_M
from climate_risk.gis.coverage import (
    UncertainPoint,
    is_within_coverage,
    match_known_uncertain_point,
    to_flood_map_crs,
)
from climate_risk.gis.loader import FloodRiskZone, LoadedFloodRegion, load_all_regions

TIER_INNER = "내부"
TIER_NEAR = "근접"
TIER_FAR = "원거리"
NEAR_THRESHOLD_M = 100.0

METHODOLOGY_DISCLAIMER = (
    "환경부 하천범람지도는 제방붕괴·월류의 극한 상황을 가정한 가상의 분석 결과이며 "
    "실제 하천제방의 안전성과는 무관합니다(환경부 공식 문구). 발생확률 예측이 아닌 "
    "보수적 익스포저 상한으로 해석하고, 실측 침수흔적 이력과 교차 등급화해 참고하십시오."
)


@dataclass(frozen=True)
class FloodRiskResult:
    coverage: str  # "IN_SCOPE" | "OUT_OF_SCOPE"
    in_polygon: bool | None
    tier: str | None
    distance_to_polygon_m: float | None
    freq_label: str | None
    river_name: str | None
    region_name: str | None
    source_shp_file: str | None
    license: str | None
    methodology_disclaimer: str
    uncertain: UncertainPoint | None
    # Week3(B3)에서 flood_history_events 큐레이션 완료 후 채워짐 — 스키마 선점.
    history_events: list = None  # type: ignore[assignment]

    def __post_init__(self):
        if self.history_events is None:
            object.__setattr__(self, "history_events", [])


def _out_of_scope() -> FloodRiskResult:
    return FloodRiskResult(
        coverage="OUT_OF_SCOPE",
        in_polygon=None,
        tier=None,
        distance_to_polygon_m=None,
        freq_label=None,
        river_name=None,
        region_name=None,
        source_shp_file=None,
        license=None,
        methodology_disclaimer=METHODOLOGY_DISCLAIMER,
        uncertain=None,
    )


def _pool_zones(regions: list[LoadedFloodRegion]) -> list[FloodRiskZone]:
    return [zone for region in regions for zone in region.zones]


def query_flood_risk(
    lat: float,
    lon: float,
    radius_m: float = DEFAULT_SEARCH_RADIUS_M,
    regions: list[LoadedFloodRegion] | None = None,
) -> FloodRiskResult:
    """HANDOVER §4.2 홍수 에이전트 처리 순서 그대로:

    ① WGS84→EPSG:5186 변환 ② 커버리지 게이트(1단, coverage.py) — 밖이면 즉시
    OUT_OF_SCOPE ③ point-in-polygon(ST_Contains 상당) ④ 내부 아니면 최근접 거리로
    3단계 tier(내부/근접≤100m/원거리>100m) ⑤ KNOWN_UNCERTAIN_POINTS 매칭(해당되면
    uncertain 필드에 판정보류 근거 첨부 — coverage/tier는 그대로 정직하게 반환,
    이 필드는 UI 라벨링용 오버레이일 뿐 판정 자체를 바꾸지 않는다).
    """
    regions = regions if regions is not None else load_all_regions()

    if not is_within_coverage(lat, lon, regions):
        return _out_of_scope()

    x, y = to_flood_map_crs(lat, lon)
    point = shapely.geometry.Point(x, y)

    zones = _pool_zones(regions)
    if not zones:
        return _out_of_scope()

    tree = STRtree([zone.geom for zone in zones])

    contains_idx = tree.query(point, predicate="contains")
    if len(contains_idx) > 0:
        chosen = zones[int(contains_idx[0])]
        in_polygon = True
        distance = 0.0
    else:
        nearest_idx = int(tree.nearest(point))
        chosen = zones[nearest_idx]
        in_polygon = False
        distance = chosen.geom.distance(point)

    if distance <= 0.0:
        tier = TIER_INNER
    elif distance <= NEAR_THRESHOLD_M:
        tier = TIER_NEAR
    else:
        tier = TIER_FAR

    uncertain = match_known_uncertain_point(lat, lon)

    return FloodRiskResult(
        coverage="IN_SCOPE",
        in_polygon=in_polygon,
        tier=tier,
        distance_to_polygon_m=round(distance, 1),
        freq_label=chosen.freq_label,
        river_name=chosen.river_name,
        region_name=chosen.region_name,
        source_shp_file=chosen.source_file,
        license=chosen.license,
        methodology_disclaimer=METHODOLOGY_DISCLAIMER,
        uncertain=uncertain,
    )
