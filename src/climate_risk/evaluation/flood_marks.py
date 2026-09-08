"""safemap 실측 침수흔적도(A2SM_FLUDMARKS_WI) 골든셋 로더 + 원인 분류 — DEV_LOG.md
2026-08-26 조사 결과를 코드화한 것. `gis/golden_points.py`(사람이 정답을 직접 확인한
소규모 골든셋)와는 성격이 다르다 — 여기엔 우리가 통제하는 '정답'이 없고, 실제로
침수됐던 지점을 우리 화이트박스 판정이 얼마나 잘 잡아내는지를 있는 그대로 재는 용도다
(evaluation/metrics.py::flood_marks_recall_metric 참조).

데이터 출처: data/.../curated/flood_marks_validation/A2SM_FLUDMARKS_WI_target_regions.json
(우리가 등록한 6개 지역만 CQL_FILTER로 추출, 좌표는 원본 EPSG:3857 폴리곤 정점 단순평균을
EPSG:4326으로 역변환한 근사 centroid). 라이선스 미확인 상태라 재배포하지 않는다 — 파일
자체의 license_note 참조.
"""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass
from functools import lru_cache
from pathlib import Path

from climate_risk.config import FLOOD_MARKS_NEARBY_RADII_M, REPO_ROOT

FLOOD_MARKS_VALIDATION_PATH = (
    REPO_ROOT
    / "data"
    / "climate-collateral-underwriting-ai"
    / "curated"
    / "flood_marks_validation"
    / "A2SM_FLUDMARKS_WI_target_regions.json"
)

CAUSE_RIVER = "하천범람"
CAUSE_URBAN_DRAINAGE = "내수배제"
CAUSE_MIXED = "혼합"
CAUSE_COASTAL = "해안범람"
CAUSE_UNCLASSIFIED = "미분류"

# safemap flud_nm2는 통제 어휘(controlled vocabulary)가 아니라 자유서술(오탈자 포함) —
# 키워드 매칭 외에는 신뢰할 수 있는 구조가 없다(DEV_LOG.md 2026-08-26 표본 조사 결과).
_RIVER_KEYWORDS = ("하천", "세천", "월류", "제방")
_URBAN_KEYWORDS = ("내수", "우수관", "우수량", "방재시설", "개거", "배수")
_COASTAL_KEYWORDS = ("조위", "월파", "해안")


def classify_flud_cause(text: str) -> str:
    """flud_nm2 자유서술 텍스트 → 하천범람/내수배제/혼합/해안범람/미분류.

    하천·내수 키워드가 둘 다 걸리면 '혼합'(실제로 힌남노 기록 다수가 이 경우 —
    "하천 수위 상승으로 인한 역류 및 내수배제 불량"). 아무 키워드도 안 걸리면
    (예: "집중호우"·"저지대 침수") 원인을 지어내지 않고 '미분류'로 정직하게 남긴다 —
    "데이터 없음≠위험 없음"과 같은 정신: 근거 없는 분류를 하지 않는다.
    """
    has_river = any(k in text for k in _RIVER_KEYWORDS)
    has_urban = any(k in text for k in _URBAN_KEYWORDS)
    has_coastal = any(k in text for k in _COASTAL_KEYWORDS)

    if has_river and has_urban:
        return CAUSE_MIXED
    if has_river:
        return CAUSE_RIVER
    if has_urban:
        return CAUSE_URBAN_DRAINAGE
    if has_coastal:
        return CAUSE_COASTAL
    return CAUSE_UNCLASSIFIED


@dataclass(frozen=True)
class FloodMarkRecord:
    sgg_cd: str
    region_name: str
    flud_year: str
    cause_text: str
    cause_category: str
    avg_fldwtl_cm: float
    lat: float
    lon: float


@dataclass(frozen=True)
class FloodMarksValidationSet:
    dataset: str
    fetched_at: str
    license_note: str
    records: list[FloodMarkRecord]


def load_flood_marks_validation_set(
    path: Path = FLOOD_MARKS_VALIDATION_PATH,
) -> FloodMarksValidationSet:
    raw = json.loads(path.read_text(encoding="utf-8"))
    cause_texts: list[str] = raw["cause_texts"]
    region_names: dict[str, str] = raw["region_names"]

    records = [
        FloodMarkRecord(
            sgg_cd=r["sgg_cd"],
            region_name=region_names.get(r["sgg_cd"], "미등록 지역"),
            flud_year=r["flud_year"],
            cause_text=cause_texts[r["cause_idx"]],
            cause_category=classify_flud_cause(cause_texts[r["cause_idx"]]),
            avg_fldwtl_cm=r["avg_fldwtl_cm"],
            lat=r["lat"],
            lon=r["lon"],
        )
        for r in raw["records"]
    ]

    return FloodMarksValidationSet(
        dataset=raw["dataset"],
        fetched_at=raw["fetched_at"],
        license_note=raw["license_note"],
        records=records,
    )


# ---- 2026-09-08 추가(DEV_LOG.md 참조) — 담보 좌표 주변 실측 침수흔적 요약(화면 표시용) ----

@dataclass(frozen=True)
class FloodMarksNearby:
    nearest_m: float | None
    nearest_year: str | None
    nearest_cause: str | None
    nearest_depth_cm: float | None
    counts_by_radius_m: dict[str, int]  # {"500": n, "2000": n}
    total_in_dataset: int
    dataset: str
    license_note: str


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6_371_000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


@lru_cache(maxsize=1)
def _cached_validation_set(path_str: str) -> FloodMarksValidationSet:
    return load_flood_marks_validation_set(Path(path_str))


def summarize_flood_marks_near(
    lat: float,
    lon: float,
    path: Path = FLOOD_MARKS_VALIDATION_PATH,
    radii_m: tuple[float, ...] = FLOOD_MARKS_NEARBY_RADII_M,
) -> FloodMarksNearby | None:
    """좌표 주변 실측 침수흔적 건수·최근접 1건. 파일이 없으면 None(데이터 없음 — 위험 없음 아님).
    좌표·원본 레코드는 반환하지 않는다(재배포 금지 데이터, 파일의 license_note 참조)."""
    if not Path(path).exists():
        return None
    vs = _cached_validation_set(str(path))
    dists = [(_haversine_m(lat, lon, r.lat, r.lon), r) for r in vs.records]
    dists.sort(key=lambda t: t[0])
    counts = {str(int(rad)): sum(1 for d, _ in dists if d <= rad) for rad in radii_m}
    nearest = dists[0] if dists else None
    return FloodMarksNearby(
        nearest_m=round(nearest[0], 1) if nearest else None,
        nearest_year=nearest[1].flud_year if nearest else None,
        nearest_cause=nearest[1].cause_category if nearest else None,
        nearest_depth_cm=nearest[1].avg_fldwtl_cm if nearest else None,
        counts_by_radius_m=counts,
        total_in_dataset=len(vs.records),
        dataset=vs.dataset,
        license_note=vs.license_note,
    )


def flood_marks_nearby_to_dict(summary: FloodMarksNearby | None) -> dict | None:
    return asdict(summary) if summary else None
