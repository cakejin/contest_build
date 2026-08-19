"""기상청 API허브(apihub.kma.go.kr) 특보 이력 조회 — HANDOVER §④ 실시간 특보 연동의
"날짜 기반 과거 조회" 확장(DEV_LOG.md 2026-08-18/19 사용자와의 조사·활용신청 실측 참조).

`advisory/live.py`가 쓰는 data.go.kr의 `WthrWrnInfoService`는 "지금 시점" 조회 전용이라
과거 6일 초과 조회가 구조적으로 불가능하다(resultCode 99). 이 모듈이 쓰는
`apihub.kma.go.kr`은 **완전히 다른 포털·인증키**(`KMA_API_HUB_KEY`, `DATA_GO_KR_API_KEY`
아님)이고, 2004-06-30부터 현재까지 정형 특보 발효/해제 이력을 조회할 수 있다.

**API마다 개별 활용신청이 필요하다** — 계정 키(`KMA_API_HUB_KEY`)가 있어도 "특보자료
API"(`wrn_met_data.php`)·"특보구역 API"(`wrn_reg.php`) 각각 별도 승인을 받아야 호출된다
(실측 확인: 승인 전엔 두 API 모두 HTTP 403 `"활용신청이 필요한 API 입니다"`를 반환하며,
같은 계정의 다른 API(`wrn_inf_rpt.php`, 자유서술형 브리핑)는 승인 없이도 되는 것과 대비됨).

**대구 5개구(남구·중구·수성구·동구·북구)는 이 API로도 개별 구분이 안 된다** — 기상청
특보구역 자체가 "대구광역시" 하나로 묶여있다. 2026-05-31 13:30에 특보구역이 개편되어
달성군·군위군은 분리됐지만(REG_ID `L1140000`→`L1140100`, REG_NAME "대구광역시"→
"대구중부"로 개편) 도심 5개구는 개편 후에도 여전히 통합돼있다 — `advisory/live.py`의
`REGION_CODE_TO_KMA_STN_ID`(대구 5개구가 전부 stnId=143)와 같은 한계가 다른 소스로도
재확인된 것뿐이지 새로운 제약은 아니다.

**특보구역 코드가 시간에 따라 바뀐다** — 위 개편처럼 REG_ID/REG_NAME 자체가 특정 시점
이후 달라질 수 있어, 이 모듈은 REG_ID를 하드코딩하지 않고 조회 시점(as_of)에 유효했던
구역을 매번 `resolve_region_zone()`으로 동적으로 찾는다(2026-07 대구 수성구 집중호우
실이벤트로 신·구 코드 전환이 실측 교차검증됨).
"""

from __future__ import annotations

import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from climate_risk.config import KMA_API_HUB_KEY, KMA_WRN_MET_DATA_URL, KMA_WRN_REG_URL

STATUS_OK = "OK"
STATUS_UPSTREAM_ERROR = "UPSTREAM_ERROR"
STATUS_ACTIVATION_REQUIRED = "ACTIVATION_REQUIRED"  # 이 authKey로 해당 API 활용신청 미승인
STATUS_NO_ZONE_MATCH = "NO_ZONE_MATCH"  # region_code는 알지만 그 시점 유효한 특보구역을 못 찾음

_KST = timezone(timedelta(hours=9))
_SENTINEL_NEVER_EXPIRES = datetime(2100, 12, 31, 23, 59, tzinfo=_KST)

# 기상청 API허브 문서(예특보 > 기상특보 > 특·정보 자료 조회 > 특보자료 API) 실측 확인
# (2026-08-19). "11개 기상현상"(강풍·풍랑·호우·대설·건조·폭풍해일·한파·태풍·황사·폭염·
# 열대야) + 지진해일·안개 2종 추가.
WRN_CODE_LABELS: dict[str, str] = {
    "W": "강풍", "R": "호우", "C": "한파", "D": "건조", "O": "폭풍해일",
    "N": "지진해일", "V": "풍랑", "T": "태풍", "S": "대설", "Y": "황사",
    "H": "폭염", "F": "안개", "K": "열대야",
}
LVL_CODE_LABELS: dict[str, str] = {"1": "예비", "2": "주의보", "3": "경보", "4": "중대경보"}
CMD_CODE_LABELS: dict[str, str] = {
    "1": "발표", "2": "대치", "3": "해제", "4": "대치해제", "5": "연장", "6": "변경", "7": "변경해제",
}

