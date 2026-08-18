"""기존 316건에 `insurance_covered` 필드 소급 채우기 — 2026-08-18 스키마 추가분.

`generate_portfolio.py`가 만든 316건은 이 필드가 도입되기 전에 생성됐다(전부 기본값
`None`). 재계산 파이프라인(홍수·건물취약도·EAL)은 다시 돌릴 필요가 없으므로 이 필드만
소급 채운다 — `balance`/`ltv`와 같은 성격의 "은행만 아는 정보"라 근거문헌 없는 잠정
분포(가입 70%)로 합성한다(`schema.py` 주석 참조). 시드 고정으로 재실행해도 동일 결과.
"""

from __future__ import annotations

import dataclasses
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np  # noqa: E402

from climate_risk.config import PORTFOLIO_DATA_PATH  # noqa: E402
from climate_risk.portfolio.loader import load_portfolio, save_portfolio  # noqa: E402

INSURANCE_COVERED_PROB = 0.70  # 잠정치 — 근거문헌 없음, generate_portfolio.py와 동일 정신
INSURANCE_SEED = 2026  # generate_portfolio.py의 FIN_SEED와 동일값 재사용(재현성 목적, 값 자체는 무관)


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

    records = load_portfolio(PORTFOLIO_DATA_PATH)
    rng = np.random.default_rng(INSURANCE_SEED)

    updated = [
        dataclasses.replace(r, insurance_covered=bool(rng.random() < INSURANCE_COVERED_PROB))
        for r in records
    ]
    save_portfolio(updated, PORTFOLIO_DATA_PATH)

    covered = sum(1 for r in updated if r.insurance_covered)
    print(f"{len(updated)}건 중 {covered}건 가입({covered / len(updated):.1%}) — {PORTFOLIO_DATA_PATH}", file=sys.stderr)


if __name__ == "__main__":
    main()
