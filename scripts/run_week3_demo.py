"""Week3 데모 CLI — "주소입력→힌남노리플레이→심사메모" Done기준의 실물.

사용 예:
    python scripts/run_week3_demo.py --address "경상북도 포항시 남구 인덕로 27" \
        --collateral-value 500000000
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from _demo_cli import run_demo_cli  # noqa: E402
from climate_risk.graph.week3_demo import run_week3_demo  # noqa: E402


def main() -> None:
    run_demo_cli(run_week3_demo, "Week3 통합 데모: 주소입력→힌남노리플레이→심사메모")


if __name__ == "__main__":
    main()
