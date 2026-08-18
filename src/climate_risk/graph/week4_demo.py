"""Week4 통합 리허설 엔트리포인트 — HANDOVER.md Week4 Done기준 "주소입력→힌남노리플레이
→포트폴리오재계산→ESG추천까지 끊김없이 1회 완주"의 실물.

`run_week3_demo()`를 그대로 감싸고(하위 호환 — 기존 키 제거/변경 없음) ESG 추천·평가
지표·레드팀 체크 3개를 덧붙일 뿐이다. 새 판정 로직은 만들지 않는다.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from climate_risk.agents.building_agent import BuildingAgentOutput
from climate_risk.agents.flood_agent import FloodAgentOutput
from climate_risk.config import (
    DEFAULT_EAL_ITERATIONS,
    DEFAULT_EAL_SEED,
    HINNAMNO_TIMELINE_PATH,
    PORTFOLIO_DATA_PATH,
)
from climate_risk.evaluation.metrics import (
    citation_metric,
    coverage_gate_metric,
    coverage_uncertain_point_metric,
    eal_reproducibility_metric,
    forbidden_phrase_absence_metric,
)
from climate_risk.gis.query import FloodRiskResult
from climate_risk.graph.week3_demo import OnStage, run_week3_demo
from climate_risk.memo.schema import MemoAgentOutput, MemoSection, RejectedSentence
from climate_risk.policy.esg_recommendations import (
    build_esg_recommendations,
    count_insurance_unconfirmed,
)
from climate_risk.policy.redteam_checks import run_all_redteam_checks

# EAL 재현성은 특정 주소의 실시간 지오코딩·건축HUB 결과가 아니라 몬테카를로 엔진
# 자체의 성질이다(scenario/eal.py — 같은 seed는 항상 같은 난수 시퀀스). 매 리허설마다
# 이 체크를 위해 지오코딩·건축HUB API를 추가로 호출하지 않도록, tests/conftest.py
# in_scope_flood와 동일한 패턴의 고정 IN_SCOPE 픽스처를 재사용한다.
_EAL_CHECK_FLOOD = FloodAgentOutput(
    flood=FloodRiskResult(
        coverage="IN_SCOPE", in_polygon=True, tier="내부", distance_to_polygon_m=0.0,
        freq_label="MAX", river_name="냉천", region_name="포항시 남구",
        source_shp_file="RFM_SGG_RGN_47111_MAX.shp", license="공공누리4유형",
        methodology_disclaimer="eal_reproducibility_check", uncertain=None,
    ),
    source_id="flood:eal_reproducibility_check", field_sources={},
)
_EAL_CHECK_BUILDING = BuildingAgentOutput(
    vulnerability_score=55.0, contributing_factors=[], source="eal_reproducibility_check",
    source_id="building:eal_reproducibility_check", missing_fields=[], status="OK", note=None,
)


def _memo_dataclass_from_dict(memo_dict: dict) -> MemoAgentOutput:
    return MemoAgentOutput(
        sections=[MemoSection(**s) for s in memo_dict["sections"]],
        rejected_sentences=[RejectedSentence(**r) for r in memo_dict["rejected_sentences"]],
        citation_failure_rate=memo_dict["citation_failure_rate"],
        fallback_used=memo_dict["fallback_used"],
        source_id=memo_dict["source_id"],
        disclosure=memo_dict["disclosure"],
    )


def run_week4_demo(
    address: str,
    collateral_value: float,
    region_code: str = "47111",
    portfolio_path: Path = PORTFOLIO_DATA_PATH,
    timeline_path: Path = HINNAMNO_TIMELINE_PATH,
    mode: str = "replay",
    seed: int = DEFAULT_EAL_SEED,
    n_iterations: int = DEFAULT_EAL_ITERATIONS,
    on_stage: OnStage | None = None,
    target_floor: dict | None = None,
) -> dict[str, Any]:
    result = run_week3_demo(
        address=address,
        collateral_value=collateral_value,
        region_code=region_code,
        portfolio_path=portfolio_path,
        timeline_path=timeline_path,
        mode=mode,
        seed=seed,
        n_iterations=n_iterations,
        on_stage=on_stage,
        target_floor=target_floor,
    )
    if "error" in result:
        return result

    memo = _memo_dataclass_from_dict(result["memo"])

    esg_recommendations = []
    insurance_unconfirmed_count = 0
    portfolio_batch = result.get("portfolio_batch")
    if portfolio_batch is not None:
        alerts = portfolio_batch["alerts"]
        esg_recommendations = [
            {"collateral_id": r.collateral_id, "actions": r.actions}
            for r in build_esg_recommendations(alerts)
        ]
        # HANDOVER §③ "보험 커버리지 미확인 N건" — 알림 화면 헤드라인 숫자.
        insurance_unconfirmed_count = count_insurance_unconfirmed(alerts)

    eval_metrics = {
        "citation": citation_metric(memo),
        "forbidden_phrase_absence": forbidden_phrase_absence_metric(memo),
        "eal_reproducibility": eal_reproducibility_metric(
            _EAL_CHECK_FLOOD, _EAL_CHECK_BUILDING, collateral_value, seed=seed, n_iterations=n_iterations
        ),
        "coverage_gate": coverage_gate_metric(),
        "coverage_uncertain_points": coverage_uncertain_point_metric(),
    }

    result["esg_recommendations"] = esg_recommendations
    result["insurance_unconfirmed_count"] = insurance_unconfirmed_count
    result["eval_metrics"] = eval_metrics
    result["redteam_checks"] = run_all_redteam_checks()
    return result
