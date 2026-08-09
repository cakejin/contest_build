"""커버리지 게이트 — "데이터 없음 ≠ 위험 없음" 원칙의 기술적 구현.

2026-08-09 DEV_LOG 반영: "판정보류"는 거리 임계값으로 일반화되는 알고리즘 규칙이
아니다(냉천교 38.4m와 침산교 36.4m처럼, 어떤 거리 임계값을 잡아도 두 그룹을
가르지 못함이 실측으로 확인됨 — DEV_LOG.md 2026-08-09 참조). 그래서 이 모듈은
역할을 둘로 분리한다:

1단 — is_within_coverage(): "로딩된 SHP가 커버하는 지리적 범위 밖"이라는 **일반화
      가능한** 규칙. 임의의 미래 좌표(예: 서울)에도 그대로 적용된다. 여기서 밖으로
      나오면 OUT_OF_SCOPE — tier 계산 자체를 시도하지 않는다.
2단 — 범위 안이면 거리·tier는 gis/query.py가 있는 그대로 계산해 반환한다(이 모듈은
      관여하지 않음). 거리가 멀다고 이 모듈이 임의로 걸러내지 않는다.

"판정보류" 라벨은 KNOWN_UNCERTAIN_POINTS — 신천 4개 좌표에 대한 PM의 수동 확인
결과를 그대로 담은 조회 테이블이다. 지오메트리 알고리즘의 출력이 아니라
사람이 직접 여러 구 SHP를 교차대조해 내린 정성적 판단을 코드 상수로 고정한 것이며,
이 5개(+냉천 대조군) 좌표 외에는 적용되지 않는다 — 새 좌표가 애매하게 나온다고
자동으로 여기 추가되지 않는다.
"""

from __future__ import annotations

from dataclasses import dataclass

import pyproj
import shapely.geometry

from climate_risk.config import (
    COVERAGE_BBOX_BUFFER_M,
    FLOOD_MAP_SOURCE_CRS,
)
from climate_risk.gis.loader import LoadedFloodRegion

_TRANSFORMER_4326_TO_5186 = pyproj.Transformer.from_crs(
    "EPSG:4326", FLOOD_MAP_SOURCE_CRS, always_xy=True
)


def to_flood_map_crs(lat: float, lon: float) -> tuple[float, float]:
    """WGS84(lat, lon) → SHP 원본 좌표계(EPSG:5186)로 변환한 (x, y)."""
    x, y = _TRANSFORMER_4326_TO_5186.transform(lon, lat)
    return x, y


def region_coverage_bbox(
    region: LoadedFloodRegion, buffer_m: float = COVERAGE_BBOX_BUFFER_M
) -> shapely.geometry.base.BaseGeometry:
    """해당 SHP가 로딩한 폴리곤 전체의 bbox에 여유폭을 더한 커버리지 범위(5186).

    개별 폴리곤은 최대 수만 개 정점(예: 냉천 SGG N331 = 68,971점)을 가져
    union_all() 등 실제 지오메트리 연산을 걸면 매우 느리다. bbox 계산에는
    정점 좌표의 min/max만 필요하므로 각 zone의 .bounds(가벼운 스캔)만 모아
    합치고, 복잡한 폴리곤 형상 자체는 건드리지 않는다.
    """
    xs_min, ys_min, xs_max, ys_max = zip(*(zone.geom.bounds for zone in region.zones))
    box = shapely.geometry.box(min(xs_min), min(ys_min), max(xs_max), max(ys_max))
    return box.buffer(buffer_m, join_style="mitre")


def is_within_coverage(
    lat: float, lon: float, regions: list[LoadedFloodRegion]
) -> bool:
    """1단 게이트: 좌표가 로딩된 SHP 중 하나라도의 커버리지 범위 안에 있는가.

    범위 밖이면 False — 호출자는 tier 계산을 시도하지 않고 OUT_OF_SCOPE를
    즉시 반환해야 한다(설계 원칙: 데이터 없음을 위험 없음으로 둔갑시키지 않음 —
    여기서는 반대로 "판정 자체를 보류"하는 방향으로 안전하게 작동).
    """
    x, y = to_flood_map_crs(lat, lon)
    point = shapely.geometry.Point(x, y)
    return any(
        region_coverage_bbox(region).contains(point) for region in regions if region.zones
    )


