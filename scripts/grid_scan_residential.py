"""담보 포트폴리오 확장 — 2단계: 단독주택/다가구주택/공동주택은 POI 검색으로 거의
안 잡힌다(이름 붙은 시설이 아니라서, discover_collateral_addresses.py 결과 6~7건뿐).

대신 대구·포항의 실제 주거밀집 법정동 좌표를 격자로 훑어 각 지점을 V-World
역지오코딩(대지 지번 해석) -> 건축HUB getBrTitleInfo로 라이브 조회한다 — 좌표는
임의 생성이지만 그 좌표에 실제로 존재하는 건물의 실제 등록정보만 채택하므로
"실주소만 사용, 무작위 생성 금지" 원칙 위반이 아니다(격자점 자체가 결과가 아니라
그 지점에 걸리는 진짜 지번을 찾는 도구일 뿐).
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from climate_risk.building.address_resolver import resolve_admin_codes  # noqa: E402
from climate_risk.building.brhub import BrHubError, fetch_br_title_info  # noqa: E402
from climate_risk.geocoding.vworld import VWorldGeocodeError, get_json  # noqa: E402

OUT_PATH = Path(__file__).resolve().parents[1] / "data" / "climate-collateral-underwriting-ai" / "curated" / "portfolio" / "_grid_scan_candidates.json"

# 대구·포항 실제 주거밀집 법정동 중심좌표(POI 조사·기존 40건 데이터에서 실증된 동네) —
# 원룸촌(다가구주택 밀집)으로 알려진 대학가 인근도 포함.
CENTERS = [
    ("대구 남구 대명동", 35.8400, 128.5670),
    ("대구 남구 봉덕동", 35.8430, 128.5980),
    ("대구 중구 남산동", 35.8590, 128.5860),
    ("대구 동구 신암동", 35.8790, 128.6160),
    ("대구 수성구 중동", 35.8390, 128.6110),
    ("대구 북구 구암동", 35.9300, 128.5560),
    ("대구 북구 복현동(경북대 인근 원룸촌)", 35.8940, 128.6110),
    ("대구 달서구 신당동(계명대 인근 원룸촌)", 35.8500, 128.4970),
    ("포항 남구 인덕동", 35.9867, 129.3977),
    ("포항 남구 상도동", 36.0300, 129.3700),
    ("포항 북구 흥해읍", 36.0900, 129.3450),
]

GRID_N = 5  # N x N
STEP_DEG = 0.0018  # 약 200m 간격


def _reverse_geocode(lat: float, lon: float):
    from climate_risk.config import VWORLD_API_KEY

    data = get_json(
        "address",
        {
            "service": "address",
            "request": "getAddress",
            "version": "2.0",
            "crs": "epsg:4326",
            "point": f"{lon},{lat}",
            "format": "json",
            "type": "road",
            "key": VWORLD_API_KEY,
        },
    )
    if data["response"]["status"] != "OK":
        return None
    results = data["response"].get("result") or []
    return results[0]["text"] if results else None


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

    seen_parcel: set[str] = set()
    found: list[dict] = []

    for name, base_lat, base_lon in CENTERS:
        hits_here = 0
        for i in range(GRID_N):
            for j in range(GRID_N):
                lat = base_lat + i * STEP_DEG
                lon = base_lon + j * STEP_DEG
                try:
                    admin = resolve_admin_codes(lat=lat, lon=lon)
                    if admin is None:
                        continue
                    if admin.source_id in seen_parcel:
                        continue
                    info = fetch_br_title_info(admin)
                except (VWorldGeocodeError, BrHubError, OSError, ValueError, KeyError) as exc:
                    print(f"    [WARN] {lat:.4f},{lon:.4f}: {type(exc).__name__}", file=sys.stderr)
                    time.sleep(0.5)
                    continue
                if info is None or info.main_purps_cd_nm is None:
                    continue
                purps = info.main_purps_cd_nm
                if not any(k in purps for k in ("단독주택", "다가구주택", "다중주택", "공동주택")):
                    continue
                seen_parcel.add(admin.source_id)
                try:
                    road = _reverse_geocode(lat, lon)
                except VWorldGeocodeError:
                    road = None
                found.append(
                    {
                        "lat": lat,
                        "lon": lon,
                        "main_purps_cd_nm": purps,
                        "grnd_flr_cnt": info.grnd_flr_cnt,
                        "road_address": road,
                        "area": name,
                    }
                )
                hits_here += 1
                time.sleep(0.12)
        print(f"{name}: {hits_here}건", file=sys.stderr)

    OUT_PATH.write_text(json.dumps(found, ensure_ascii=False, indent=2), encoding="utf-8")
    from collections import Counter

    print(f"총 {len(found)}건 저장: {OUT_PATH}", file=sys.stderr)
    print(Counter(f["main_purps_cd_nm"] for f in found), file=sys.stderr)


if __name__ == "__main__":
    main()
