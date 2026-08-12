"""포트폴리오 지오코딩 캐시 — 매 배치 재계산마다 V-World를 다시 부르지 않기 위한
1회성 워밍업 로직(scripts/geocode_portfolio.py가 호출부).

`geocode_road_address`/`run_flood_agent`를 이 모듈 이름공간으로 임포트해둔다 — 테스트가
`monkeypatch.setattr(geocode_cache, "geocode_road_address", ...)` 식으로 실제 네트워크
호출 없이 검증할 수 있는 seam이다.

실패해도 크래시하지 않는다("데이터 없음≠위험 없음"과 같은 정신 — 지오코딩 실패를
"이 담보는 안전"으로 둔갑시키지 않고 `geocode_confidence="FAILED"`로 명시한다).
"""

from __future__ import annotations

from datetime import datetime, timezone

from climate_risk.agents.flood_agent import run_flood_agent
from climate_risk.config import SHP_FILENAME_TO_REGION_CODE
from climate_risk.geocoding.vworld import VWorldGeocodeError, geocode_road_address
from climate_risk.portfolio.schema import PortfolioRecord

_CONFIDENCE_OK = "OK"
_CONFIDENCE_FAILED = "FAILED"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_geocoded(records: list[PortfolioRecord]) -> list[PortfolioRecord]:
    """이미 lat/lon이 있거나 이전 시도에서 FAILED로 확정된 레코드는 재호출하지
    않는다(idempotent) — 아직 시도하지 않은(geocode_confidence=None) 레코드만
    지오코딩 + region_code 역조회를 시도한다."""
    result: list[PortfolioRecord] = []
    for record in records:
        if record.lat is not None and record.lon is not None:
            result.append(record)
            continue
        if record.geocode_confidence == _CONFIDENCE_FAILED:
            result.append(record)
            continue

        try:
            geocoded = geocode_road_address(record.address)
        except VWorldGeocodeError:
            geocoded = None

        if geocoded is None:
            result.append(
                record.with_geocode(
                    lat=None,
                    lon=None,
                    region_code=None,
                    geocode_confidence=_CONFIDENCE_FAILED,
                    geocoded_at=_now_iso(),
                )
            )
            continue

        flood = run_flood_agent(geocoded.lat, geocoded.lon)
        region_code = SHP_FILENAME_TO_REGION_CODE.get(flood.flood.source_shp_file or "")

        result.append(
            record.with_geocode(
                lat=geocoded.lat,
                lon=geocoded.lon,
                region_code=region_code,
                geocode_confidence=_CONFIDENCE_OK,
                geocoded_at=_now_iso(),
            )
        )
    return result
