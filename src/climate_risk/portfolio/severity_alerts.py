"""특보·강수 기반 재심사 알림 채널 — DEV_LOG.md 2026-08-31(신설)·2026-09-03(계속10, 규칙 교체) 참조.

`portfolio/alerts.py`(EAL 변화율 기반)의 형제 모듈이지 확장이 아니다 — 의도적으로 완전히
분리된 별도 데이터클래스를 쓴다. 이 모듈이 만드는 `SeverityAlertQueueEntry`에는 EAL·LTV·
금리·score 계열 필드가 하나도 없다: 특보/재난문자의 심각도와 강수량이 `scenario/eal.py`의
금전 계산 경로에 절대 섞여들 수 없다는 걸 스키마 자체로 강제한다(CLAUDE.md 설계원칙2 —
`policy/redteam_checks.py` `check_scenario_severity_isolation()`이 회귀 테스트로 고정).

2026-09-03 규칙 교체(3단계 검증 결과, DEV_LOG (계속4)~(계속9)):
1. **지역 트리거**: `is_high_severity_event`가 종류 조건을 갖는다 — 호우·태풍·홍수·폭풍해일
   특보가 경보 이상이거나 호우·홍수·태풍 재난문자가 긴급재난 이상(검증 후보 A2). 폭염·강풍
   경보에는 더 이상 켜지지 않는다.
2. **담보별 2단계**: 지역이 켜지면 담보마다 가장 가까운 지상관측소(ASOS·AWS)의 조회 창 내
   최대 일강수를 보고 ≥110mm면 "주의", ≥180mm면 "심각"으로 알림을 낸다(임계값 근거: 기상청
   호우주의보 12h 110mm·호우경보 12h 180mm의 일강수 근사 — config.py). 110mm 미만이면 그
   담보엔 알림을 내지 않는다. **강수 관측을 못 받으면**(조회 창 미지정·API 실패) 매칭 담보
   전원에 "강수미확인" 등급으로 알림을 유지한다 — 데이터 없음을 위험 없음으로 바꾸지 않는다
   (설계원칙1).
3. **요약 1건**: 실무 알림 피로를 줄이기 위해 `SeverityAlertSummary`(매칭 N건 중 주의 a·심각 s)를
   대시보드와 향후 푸시의 최종 알림 단위로 두고, 담보별 목록은 심사역이 조회한다(사용자 결정).

MVP는 `filter_by_region`과 동일하게 지역(region_code) 단위 매칭이다.
"""

from __future__ import annotations

import dataclasses
import json
from dataclasses import dataclass
from pathlib import Path

from climate_risk.advisory.kma_observation import StationRainfall, nearest_station
from climate_risk.advisory.schema import AdvisoryEvent
from climate_risk.agents.advisory_agent import is_high_severity_event
from climate_risk.config import (
    REASSESSMENT_RAIN_THRESHOLD_ADVISORY_MM,
    REASSESSMENT_RAIN_THRESHOLD_BASIS,
    REASSESSMENT_RAIN_THRESHOLD_WARNING_MM,
)
from climate_risk.portfolio.schema import PortfolioRecord

_HISTORICAL_WARNING_EVENT_TYPE = "특보"

SEVERITY_SOURCE_HISTORICAL_WARNING = "historical_warning"
SEVERITY_SOURCE_DISASTER_MSG = "disaster_msg"

ALERT_TIER_WARNING = "심각"
ALERT_TIER_ADVISORY = "주의"
ALERT_TIER_RAIN_UNKNOWN = "강수미확인"

RAIN_STATUS_OK = "OK"
RAIN_STATUS_NOT_QUERIED = "NOT_QUERIED"  # 조회 창 미지정(replay 등)


@dataclass(frozen=True)
class SeverityAlertQueueEntry:
    collateral_id: str
    region_code: str | None
    severity_level: str
    severity_source: str  # "historical_warning" | "disaster_msg"
    event_description: str
    issued_at: str
    source_url: str
    geocode_confidence: str | None
    # 2026-09-03 추가 — 담보별 강수 등급(주의/심각/강수미확인)과 근거. 금전 필드는 여전히 없다.
    alert_tier: str = ALERT_TIER_RAIN_UNKNOWN
    rain_mm: float | None = None
    rain_station: str | None = None
    rain_station_km: float | None = None


@dataclass(frozen=True)
class SeverityAlertSummary:
    """지역별 최종 알림 1건의 내용 — 대시보드 표시·향후 푸시의 단위."""
    matched_count: int
    alert_count: int  # 주의 이상(강수미확인 포함)
    warning_count: int  # 심각
    advisory_count: int  # 주의(심각 제외)
    rain_unknown_count: int
    region_triggered: bool
    rain_status: str  # OK | NOT_QUERIED | 업스트림 상태 문자열
    rain_note: str
    threshold_advisory_mm: float
    threshold_warning_mm: float
    threshold_basis: str
    representative_event: str | None
    representative_issued_at: str | None


