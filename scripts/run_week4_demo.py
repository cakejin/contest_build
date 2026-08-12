"""Week4 통합 리허설 CLI — "주소입력→힌남노리플레이→포트폴리오재계산→ESG추천까지
끊김없이 1회 완주"(HANDOVER.md Week4 Done기준)의 실물.

사용 예:
    python scripts/run_week4_demo.py --address "경상북도 포항시 남구 인덕로 27" \
        --collateral-value 500000000
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from _demo_cli import run_demo_cli  # noqa: E402
from climate_risk.graph.week4_demo import run_week4_demo  # noqa: E402


def main() -> None:
    run_demo_cli(
        run_week4_demo, "Week4 통합 리허설: 주소입력→힌남노리플레이→포트폴리오재계산→ESG추천"
    )


if __name__ == "__main__":
    main()
