"""담보 포트폴리오 확장 — 미달 5종(공동주택·다가구주택·업무시설·창고·공장) 보충 발굴.

V-World 지명(POI) 검색은 "이름 붙은 시설"만 잡혀 이 5종에서 특히 부족했다
(discover_collateral_addresses.py + grid_scan_residential.py 결과 참조). 도로명주소
검색API(business.juso.go.kr, jstRoadNmAddrApiSearch)는 국가 표준 주소 DB 전체를
키워드로 검색해주므로 "OO빌라"/"OO원룸" 같은 건물명 패턴으로 훨씬 많은 실주소 후보를
찾을 수 있다 — 단, 키워드가 느슨하게 매칭돼(예: "대구 빌라"가 대전 건물명에도 매치)
반드시 응답의 실제 도로명주소가 대구·포항으로 시작하는지 재확인해야 한다.

이 API는 좌표를 안 주므로(주소 문자열만) V-World로 geocode까지 이 단계에서 끝내
generate_portfolio.py가 그대로 소비할 수 있는 형태(_address_candidates.json과 동일
스키마)로 기존 파일에 병합한다.
"""

from __future__ import annotations

import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from climate_risk.config import JUSO_API_KEY  # noqa: E402
from climate_risk.geocoding.vworld import VWorldGeocodeError, geocode_road_address  # noqa: E402

CANDIDATES_PATH = Path(__file__).resolve().parents[1] / "data" / "climate-collateral-underwriting-ai" / "curated" / "portfolio" / "_address_candidates.json"

_JUSO_URL = "https://business.juso.go.kr/addrlink/addrLinkApi.do"
_ALLOWED_PREFIXES = ("대구광역시", "경상북도 포항시")

# 담보유형 -> 도로명주소 검색 키워드 목록(건물명 패턴 기반)
TYPE_KEYWORDS: dict[str, list[str]] = {
    "공동주택": ["대구 빌라", "포항 빌라", "대구 연립주택", "포항 연립주택", "대구 다세대주택", "포항 다세대주택"],
    "다가구주택": ["대구 다가구주택", "포항 다가구주택", "대구 원룸텔", "포항 원룸텔", "대구 하우스", "포항 하우스"],
    "업무시설": ["대구 오피스텔", "포항 오피스텔", "대구 사옥", "포항 사옥", "대구 비즈니스센터", "대구 타워"],
    "창고": [
        "대구 물류창고", "포항 물류창고", "대구 냉동창고", "포항 냉동창고", "대구 유통센터", "포항 유통센터",
        "대구 냉장창고", "포항 냉장창고", "대구 화물터미널", "포항 화물터미널", "대구 자재창고", "포항 자재창고",
        "대구 보관소", "포항 보관소", "대구 물류센터", "포항 물류센터", "대구 콜드체인", "대구 창고1",
        "대구 창고2", "포항 창고1", "대구 배송센터", "포항 배송센터", "대구 저장고", "포항 저장고",
        "대구 곡물창고", "포항 곡물창고", "대구 상품창고", "대구 택배터미널", "포항 택배터미널", "대구 물류단지",
    ],
    "공장": [
        "대구 제1공장", "대구 제2공장", "포항 제1공장", "포항 제2공장", "대구 산업단지", "포항 산업단지",
        "대구 정밀공업", "포항 정밀공업", "대구 금속공업", "포항 금속공업", "대구 화학공장", "포항 화학공장",
        "대구 자동차부품", "포항 자동차부품", "대구 제조", "포항 제조", "대구 공업사", "포항 공업사",
    ],
}

PAGES_PER_KEYWORD = 3
COUNT_PER_PAGE = 100
# generate_portfolio.py는 유형당 최대 40건만 쓴다 — 건축HUB 검증 탈락분 버퍼로 60건 확보되면
# 더 찾지 않고 다음 유형으로 넘어간다(불필요한 V-World geocode 호출 낭비 방지).
CAP_PER_TYPE = 60


def _search_juso(keyword: str, page: int) -> dict:
    params = {
        "confmKey": JUSO_API_KEY,
        "currentPage": str(page),
        "countPerPage": str(COUNT_PER_PAGE),
        "keyword": keyword,
        "resultType": "json",
    }
    url = _JUSO_URL + "?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=15) as resp:
        return json.load(resp)


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

    existing: dict[str, list[dict]] = json.loads(CANDIDATES_PATH.read_text(encoding="utf-8"))
    all_seen_roads: set[str] = {c["road_address"] for items in existing.values() for c in items}

    for ctype, keywords in TYPE_KEYWORDS.items():
        bucket = existing.setdefault(ctype, [])
        added_here = 0
        for kw in keywords:
            if len(bucket) >= CAP_PER_TYPE:
                break
            for page in range(1, PAGES_PER_KEYWORD + 1):
                if len(bucket) >= CAP_PER_TYPE:
                    break
                try:
                    data = _search_juso(kw, page)
                except Exception as exc:  # noqa: BLE001
                    print(f"  [WARN] {kw!r} p{page} 실패: {exc}", file=sys.stderr)
                    time.sleep(1)
                    continue
                common = data.get("results", {}).get("common", {})
                if common.get("errorCode") not in ("0", 0):
                    print(f"  [WARN] {kw!r} p{page} errorCode={common.get('errorCode')} {common.get('errorMessage')}", file=sys.stderr)
                    break
                juso_list = data.get("results", {}).get("juso") or []
                if not juso_list:
                    break
                for item in juso_list:
                    if len(bucket) >= CAP_PER_TYPE:
                        break
                    road = item.get("roadAddr", "")
                    if not road.startswith(_ALLOWED_PREFIXES):
                        continue
                    if road in all_seen_roads:
                        continue
                    all_seen_roads.add(road)

                    try:
                        geocoded = geocode_road_address(road)
                    except VWorldGeocodeError:
                        geocoded = None
                    if geocoded is None:
                        continue

                    bucket.append(
                        {
                            "road_address": road,
                            "lat": geocoded.lat,
                            "lon": geocoded.lon,
                            "label": item.get("bdNm") or road,
                        }
                    )
                    added_here += 1
                    time.sleep(0.08)
                if len(juso_list) < COUNT_PER_PAGE:
                    break
            time.sleep(0.2)
        print(f"{ctype}: +{added_here}건 추가 (누적 {len(bucket)}건)", file=sys.stderr)

    CANDIDATES_PATH.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"저장 완료: {CANDIDATES_PATH}", file=sys.stderr)


if __name__ == "__main__":
    main()
