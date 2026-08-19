"""홍수위험지도 SHP 로딩 — pyshp로 읽어 shapely geometry로 변환.

HANDOVER.md §4.3: "로딩 스크립트는 idempotent(기존 테이블 truncate 후 재적재) —
동일 SHP 재실행 시 동일 레코드 수·geometry 해시가 나오는지 CI에서 검증"을
로컬(비-PostGIS) 경로에서 구현한다. 여기서는 매 호출이 파일을 새로 읽어
새 객체를 만들 뿐이므로("truncate" 개념이 없음) idempotency는 자동으로
성립하고, 테스트는 이를 실측으로 확인한다(tests/test_loader_idempotent.py).
"""

from __future__ import annotations

import hashlib
import pickle
from dataclasses import dataclass, field

import shapefile
import shapely
import shapely.geometry
import shapely.ops

from climate_risk.config import FLOOD_SHP_SOURCES, GIS_LOAD_CACHE_PATH, FloodShpSource, LICENSE_LABEL

# 캐시 파일 포맷이 바뀌면(예: LoadedFloodRegion 필드 추가) 올려서 옛 피클을 자동
# 무효화한다 — 잘못된 스키마의 캐시를 그대로 읽어 조용히 틀린 값을 쓰는 걸 방지.
_CACHE_FORMAT_VERSION = 1


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
    # gis/coverage.py의 region_coverage_bbox()가 지연 계산 후 채우는 캐시 슬롯 —
    # 이 region 객체 자체에 귀속시켜 id() 재사용 등으로 인한 오염 위험 없이 캐싱한다.
    coverage_bbox_cache: shapely.geometry.base.BaseGeometry | None = field(
        default=None, repr=False, compare=False
    )


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


def _source_manifest_entry(source: FloodShpSource) -> tuple[str, int, int]:
    """SHP + 동반 dbf 파일의 (경로, mtime_ns, size) — 캐시 무효화 판단용.

    geometry는 .shp, 속성(SGG_CD 등)은 .dbf에 있어 둘 다 봐야 내용 변경을
    놓치지 않는다. .shx는 인덱스일 뿐이라 제외.
    """
    shp_path = source.path
    dbf_path = shp_path.with_suffix(".dbf")
    entries = []
    for p in (shp_path, dbf_path):
        stat = p.stat()
        entries.append((str(p), stat.st_mtime_ns, stat.st_size))
    return entries


def load_all_regions_cached(
    sources: list[FloodShpSource] | None = None,
    cache_path=GIS_LOAD_CACHE_PATH,
) -> list[LoadedFloodRegion]:
    """`load_all_regions()`과 동일한 결과를 반환하되, 디스크 피클 캐시를 우선 쓴다.

    SHP 콜드 로딩(polygonize+make_valid, 냉천/신천/거제 7개 합쳐 수 분)이 프로세스가
    새로 뜰 때마다(pytest 재실행, 서버 재시작) 반복되던 걸 없애기 위함
    (2026-08-19, DEV_LOG.md 참조). SHP/dbf 파일의 mtime+size로 원본 데이터 변경을
    감지해 자동 무효화한다 — 원본이 안 바뀌었으면 캐시를 신뢰하고, 바뀌었으면(또는
    캐시 포맷 버전이 바뀌었으면) 조용히 다시 콜드 로딩해 캐시를 갱신한다.

    `tests/test_loader_idempotent.py`는 "진짜 재파싱이 매번 동일 결과를 내는지"를
    검증하는 테스트라 이 캐시를 쓰지 않고 `load_all_regions()`를 직접 호출한다 —
    캐시를 쓰면 그 테스트의 검증 의미가 없어짐.
    """
    sources = sources if sources is not None else FLOOD_SHP_SOURCES
    manifest = [entry for source in sources for entry in _source_manifest_entry(source)]

    if cache_path.exists():
        try:
            with cache_path.open("rb") as f:
                cached = pickle.load(f)
        except (pickle.UnpicklingError, EOFError, AttributeError, ImportError):
            cached = None
        if (
            cached is not None
            and cached.get("version") == _CACHE_FORMAT_VERSION
            and cached.get("manifest") == manifest
        ):
            return cached["regions"]

    regions = load_all_regions(sources)

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = cache_path.with_suffix(cache_path.suffix + ".tmp")
    with tmp_path.open("wb") as f:
        pickle.dump(
            {"version": _CACHE_FORMAT_VERSION, "manifest": manifest, "regions": regions},
            f,
            protocol=pickle.HIGHEST_PROTOCOL,
        )
    tmp_path.replace(cache_path)  # 원자적 교체 — 쓰다 만 캐시 파일이 안 남게

    return regions


def region_geometry_hash(region: LoadedFloodRegion) -> str:
    """재현성 검증용 — 동일 SHP 재적재 시 동일 값이 나와야 한다."""
    hasher = hashlib.sha256()
    for zone in sorted(region.zones, key=lambda z: z.seg_code):
        hasher.update(zone.seg_code.encode("utf-8"))
        hasher.update(zone.geom.wkb)
    return hasher.hexdigest()
