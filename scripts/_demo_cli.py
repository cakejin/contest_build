"""Week3/Week4 데모 CLI 공통 로직 — argparse/배너/JSON 출력이 두 스크립트에서 완전히
동일해 복붙해두면 한쪽만 고치고 다른 쪽을 잊는 드리프트가 생긴다(플래그 추가·배너
문구 변경 등)."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Callable

from climate_risk.config import DEFAULT_EAL_ITERATIONS, DEFAULT_EAL_SEED

_LOADING_BANNER = (
    "침수위험 SHP 최초 로딩 중 — 프로세스 첫 호출에서 약 75초 소요됩니다. "
    "메모 에이전트는 claude -p를 호출하므로 추가로 5~10초가 걸립니다."
)


def run_demo_cli(run_fn: Callable[..., dict[str, Any]], description: str) -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--address", required=True, help="담보 도로명주소")
    parser.add_argument("--collateral-value", required=True, type=float, help="담보가액(원)")
    parser.add_argument("--region-code", default="47111", help="특보 리플레이 대상 지역코드(기본: 포항시 남구)")
    parser.add_argument("--seed", type=int, default=DEFAULT_EAL_SEED, help="몬테카를로 EAL 시드")
    parser.add_argument(
        "--n-iterations", type=int, default=DEFAULT_EAL_ITERATIONS, help="몬테카를로 반복 횟수"
    )
    args = parser.parse_args()

    print(_LOADING_BANNER, file=sys.stderr)

    result = run_fn(
        address=args.address,
        collateral_value=args.collateral_value,
        region_code=args.region_code,
        seed=args.seed,
        n_iterations=args.n_iterations,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
