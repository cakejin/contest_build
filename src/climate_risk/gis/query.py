"""query_flood_risk — HANDOVER.md §4.3 point-in-polygon 질의 인터페이스.

2차 경로(로컬/오프라인): pyshp로 로딩한 shapely geometry + STRtree.
HANDOVER §4.2 홍수 에이전트 출력 스키마를 그대로 따른다.
"""

from __future__ import annotations

import functools
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
    # HANDOVER.md §⑧(층별 리스크 차등화) 데이터소스 1번 — SHP의 SEG_CODE 필드 그대로.
    # N330=0.5m미만/N331=0.5~1.0m/N332=1.0~2.0m/N333=2.0~5.0m/N334=5.0m이상.
    # loader.py가 이미 FloodRiskZone.seg_code로 읽고 있었으나 결과에 노출만 안 됐던 것 —
    # 2026-08-18 추가. in_polygon이 아닌(근접/원거리) tier에서는 "가장 가까운 폴리곤"의
    # 등급일 뿐 그 좌표 자체의 등급이 아니므로, scenario/floor_exposure.py는 tier=="내부"일
    # 때만 이 값을 신뢰한다.
    seg_code: str | None = None
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


@functools.lru_cache(maxsize=1)
def _cached_default_regions() -> tuple[LoadedFloodRegion, ...]:
    """load_all_regions() 기본 소스 로딩 결과를 프로세스 수명 동안 1회만 계산한다.

    실측(2026-08-09): load_all_regions()는 콜드 호출 시 157.8초 걸린다(6개 SHP를
    pyshp로 읽고 최대 68,971점짜리 다중파트 폴리곤을 polygonize+make_valid로
    재구성하기 때문 — loader.py `_shape_to_geometry` 참조). query_flood_risk()가
    regions 인자 없이 호출될 때마다 이 비용을 다시 치르면 Week2(홍수 에이전트)·
    Week3(포트폴리오 300~500건 배치)에서 감당 불가능하다(배치 1건당 95초 이상).
    이 함수는 그 경로에서만 쓰인다 — 명시적으로 regions를 넘기는 호출(테스트 등)은
    이 캐시를 우회하며 매번 새로 로딩된다(재현성 검증 목적이라 의도적).
    """
    return tuple(load_all_regions())


@functools.lru_cache(maxsize=1)
def _cached_default_zones() -> tuple[FloodRiskZone, ...]:
    return tuple(_pool_zones(list(_cached_default_regions())))


@functools.lru_cache(maxsize=1)
def _cached_default_tree() -> STRtree | None:
    """기본 경로(regions 미지정) 전용 STRtree — 프로세스 수명 동안 1회만 빌드한다.

    수정 전에는 query_flood_risk() 호출마다(포트폴리오 배치 300~500건) zone 전체로
    STRtree를 새로 빌드했다 — _cached_default_regions()가 이미 해결한 것과 같은
    종류의 반복 비용이라 동일한 lru_cache 패턴으로 없앤다. regions를 명시적으로
    넘기는 호출(테스트 등)은 이 캐시를 우회하며 매번 새로 빌드한다(기존 동작 유지).
    """
    zones = _cached_default_zones()
    return STRtree([zone.geom for zone in zones]) if zones else None


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
    using_default_regions = regions is None
    regions = regions if regions is not None else _cached_default_regions()

    if not is_within_coverage(lat, lon, regions):
        return _out_of_scope()

    x, y = to_flood_map_crs(lat, lon)
    point = shapely.geometry.Point(x, y)

    if using_default_regions:
        zones = _cached_default_zones()
        tree = _cached_default_tree()
    else:
        zones = _pool_zones(regions)
        tree = STRtree([zone.geom for zone in zones]) if zones else None

    if not zones or tree is None:
        return _out_of_scope()

    # 실측 확인(2026-08-09): STRtree.query(point, predicate="covers"/"contains")는
    # 매우 복잡한 다중 파트 지오메트리(최대 3236 parts, polygonize+make_valid 재구성본)에서
    # zone.geom.covers(point)가 직접 True를 반환하는 점조차 매치하지 못하는 케이스가
    # 실측으로 확인됐다(GEOS의 STRtree 내부 prepared-geometry 판정이 이런 위상에서
    # 신뢰 불가) — bbox 후보 필터링에만 STRtree를 쓰고, 실제 covers 판정은 개별
    # shapely 지오메트리에 직접 호출한다(느리지만 zone 수가 적어 비용 무시 가능).
    bbox_candidate_idx = tree.query(point)  # predicate 없음 = bbox intersects만
    covering_zone = next(
        (zones[int(i)] for i in bbox_candidate_idx if zones[int(i)].geom.covers(point)),
        None,
    )
    if covering_zone is not None:
        chosen = covering_zone
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
        seg_code=chosen.seg_code,
    )
