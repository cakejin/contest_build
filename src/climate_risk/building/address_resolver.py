"""주소/좌표/PNU → 건축HUB `getBrTitleInfo` 파라미터(sigunguCd·bjdongCd·platGbCd·bun·ji) 해석.

`getBrTitleInfo`는 자유 주소를 받지 않는다 — 5개 코드가 필수다. 이 사실 자체가 연구
단계에서 검증되지 않았던 부분이라(DEV_LOG.md 2026-08-11 참조), Week2 구현 착수 시
라이브 호출로 다음을 확인했다:

- Week1이 쓰는 V-World 주소 API의 **순방향**(`request=getcoord`) 응답은 법정동코드가
  비어있거나(road 타입) 도로명코드가 들어가(역지오코딩 road 타입) 쓸 수 없었다.
- 대신 **역지오코딩**(`request=getAddress`, `type=parcel`, 좌표 입력)의
  `structure.level4LC`가 정확히 10자리(`sigunguCd(5)+bjdongCd(5)`)로 나오고,
  `structure.level5`가 지번("222-5")으로 나온다 — 이 조합이 `getBrTitleInfo`를
  실제로 통과함을 확인했다(building/brhub.py 체크포인트 참조).
- 애초 계획했던 `req/data` feature query·수동 법정동코드 테이블 폴백은 이 경로가
  깨끗하게 풀려 불필요해졌다(DEV_LOG.md 참조) — 이 모듈은 그 두 폴백을 구현하지 않는다.

이 모듈은 `geocoding/vworld.py`의 함수 계약을 바꾸지 않는다 — road 주소→좌표 변환은
그 모듈의 `geocode_road_address()`를 그대로 재사용하고, 좌표→법정동코드 역지오코딩만
이 모듈이 독자적으로 호출한다(같은 VWORLD_API_KEY, 새 자격증명 불필요).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from climate_risk.config import VWORLD_API_KEY
from climate_risk.geocoding.vworld import VWorldGeocodeError, geocode_road_address, get_json

RESOLUTION_PNU = "PNU"
RESOLUTION_REVERSE_GEOCODE = "VWORLD_REVERSE_GEOCODE_PARCEL"


@dataclass(frozen=True)
class AdminCodeMatch:
    sigungu_cd: str
    bjdong_cd: str
    plat_gb_cd: str
    bun: str
    ji: str
    resolution_path: str
    source_id: str


def _leading_digits(text: str) -> str:
    """지번 조각의 숫자 접두만 추출 — "1617-1천"처럼 비숫자 접미사가 붙는 경우가
    실측으로 확인됐다(DEV_LOG.md 2026-08-11, 신천 남구·봉덕동 좌표). 매치 없으면 "0"."""
    match = re.match(r"\d+", text)
    return match.group(0) if match else "0"


def resolve_from_pnu(pnu: str) -> AdminCodeMatch:
    """19자리 PNU를 직접 분해 — 네트워크 호출 0회.

    PNU 자릿수 구성: sigunguCd(5)+bjdongCd(5)+platGbCd(1)+bun(4)+ji(4) = 19.
    """
    if len(pnu) != 19 or not pnu.isdigit():
        raise ValueError(f"PNU는 숫자 19자리여야 합니다: {pnu!r}")
    return AdminCodeMatch(
        sigungu_cd=pnu[0:5],
        bjdong_cd=pnu[5:10],
        plat_gb_cd=pnu[10:11],
        bun=pnu[11:15],
        ji=pnu[15:19],
        resolution_path=RESOLUTION_PNU,
        source_id=f"pnu:{pnu}",
    )


def _reverse_geocode_parcel(lat: float, lon: float) -> dict | None:
    """좌표 -> V-World 역지오코딩(지번 타입). 매칭 없으면 None, 비정상 status면 예외.

    HTTP GET + JSON 파싱은 geocoding/vworld.py의 get_json()을 그대로 재사용한다(같은
    V-World API 계약이라 중복 구현할 이유가 없다) — 비정상 status도 그 모듈의
    VWorldGeocodeError로 통일해, 호출자(building_agent.py)가 V-World 계열 실패를
    하나의 예외 타입으로 캐치할 수 있게 한다.
    """
    data = get_json(
        "address",
        {
            "service": "address",
            "request": "getAddress",
            "version": "2.0",
            "crs": "epsg:4326",
            "point": f"{lon},{lat}",
            "format": "json",
            "type": "parcel",
            "key": VWORLD_API_KEY,
        },
    )

    status = data["response"]["status"]
    if status == "NOT_FOUND":
        return None
    if status != "OK":
        raise VWorldGeocodeError(
            f"V-World reverse geocode(parcel) status={status} lat={lat} lon={lon}"
        )

    results = data["response"].get("result") or []
    if not results:
        return None
    return results[0]


def resolve_admin_codes(
    lat: float | None = None,
    lon: float | None = None,
    address: str | None = None,
    pnu: str | None = None,
) -> AdminCodeMatch | None:
    """주소/좌표/PNU 중 하나로부터 건축HUB 코드 5종을 해석한다.

    전부 실패하면 예외가 아니라 None을 반환한다(geocoding/vworld.py의 "예상된
    부재→None" 관례와 동일 — 주소를 못 찾는 것은 오류가 아니라 정상적인 결과값이다).
    """
    if pnu is not None:
        return resolve_from_pnu(pnu)

    if lat is None or lon is None:
        if address is None:
            return None
        geocoded = geocode_road_address(address)
        if geocoded is None:
            return None
        lat, lon = geocoded.lat, geocoded.lon

    parcel = _reverse_geocode_parcel(lat, lon)
    if parcel is None:
        return None

    structure = parcel["structure"]
    level4lc = structure.get("level4LC", "")
    if len(level4lc) < 10:
        # 도로명 타입 역지오코딩이 섞여 들어오는 등 예상 밖 응답 — 해석 불가로 처리.
        return None

    sigungu_cd = level4lc[:5]
    bjdong_cd = level4lc[5:10]

    level5 = structure.get("level5", "")
    parts = level5.split("-")
    bun = _leading_digits(parts[0]).zfill(4) if parts and parts[0] else "0000"
    ji = _leading_digits(parts[1]).zfill(4) if len(parts) > 1 else "0000"

    # "산" 지목 판정: 응답 text의 마지막 토큰 앞에 "산"이 단독으로 오면 산 지번
    # (예: "... 인덕동 산 1-1"). platGbCd="1"(산)은 실호출로 검증하지 못했다 —
    # 데모 대상 주소는 전부 대지라 실무 영향은 낮음(DEV_LOG.md 2026-08-11 참조).
    text_parts = parcel.get("text", "").split()
    plat_gb_cd = "1" if len(text_parts) >= 2 and text_parts[-2] == "산" else "0"

    return AdminCodeMatch(
        sigungu_cd=sigungu_cd,
        bjdong_cd=bjdong_cd,
        plat_gb_cd=plat_gb_cd,
        bun=bun,
        ji=ji,
        resolution_path=RESOLUTION_REVERSE_GEOCODE,
        source_id=f"vworld_reverse_geocode:{sigungu_cd}{bjdong_cd}{plat_gb_cd}{bun}{ji}",
    )