# 우리 SGG region_code -> (검색할 특보구역명 접두어, 그 구역의 상위(province) REG_ID).
# REG_ID 자체가 시간에 따라 바뀌므로(위 docstring) 이름+상위구역+유효기간으로 찾는다.
# 대구 5개구는 전부 같은 항목으로 수렴한다 — 개별 구분 불가(위 docstring 참조).
_DAEGU_PROVINCE_REG_ID = "L1140000"
_POHANG_PROVINCE_REG_ID = "L1070000"
# 2026-08-19 추가 — 거제(48310). "경상남도"(L1080000, 전국 직계 자식) 아래 "거제"(REG_ID
# L1082200, "거제시")가 있음을 실측 확인. 대구·포항과 달리 거제는 SHP가 시 전체를 하나로
# 커버해서(6개 빈도 지방하천 통합) 이 특보구역도 시 전체와 1:1로 대응 — 개별 구분 문제 없음.
_GEOJE_PROVINCE_REG_ID = "L1080000"
REGION_CODE_TO_KMA_ZONE: dict[str, tuple[str, str]] = {
    "47111": ("포항", _POHANG_PROVINCE_REG_ID),
    "48310": ("거제", _GEOJE_PROVINCE_REG_ID),
    "27200": ("대구", _DAEGU_PROVINCE_REG_ID),
    "27110": ("대구", _DAEGU_PROVINCE_REG_ID),
    "27260": ("대구", _DAEGU_PROVINCE_REG_ID),
    "27140": ("대구", _DAEGU_PROVINCE_REG_ID),
    "27230": ("대구", _DAEGU_PROVINCE_REG_ID),
}


@dataclass(frozen=True)
class RegionZone:
    reg_id: str
    reg_name: str
    valid_from: datetime
    valid_to: datetime
    parent_reg_id: str


@dataclass(frozen=True)
class HistoricalWarningEvent:
    reg_id: str
    tm_fc: datetime  # 발표시각
    tm_ef: datetime  # 발효시각
    wrn_code: str
    wrn_label: str
    lvl_code: str
    lvl_label: str
    cmd_code: str
    cmd_label: str


@dataclass(frozen=True)
class HistoricalQueryResult:
    status: str
    events: list[HistoricalWarningEvent]
    reg_id: str | None
    note: str


def _tm_to_datetime(raw: str) -> datetime:
    dt = datetime.strptime(raw.strip(), "%Y%m%d%H%M").replace(tzinfo=_KST)
    if dt.year >= 2100:
        return _SENTINEL_NEVER_EXPIRES
    return dt


def _datetime_to_tm(dt: datetime) -> str:
    return dt.astimezone(_KST).strftime("%Y%m%d%H%M")


def _decode_response(raw: bytes) -> str:
    """실측 확인: 이 API 계열은 EUC-KR로 응답한다(UTF-8 아님, 2026-08-19 확인)."""
    return raw.decode("euc-kr")


