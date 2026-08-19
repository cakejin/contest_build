"""담보 포트폴리오 거제 확장 — 1단계: 실주소 후보 발굴(V-World POI 검색).

`discover_collateral_addresses.py`(대구·포항 전용)를 건드리지 않고 거제시만 별도로
검색해 별도 파일에 저장한다 — 기존 대구·포항 후보 파일을 덮어쓸 위험을 원천 차단.
방법론은 동일(HANDOVER "실주소만 사용, 무작위 생성 금지" 원칙 — 실존 법인명·건물명이
붙은 POI를 쿼리로 발굴).
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from climate_risk.geocoding.vworld import VWorldGeocodeError, search_place  # noqa: E402

OUT_PATH = Path(__file__).resolve().parents[1] / "data" / "climate-collateral-underwriting-ai" / "curated" / "portfolio" / "_geoje_address_candidates.json"

TYPE_QUERIES: dict[str, dict] = {
    "아파트": {
        "queries": ["거제 아파트", "거제 아파트단지"],
        "category_keywords": ["아파트단지", "주거용공동주택"],
    },
    "공동주택": {
        "queries": ["거제 다세대주택", "거제 연립주택", "거제 빌라"],
        "category_keywords": ["주거용공동주택", "공동주택"],
    },
    "단독주택": {
        "queries": ["거제 단독주택"],
        "category_keywords": [],
    },
    "다가구주택": {
        "queries": ["거제 다가구주택", "거제 원룸"],
        "category_keywords": [],
    },
    "근린생활시설": {
        "queries": ["거제 상가", "거제 근린생활시설"],
        "category_keywords": ["근린생활시설"],
    },
    "업무시설": {
        "queries": ["거제 업무시설", "거제 오피스빌딩", "거제 사옥"],
        "category_keywords": ["업무시설"],
    },
    "창고": {
        "queries": ["거제 창고", "거제 물류센터", "거제 냉동창고"],
        "category_keywords": ["창고"],
    },
    "공장": {
        # 거제는 조선업 밀집지역 — 조선소 관련 키워드도 추가
        "queries": ["거제 공장", "거제 조선소", "거제 조선업", "거제 산업단지"],
        "category_keywords": ["공장"],
    },
}

_ALLOWED_CITY_PREFIXES = ("경상남도 거제시",)


def _road_in_scope(road: str) -> bool:
    return bool(road) and road.startswith(_ALLOWED_CITY_PREFIXES)


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

    all_candidates: dict[str, list[dict]] = {}

    for ctype, spec in TYPE_QUERIES.items():
        seen_parcel: set[str] = set()
        candidates: list[dict] = []
        for q in spec["queries"]:
            try:
                results = search_place(q, size=30)
            except VWorldGeocodeError as exc:
                print(f"  [WARN] {q!r} 검색 실패: {exc}", file=sys.stderr)
                continue
            for r in results:
                if not _road_in_scope(r.road_address):
                    continue
                if spec["category_keywords"] and not any(k in r.category for k in spec["category_keywords"]):
                    continue
                if r.parcel_address in seen_parcel:
                    continue
                seen_parcel.add(r.parcel_address)
                candidates.append(
                    {
                        "title": r.title,
                        "category": r.category,
                        "road_address": r.road_address,
                        "parcel_address": r.parcel_address,
                        "lat": r.lat,
                        "lon": r.lon,
                    }
                )
            time.sleep(0.1)
        all_candidates[ctype] = candidates
        print(f"{ctype}: {len(candidates)}건 후보 확보", file=sys.stderr)

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(all_candidates, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"저장 완료: {OUT_PATH}", file=sys.stderr)


if __name__ == "__main__":
    main()
