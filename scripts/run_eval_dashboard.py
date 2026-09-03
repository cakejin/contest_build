"""평가 대시보드 최소셋 CLI — HANDOVER.md §4.4 지표 중 인용률·커버리지게이트 통과에
EAL 재현성·금지어 부재를 더한 4개를 JSON으로 출력한다.

`--address`를 주면 실제 파이프라인을 1회 실행해 인용률·EAL재현성·금지어부재까지 계산하고,
`--address`가 없으면 좌표 불필요한 커버리지게이트(골든셋)만 실행한다.

사용 예:
    python scripts/run_eval_dashboard.py --address "경상북도 포항시 남구 인덕로 27" \
        --collateral-value 500000000
    python scripts/run_eval_dashboard.py   # 커버리지게이트만
    python scripts/run_eval_dashboard.py --alert-validation   # + 알림 트리거 후보 4분면(오프라인 캐시 필요)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from climate_risk.agents.building_agent import run_building_agent  # noqa: E402
from climate_risk.agents.flood_agent import run_flood_agent  # noqa: E402
from climate_risk.agents.memo_agent import run_memo_agent  # noqa: E402
from climate_risk.agents.scenario_agent import run_scenario_agent  # noqa: E402
from climate_risk.config import DEFAULT_EAL_ITERATIONS, DEFAULT_EAL_SEED  # noqa: E402
from climate_risk.evaluation.alert_validation import AlertValidationDataError  # noqa: E402
from climate_risk.evaluation.metrics import (  # noqa: E402
    alert_trigger_precision_metric,
    citation_metric,
    coverage_gate_metric,
    coverage_uncertain_point_metric,
    eal_reproducibility_metric,
    forbidden_phrase_absence_metric,
)
from climate_risk.geocoding.vworld import geocode_road_address  # noqa: E402


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="평가 대시보드 최소셋: 인용률·커버리지게이트·EAL재현성·금지어부재")
    parser.add_argument("--address", help="담보 도로명주소(생략 시 커버리지게이트만 실행)")
    parser.add_argument("--collateral-value", type=float, help="담보가액(원) — --address와 함께 필요")
    parser.add_argument("--seed", type=int, default=DEFAULT_EAL_SEED)
    parser.add_argument("--n-iterations", type=int, default=DEFAULT_EAL_ITERATIONS)
    parser.add_argument(
        "--alert-validation",
        action="store_true",
        help="재심사 알림 트리거 후보 4분면 검증(HANDOVER §4.4 알림 정밀도)을 포함 — 오프라인 캐시 필요(scripts/fetch_alert_validation_cache.py)",
    )
    args = parser.parse_args()

    metrics: dict = {
        "coverage_gate": coverage_gate_metric(),
        "coverage_uncertain_points": coverage_uncertain_point_metric(),
    }

    if args.alert_validation:
        try:
            metrics["alert_trigger_precision"] = alert_trigger_precision_metric()
        except AlertValidationDataError as exc:
            # 캐시가 없으면 조용히 빼지 않고 이유를 남긴다(설계원칙1과 같은 정신).
            metrics["alert_trigger_precision"] = {"error": str(exc)}

    if args.address:
        if args.collateral_value is None:
            parser.error("--address를 주면 --collateral-value도 필요합니다")

        geocoded = geocode_road_address(args.address)
        if geocoded is None:
            metrics["error"] = "주소 인식 실패 — 주소 수정 요청"
            print(json.dumps(metrics, ensure_ascii=False, indent=2, default=str))
            return

        flood = run_flood_agent(geocoded.lat, geocoded.lon)
        building = run_building_agent(lat=geocoded.lat, lon=geocoded.lon)
        scenario = run_scenario_agent(
            flood, building, args.collateral_value, seed=args.seed, n_iterations=args.n_iterations
        )
        memo = run_memo_agent(flood, building, scenario)

        metrics["citation"] = citation_metric(memo)
        metrics["forbidden_phrase_absence"] = forbidden_phrase_absence_metric(memo)
        metrics["eal_reproducibility"] = eal_reproducibility_metric(
            flood, building, args.collateral_value, seed=args.seed, n_iterations=args.n_iterations
        )

    print(json.dumps(metrics, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
