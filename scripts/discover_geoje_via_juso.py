"""담보 포트폴리오 거제 확장 — 2단계: 도로명주소 검색API(JUSO)로 보완 발굴.

`discover_geoje_addresses.py`(V-World POI)가 "이름 붙은 시설" 위주라 단독주택 등은
거의 안 잡힌다(실측: 2건뿐) — JUSO 검색으로 건물명 패턴 기반 후보를 추가한다.
`discover_via_juso.py`(대구·포항 전용)와 동일 로직이나 완전히 별도 파일에 저장해
기존 대구·포항 후보 파일을 건드리지 않는다.
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

CANDIDATES_PATH = Path(__file__).resolve().parents[1] / "data" / "climate-collateral-underwriting-ai" / "curated" / "portfolio" / "_geoje_address_candidates.json"

_JUSO_URL = "https://business.juso.go.kr/addrlink/addrLinkApi.do"
_ALLOWED_PREFIXES = ("경상남도 거제시",)

TYPE_KEYWORDS: dict[str, list[str]] = {
    "아파트": ["거제 아파트"],
    "공동주택": ["거제 빌라", "거제 연립주택", "거제 다세대주택"],
    "단독주택": ["거제 단독주택", "거제 주택"],
    "다가구주택": ["거제 다가구주택", "거제 원룸텔", "거제 하우스"],
    "근린생활시설": ["거제 상가"],
    "업무시설": ["거제 오피스텔", "거제 사옥", "거제 비즈니스센터"],
    "창고": ["거제 물류창고", "거제 냉동창고", "거제 유통센터", "거제 냉장창고", "거제 보관소"],
    "공장": ["거제 제1공장", "거제 제2공장", "거제 조선", "거제 공업사", "거제 산업단지"],
}

PAGES_PER_KEYWORD = 3
COUNT_PER_PAGE = 100
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
