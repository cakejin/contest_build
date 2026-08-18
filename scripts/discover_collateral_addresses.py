"""담보 포트폴리오 확장(8종×40건) — 1단계: 실주소 후보 발굴.

HANDOVER.md의 "실주소만 사용, 무작위 생성 금지" 원칙을 지키기 위해, V-World
지명(POI) 검색(`search_place`, type=place)으로 대구광역시·포항시 내 실존 건물/시설을
유형별로 찾는다. 무작위 생성이 아니라 실제 존재하는 법인명·건물명이 붙은 POI를
쿼리로 발굴하는 것 — 결과의 `road_address`가 비어있으면(도로명 미부여) 버린다.

이 스크립트는 후보만 모으고 검증(건축HUB 대조)·데이터 생성은 하지 않는다 —
다음 단계(generate_portfolio.py)가 후보 중 필요한 만큼만 뽑아 실제 파이프라인으로
검증한다. 후보를 넉넉히 모아두는 이유: 건축HUB 매칭 실패·중복 등으로 후보 중
일부는 실사용되지 못하기 때문이다.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from climate_risk.geocoding.vworld import VWorldGeocodeError, search_place  # noqa: E402

OUT_PATH = Path(__file__).resolve().parents[1] / "data" / "climate-collateral-underwriting-ai" / "curated" / "portfolio" / "_address_candidates.json"

# 담보유형 -> (쿼리 목록, category에 이 키워드 중 하나라도 포함돼야 채택)
TYPE_QUERIES: dict[str, dict] = {
    "아파트": {
        "queries": ["대구 아파트", "포항 아파트", "대구 아파트단지", "포항 아파트단지"],
        "category_keywords": ["아파트단지", "주거용공동주택"],
    },
    "공동주택": {
        "queries": ["대구 다세대주택", "대구 연립주택", "포항 다세대주택", "포항 연립주택"],
        "category_keywords": ["주거용공동주택", "공동주택"],
    },
    "단독주택": {
        "queries": ["대구 단독주택", "포항 단독주택"],
        "category_keywords": [],  # 결과가 적으면 category 필터를 느슨하게(빈 리스트=전부 허용)
    },
    "다가구주택": {
        "queries": ["대구 다가구주택", "포항 다가구주택"],
        "category_keywords": [],
    },
    "근린생활시설": {
        "queries": ["대구 상가", "포항 상가", "대구 근린생활시설", "포항 근린생활시설"],
        "category_keywords": ["근린생활시설"],
    },
    "업무시설": {
        "queries": ["대구 업무시설", "포항 업무시설", "대구 오피스빌딩", "포항 오피스빌딩", "대구 사옥", "포항 사옥"],
        "category_keywords": ["업무시설"],
    },
    "창고": {
        "queries": ["대구 창고", "포항 창고", "대구 물류센터", "포항 물류센터"],
        "category_keywords": ["창고"],
    },
    "공장": {
        "queries": ["대구 공장", "포항 공장", "포항 철강", "포항 제철", "대구 산업단지 공장"],
        "category_keywords": ["공장"],
    },
}

_ALLOWED_CITY_PREFIXES = ("대구광역시", "경상북도 포항시")


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
