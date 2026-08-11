"""합성 포트폴리오 1회성 지오코딩 warm-up — HANDOVER.md §4.1 포트폴리오 배치 재계산 전제.

매 데모 실행마다 V-World/홍수 에이전트를 다시 부르지 않도록, 이 스크립트를 1회
실행해 lat/lon/region_code를 파일에 캐시해둔다(portfolio/geocode_cache.py 참조).
지오코딩 실패 레코드도 "FAILED"로 명시 기록되고 재실행해도 이미 기록된 레코드는
건드리지 않는다(idempotent).

사용 예:
    python scripts/geocode_portfolio.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from climate_risk.config import PORTFOLIO_DATA_PATH  # noqa: E402
from climate_risk.portfolio.geocode_cache import ensure_geocoded  # noqa: E402
from climate_risk.portfolio.loader import load_portfolio, save_portfolio  # noqa: E402


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

    print(f"포트폴리오 로딩: {PORTFOLIO_DATA_PATH}", file=sys.stderr)
    records = load_portfolio(PORTFOLIO_DATA_PATH)

    already_done = sum(1 for r in records if r.lat is not None)
    print(f"총 {len(records)}건 중 {already_done}건 이미 지오코딩 완료 — 나머지만 조회합니다.", file=sys.stderr)

    updated = ensure_geocoded(records)
    save_portfolio(updated, PORTFOLIO_DATA_PATH)

    ok = sum(1 for r in updated if r.geocode_confidence == "OK")
    failed = sum(1 for r in updated if r.geocode_confidence == "FAILED")
    print(f"완료: OK={ok}건, FAILED={failed}건, 파일 저장: {PORTFOLIO_DATA_PATH}")


if __name__ == "__main__":
    main()
