"""Week4 통합 리허설 CLI — "주소입력→힌남노리플레이→포트폴리오재계산→ESG추천까지
끊김없이 1회 완주"(HANDOVER.md Week4 Done기준)의 실물.

사용 예:
    python scripts/run_week4_demo.py --address "경상북도 포항시 남구 인덕로 27" \
        --collateral-value 500000000
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from climate_risk.config import DEFAULT_EAL_ITERATIONS, DEFAULT_EAL_SEED  # noqa: E402
from climate_risk.graph.week4_demo import run_week4_demo  # noqa: E402


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(
        description="Week4 통합 리허설: 주소입력→힌남노리플레이→포트폴리오재계산→ESG추천"
    )
    parser.add_argument("--address", required=True, help="담보 도로명주소")
    parser.add_argument("--collateral-value", required=True, type=float, help="담보가액(원)")
    parser.add_argument("--region-code", default="47111", help="특보 리플레이 대상 지역코드(기본: 포항시 남구)")
    parser.add_argument("--seed", type=int, default=DEFAULT_EAL_SEED, help="몬테카를로 EAL 시드")
    parser.add_argument(
        "--n-iterations", type=int, default=DEFAULT_EAL_ITERATIONS, help="몬테카를로 반복 횟수"
    )
    args = parser.parse_args()

    print(
        "침수위험 SHP 최초 로딩 중 — 프로세스 첫 호출에서 약 75초 소요됩니다. "
        "메모 에이전트는 claude -p를 호출하므로 추가로 5~10초가 걸립니다.",
        file=sys.stderr,
    )

    result = run_week4_demo(
        address=args.address,
        collateral_value=args.collateral_value,
        region_code=args.region_code,
        seed=args.seed,
        n_iterations=args.n_iterations,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
