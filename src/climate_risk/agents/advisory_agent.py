"""특보 에이전트 — HANDOVER.md §4.2 2.2.

`trigger_event`는 규칙기반 boolean이다(설계원칙2 "특보 에이전트의 출력은 '알림'에만
연결되고... 트리거 여부 자체는 규칙"): event_type이 알림성 이벤트({"특보","재난문자"})
집합에 속하는 이벤트가 하나라도 있으면 True. LLM이 이 판정에 관여하지 않는다 —
LLM은 Week3에서 아직 원문 파싱 요약 용도로도 쓰지 않는다(큐레이션 JSON 자체가 이미
구조화돼 있어 파싱이 필요 없다).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from climate_risk.advisory.curated_loader import load_curated_timeline
from climate_risk.advisory.live import (
    STATUS_OK as _LIVE_STATUS_OK,
    STATUS_UNKNOWN_REGION as _LIVE_STATUS_UNKNOWN_REGION,
    STATUS_UPSTREAM_ERROR as _LIVE_STATUS_UPSTREAM_ERROR,
    run_live_query,
)
from climate_risk.advisory.live_log import append_live_query_log
from climate_risk.advisory.replay import replay_timeline
from climate_risk.advisory.schema import AdvisoryEvent
from climate_risk.config import ADVISORY_LIVE_LOG_PATH, HINNAMNO_TIMELINE_PATH

_TRIGGER_EVENT_TYPES = {"특보", "재난문자"}

STATUS_OK = "OK"
STATUS_NO_CURATED_DATA_FOR_REGION = "NO_CURATED_DATA_FOR_REGION"
STATUS_LIVE_UPSTREAM_ERROR = "LIVE_UPSTREAM_ERROR"


@dataclass(frozen=True)
class AdvisoryAgentOutput:
    active_warnings: list[dict]  # HANDOVER §4.2 2.2 출력 형태: {type, issued_at, source_url}
    trigger_event: bool
    mode: str
    timeline: list[AdvisoryEvent]
    region_code: str
    status: str
    source_id: str


def _to_active_warning(event: AdvisoryEvent) -> dict:
    return {
        "type": event.warning_type or event.event_type,
        "issued_at": event.issued_at,
        "source_url": event.source_url,
    }


def run_advisory_agent(
    region_code: str,
    mode: str = "replay",
    timeline_path: Path = HINNAMNO_TIMELINE_PATH,
    as_of: datetime | None = None,
    # 2026-08-18 추가(DEV_LOG.md 참조) — 라이브 조회 결과를 append-only로 적재해 나중에
    # 날짜 기반 리플레이를 만들 수 있는 원자료를 쌓는다. replay 모드는 이미 정적 큐레이션
    # 데이터라 로그 대상이 아니다.
    live_log_path: Path = ADVISORY_LIVE_LOG_PATH,
) -> AdvisoryAgentOutput:
    if mode == "live":
        live_result = run_live_query(region_code)

        if live_result.status == _LIVE_STATUS_UNKNOWN_REGION:
            append_live_query_log(region_code, live_result, trigger_event=False, log_path=live_log_path)
            return AdvisoryAgentOutput(
                active_warnings=[],
                trigger_event=False,
                mode=mode,
                timeline=[],
                region_code=region_code,
                status=STATUS_NO_CURATED_DATA_FOR_REGION,
                source_id="advisory:live:unmapped_region",
            )
        if live_result.status == _LIVE_STATUS_UPSTREAM_ERROR:
            append_live_query_log(region_code, live_result, trigger_event=False, log_path=live_log_path)
            return AdvisoryAgentOutput(
                active_warnings=[],
                trigger_event=False,
                mode=mode,
                timeline=[],
                region_code=region_code,
                status=STATUS_LIVE_UPSTREAM_ERROR,
                source_id="advisory:live:upstream_error",
            )

        assert live_result.status == _LIVE_STATUS_OK
        trigger_event = any(event.event_type in _TRIGGER_EVENT_TYPES for event in live_result.events)
        append_live_query_log(region_code, live_result, trigger_event=trigger_event, log_path=live_log_path)
        return AdvisoryAgentOutput(
            active_warnings=[_to_active_warning(e) for e in live_result.events],
            trigger_event=trigger_event,
            mode=mode,
            timeline=live_result.events,
            region_code=region_code,
            status=STATUS_OK,
            source_id=f"advisory:live:kma:stnId={live_result.stn_id}",
        )

    if mode != "replay":
        raise ValueError(f"알 수 없는 mode={mode!r} — 'replay' 또는 'live'만 지원합니다")

    curated = load_curated_timeline(timeline_path)

    if curated.region_code != region_code:
        return AdvisoryAgentOutput(
            active_warnings=[],
            trigger_event=False,
            mode=mode,
            timeline=[],
            region_code=region_code,
            status=STATUS_NO_CURATED_DATA_FOR_REGION,
            source_id="advisory:no_curated_data",
        )

    events = replay_timeline(curated, as_of=as_of)
    trigger_event = any(event.event_type in _TRIGGER_EVENT_TYPES for event in events)

    return AdvisoryAgentOutput(
        active_warnings=[_to_active_warning(e) for e in events],
        trigger_event=trigger_event,
        mode=mode,
        timeline=events,
        region_code=region_code,
        status=STATUS_OK,
        source_id=f"advisory:curated:{timeline_path.name}",
    )
