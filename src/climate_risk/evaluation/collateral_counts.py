"""담보별 재심사 알림 건수 지표 — DEV_LOG.md 2026-09-03(계속8) 사전 등록 규칙의 구현(평가 전용).

"사건 심각도 = 지역 내 알림 담보 수"로 표기하기 위해, 지역 트리거(A2)가 켜진 사건에서
담보마다 **가장 가까운 지상관측소의 사건 창 내 최대 일강수**가 임계값(110mm 주의 /
180mm 심각, 기상청 호우주의보·경보 12시간 기준의 일강수 근사) 이상인지로 알림 대상을 거른다.

관측소 목록·일강수는 `sfc_aws_day.php`(stn=0, 위경도 포함)를 창의 날짜마다 조회해 지점별
최대값으로 만든 캐시(`alert_validation/station_rainfall/{event_id}.json`)를 읽는다 — 라이브
호출은 scripts/fetch_alert_validation_cache.py --station-rainfall 한 곳뿐.

프로덕션과 같은 매칭 규칙(`PortfolioRecord.region_code == 사건 region_code`, portfolio/filter.py)을
쓴다. 침수 tier는 gis/query.py 화이트박스 판정을 그대로 재호출한다(새 판정 로직 없음).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from climate_risk.advisory.kma_observation import StationRainfall, nearest_station  # noqa: F401 (재수출)
from climate_risk.config import ALERT_VALIDATION_DIR, PORTFOLIO_DATA_PATH
from climate_risk.evaluation.alert_validation import (
    AlertValidationDataError,
    AlertValidationSet,
    CachedTimeline,
    LabeledAlertEvent,
    load_alert_validation_set,
    load_cached_timeline,
)
from climate_risk.evaluation.trigger_candidates import c2_hydro_high_severity
from climate_risk.gis.query import TIER_INNER, TIER_NEAR, query_flood_risk
from climate_risk.portfolio.loader import load_portfolio
from climate_risk.portfolio.schema import PortfolioRecord

STATION_RAINFALL_DIR = ALERT_VALIDATION_DIR / "station_rainfall"

# 사전 등록 임계값(DEV_LOG (계속8)) — 기상청 호우주의보(12h 110mm)·호우경보(12h 180mm)의 일강수 근사.
THRESHOLD_ADVISORY_MM = 110.0
THRESHOLD_WARNING_MM = 180.0
THRESHOLDS_MM: tuple[float, ...] = (THRESHOLD_ADVISORY_MM, THRESHOLD_WARNING_MM)
STRUCTURED_PREFIXES = ("kma-historical-", "disaster-msg-")


@dataclass(frozen=True)
class StationRainfallCache:
    event_id: str
    region_code: str
    fetched_at: str
    days: list[str]  # 조회한 날짜(YYYY-MM-DD)
    day_status: dict  # {day: status}
    stations: list[StationRainfall]


def station_rainfall_cache_path(event_id: str, directory: Path = STATION_RAINFALL_DIR) -> Path:
    return directory / f"{event_id}.json"


def load_station_rainfall(event_id: str, directory: Path = STATION_RAINFALL_DIR) -> StationRainfallCache:
    path = station_rainfall_cache_path(event_id, directory)
    if not path.exists():
        raise AlertValidationDataError(
            f"관측소 일강수 캐시가 없습니다: {path} — scripts/fetch_alert_validation_cache.py --station-rainfall 로 먼저 생성하세요."
        )
    raw = json.loads(path.read_text(encoding="utf-8"))
    return StationRainfallCache(
        event_id=raw["event_id"], region_code=raw["region_code"], fetched_at=raw.get("fetched_at", ""),
        days=raw.get("days", []), day_status=raw.get("day_status", {}),
        stations=[StationRainfall(**s) for s in raw.get("stations", [])],
    )


def station_rainfall_cache_to_dict(cache: StationRainfallCache) -> dict:
    return {
        "event_id": cache.event_id, "region_code": cache.region_code, "fetched_at": cache.fetched_at,
        "days": cache.days, "day_status": cache.day_status,
        "stations": [s.__dict__ for s in cache.stations],
    }


@dataclass(frozen=True)
class CollateralAssessment:
    collateral_id: str
    tier: str | None  # 내부/근접/원거리 또는 None(커버리지 밖)
    station_stn: str | None
    station_name: str | None
    station_km: float | None
    rain_mm: float | None


def assess_collaterals(records: list[PortfolioRecord], stations: list[StationRainfall]) -> list[CollateralAssessment]:
    out: list[CollateralAssessment] = []
    for r in records:
        if r.lat is None or r.lon is None:
            continue
        fr = query_flood_risk(r.lat, r.lon)
        tier = fr.tier if fr.coverage == "IN_SCOPE" else None
        near = nearest_station(r.lat, r.lon, stations)
        if near is None:
            out.append(CollateralAssessment(r.collateral_id, tier, None, None, None, None))
        else:
            s, km = near
            out.append(CollateralAssessment(r.collateral_id, tier, s.stn, s.name, km, s.max_rn_day_mm))
    return out


def count_alerts(assessments: list[CollateralAssessment], threshold_mm: float, require_tier: bool) -> int:
    n = 0
    for a in assessments:
        rain_ok = a.rain_mm is not None and a.rain_mm >= threshold_mm
        tier_ok = (a.tier in (TIER_INNER, TIER_NEAR)) if require_tier else True
        n += int(rain_ok and tier_ok)
    return n


def _structured_only(tl: CachedTimeline) -> list:
    return [e for e in tl.events if e.event_id.startswith(STRUCTURED_PREFIXES)]


def _dist(values: list[float]) -> dict:
    if not values:
        return {"min": None, "median": None, "max": None}
    v = sorted(values)
    return {"min": v[0], "median": v[len(v) // 2], "max": v[-1]}


def collateral_alert_count_metric(
    validation_set: AlertValidationSet | None = None,
    portfolio: list[PortfolioRecord] | None = None,
    thresholds_mm: tuple[float, ...] = THRESHOLDS_MM,
    region_trigger=c2_hydro_high_severity,
) -> dict:
    """라벨 사건별 "매칭 담보 중 알림 담보 수"(DEV_LOG 2026-09-03(계속8)).

    - 지역 트리거(기본 A2=C2)가 꺼진 사건은 알림 0(담보 조건과 무관).
    - 임계값마다 (a) 강수만 (b) 강수 ∧ tier 내부·근접 두 변형을 센다.
    - 수치는 있는 그대로 보고; 테스트는 불변식만 확인한다(같은 관례).
    """
    if validation_set is None:
        validation_set = load_alert_validation_set()
    if portfolio is None:
        portfolio = load_portfolio(PORTFOLIO_DATA_PATH)

    events_out: dict[str, dict] = {}
    missing: list[str] = []
    for ev in validation_set.events:
        tl = load_cached_timeline(ev.event_id)
        triggered = bool(region_trigger(_structured_only(tl)))
        matched = [p for p in portfolio if p.region_code == ev.region_code]
        try:
            cache = load_station_rainfall(ev.event_id)
        except AlertValidationDataError:
            missing.append(ev.event_id)
            events_out[ev.event_id] = {
                "damage_confirmed": ev.damage_confirmed, "region_code": ev.region_code,
                "matched": len(matched), "region_triggered": triggered, "station_rainfall": "MISSING",
            }
            continue
        assessments = assess_collaterals(matched, cache.stations)
        tiers: dict[str, int] = {}
        for a in assessments:
            key = a.tier or "OUT_OF_SCOPE"
            tiers[key] = tiers.get(key, 0) + 1
        rains = [a.rain_mm for a in assessments if a.rain_mm is not None]
        kms = [a.station_km for a in assessments if a.station_km is not None]
        counts = {}
        for t in thresholds_mm:
            key = f"{t:.0f}mm"
            counts[key] = {
                "rain_only": count_alerts(assessments, t, require_tier=False) if triggered else 0,
                "rain_and_tier": count_alerts(assessments, t, require_tier=True) if triggered else 0,
                "rain_only_ignoring_trigger": count_alerts(assessments, t, require_tier=False),
            }
        events_out[ev.event_id] = {
            "damage_confirmed": ev.damage_confirmed,
            "region_code": ev.region_code,
            "window": [ev.window_start.isoformat(), ev.window_end.isoformat()],
            "matched": len(matched),
            "assessed": len(assessments),
            "region_triggered": triggered,
            "tiers": tiers,
            "rain_mm": _dist(rains),
            "station_km": _dist(kms),
            "stations_used": sorted({f"{a.station_stn} {a.station_name}" for a in assessments if a.station_stn}),
            "day_status": cache.day_status,
            "alerts": counts,
        }

    return {
        "rule": {
            "region_trigger": getattr(region_trigger, "__name__", str(region_trigger)),
            "collateral_rule": "최근접 지상관측소(ASOS·AWS)의 창 내 최대 일강수 ≥ 임계값 (변형: ∧ 침수 tier 내부·근접)",
            "thresholds_mm": list(thresholds_mm),
            "threshold_basis": "기상청 호우주의보 12h 110mm / 호우경보 12h 180mm의 일강수 근사(DEV_LOG 2026-09-03(계속8))",
            "match_rule": "PortfolioRecord.region_code == 사건 region_code (portfolio/filter.py와 동일)",
        },
        "events": events_out,
        "station_rainfall_missing": missing,
    }
