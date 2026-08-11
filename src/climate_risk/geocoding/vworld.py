"""V-World Geocoder 2.0 래퍼 — 담보 주소(도로명주소) → WGS84 좌표.

HANDOVER.md §2: "위경도 | V-World Geocoder 실시간 호출 결과 | 실키 검증 완료".
담보 주소 입력 → 좌표 변환은 홍수 에이전트(gis/query.py)의 첫 단계 입력이다.

search_place()는 지오코더(도로명주소 전용)로는 다리·지명 같은 POI를 찾을 수 없어
별도로 둔 지명 검색(type=place) 경로 — Week1 스파이크에서 신천 판정보류 지점(다리 이름)
좌표를 확보하는 데 썼다(gis/coverage.py KNOWN_UNCERTAIN_POINTS 참조). 담보 주소는
도로명주소로 들어오므로 실제 담보 지오코딩 경로는 geocode_road_address()다.
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from dataclasses import dataclass

from climate_risk.config import VWORLD_API_KEY

_BASE_URL = "https://api.vworld.kr/req"


class VWorldGeocodeError(RuntimeError):
    """V-World API가 OK가 아닌 status를 반환했을 때."""


@dataclass(frozen=True)
class GeocodedAddress:
    lat: float
    lon: float
    refined_text: str
    input_address: str


@dataclass(frozen=True)
class PlaceMatch:
    title: str
    category: str
    lat: float
    lon: float
    parcel_address: str
    road_address: str


def get_json(path: str, params: dict[str, str]) -> dict:
    """V-World `{_BASE_URL}/{path}` GET + JSON 파싱 — 이 모듈 밖(building/address_resolver.py의
    역지오코딩 호출 등)에서도 같은 V-World HTTP 계약을 재사용하도록 공개해둔다."""
    url = f"{_BASE_URL}/{path}?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=10) as resp:
        return json.load(resp)


def geocode_road_address(address: str) -> GeocodedAddress | None:
    """도로명주소 → WGS84 좌표. 매칭 실패(NOT_FOUND) 시 None — 예외로 취급하지 않는다.

    HANDOVER §2 데모 데이터 스펙: 매칭 실패는 담보 레코드 단위 폴백 경로를 타야 하므로
    (건축HUB 매칭 실패 시 합성 폴백과 동일한 패턴) 호출자가 명시적으로 처리해야 한다.
    """
    data = get_json(
        "address",
        {
            "service": "address",
            "request": "getcoord",
            "version": "2.0",
            "crs": "epsg:4326",
            "address": address,
            "refine": "true",
            "simple": "false",
            "format": "json",
            "type": "road",
            "key": VWORLD_API_KEY,
        },
    )
    status = data["response"]["status"]
    if status == "NOT_FOUND":
        return None
    if status != "OK":
        raise VWorldGeocodeError(f"V-World address API status={status} address={address!r}")

    result = data["response"]["result"]
    return GeocodedAddress(
        lat=float(result["point"]["y"]),
        lon=float(result["point"]["x"]),
        refined_text=data["response"]["refined"]["text"],
        input_address=address,
    )


def search_place(query: str, size: int = 20) -> list[PlaceMatch]:
    """지명(POI) 검색 — 도로명주소가 없는 다리·지형지물 이름 조회용(type=place).

    담보 주소 지오코딩 경로가 아니다 — Week1 신천 판정보류 지점처럼 "이름은 알지만
    도로명주소가 없는" 지점을 1회성으로 찾을 때만 쓴다.
    """
    data = get_json(
        "search",
        {
            "service": "search",
            "request": "search",
            "version": "2.0",
            "crs": "epsg:4326",
            "size": str(size),
            "page": "1",
            "query": query,
            "type": "place",
            "format": "json",
            "key": VWORLD_API_KEY,
        },
    )
    status = data["response"]["status"]
    if status == "NOT_FOUND":
        return []
    if status != "OK":
        raise VWorldGeocodeError(f"V-World search API status={status} query={query!r}")

    items = data["response"]["result"]["items"]
    return [
        PlaceMatch(
            title=item["title"],
            category=item["category"],
            lat=float(item["point"]["y"]),
            lon=float(item["point"]["x"]),
            parcel_address=item["address"]["parcel"],
            road_address=item["address"]["road"],
        )
        for item in items
    ]
