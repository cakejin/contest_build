"""라이브 기상청 특보 API 모드 — `WthrWrnInfoService/getWthrWrnList`(data.go.kr).

2026-08-12 실호출로 스펙 확정(DEV_LOG.md 참조): 엔드포인트·파라미터(`serviceKey, pageNo,
numOfRows, dataType, stnId`)·응답 스키마 전부 이 저장소에서 직접 검증했다 — HANDOVER.md
작성 시점(contest_research)에는 "접근 가능·검증 완료"라는 결론만 있었고 정확한 요청/응답
형태는 문서화돼 있지 않았다.

**stnId는 SGG(시군구) region_code와 다르다** — 기상청 특보구역/관서 코드다. 대구 5개구(신천
유역)는 API 자체가 구 단위로 세분화하지 못해 전부 stnId=143(대구)으로 묶인다(실측 확인:
전국 피드(108)와 다른 목록을 반환함을 확인). `config.REGION_CODE_TO_KMA_STN_ID`가 매핑
테이블이며, 실경보로 검증되지 않은 지역은 `stn_id_verified=False`로 정직하게 표기한다
(설계원칙1 "데이터 없음≠위험 없음"과 같은 정신 — 매핑 정확성도 검증 없이 확신하지 않는다).

**과거 조회는 구조적으로 불가능하다** — 6일 초과 과거 조회는 `resultCode 99`로 실패함이
`contest_research`에서 실측 확인됐다(힌남노 2022 조회 시도). 이 모듈은 애초에 "지금 시점"
조회 전용이며 `as_of` 같은 과거 시점 파라미터를 받지 않는다 — 힌남노 스타일의 과거 재현은
`advisory/replay.py`(큐레이션 JSON) 몫이다.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from climate_risk.advisory.schema import AdvisoryEvent
from climate_risk.config import DATA_GO_KR_API_KEY, KMA_WTHR_WRN_BASE_URL, REGION_CODE_TO_KMA_STN_ID

STATUS_OK = "OK"
STATUS_UNKNOWN_REGION = "UNKNOWN_REGION_MAPPING"
STATUS_UPSTREAM_ERROR = "UPSTREAM_ERROR"

_KST = timezone(timedelta(hours=9))
# 개별 특보 아이템에 대한 기사 URL이 없으므로(공식 API 실시간 조회 결과 자체가 출처),
# 기상청 특보 종합 조회 페이지를 source_url로 쓴다 — 실존·상시 접근 가능한 공식 페이지.
_SOURCE_URL = "https://www.weather.go.kr/w/special-report/overall.do"
# title 형식 실측 예: "[특보] 제08-94호 : 2026.08.12.11:00 / 풍랑주의보 해제 (*)"
_TITLE_RE = re.compile(r"^\[(?P<category>[^\]]+)\]\s*제[\d-]+호\s*:\s*[\d.:]+\s*/\s*(?P<detail>.+?)\s*(?:\(\*\))?$")


@dataclass(frozen=True)
class LiveQueryResult:
    status: str
    events: list[AdvisoryEvent]
    stn_id: str | None
    stn_id_verified: bool
    note: str


def _fetch_kma_json(stn_id: str) -> dict:
    """실제 HTTP 호출 지점 — 단일 seam으로 분리해 테스트가
    `monkeypatch.setattr(live, "_fetch_kma_json", ...)`로 네트워크 없이 검증할 수 있게 한다
    (memo_agent.call_claude_structured·geocoding.geocode_road_address와 동일 패턴)."""
    url = (
        f"{KMA_WTHR_WRN_BASE_URL}?serviceKey={DATA_GO_KR_API_KEY}"
        f"&pageNo=1&numOfRows=50&dataType=JSON&stnId={stn_id}"
    )
    with urllib.request.urlopen(url, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _tm_fc_to_iso(tm_fc: int) -> str:
    dt = datetime.strptime(str(tm_fc), "%Y%m%d%H%M").replace(tzinfo=_KST)
    return dt.isoformat()


def _severity_from_detail(detail: str) -> str | None:
    """실시간 특보 제목의 detail("호우경보 발표", "폭염주의보 변경·열대야주의보 발표" 등)에서
    등급을 읽는다 — "경보"가 하나라도 있으면 경보, 아니면 주의보, 둘 다 없으면 None
    (2026-09-03(계속10): 실시간 모드에서도 재심사 알림 지역 트리거가 동작하게 하기 위함)."""
    if "경보" in detail:
        return "경보"
    if "주의보" in detail:
        return "주의보"
    return None


def _item_to_event(item: dict) -> AdvisoryEvent:
    title = item["title"]
    match = _TITLE_RE.match(title)
    detail = match.group("detail") if match else title
    return AdvisoryEvent(
        event_id=f"kma-live-{item['stnId']}-{item['tmSeq']}",
        issued_at=_tm_fc_to_iso(item["tmFc"]),
        time_precision="exact",
        event_type="특보",
        warning_type=detail,
        description=title,
        source_url=_SOURCE_URL,
        target_region_text=f"기상청 특보구역 stnId={item['stnId']}",
        severity_level=_severity_from_detail(detail),
    )


def run_live_query(region_code: str) -> LiveQueryResult:
    """region_code(SGG)에 매핑된 기상청 특보구역(stnId)의 "지금 시점" 발효 특보를 조회한다.

    매핑이 없는 region_code는 조용히 "특보 없음"으로 처리하지 않고 `STATUS_UNKNOWN_REGION`을
    명시 반환한다. API 호출 자체가 실패해도 마찬가지로 `STATUS_UPSTREAM_ERROR`를 반환한다 —
    두 경우 모두 "판정 불가"이지 "안전 확인됨"이 아니다.
    """
    mapping = REGION_CODE_TO_KMA_STN_ID.get(region_code)
    if mapping is None:
        return LiveQueryResult(
            status=STATUS_UNKNOWN_REGION,
            events=[],
            stn_id=None,
            stn_id_verified=False,
            note=f"region_code={region_code!r}에 대한 기상청 특보구역(stnId) 매핑이 없습니다.",
        )
    stn_id, verified = mapping

    try:
        data = _fetch_kma_json(stn_id)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        return LiveQueryResult(
            status=STATUS_UPSTREAM_ERROR,
            events=[],
            stn_id=stn_id,
            stn_id_verified=verified,
            note=f"기상청 API 호출 실패: {exc}",
        )

    header = data.get("response", {}).get("header", {})
    result_code = header.get("resultCode")

    if result_code == "03":  # NO_DATA — 이 구역에 발효 중인 특보가 없는 정상 상태.
        return LiveQueryResult(
            status=STATUS_OK,
            events=[],
            stn_id=stn_id,
            stn_id_verified=verified,
            note="현재 이 구역에 발효 중인 특보가 없습니다(정상 상태).",
        )
    if result_code != "00":
        return LiveQueryResult(
            status=STATUS_UPSTREAM_ERROR,
            events=[],
            stn_id=stn_id,
            stn_id_verified=verified,
            note=f"기상청 API가 비정상 응답을 반환했습니다: resultCode={result_code!r} {header.get('resultMsg')!r}",
        )

    items = data["response"]["body"]["items"]["item"]
    events = [_item_to_event(item) for item in items]
    return LiveQueryResult(
        status=STATUS_OK,
        events=events,
        stn_id=stn_id,
        stn_id_verified=verified,
        note="" if verified else "이 지역의 stnId 매핑은 실경보로 검증되지 않았습니다(best-effort).",
    )
