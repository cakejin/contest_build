"""합성 포트폴리오 레코드 형태 — HANDOVER.md §③ "초기 구현은 30~50건 소표본"의 실체.

`score_before`/`eal_before`는 이 시드 파일에 미리 박아둔 "최근 평가 시점 스냅샷"이다 —
특보 트리거가 EAL을 직접 움직이면 안 되므로(CLAUDE.md 규칙2), before는 고정값이고
after는 재계산 시점의 신선한 산출값이다(portfolio/recalc.py 참조).

lat/lon/region_code/geocode_confidence/geocoded_at은 이 파일에 처음엔 None으로 들어있고,
scripts/geocode_portfolio.py(1회성 warm-up)가 채운다 — 매 실행마다 지오코딩 API를
다시 부르지 않기 위한 캐시다.
"""

from __future__ import annotations

from dataclasses import dataclass, replace


@dataclass(frozen=True)
class PortfolioRecord:
    collateral_id: str
    address: str
    collateral_type: str
    balance: float
    collateral_value: float
    ltv: float
    score_before: float
    eal_before: float
    lat: float | None = None
    lon: float | None = None
    region_code: str | None = None
    geocode_confidence: str | None = None  # None(미시도) | "OK" | "FAILED"
    geocoded_at: str | None = None

    def with_geocode(
        self,
        lat: float | None,
        lon: float | None,
        region_code: str | None,
        geocode_confidence: str,
        geocoded_at: str,
    ) -> "PortfolioRecord":
        return replace(
            self,
            lat=lat,
            lon=lon,
            region_code=region_code,
            geocode_confidence=geocode_confidence,
            geocoded_at=geocoded_at,
        )
