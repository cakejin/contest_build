"""특보 에이전트 — HANDOVER.md §4.2 2.2.

`trigger_event`는 규칙기반 boolean이다(설계원칙2 "특보 에이전트의 출력은 '알림'에만
연결되고... 트리거 여부 자체는 규칙"): event_type이 알림성 이벤트({"특보","재난문자"})
집합에 속하는 이벤트가 하나라도 있으면 True. LLM이 이 판정에 관여하지 않는다 —
LLM은 Week3에서 아직 원문 파싱 요약 용도로도 쓰지 않는다(큐레이션 JSON 자체가 이미
구조화돼 있어 파싱이 필요 없다).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from climate_risk.advisory.curated_loader import load_curated_timeline
from climate_risk.advisory.disaster_msg import (
    STATUS_OK as _DM_STATUS_OK,
    STATUS_PAGE_LIMIT_REACHED as _DM_STATUS_PAGE_LIMIT_REACHED,
    STATUS_UNMAPPED_REGION as _DM_STATUS_UNMAPPED_REGION,
    STATUS_UNREGISTERED_IP as _DM_STATUS_UNREGISTERED_IP,
    STATUS_UPSTREAM_ERROR as _DM_STATUS_UPSTREAM_ERROR,
    DisasterMessage,
    query_disaster_messages_for_region,
)
from climate_risk.advisory.kma_historical import (
    STATUS_ACTIVATION_REQUIRED as _HIST_STATUS_ACTIVATION_REQUIRED,
    STATUS_NO_ZONE_MATCH as _HIST_STATUS_NO_ZONE_MATCH,
    STATUS_OK as _HIST_STATUS_OK,
    STATUS_UPSTREAM_ERROR as _HIST_STATUS_UPSTREAM_ERROR,
    HistoricalWarningEvent,
    query_historical_warnings,
)
from climate_risk.advisory.live import (
    STATUS_OK as _LIVE_STATUS_OK,
    STATUS_UNKNOWN_REGION as _LIVE_STATUS_UNKNOWN_REGION,
    STATUS_UPSTREAM_ERROR as _LIVE_STATUS_UPSTREAM_ERROR,
    run_live_query,
)
from climate_risk.advisory.live_log import append_live_query_log
from climate_risk.advisory.replay import replay_timeline
from climate_risk.advisory.schema import AdvisoryEvent
from climate_risk.config import (
    ADVISORY_LIVE_LOG_PATH,
    DAEGU_SUSEONG_2026_TIMELINE_PATH,
    HINNAMNO_TIMELINE_PATH,
)

_KST = timezone(timedelta(hours=9))

# 2026-08-19(계속) — 사용자 피드백: "공식 특보(광역 단위)"와 "뉴스 기반 큐레이션(국지
# 피해 서술)"은 서로 다른 종류의 사실이라 하나가 다른 하나를 대체하지 않는다(힌남노
# 당일 실제 대조 결과 서로 보완적이었음, DEV_LOG.md 참조). mode="historical" 조회 구간이
# 아래 두 큐레이션 사건의 날짜와 겹치면 공식 이력에 자동으로 병합해서 보여준다 —
# 날짜 범위는 여유 하루씩 포함한 대략치(정확한 사건 경계가 아니라 "겹치는지" 판정용).
_CURATED_OVERLAP_WINDOWS: list[tuple[str, Path, datetime, datetime]] = [
    ("47111", HINNAMNO_TIMELINE_PATH, datetime(2022, 9, 4, tzinfo=_KST), datetime(2022, 9, 8, tzinfo=_KST)),
    ("27260", DAEGU_SUSEONG_2026_TIMELINE_PATH, datetime(2026, 7, 16, tzinfo=_KST), datetime(2026, 7, 20, tzinfo=_KST)),
]

_TRIGGER_EVENT_TYPES = {"특보", "재난문자"}

STATUS_OK = "OK"
STATUS_NO_CURATED_DATA_FOR_REGION = "NO_CURATED_DATA_FOR_REGION"
STATUS_LIVE_UPSTREAM_ERROR = "LIVE_UPSTREAM_ERROR"
# 2026-08-19 추가(DEV_LOG.md 참조) — mode="historical"(기상청 API허브 과거 특보 이력)
# 3종 실패 상태. kma_historical.py의 원시 상태를 그대로 번역만 한다(live_/replay_
# 분기와 같은 관례) — 조용히 빈 값으로 뭉개지 않는다(설계원칙1).
STATUS_HISTORICAL_ACTIVATION_REQUIRED = "HISTORICAL_ACTIVATION_REQUIRED"
STATUS_HISTORICAL_NO_ZONE_MATCH = "HISTORICAL_NO_ZONE_MATCH"
STATUS_HISTORICAL_UPSTREAM_ERROR = "HISTORICAL_UPSTREAM_ERROR"
# 2026-08-20 추가(DEV_LOG.md 참조) — mode="disaster_msg"(safetydata.go.kr 재난문자,
# 산불·화재 포함) 4종 실패 상태. disaster_msg.py의 원시 상태를 그대로 번역만 한다
# (다른 mode 분기와 같은 관례) — 조용히 빈 값으로 뭉개지 않는다(설계원칙1).
STATUS_DISASTER_MSG_UNREGISTERED_IP = "DISASTER_MSG_UNREGISTERED_IP"
STATUS_DISASTER_MSG_UNMAPPED_REGION = "DISASTER_MSG_UNMAPPED_REGION"
STATUS_DISASTER_MSG_UPSTREAM_ERROR = "DISASTER_MSG_UPSTREAM_ERROR"
STATUS_DISASTER_MSG_PAGE_LIMIT_REACHED = "DISASTER_MSG_PAGE_LIMIT_REACHED"


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


# 개별 특보 이력 레코드에 딸린 기사 URL이 없다(정형 API 응답 자체가 출처) — live.py의
# _SOURCE_URL 관례와 동일하게 실존·상시 접근 가능한 공식 포털 페이지를 쓴다.
_HISTORICAL_SOURCE_URL = "https://apihub.kma.go.kr/"


def _historical_event_to_advisory_event(event: HistoricalWarningEvent) -> AdvisoryEvent:
    tm_fc_tag = event.tm_fc.strftime("%Y%m%d%H%M")
    description = (
        f"{event.wrn_label} {event.lvl_label} {event.cmd_label}"
        f"(발표 {event.tm_fc.isoformat()}, 발효 {event.tm_ef.isoformat()})"
    )
    return AdvisoryEvent(
        event_id=f"kma-historical-{event.reg_id}-{tm_fc_tag}-{event.wrn_code}{event.lvl_code}{event.cmd_code}",
        issued_at=event.tm_ef.isoformat(),
        time_precision="exact",
        event_type="특보",
        warning_type=f"{event.wrn_label} {event.lvl_label} {event.cmd_label}",
        description=description,
        source_url=_HISTORICAL_SOURCE_URL,
        target_region_text=f"기상청 특보구역 reg_id={event.reg_id}",
    )


# safetydata.go.kr 공식 API 상세 페이지 — 개별 재난문자 레코드에 딸린 기사 URL이 없으므로
# (정형 API 응답 자체가 출처) live.py·kma_historical.py와 같은 관례로 실존·상시 접근
# 가능한 공식 페이지를 쓴다. 사용자가 직접 확인해 알려준 URL(2026-08-20).
_DISASTER_MSG_SOURCE_URL = "https://www.safetydata.go.kr/disaster-data/view?dataSn=228"
_DISASTER_MSG_CONTENT_PREVIEW_LEN = 200  # MSG_CN이 최대 4000자라 인용 문장이 과도하게 길어지지 않게 자름


def _disaster_message_to_advisory_event(msg: DisasterMessage) -> AdvisoryEvent:
    msg_preview = msg.msg_cn[:_DISASTER_MSG_CONTENT_PREVIEW_LEN]
    if len(msg.msg_cn) > _DISASTER_MSG_CONTENT_PREVIEW_LEN:
        msg_preview += "…"
    return AdvisoryEvent(
        event_id=f"disaster-msg-{msg.sn}",
        issued_at=msg.crt_dt.isoformat(),
        time_precision="exact",
        event_type="재난문자",
        warning_type=msg.dst_se_nm,
        description=f"[{msg.dst_se_nm}/{msg.emrg_step_nm}] {msg_preview}",
        source_url=_DISASTER_MSG_SOURCE_URL,
        target_region_text=msg.rcptn_rgn_nm.strip(),
    )


def _disaster_msg_supplemental_events(region_code: str, start: datetime, end: datetime) -> list[AdvisoryEvent]:
    """historical 모드에 재난문자(산불·화재 포함)를 자동으로 병합하는 보강 조회
    (2026-08-20 사용자 결정 — 별도 모드/UI 토글 대신 큐레이션 병합과 같은 방식으로
    자동 병합). 실패해도 historical 모드 자체를 깨뜨리지 않는다 — KMA가 이미 1차
    데이터소스로 성공했으므로, 이 보강 조회의 실패(IP 화이트리스트·업스트림 오류·
    페이지 상한 등)는 "판정 불가"가 아니라 "보강 정보 없음"에 해당한다(설계원칙1이
    보호하는 건 홍수 커버리지 게이트 같은 1차 데이터이지, 여러 소스 중 하나인 보강
    신호가 아니다). region_code가 재난문자 매핑에 없어도(STATUS_UNMAPPED_REGION)
    마찬가지로 조용히 빈 목록만 반환한다."""
    result = query_disaster_messages_for_region(region_code, start, end)
    if result.status != _DM_STATUS_OK:
        return []
    return [_disaster_message_to_advisory_event(m) for m in result.messages]


def _overlapping_curated_events(region_code: str, start: datetime, end: datetime) -> list[AdvisoryEvent]:
    """`start`~`end` 조회 구간이 큐레이션 사건 날짜와 겹치면 그 사건의 전체 타임라인을
    반환한다(겹치면 사건 전체를 보여준다 — 구간 안의 이벤트만 잘라내는 정밀 필터링은
    안 함, 큐레이션 사건은 몇 건 안 돼 전체를 보여줘도 부담이 없다)."""
    matches: list[AdvisoryEvent] = []
    for rc, path, win_start, win_end in _CURATED_OVERLAP_WINDOWS:
        if rc != region_code:
            continue
        if start <= win_end and end >= win_start:
            matches.extend(replay_timeline(load_curated_timeline(path)))
    return matches


def run_advisory_agent(
    region_code: str,
    mode: str = "replay",
    timeline_path: Path = HINNAMNO_TIMELINE_PATH,
    as_of: datetime | None = None,
    # 2026-08-18 추가(DEV_LOG.md 참조) — 라이브 조회 결과를 append-only로 적재해 나중에
    # 날짜 기반 리플레이를 만들 수 있는 원자료를 쌓는다. replay 모드는 이미 정적 큐레이션
    # 데이터라 로그 대상이 아니다.
    live_log_path: Path = ADVISORY_LIVE_LOG_PATH,
    # 2026-08-19 추가(DEV_LOG.md 참조) — mode="historical"에서만 쓰인다. 기상청 API허브
    # 특보자료 API가 [start, end] 구간 조회만 지원해(kma_historical.py) 단일 시점이 아닌
    # 구간을 그대로 받는다 — "그 날짜에 어떤 특보가 있었나"를 임의의 버퍼 규칙으로
    # 추정하지 않고 호출부(웹/CLI)가 명시한 구간 그대로 조회한다.
    historical_start: datetime | None = None,
    historical_end: datetime | None = None,
) -> AdvisoryAgentOutput:
    if mode == "historical":
        if historical_start is None or historical_end is None:
            raise ValueError("mode='historical'에는 historical_start/historical_end가 모두 필요합니다")

        hist_result = query_historical_warnings(region_code, historical_start, historical_end)

        if hist_result.status == _HIST_STATUS_ACTIVATION_REQUIRED:
            return AdvisoryAgentOutput(
                active_warnings=[], trigger_event=False, mode=mode, timeline=[],
                region_code=region_code, status=STATUS_HISTORICAL_ACTIVATION_REQUIRED,
                source_id="advisory:historical:activation_required",
            )
        if hist_result.status == _HIST_STATUS_NO_ZONE_MATCH:
            return AdvisoryAgentOutput(
                active_warnings=[], trigger_event=False, mode=mode, timeline=[],
                region_code=region_code, status=STATUS_HISTORICAL_NO_ZONE_MATCH,
                source_id="advisory:historical:no_zone_match",
            )
        if hist_result.status == _HIST_STATUS_UPSTREAM_ERROR:
            return AdvisoryAgentOutput(
                active_warnings=[], trigger_event=False, mode=mode, timeline=[],
                region_code=region_code, status=STATUS_HISTORICAL_UPSTREAM_ERROR,
                source_id="advisory:historical:upstream_error",
            )

        assert hist_result.status == _HIST_STATUS_OK
        events = [_historical_event_to_advisory_event(e) for e in hist_result.events]
        # 공식 특보 이력 + (겹치면) 뉴스 기반 큐레이션 서술 + 재난문자(산불·화재 포함)를
        # 함께 보여준다 — 서로 다른 종류의 사실이라 하나가 다른 하나를 대체하지 않는다
        # (위 docstring 참조). 재난문자 보강은 실패해도 이 결과 자체를 깨뜨리지 않는다
        # (_disaster_msg_supplemental_events 참조).
        events += _overlapping_curated_events(region_code, historical_start, historical_end)
        events += _disaster_msg_supplemental_events(region_code, historical_start, historical_end)
        events.sort(key=lambda e: e.issued_at)
        trigger_event = any(event.event_type in _TRIGGER_EVENT_TYPES for event in events)
        return AdvisoryAgentOutput(
            active_warnings=[_to_active_warning(e) for e in events],
            trigger_event=trigger_event,
            mode=mode,
            timeline=events,
            region_code=region_code,
            status=STATUS_OK,
            source_id=f"advisory:historical:kma:reg_id={hist_result.reg_id}",
        )

    if mode == "disaster_msg":
        if historical_start is None or historical_end is None:
            raise ValueError("mode='disaster_msg'에는 historical_start/historical_end가 모두 필요합니다")

        dm_result = query_disaster_messages_for_region(region_code, historical_start, historical_end)

        if dm_result.status == _DM_STATUS_UNREGISTERED_IP:
            return AdvisoryAgentOutput(
                active_warnings=[], trigger_event=False, mode=mode, timeline=[],
                region_code=region_code, status=STATUS_DISASTER_MSG_UNREGISTERED_IP,
                source_id="advisory:disaster_msg:unregistered_ip",
            )
        if dm_result.status == _DM_STATUS_UNMAPPED_REGION:
            return AdvisoryAgentOutput(
                active_warnings=[], trigger_event=False, mode=mode, timeline=[],
                region_code=region_code, status=STATUS_DISASTER_MSG_UNMAPPED_REGION,
                source_id="advisory:disaster_msg:unmapped_region",
            )
        if dm_result.status == _DM_STATUS_PAGE_LIMIT_REACHED:
            return AdvisoryAgentOutput(
                active_warnings=[], trigger_event=False, mode=mode, timeline=[],
                region_code=region_code, status=STATUS_DISASTER_MSG_PAGE_LIMIT_REACHED,
                source_id="advisory:disaster_msg:page_limit_reached",
            )
        if dm_result.status == _DM_STATUS_UPSTREAM_ERROR:
            return AdvisoryAgentOutput(
                active_warnings=[], trigger_event=False, mode=mode, timeline=[],
                region_code=region_code, status=STATUS_DISASTER_MSG_UPSTREAM_ERROR,
                source_id="advisory:disaster_msg:upstream_error",
            )

        assert dm_result.status == _DM_STATUS_OK
        events = [_disaster_message_to_advisory_event(m) for m in dm_result.messages]
        events.sort(key=lambda e: e.issued_at)
        trigger_event = any(event.event_type in _TRIGGER_EVENT_TYPES for event in events)
        return AdvisoryAgentOutput(
            active_warnings=[_to_active_warning(e) for e in events],
            trigger_event=trigger_event,
            mode=mode,
            timeline=events,
            region_code=region_code,
            status=STATUS_OK,
            source_id="advisory:disaster_msg:safetydata",
        )

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
        raise ValueError(f"알 수 없는 mode={mode!r} — 'replay'·'live'·'historical'·'disaster_msg'만 지원합니다")

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
