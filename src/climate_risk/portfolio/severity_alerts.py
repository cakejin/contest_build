"""심각도 기반 재심사 알림 채널 — DEV_LOG.md 2026-08-31 참조.

`portfolio/alerts.py`(EAL 변화율 기반)의 형제 모듈이지 확장이 아니다 — 의도적으로 완전히
분리된 별도 데이터클래스를 쓴다. 이 모듈이 만드는 `SeverityAlertQueueEntry`에는 EAL·LTV·
금리·score 계열 필드가 하나도 없다: 특보/재난문자의 심각도(`lvl_label`: 예비/주의보/경보/
중대경보, `emrg_step_nm`: 안전안내/긴급재난/위급재난)가 `scenario/eal.py`의 금전 계산
경로에 절대 섞여들 수 없다는 걸 스키마 자체로 강제한다(CLAUDE.md 설계원칙2 "특보는 알림
트리거로만, EAL·LTV·금리 계산에 직접 연결 금지"의 구조적 준수 — `policy/redteam_checks.py`
`check_scenario_severity_isolation()`이 이걸 회귀 테스트로 고정).

거제 2026-08 실호우 사건 재현에서 확인된 공백을 메운다: 기존 EAL 임계치 알림은 재계산이
좌표·건물등록정보·고정seed만 보는 순수 정적 모델이라 특보가 아무리 심각해도 반응하지 않는다
(건축물대장 갱신은 수주~수개월 걸리는 행정절차라 "특보 발효 당일 재계산" 시간축과 안 맞음).
이 모듈은 EAL 재계산 결과를 전혀 보지 않고, 특보/재난문자 자체의 심각도만으로 별도 알림을
띄운다 — 그래서 물리 데이터가 안 바뀌어도(EAL 채널은 0% 변화로 조용해도) 뜰 수 있다.

MVP는 `filter_by_region`과 동일하게 지역(region_code) 단위 매칭만 한다 — 동/읍/면 단위
매칭(재난문자 RCPTN_RGN_NM은 이미 그 정밀도를 주지만, `PortfolioRecord`에 구조화된 하위지역
필드가 없음)은 향후 확장 과제로 남긴다.
"""

from __future__ import annotations

import dataclasses
import json
from dataclasses import dataclass
from pathlib import Path

from climate_risk.advisory.schema import AdvisoryEvent
from climate_risk.agents.advisory_agent import is_high_severity_event
from climate_risk.portfolio.schema import PortfolioRecord

_HISTORICAL_WARNING_EVENT_TYPE = "특보"

SEVERITY_SOURCE_HISTORICAL_WARNING = "historical_warning"
SEVERITY_SOURCE_DISASTER_MSG = "disaster_msg"


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


def _severity_source(event: AdvisoryEvent) -> str:
    return (
        SEVERITY_SOURCE_HISTORICAL_WARNING
        if event.event_type == _HISTORICAL_WARNING_EVENT_TYPE
        else SEVERITY_SOURCE_DISASTER_MSG
    )


def build_severity_alert_queue(
    matched_records: list[PortfolioRecord],
    advisory_events: list[AdvisoryEvent],
) -> list[SeverityAlertQueueEntry]:
    """매칭된(지역필터 통과) 담보 전원에게, 이번 조회 구간의 가장 최근 고심각도
    이벤트 하나를 대표값으로 붙인다. `advisory_events`(=`AdvisoryAgentOutput.timeline`)는
    이미 issued_at 오름차순 정렬돼 있으므로(advisory_agent.py) 리스트의 마지막 항목이
    최신 고심각도 이벤트다 — 이벤트별로 레코드마다 중복 생성하지 않는다(55건짜리 구간
    조회 시 담보당 55개씩 쌓이는 걸 방지)."""
    high_severity_events = [e for e in advisory_events if is_high_severity_event(e)]
    if not high_severity_events or not matched_records:
        return []

    representative = high_severity_events[-1]
    severity_source = _severity_source(representative)

    return [
        SeverityAlertQueueEntry(
            collateral_id=record.collateral_id,
            region_code=record.region_code,
            severity_level=representative.severity_level,
            severity_source=severity_source,
            event_description=representative.description,
            issued_at=representative.issued_at,
            source_url=representative.source_url,
            geocode_confidence=record.geocode_confidence,
        )
        for record in matched_records
    ]


def append_to_severity_alert_queue_log(entries: list[SeverityAlertQueueEntry], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        for entry in entries:
            f.write(json.dumps(dataclasses.asdict(entry), ensure_ascii=False) + "\n")
