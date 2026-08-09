"""홍수위험지도 SHP 로딩 — pyshp로 읽어 shapely geometry로 변환.

HANDOVER.md §4.3: "로딩 스크립트는 idempotent(기존 테이블 truncate 후 재적재) —
동일 SHP 재실행 시 동일 레코드 수·geometry 해시가 나오는지 CI에서 검증"을
로컬(비-PostGIS) 경로에서 구현한다. 여기서는 매 호출이 파일을 새로 읽어
새 객체를 만들 뿐이므로("truncate" 개념이 없음) idempotency는 자동으로
성립하고, 테스트는 이를 실측으로 확인한다(tests/test_loader_idempotent.py).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

import shapefile
import shapely
import shapely.geometry
import shapely.ops

from climate_risk.config import FLOOD_SHP_SOURCES, FloodShpSource, LICENSE_LABEL


@dataclass(frozen=True)
class FloodRiskZone:
    """SHP의 폴리곤 레코드 1건 (dbf 속성 + geometry, 원본 좌표계 EPSG:5186 그대로)."""

    region_code: str
    region_name: str
    river_name: str
    freq_label: str
    seg_code: str
    source_file: str
    license: str
    geom: shapely.geometry.base.BaseGeometry


@dataclass(frozen=True)
class LoadedFloodRegion:
    """SHP 파일 1개(=행정구역 1개)를 로딩한 결과 — 폴리곤들 + 메타데이터.

    skipped_null_seg_codes: 원본 SHP에 shapeType=NULL(빈 지오메트리)로 들어있어
    로딩에서 제외한 레코드의 SEG_CODE 목록. 정부 원본 데이터 자체의 결측이며
    로더 버그가 아니다 — "데이터 없음≠위험 없음" 원칙에 따라 조용히 버리지 않고
    여기 남겨 추적 가능하게 한다.
    """

    source: FloodShpSource
    zones: list[FloodRiskZone] = field(default_factory=list)
    skipped_null_seg_codes: list[str] = field(default_factory=list)


def _shape_to_geometry(shp) -> shapely.geometry.base.BaseGeometry:
    """POLYGON shape → shapely geometry, pyshp의 __geo_interface__를 우회한다.

    pyshp의 __geo_interface__는 각 링을 부호(방향)로 exterior/interior 판정한 뒤
    모든 interior 링을 어떤 exterior 링이 감싸는지 순수 Python으로 탐색한다 —
    이 프로젝트의 SHP는 폴리곤 1개가 최대 3,236 parts(냉천 SGG N330)까지 쪼개져
    있어 이 탐색이 사실상 멈춘 것처럼 느려진다(수십 초~수분). 대신 모든 링을
    LinearRing으로 만들어 shapely.ops.polygonize(GEOS 기반, C 구현)에 넘기면
    동일한 위상(구멍 포함)을 훨씬 빠르게 재구성한다 — 링 방향(시계/반시계)에
    의존하지 않고 실제 기하 관계로 판정하므로 결과도 더 견고하다.
    """
    points = shp.points
    parts = list(shp.parts) + [len(points)]
    rings = []
    for i in range(len(parts) - 1):
        ring_points = points[parts[i] : parts[i + 1]]
        if len(ring_points) < 4:
            continue  # 폐합 링 최소 점 개수(4) 미만인 손상 레코드는 제외
        rings.append(shapely.geometry.LinearRing(ring_points))

    polygons = list(shapely.ops.polygonize(rings))
    if not polygons:
        return shapely.geometry.Polygon()
    geom = polygons[0] if len(polygons) == 1 else shapely.geometry.MultiPolygon(polygons)

    # polygonize() 결과가 자기교차 등으로 위상적으로 invalid할 수 있다(실측 확인:
    # 6개 SHP 전량이 invalid로 나옴 — 원본 데이터 자체가 복잡한 다중 파트 구성).
    # invalid geometry에서는 STRtree의 predicate 질의(contains 등)가 개별
    # .contains() 호출과 다른(틀린) 결과를 낼 수 있음이 실측으로 확인돼
    # make_valid()로 교정한다.
    if not geom.is_valid:
        geom = shapely.make_valid(geom)
    return geom


def _load_one(source: FloodShpSource) -> LoadedFloodRegion:
    if not source.path.exists():
        raise FileNotFoundError(
            f"SHP 파일을 찾을 수 없음: {source.path} "
            f"(region_code={source.region_code}) — data/ 원본이 삭제됐거나 경로가 바뀌었을 수 있음"
        )

    reader = shapefile.Reader(str(source.path))
    zones: list[FloodRiskZone] = []
    skipped_null_seg_codes: list[str] = []
    for shape_record in reader.iterShapeRecords():
        record = shape_record.record.as_dict()
        dbf_sgg_cd = record.get("SGG_CD")
        if dbf_sgg_cd != source.region_code:
            raise ValueError(
                f"{source.path.name}: dbf SGG_CD({dbf_sgg_cd}) != config region_code"
                f"({source.region_code}) — config.py 수동 태깅 오류 가능성"
            )

        seg_code = record.get("SEG_CODE", "")
        if shape_record.shape.shapeType == shapefile.NULL:
            # 원본 SHP 자체에 이 세그먼트의 지오메트리가 비어있음(정부 데이터 결측).
            skipped_null_seg_codes.append(seg_code)
            continue

        geom = _shape_to_geometry(shape_record.shape)
        zones.append(
            FloodRiskZone(
                region_code=source.region_code,
                region_name=source.region_name,
                river_name=source.river_name,
                freq_label=record.get("FLDLV_FREQ", source.freq_label),
                seg_code=seg_code,
                source_file=str(source.path),
                license=LICENSE_LABEL,
                geom=geom,
            )
        )

    reader.close()
    return LoadedFloodRegion(
        source=source, zones=zones, skipped_null_seg_codes=skipped_null_seg_codes
    )


def load_all_regions(
    sources: list[FloodShpSource] | None = None,
) -> list[LoadedFloodRegion]:
    """등록된 SHP 전량(기본: config.FLOOD_SHP_SOURCES)을 로딩한다.

    하천/지역 수를 하드코딩하지 않는다 — sources 리스트 길이만큼 순회할 뿐이므로
    config.py에 SHP 항목을 추가하는 것만으로 확장된다.
    """
    sources = sources if sources is not None else FLOOD_SHP_SOURCES
    return [_load_one(source) for source in sources]


def region_geometry_hash(region: LoadedFloodRegion) -> str:
    """재현성 검증용 — 동일 SHP 재적재 시 동일 값이 나와야 한다."""
    hasher = hashlib.sha256()
    for zone in sorted(region.zones, key=lambda z: z.seg_code):
        hasher.update(zone.seg_code.encode("utf-8"))
        hasher.update(zone.geom.wkb)
    return hasher.hexdigest()
