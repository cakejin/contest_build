"""safetydata.go.kr 행정안전부 재난문자 발송내역 조회(DSSP-IF-00247) — 대구 5개구처럼
기상청 특보 API(advisory/live.py·advisory/kma_historical.py)로는 개별 구분이 안 되는
지역을 재난문자로 보완하는 모듈(DEV_LOG.md 2026-08-19/20 참조).

**요청/응답 스펙(2026-08-20, 사용자가 safetydata.go.kr API 상세 페이지에서 직접 캡처해준
공식 스펙 그대로 — 이 저장소 관례상 원격 문서 추측보다 항상 더 정확했다)**:
- 요청변수: `serviceKey`(필수)·`numOfRows`·`pageNo`·`returnType`·`crtDt`("조회시작일자",
  YYYYMMDD — **시작일뿐, 종료일 파라미터는 없다**)·`rgnNm`("지역명(시도명, 시군구명)").
- 응답 필드: `SN`·`CRT_DT`("생성일시", "YYYY/MM/DD HH:MM:SS")·`MSG_CN`(메시지 내용)·
  `RCPTN_RGN_NM`(수신지역명, 쉼표로 구분된 다중 지역이 올 수 있고 시/군/구보다 더
  세분화된 읍/면/동까지 오는 경우도 실측 확인됨 — 예: "대구광역시 수성구 지산동")·
  `EMRG_STEP_NM`(긴급재난/안전안내/위급재난)·`DST_SE_NM`(재해구분명, 공식 전체 목록은
  아래 `_ALL_DST_SE_NM_VALUES` 참조)·`REG_YMD`·`MDFCN_YMD`.

**crtDt는 종료일이 없다 — 응답도 날짜순 정렬이 아니다(실측 확인)**: `rgnNm`+`crtDt`로
조회한 실제 응답에서 레코드 순서가 `CRT_DT` 오름차순도 내림차순도 아니었다(2026-07-17
레코드와 2026-08-18 레코드가 뒤섞여 나옴). 따라서 [start, end] 구간 조회는 `crtDt=start`로
서버측 하한을 걸고, **상한(end)은 클라이언트에서 직접 필터링**한다 — 서버가 정렬해줄
거라고 가정하지 않는다.

**IP 화이트리스트 — 1개만 등록 가능, 등록 IP는 그때그때 접속 환경에 따라 달라질 수
있다**: 등록한 IP가 아니면 계정 키가 유효해도 무조건 거부된다(2026-08-20 실측:
resultCode="32", HTTP 200 안에 에러가 실려 옴 — HTTPError 아님). "폰 핫스팟이면 항상
된다" 같은 특정 네트워크를 전제하지 않는다 — 등록 IP 자체가 인터넷 연결 상황에 따라
수시로 바뀔 수 있어, 어떤 네트워크가 맞는지는 그때그때 safetydata.go.kr에서 확인해야
한다(사용자 명시 요청, DEV_LOG.md 2026-08-19/20). success resultCode="00"도 실측
확인됨(추측 아님, 2026-08-20 재확인).

**REGION_CODE_TO_DISASTER_MSG_REGION_NAME은 config.py의 FloodShpSource.region_name과
다른 별도 매핑이다** — region_name은 표시용 라벨이라 포항(`"포항시 남구"`)·거제
(`"거제시"`)에 광역단체명이 빠져 있는데, `rgnNm`/`RCPTN_RGN_NM` 매칭에는 전체 행정구역명
(`"경상북도 포항시 남구"`)이 필요하다. 실측 캡처(힌남노 2022-09-06 당일 데이터)로 정확한
전체 텍스트를 직접 확인해 만들었다 — 추측 아님.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from climate_risk.config import SAFETYDATA_DISASTER_MSG_API_KEY, SAFETYDATA_DISASTER_MSG_URL

STATUS_OK = "OK"
STATUS_UNREGISTERED_IP = "UNREGISTERED_IP"
STATUS_UPSTREAM_ERROR = "UPSTREAM_ERROR"
STATUS_UNMAPPED_REGION = "UNMAPPED_REGION"
# 안전장치 — 페이지 상한에 도달하면 결과를 자를 게 아니라 그 사실 자체를 명시 반환한다
# (설계원칙1과 같은 정신). 실측상 특정 지역 1건 조회는 보통 1~2페이지(수십 건) 수준.
STATUS_PAGE_LIMIT_REACHED = "PAGE_LIMIT_REACHED"

_KST = timezone(timedelta(hours=9))
_MAX_PAGES = 20
_PAGE_SIZE = 100

# 2026-08-20 실측 확인(DEV_LOG.md 참조) — 화이트리스트에 없는 IP로 호출하면 HTTP 200에
# 이 resultCode가 담겨 온다(HTTPError가 아니라 정상 응답 바디 안에 에러가 실려 있음).
_UNREGISTERED_IP_RESULT_CODE = "32"
_SUCCESS_RESULT_CODE = "00"

_IP_WHITELIST_GUIDANCE = (
    "재난문자 API는 safetydata.go.kr에 등록된 IP 1개에서만 호출할 수 있어요 — "
    "지금 접속 중인 네트워크의 IP가 등록된 IP와 달라서 거부됐습니다. safetydata.go.kr "
    "마이페이지에서 등록된 IP를 확인하고, 그 IP를 쓰는 네트워크로 전환하거나 "
    "지금 IP로 화이트리스트를 다시 등록한 뒤 재시도해 주세요."
)

# 재난문자 API가 실제로 쓰는 DST_SE_NM 공식 전체 목록(2026-08-20, safetydata.go.kr API
# 상세 페이지에서 사용자가 직접 캡처해준 스펙 그대로) — 참고용 문서화.
_ALL_DST_SE_NM_VALUES = frozenset({
    "AI", "가뭄", "가축질병", "강풍", "건조", "교통", "교통사고", "교통통제", "금융", "기타",
    "대설", "미세먼지", "민방공", "붕괴", "산불", "산사태", "수도", "안개", "에너지", "전염병",
    "정전", "지진", "지진해일", "태풍", "테러", "통신", "폭발", "폭염", "풍랑", "한파", "호우",
    "홍수", "화재", "환경오염사고", "황사",
})

# 이 시스템 목적(담보 물리적 손상 기후리스크)과 직접 관련 있는 재해구분만 알림 대상으로
# 삼는다 — 기존 기상특보 2종(live.py·kma_historical.py)이 이미 다루는 홍수 인접 카테고리
# (호우·홍수·태풍·강풍·대설·산사태·풍랑·폭풍해일)에 더해, 2026-08-20 사용자 요청으로
# 산불·화재를 신규 추가했다. 폭염·황사·미세먼지·교통·가축질병·금융·통신 등은 담보 물리적
# 손상과 무관해 제외(CLAUDE.md 설계원칙2 "특보=알림 트리거"와 같은 정신 — 무관한 신호로
# 포트폴리오 재계산을 유발하지 않는다). PM이 목록 조정 필요하면 이 상수만 고치면 된다.
RELEVANT_DST_SE_NM = frozenset({
    "호우", "홍수", "태풍", "강풍", "대설", "산사태", "풍랑", "폭풍해일", "산불", "화재",
})

# config.py의 FloodShpSource.region_name과 별도 — 위 모듈 docstring 참조.
REGION_CODE_TO_DISASTER_MSG_REGION_NAME: dict[str, str] = {
    "47111": "경상북도 포항시 남구",
    "48310": "경상남도 거제시",
    "27200": "대구광역시 남구",
    "27110": "대구광역시 중구",
    "27260": "대구광역시 수성구",
    "27140": "대구광역시 동구",
    "27230": "대구광역시 북구",
}


@dataclass(frozen=True)
class DisasterMessage:
    sn: int
    crt_dt: datetime  # KST
    msg_cn: str
    rcptn_rgn_nm: str  # 원본 그대로(쉼표구분 다중지역 가능) — 매칭은 _message_matches_region()이 담당
    emrg_step_nm: str
    dst_se_nm: str


@dataclass(frozen=True)
class DisasterMsgQueryResult:
    status: str
    raw_body: list[dict] | None  # 성공 시 원본 body(필드 파싱 전 raw list)
    note: str


@dataclass(frozen=True)
class DisasterMsgRegionQueryResult:
    status: str
    messages: list[DisasterMessage]
    note: str


def _fetch_disaster_msg_raw(params: dict[str, str]) -> bytes:
    """실제 HTTP 호출 지점(seam) — kma_historical.py의 `_fetch_wrn_reg_raw`와 동일 패턴으로
    테스트가 monkeypatch로 네트워크 없이 검증할 수 있게 분리한다."""
    query = urllib.parse.urlencode(params)
    url = f"{SAFETYDATA_DISASTER_MSG_URL}?serviceKey={SAFETYDATA_DISASTER_MSG_API_KEY}&{query}"
    with urllib.request.urlopen(url, timeout=15) as resp:
        return resp.read()


def query_disaster_messages(params: dict[str, str]) -> DisasterMsgQueryResult:
    """`params`(pageNo/numOfRows/crtDt/rgnNm 등 — 위 모듈 docstring "요청/응답 스펙"
    참조)로 재난문자 발송내역을 조회한다. 봉투(header) 상태만 분류하고, body는 원본
    리스트를 그대로 반환한다 — 레코드 단위 파싱은 `_parse_disaster_message()` 몫이다.
    """
    try:
        raw = _fetch_disaster_msg_raw(params)
    except (urllib.error.URLError, TimeoutError) as exc:
        return DisasterMsgQueryResult(
            status=STATUS_UPSTREAM_ERROR, raw_body=None, note=f"재난문자 API 호출 실패: {exc}"
        )

    data = json.loads(raw.decode("utf-8"))
    header = data.get("header", {})
    result_code = header.get("resultCode")

    if result_code == _UNREGISTERED_IP_RESULT_CODE:
        return DisasterMsgQueryResult(status=STATUS_UNREGISTERED_IP, raw_body=None, note=_IP_WHITELIST_GUIDANCE)

    if result_code != _SUCCESS_RESULT_CODE:
        return DisasterMsgQueryResult(
            status=STATUS_UPSTREAM_ERROR,
            raw_body=None,
            note=f"재난문자 API가 비정상 응답을 반환했습니다: resultCode={result_code!r} {header.get('resultMsg')!r}",
        )

    return DisasterMsgQueryResult(status=STATUS_OK, raw_body=data.get("body") or [], note="")


def _parse_disaster_message(record: dict) -> DisasterMessage:
    crt_dt = datetime.strptime(record["CRT_DT"].strip(), "%Y/%m/%d %H:%M:%S").replace(tzinfo=_KST)
    return DisasterMessage(
        sn=int(record["SN"]),
        crt_dt=crt_dt,
        msg_cn=record.get("MSG_CN", ""),
        rcptn_rgn_nm=record.get("RCPTN_RGN_NM", ""),
        emrg_step_nm=record.get("EMRG_STEP_NM", ""),
        dst_se_nm=record.get("DST_SE_NM", ""),
    )


def _message_matches_region(rcptn_rgn_nm: str, target_region_name: str) -> bool:
    """`rcptn_rgn_nm`(쉼표구분 다중지역 가능, 각 항목에 앞뒤 공백 有)의 항목 중 하나라도
    `target_region_name`과 일치하거나, 그보다 더 넓은 상위지역(예: "경상북도 포항시"가
    "경상북도 포항시 남구"를 포함)이거나, 더 세분화된 하위지역(예: "경상북도 포항시 남구
    오천읍")이면 True. 토큰(공백) 경계로 비교해 "남구"가 "동남구"에 우연히 걸리는 등의
    오탐을 막는다."""
    for entry in rcptn_rgn_nm.split(","):
        entry = " ".join(entry.split())  # 연속/후행 공백 정규화
        if not entry:
            continue
        if entry == target_region_name:
            return True
        if entry.startswith(target_region_name + " "):  # entry가 target의 하위지역(더 세분화)
            return True
        if target_region_name.startswith(entry + " "):  # entry가 target을 포함하는 상위지역
            return True
    return False


def query_disaster_messages_for_region(
    region_code: str, start: datetime, end: datetime
) -> DisasterMsgRegionQueryResult:
    """`region_code`(우리 SGG 코드)의 [start, end] 구간 재난문자를 조회한다.

    `crtDt=start`로 서버측 하한만 걸고(종료일 파라미터가 없음, 모듈 docstring 참조),
    `rgnNm`으로 서버측 1차 필터링한 뒤, 상한(end)·정확한 지역 매칭·재해구분
    화이트리스트(RELEVANT_DST_SE_NM)는 클라이언트에서 적용한다. `_MAX_PAGES`(20페이지×
    100건=2000건)를 넘기면 결과를 조용히 자르지 않고 STATUS_PAGE_LIMIT_REACHED를
    명시 반환한다.
    """
    if region_code not in REGION_CODE_TO_DISASTER_MSG_REGION_NAME:
        return DisasterMsgRegionQueryResult(
            status=STATUS_UNMAPPED_REGION,
            messages=[],
            note=f"region_code={region_code!r}에 대한 재난문자 지역명 매핑이 없습니다.",
        )

    target_region_name = REGION_CODE_TO_DISASTER_MSG_REGION_NAME[region_code]
    raw_records: list[dict] = []

    for page in range(1, _MAX_PAGES + 1):
        result = query_disaster_messages(
            {
                "pageNo": str(page),
                "numOfRows": str(_PAGE_SIZE),
                "crtDt": start.astimezone(_KST).strftime("%Y%m%d"),
                "rgnNm": target_region_name,
            }
        )
        if result.status == STATUS_UNREGISTERED_IP:
            return DisasterMsgRegionQueryResult(status=STATUS_UNREGISTERED_IP, messages=[], note=result.note)
        if result.status != STATUS_OK:
            return DisasterMsgRegionQueryResult(status=STATUS_UPSTREAM_ERROR, messages=[], note=result.note)

        page_records = result.raw_body or []
        raw_records.extend(page_records)
        if len(page_records) < _PAGE_SIZE:
            break
    else:
        return DisasterMsgRegionQueryResult(
            status=STATUS_PAGE_LIMIT_REACHED,
            messages=[],
            note=f"페이지 상한({_MAX_PAGES}페이지)에 도달해 결과를 신뢰할 수 없습니다 — 구간을 좁혀 재조회하세요.",
        )

    messages = [_parse_disaster_message(r) for r in raw_records]
    filtered = [
        m
        for m in messages
        if start <= m.crt_dt <= end
        and m.dst_se_nm in RELEVANT_DST_SE_NM
        and _message_matches_region(m.rcptn_rgn_nm, target_region_name)
    ]
    return DisasterMsgRegionQueryResult(status=STATUS_OK, messages=filtered, note="")