@dataclass(frozen=True)
class UncertainPoint:
    """신천 4개 판정보류 지점 — 사람이 직접 인접 구 SHP 5개와 교차대조해 내린 결론.

    own_region_distance_m: '자기 구' 파일 기준 최근접 거리(§1.11 원본 실측표).
    note: PM의 정성적 판단 근거(원본 문서 그대로).
    """

    label: str
    lat: float
    lon: float
    own_region_distance_m: float
    note: str
    source_doc: str = (
        "contest_research/plans/data-security_climate-collateral-underwriting-ai.md §1.11"
    )


# 2026-08-09 V-World 검색 API(type=place)로 지오코딩 — 도로명주소가 없는 다리 이름이라
# geocoding.vworld.geocode_road_address()(주소 기반)가 아니라 search_place()(지명 기반)를
# 썼다. 각 좌표는 own_region_distance_m과 비교해 "합리적인 근사"인지 검증했다(DEV_LOG.md
# 2026-08-09 항목 참조) — 침산교·대봉교는 거리 오차 1~3m로 원본 실측과 사실상 일치,
# 수성교·신천동은 같은 tier(근접/원거리)로는 일치하나 절대 거리는 §1.11 원본 실측과
# 40~110m 차이가 난다(POI 좌표가 PM이 원래 짚은 지점과 정확히 같지 않을 수 있음).
# own_region_distance_m 필드는 이 좌표로 재계산한 값이 아니라 §1.11 원본 실측표 값
# 그대로다 — note 필드에 실제 재계산값과의 괴리를 남긴다.
# 신천대로(봉덕동, 남구)는 §1.11에서 내부(0.0m)로 명확히 확인된 지점이라 애초에
# "판정보류" 대상이 아니다 — 여기 4개만 판정보류 대상.
KNOWN_UNCERTAIN_POINTS: list[UncertainPoint] = [
    UncertainPoint(
        label="대봉교(중구·남구 경계)",
        lat=35.854937,
        lon=128.606197,
        own_region_distance_m=50.1,
        note=(
            "V-World 지명 검색에 다리 자체 POI가 없어 대봉교역(지하철역, 다리와 동일 "
            "이천동 214-684) 좌표로 프록시. own_region(중구) SHP 기준 재계산 거리 47.1m "
            "— §1.11 원본 50.1m와 근접 일치."
        ),
    ),
    UncertainPoint(
        label="수성교(수성동)",
        lat=35.861410,
        lon=128.608928,
        own_region_distance_m=99.4,
        note=(
            "V-World 지명 검색 '수성교' POI(인공지명>기간시설>교통, 중구 대봉동 669-1천). "
            "own_region(수성구) SHP 기준 재계산 거리 53.9m — §1.11 원본 99.4m와 tier(근접, "
            "<=100m)는 같으나 절대값 괴리 45m, 정확히 같은 지점인지 미확정."
        ),
    ),
    UncertainPoint(
        label="신천동(신천역 인근)",
        lat=35.874481,
        lon=128.616722,
        own_region_distance_m=395.6,
        note=(
            "V-World 지명 검색 '신천역(2번출구)' 버스정류장 POI(동구 신천동 522-1). "
            "own_region(동구) SHP 기준 재계산 거리 287.2m — §1.11 원본 395.6m와 tier(원거리, "
            ">100m)는 같으나 절대값 괴리 108m, 정확히 같은 지점인지 미확정."
        ),
    ),
    UncertainPoint(
        label="침산교(신천-금호강 합류부)",
        lat=35.900975,
        lon=128.592748,
        own_region_distance_m=36.4,
        note=(
            "V-World 지명 검색 '침산교' POI(인공지명>기간시설>교통, 북구 침산동 663-8천). "
            "own_region(북구) SHP 기준 재계산 거리 36.6m — §1.11 원본 36.4m와 사실상 일치."
        ),
    ),
]


def match_known_uncertain_point(
    lat: float, lon: float, tolerance_m: float = 50.0
) -> UncertainPoint | None:
    """좌표가 KNOWN_UNCERTAIN_POINTS 중 하나와 (tolerance_m 이내로) 일치하면 반환.

    부동소수점 좌표 재입력 오차를 흡수하기 위한 근접 매칭 — 임의의 새 좌표에
    일반화하는 규칙이 아니라 이 5개 지점 전용 lookup이라는 점이 핵심(모듈
    docstring 참조).
    """
    x1, y1 = to_flood_map_crs(lat, lon)
    for known in KNOWN_UNCERTAIN_POINTS:
        x2, y2 = to_flood_map_crs(known.lat, known.lon)
        if ((x1 - x2) ** 2 + (y1 - y2) ** 2) ** 0.5 <= tolerance_m:
            return known
    return None