def _severity_source(event: AdvisoryEvent) -> str:
    return (
        SEVERITY_SOURCE_HISTORICAL_WARNING
        if event.event_type == _HISTORICAL_WARNING_EVENT_TYPE
        else SEVERITY_SOURCE_DISASTER_MSG
    )


def classify_rain_tier(
    rain_mm: float | None,
    threshold_advisory_mm: float = REASSESSMENT_RAIN_THRESHOLD_ADVISORY_MM,
    threshold_warning_mm: float = REASSESSMENT_RAIN_THRESHOLD_WARNING_MM,
) -> str | None:
    """None(관측 없음) → 강수미확인, ≥경보 임계 → 심각, ≥주의보 임계 → 주의, 그 미만 → None(알림 없음)."""
    if rain_mm is None:
        return ALERT_TIER_RAIN_UNKNOWN
    if rain_mm >= threshold_warning_mm:
        return ALERT_TIER_WARNING
    if rain_mm >= threshold_advisory_mm:
        return ALERT_TIER_ADVISORY
    return None


def build_severity_alert_queue(
    matched_records: list[PortfolioRecord],
    advisory_events: list[AdvisoryEvent],
    station_rainfall: list[StationRainfall] | None = None,
    threshold_advisory_mm: float = REASSESSMENT_RAIN_THRESHOLD_ADVISORY_MM,
    threshold_warning_mm: float = REASSESSMENT_RAIN_THRESHOLD_WARNING_MM,
) -> list[SeverityAlertQueueEntry]:
    """지역 트리거(수문 특보 경보 이상 등)가 있을 때 매칭 담보를 강수 등급으로 걸러 알림 목록을 만든다.

    `station_rainfall`이 None이면 강수 판정을 생략하고 전원 "강수미확인"으로 유지한다(빈 리스트도
    같은 취급 — 관측소가 하나도 없으면 판정 불가). 대표 이벤트는 구간 내 가장 최근 고심각도
    이벤트 하나(issued_at 오름차순 정렬 전제, advisory_agent.py).
    """
    high_severity_events = [e for e in advisory_events if is_high_severity_event(e)]
    if not high_severity_events or not matched_records:
        return []

    representative = high_severity_events[-1]
    severity_source = _severity_source(representative)
    entries: list[SeverityAlertQueueEntry] = []
    for record in matched_records:
        rain_mm = station = km = None
        if station_rainfall and record.lat is not None and record.lon is not None:
            near = nearest_station(record.lat, record.lon, station_rainfall)
            if near is not None:
                s, km = near
                rain_mm, station = s.max_rn_day_mm, f"{s.stn} {s.name}".strip()
        tier = classify_rain_tier(rain_mm, threshold_advisory_mm, threshold_warning_mm)
        if tier is None:
            continue
        entries.append(
            SeverityAlertQueueEntry(
                collateral_id=record.collateral_id,
                region_code=record.region_code,
                severity_level=representative.severity_level,
                severity_source=severity_source,
                event_description=representative.description,
                issued_at=representative.issued_at,
                source_url=representative.source_url,
                geocode_confidence=record.geocode_confidence,
                alert_tier=tier,
                rain_mm=rain_mm,
                rain_station=station,
                rain_station_km=round(km, 1) if km is not None else None,
            )
        )
    return entries


def summarize_severity_alerts(
    matched_records: list[PortfolioRecord],
    advisory_events: list[AdvisoryEvent],
    entries: list[SeverityAlertQueueEntry],
    rain_status: str,
    rain_note: str = "",
    threshold_advisory_mm: float = REASSESSMENT_RAIN_THRESHOLD_ADVISORY_MM,
    threshold_warning_mm: float = REASSESSMENT_RAIN_THRESHOLD_WARNING_MM,
) -> SeverityAlertSummary:
    high = [e for e in advisory_events if is_high_severity_event(e)]
    rep = high[-1] if high else None
    return SeverityAlertSummary(
        matched_count=len(matched_records),
        alert_count=len(entries),
        warning_count=sum(1 for e in entries if e.alert_tier == ALERT_TIER_WARNING),
        advisory_count=sum(1 for e in entries if e.alert_tier == ALERT_TIER_ADVISORY),
        rain_unknown_count=sum(1 for e in entries if e.alert_tier == ALERT_TIER_RAIN_UNKNOWN),
        region_triggered=bool(high),
        rain_status=rain_status,
        rain_note=rain_note,
        threshold_advisory_mm=threshold_advisory_mm,
        threshold_warning_mm=threshold_warning_mm,
        threshold_basis=REASSESSMENT_RAIN_THRESHOLD_BASIS,
        representative_event=rep.description if rep else None,
        representative_issued_at=rep.issued_at if rep else None,
    )


def append_to_severity_alert_queue_log(entries: list[SeverityAlertQueueEntry], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        for entry in entries:
            f.write(json.dumps(dataclasses.asdict(entry), ensure_ascii=False) + "\n")
