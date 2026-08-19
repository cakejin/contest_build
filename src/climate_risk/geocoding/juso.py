"""도로명주소 검색API(JUSO, business.juso.go.kr) 래퍼 — 사용자 입력 자동완성용.

`scripts/discover_via_juso.py`가 포트폴리오 배치 생성용으로 이미 이 API(엔드포인트·
파라미터·키워드 매칭이 느슨하다는 특성)를 검증해뒀다(DEV_LOG.md 2026-08-18). 이 모듈은
그 경로를 웹 데모의 라이브 주소 입력창 자동완성에 연결한다 — 같은 날 DEV_LOG가
"아직 하지 않은 로드맵 항목"으로 남겨둔 것을 착수하는 것.

키워드 매칭이 느슨해 타 지역 결과가 섞이므로, 응답의 `roadAddr`가 실제로 이 시스템의
커버리지 지역(대구광역시·경상북도 포항시)으로 시작하는지 반드시 재확인한다 —
discover_via_juso.py와 동일한 필터.
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from dataclasses import dataclass

from climate_risk.config import JUSO_API_KEY

_JUSO_URL = "https://business.juso.go.kr/addrlink/addrLinkApi.do"
_ALLOWED_PREFIXES = ("대구광역시", "경상북도 포항시")
_MIN_KEYWORD_LEN = 2  # JUSO API가 1글자 키워드는 결과가 지나치게 넓어져 사실상 무의미


class JusoSearchError(RuntimeError):
    """JUSO API가 정상(errorCode "0")이 아닌 응답을 반환했을 때."""


@dataclass(frozen=True)
class AddressSuggestion:
    road_address: str
    building_name: str | None


def _fetch_juso_json(keyword: str, count: int) -> dict:
    """실제 HTTP 호출 지점(seam) — geocoding/vworld.py와 동일 패턴으로 테스트가
    monkeypatch로 네트워크 없이 검증할 수 있게 분리한다."""
    params = {
        "confmKey": JUSO_API_KEY,
        "currentPage": "1",
        "countPerPage": str(count),
        "keyword": keyword,
        "resultType": "json",
    }
    url = _JUSO_URL + "?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=8) as resp:
        return json.load(resp)


def search_road_addresses(keyword: str, count: int = 20) -> list[AddressSuggestion]:
    """키워드로 도로명주소를 검색해 커버리지 지역(대구·포항) 결과만 반환한다.

    짧은 키워드는 API가 거부하거나 무의미하게 넓은 결과를 주므로 호출 자체를
    생략하고 빈 리스트를 반환한다(불필요한 API 호출 방지).
    """
    if len(keyword.strip()) < _MIN_KEYWORD_LEN:
        return []

    data = _fetch_juso_json(keyword, count)
    common = data.get("results", {}).get("common", {})
    error_code = common.get("errorCode")
    if error_code not in ("0", 0):
        raise JusoSearchError(f"JUSO API errorCode={error_code!r} {common.get('errorMessage')!r}")

    items = data.get("results", {}).get("juso") or []
    suggestions: list[AddressSuggestion] = []
    seen: set[str] = set()
    for item in items:
        road = item.get("roadAddr", "")
        if not road.startswith(_ALLOWED_PREFIXES):
            continue
        if road in seen:
            continue
        seen.add(road)
        suggestions.append(AddressSuggestion(road_address=road, building_name=item.get("bdNm") or None))
    return suggestions
