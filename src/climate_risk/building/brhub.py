"""건축HUB 건축물대장정보 `getBrTitleInfo` HTTP 래퍼 — HANDOVER.md §4.2 2.3.

라이브 체크포인트(DEV_LOG.md 2026-08-11)로 확정된 사실 두 가지:
1. `DATA_GO_KR_API_KEY`는 `.env`에 이미 percent-encoding된 채로 저장돼 있다. 다른
   파라미터와 함께 `urllib.parse.urlencode()`에 넣으면 이중 인코딩되어 400
   (`NO_OPENAPI_SERVICE_ERROR` — 원인을 오도하는 메시지)이 난다. serviceKey는
   반드시 다른 파라미터와 분리해 raw로 쿼리스트링에 붙여야 한다.
2. 응답 `body.items.item`은 항상 리스트다(데이터 없어도 `[]`, 단건이어도 `[{...}]`) —
   레코드 없음도 `resultCode: "00"`(NORMAL SERVICE)으로 정상 응답한다(예외 아님).
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from dataclasses import dataclass

from climate_risk.building.address_resolver import AdminCodeMatch
from climate_risk.config import BR_HUB_BASE_URL, DATA_GO_KR_API_KEY

_OPERATION = "getBrTitleInfo"
_FLOOR_OPERATION = "getBrFlrOulnInfo"

# flrGbCd 코드값 — 2026-08-18 라이브 호출로 실측 확인(HANDOVER.md §⑧ 데이터소스 2번).
# 포항 남구 인덕로 27(지상만)과 지하층 보유 건물(대구 업무시설) 두 건 교차 확인해
# "10"=지하/"20"=지상이 실제 응답의 flrGbCdNm과 일치함을 확인했다 — 추정치 아님.
FLOOR_GB_UNDERGROUND = "10"
FLOOR_GB_GROUND = "20"
# mainAtchGbCd — "0"=주건축물, "1"=부속건축물(국토부 공식 활용가이드로 확인, HANDOVER §⑧).
_MAIN_BUILDING_ATCH_GB_CD = "0"


class BrHubError(RuntimeError):
    """건축HUB API가 정상(resultCode="00") 이외의 상태를 반환했을 때."""


@dataclass(frozen=True)
class BrTitleInfo:
    strct_cd_nm: str | None
    main_purps_cd_nm: str | None
    ugrnd_flr_cnt: int | None
    grnd_flr_cnt: int | None
    use_apr_day: str | None
    raw: dict


@dataclass(frozen=True)
class BrFloorInfo:
    flr_gb_cd: str  # FLOOR_GB_UNDERGROUND | FLOOR_GB_GROUND
    flr_no: int
    main_purps_cd_nm: str | None
    area: float | None
    raw: dict


def _parse_int(value: object) -> int | None:
    if value in (None, "", " "):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _parse_str(value: object) -> str | None:
    if value in (None, "", " "):
        return None
    return str(value)


def fetch_br_title_info(admin: AdminCodeMatch) -> BrTitleInfo | None:
    """레코드 없음(임야·존재하지 않는 지번 등)은 예상된 부재라 None을 반환한다.
    API 자체가 비정상 상태(resultCode != "00")를 반환하면 BrHubError를 낸다."""
    params = {
        "sigunguCd": admin.sigungu_cd,
        "bjdongCd": admin.bjdong_cd,
        "platGbCd": admin.plat_gb_cd,
        "bun": admin.bun,
        "ji": admin.ji,
        "_type": "json",
        "numOfRows": "10",
        "pageNo": "1",
    }
    url = (
        f"{BR_HUB_BASE_URL}/{_OPERATION}?serviceKey={DATA_GO_KR_API_KEY}&"
        + urllib.parse.urlencode(params)
    )
    with urllib.request.urlopen(url, timeout=10) as resp:
        data = json.load(resp)

    header = data["response"]["header"]
    result_code = header["resultCode"]
    if result_code != "00":
        raise BrHubError(
            f"getBrTitleInfo resultCode={result_code} resultMsg={header.get('resultMsg')} "
            f"admin={admin.sigungu_cd}{admin.bjdong_cd}{admin.plat_gb_cd}{admin.bun}{admin.ji}"
        )

    items = data["response"]["body"]["items"].get("item") or []
    if not items:
        return None

    item = items[0]
    return BrTitleInfo(
        strct_cd_nm=_parse_str(item.get("strctCdNm")),
        main_purps_cd_nm=_parse_str(item.get("mainPurpsCdNm")),
        ugrnd_flr_cnt=_parse_int(item.get("ugrndFlrCnt")),
        grnd_flr_cnt=_parse_int(item.get("grndFlrCnt")),
        use_apr_day=_parse_str(item.get("useAprDay")),
        raw=item,
    )


def fetch_br_floor_info(admin: AdminCodeMatch) -> list[BrFloorInfo]:
    """HANDOVER.md §⑧ 데이터소스 2번 — `getBrFlrOulnInfo`(층별개요) 라이브 조회.

    사용자가 요청한 층(`target_floor`)이 이 건물에 실제로 등록돼 있는지 검증하는
    용도다(scenario/floor_exposure.py) — "사용자가 입력한 층수를 무조건 믿는다"가
    아니라 실제 건축물대장 등록 정보와 대조한다("데이터 없음≠위험 없음"의 반대
    방향 적용: 근거 없는 입력도 그대로 믿지 않는다).

    한 주소에 주건축물·부속건축물(차고·창고 등)이 여러 행으로 섞여 반환될 수
    있어(HANDOVER §⑧ 주의사항) `mainAtchGbCd == "0"`(주건축물)만 남긴다 —
    부속건축물의 층 정보를 담보 건물 것으로 잘못 쓰는 버그를 원천 차단한다.
    레코드 없음(fetch_br_title_info와 동일하게 예상된 부재)은 빈 리스트로,
    API 자체의 비정상 상태는 BrHubError로 구분한다.
    """
    params = {
        "sigunguCd": admin.sigungu_cd,
        "bjdongCd": admin.bjdong_cd,
        "platGbCd": admin.plat_gb_cd,
        "bun": admin.bun,
        "ji": admin.ji,
        "_type": "json",
        "numOfRows": "100",
        "pageNo": "1",
    }
    url = (
        f"{BR_HUB_BASE_URL}/{_FLOOR_OPERATION}?serviceKey={DATA_GO_KR_API_KEY}&"
        + urllib.parse.urlencode(params)
    )
    with urllib.request.urlopen(url, timeout=10) as resp:
        data = json.load(resp)

    header = data["response"]["header"]
    result_code = header["resultCode"]
    if result_code != "00":
        raise BrHubError(
            f"getBrFlrOulnInfo resultCode={result_code} resultMsg={header.get('resultMsg')} "
            f"admin={admin.sigungu_cd}{admin.bjdong_cd}{admin.plat_gb_cd}{admin.bun}{admin.ji}"
        )

    items = data["response"]["body"]["items"].get("item") or []
    return [
        BrFloorInfo(
            flr_gb_cd=str(item["flrGbCd"]),
            flr_no=int(item["flrNo"]),
            main_purps_cd_nm=_parse_str(item.get("mainPurpsCdNm")),
            area=float(item["area"]) if item.get("area") not in (None, "", " ") else None,
            raw=item,
        )
        for item in items
        if str(item.get("mainAtchGbCd")) == _MAIN_BUILDING_ATCH_GB_CD
    ]
