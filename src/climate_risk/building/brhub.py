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