def _data_lines(text: str) -> list[str]:
    return [
        line for line in text.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


def _fetch_wrn_reg_raw() -> bytes:
    """실제 HTTP 호출 지점(seam) — advisory/live.py의 `_fetch_kma_json`과 동일 패턴으로
    테스트가 monkeypatch로 네트워크 없이 검증할 수 있게 분리한다."""
    url = f"{KMA_WRN_REG_URL}?authKey={KMA_API_HUB_KEY}"
    with urllib.request.urlopen(url, timeout=15) as resp:
        return resp.read()


def _fetch_wrn_met_data_raw(reg_id: str, start: datetime, end: datetime) -> bytes:
    url = (
        f"{KMA_WRN_MET_DATA_URL}?tmfc1={_datetime_to_tm(start)}&tmfc2={_datetime_to_tm(end)}"
        f"&reg={reg_id}&disp=0&help=1&authKey={KMA_API_HUB_KEY}"
    )
    with urllib.request.urlopen(url, timeout=20) as resp:
        return resp.read()


def _parse_wrn_reg(text: str) -> list[RegionZone]:
    """`REG_ID TM_ST TM_ED REG_SP REG_UP REG_KO REG_NAME` 7개 공백구분 필드(고정폭
    포맷이지만 값 자체엔 공백이 없어 단순 split()으로 안전하게 파싱 가능, 실측 확인)."""
    zones: list[RegionZone] = []
    for line in _data_lines(text):
        fields = line.split()
        if len(fields) < 7:
            continue
        reg_id, tm_st, tm_ed, _reg_sp, reg_up, _reg_ko, reg_name = fields[:7]
        zones.append(
            RegionZone(
                reg_id=reg_id,
                reg_name=reg_name,
                valid_from=_tm_to_datetime(tm_st),
                valid_to=_tm_to_datetime(tm_ed),
                parent_reg_id=reg_up,
            )
        )
    return zones


def _parse_wrn_met_data(text: str) -> list[HistoricalWarningEvent]:
    """`TM_FC, TM_EF, TM_IN, STN, REG_ID, WRN, LVL, CMD, GRD, CNT, RPT, =` 콤마구분
    포맷 — 마지막 `=`는 실데이터 필드가 아니라 레코드 종료 마커(실측 확인)."""
    events: list[HistoricalWarningEvent] = []
    for line in _data_lines(text):
        fields = [f.strip() for f in line.split(",")]
        if len(fields) < 8:
            continue
        tm_fc, tm_ef, _tm_in, _stn, reg_id, wrn, lvl, cmd = fields[:8]
        events.append(
            HistoricalWarningEvent(
                reg_id=reg_id,
                tm_fc=_tm_to_datetime(tm_fc),
                tm_ef=_tm_to_datetime(tm_ef),
                wrn_code=wrn,
                wrn_label=WRN_CODE_LABELS.get(wrn, f"미확인({wrn})"),
                lvl_code=lvl,
                lvl_label=LVL_CODE_LABELS.get(lvl, f"미확인({lvl})"),
                cmd_code=cmd,
                cmd_label=CMD_CODE_LABELS.get(cmd, f"미확인({cmd})"),
            )
        )
    return events


def resolve_region_zone(
    region_code: str, as_of: datetime, zones: list[RegionZone]
) -> RegionZone | None:
    """`region_code`(우리 SGG 코드)가 `as_of` 시점에 속했던 특보구역을 찾는다.

    이름만으로 찾지 않는다 — 대구는 2026-05-31 개편으로 REG_NAME 자체가
    "대구광역시"→"대구중부"로 바뀌어(위 모듈 docstring) 이름 완전일치로는 개편 전후를
    동시에 못 찾는다. 대신 (a) 지정된 상위(province) 구역의 직계 자식이면서
    (b) 이름이 접두어로 시작하고 (c) 그 시점에 유효기간 안인 항목을 찾는다 — 개편
    전후 이름이 달라져도 접두어("대구")는 공통이라 안정적으로 매치된다.
    """
    if region_code not in REGION_CODE_TO_KMA_ZONE:
        return None
    prefix, province_reg_id = REGION_CODE_TO_KMA_ZONE[region_code]
    for zone in zones:
        if (
            zone.parent_reg_id == province_reg_id
            and zone.reg_name.startswith(prefix)
            and zone.valid_from <= as_of <= zone.valid_to
        ):
            return zone
    return None


def fetch_region_zones() -> list[RegionZone]:
    raw = _fetch_wrn_reg_raw()
    return _parse_wrn_reg(_decode_response(raw))


def _is_activation_required_error(exc: urllib.error.HTTPError) -> bool:
    return exc.code == 403


def query_historical_warnings(
    region_code: str, start: datetime, end: datetime, as_of: datetime | None = None
) -> HistoricalQueryResult:
    """`region_code`(우리 SGG 코드)에 대해 [start, end] 구간의 과거 특보 이력을 조회한다.

    `as_of`(기본값 `start`)로 특보구역 매핑을 조회 시점 기준으로 찾은 뒤, 그 REG_ID로
    실제 이력을 조회한다 — 두 API 호출(구역 조회 → 이력 조회) 순서가 고정이다.
    """
    if as_of is None:
        as_of = start

    try:
        zones = fetch_region_zones()
    except urllib.error.HTTPError as exc:
        if _is_activation_required_error(exc):
            return HistoricalQueryResult(
                status=STATUS_ACTIVATION_REQUIRED, events=[], reg_id=None,
                note="특보구역 API 활용신청이 승인되지 않았습니다 — apihub.kma.go.kr에서 활용신청 후 다시 시도하세요.",
            )
        return HistoricalQueryResult(
            status=STATUS_UPSTREAM_ERROR, events=[], reg_id=None,
            note=f"특보구역 API 호출 실패: HTTP {exc.code}",
        )
    except (urllib.error.URLError, TimeoutError) as exc:
        return HistoricalQueryResult(
            status=STATUS_UPSTREAM_ERROR, events=[], reg_id=None, note=f"특보구역 API 호출 실패: {exc}"
        )

    zone = resolve_region_zone(region_code, as_of, zones)
    if zone is None:
        return HistoricalQueryResult(
            status=STATUS_NO_ZONE_MATCH, events=[], reg_id=None,
            note=f"region_code={region_code!r}, as_of={as_of.isoformat()!r}에 해당하는 특보구역을 찾지 못했습니다.",
        )

    try:
        raw = _fetch_wrn_met_data_raw(zone.reg_id, start, end)
    except urllib.error.HTTPError as exc:
        if _is_activation_required_error(exc):
            return HistoricalQueryResult(
                status=STATUS_ACTIVATION_REQUIRED, events=[], reg_id=zone.reg_id,
                note="특보자료 API 활용신청이 승인되지 않았습니다 — apihub.kma.go.kr에서 활용신청 후 다시 시도하세요.",
            )
        return HistoricalQueryResult(
            status=STATUS_UPSTREAM_ERROR, events=[], reg_id=zone.reg_id, note=f"특보자료 API 호출 실패: HTTP {exc.code}"
        )
    except (urllib.error.URLError, TimeoutError) as exc:
        return HistoricalQueryResult(
            status=STATUS_UPSTREAM_ERROR, events=[], reg_id=zone.reg_id, note=f"특보자료 API 호출 실패: {exc}"
        )

    events = _parse_wrn_met_data(_decode_response(raw))
    return HistoricalQueryResult(status=STATUS_OK, events=events, reg_id=zone.reg_id, note="")
