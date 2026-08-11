"""Week2 데모 CLI — 주소 1건 → EAL 분포+tier+vulnerability_score JSON 출력.

HANDOVER.md Week2 Done 기준의 실물: "주소 1건 → EAL 분포(mean/p50/p95/p99) + tier +
vulnerability_score가 JSON으로 출력, 동일 seed 재실행 시 동일 값 재현"을 실제로
시연하는 명령.

사용 예:
    python scripts/run_assessment.py --address "경상북도 포항시 남구 인덕로 27" \
        --collateral-value 500000000
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from climate_risk.config import DEFAULT_EAL_ITERATIONS, DEFAULT_EAL_SEED  # noqa: E402
from climate_risk.graph.run import run_pipeline  # noqa: E402


def main() -> None:
    # Windows에서 stdout이 실제 콘솔이 아닌 파이프/리다이렉트로 연결되면 Python이
    # UTF-8이 아닌 로컬 코드페이지로 인코딩을 추정해, 한글 출력이 깨진 바이트로
    # 저장되는 문제가 실측으로 확인됐다(cp949로도 디코드 안 되는 이중 손상 — 실행
    # 검증 중 발견). 인코딩을 명시적으로 UTF-8로 고정한다.
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="담보 주소 1건 기후리스크 계량 평가")
    parser.add_argument("--address", required=True, help="담보 도로명주소")
    parser.add_argument("--collateral-value", required=True, type=float, help="담보가액(원)")
    parser.add_argument("--seed", type=int, default=DEFAULT_EAL_SEED, help="몬테카를로 EAL 시드")
    parser.add_argument(
        "--n-iterations", type=int, default=DEFAULT_EAL_ITERATIONS, help="몬테카를로 반복 횟수"
    )
    args = parser.parse_args()

    print(
        "침수위험 SHP 최초 로딩 중 — 프로세스 첫 호출에서 약 75초 소요됩니다 "
        "(이후 호출은 캐시로 즉시 처리, DEV_LOG.md 2026-08-09 참조)",
        file=sys.stderr,
    )

    result = run_pipeline(
        address=args.address,
        collateral_value=args.collateral_value,
        seed=args.seed,
        n_iterations=args.n_iterations,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
