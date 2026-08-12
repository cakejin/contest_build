"""평가 대시보드 최소셋 — HANDOVER.md §4.4 9개 지표 중 최소셋(인용률·커버리지게이트
통과)에 EAL 재현성·금지어 부재를 더한 4개. 전부 기존 파이프라인 산출값을 그대로 읽거나
기존 순수 함수를 재호출할 뿐, 새 판정 로직을 만들지 않는다(memo/citation_gate.py,
gis/query.py, gis/coverage.py, scenario/eal.py가 이미 진실의 원천).

이 모듈은 pytest 밖(라이브 CLI, Week4 통합 리허설)에서도 그대로 호출 가능한 런타임
함수로 설계했다 — 회귀 테스트(tests/test_coverage_gate.py 등)와 이 모듈이 같은
gis/golden_points.py 골든셋을 공유해 두 곳이 조용히 어긋나지 않게 한다.
"""

from __future__ import annotations

from climate_risk.agents.building_agent import BuildingAgentOutput
from climate_risk.agents.flood_agent import FloodAgentOutput
from climate_risk.agents.scenario_agent import run_scenario_agent
from climate_risk.config import DEFAULT_EAL_ITERATIONS, DEFAULT_EAL_SEED
from climate_risk.gis.coverage import match_known_uncertain_point
from climate_risk.gis.golden_points import NAECHEON_POINTS, SINCHEON_POINTS
from climate_risk.gis.query import query_flood_risk
from climate_risk.memo.schema import MemoAgentOutput
from climate_risk.policy.forbidden_phrases import scan_forbidden_phrases


def citation_metric(memo: MemoAgentOutput) -> dict:
    accepted = len(memo.sections)
    rejected = len(memo.rejected_sentences)
    return {
        "accepted": accepted,
        "rejected": rejected,
        "rate": 1.0 - memo.citation_failure_rate,
    }


def coverage_gate_metric() -> dict:
    """골든 좌표셋(gis/golden_points.py) 전체를 실제로 질의해 기대값과 대조한다 —
    tests/test_coverage_gate.py의 회귀 assertion을 pytest 밖에서도 재실행 가능한
    형태로 노출한 것(레드팀 시나리오4 체크가 이 함수를 그대로 위임 호출한다)."""
    failures: list[dict] = []
    all_points = NAECHEON_POINTS + SINCHEON_POINTS
    for label, lat, lon, expected_in_polygon, expected_tier in all_points:
        result = query_flood_risk(lat, lon)
        ok = (
            result.coverage == "IN_SCOPE"
            and result.in_polygon is expected_in_polygon
            and result.tier == expected_tier
        )
        if not ok:
            failures.append(
                {
                    "label": label,
                    "expected": {"in_polygon": expected_in_polygon, "tier": expected_tier},
                    "actual": {"coverage": result.coverage, "in_polygon": result.in_polygon, "tier": result.tier},
                }
            )

    total = len(all_points)
    passed = total - len(failures)
    return {
        "total": total,
        "passed": passed,
        "failed": len(failures),
        "pass_rate": passed / total if total else 0.0,
        "failures": failures,
    }


def eal_reproducibility_metric(
    flood: FloodAgentOutput,
    building: BuildingAgentOutput,
    collateral_value: float,
    seed: int = DEFAULT_EAL_SEED,
    n_iterations: int = DEFAULT_EAL_ITERATIONS,
) -> dict:
    """동일 seed로 시나리오 에이전트를 2회 재실행해 EAL 분포가 바이트 단위로
    재현되는지 확인한다 — HANDOVER "절대 축소 금지" 항목을 런타임에서도 실측."""
    run1 = run_scenario_agent(flood, building, collateral_value, seed=seed, n_iterations=n_iterations)
    run2 = run_scenario_agent(flood, building, collateral_value, seed=seed, n_iterations=n_iterations)
    reproducible = run1.eal == run2.eal
    return {
        "reproducible": reproducible,
        "seed": seed,
        "EAL_mean": run1.eal.EAL_mean,
    }


def forbidden_phrase_absence_metric(memo: MemoAgentOutput) -> dict:
    """인용검증·금지어 게이트를 이미 통과한 memo.sections에 다시 한번 금지어 스캔을
    돌린다 — 게이트 통과 후에도 실제로 깨끗한지 이중검증 결과를 증거로 남긴다."""
    matches: list[dict] = []
    for section in memo.sections:
        for m in scan_forbidden_phrases(section.text):
            matches.append({"text": section.text, "phrase": m.phrase})
    return {"clean": len(matches) == 0, "matches": matches}


def coverage_uncertain_point_metric() -> dict:
    """신천 4개 판정보류 지점이 실제로 match_known_uncertain_point에 걸리는지,
    남구 확정 지점·냉천 3지점은 걸리지 않는지 런타임 확인(coverage_gate_metric과
    별도 축 — '위험 없음'과 '판정보류'를 혼동하지 않는지가 검증 대상)."""
    mismatches: list[dict] = []
    for label, lat, lon, _, _ in NAECHEON_POINTS:
        if match_known_uncertain_point(lat, lon) is not None:
            mismatches.append({"label": label, "expected_uncertain": False})
    for label, lat, lon, _, _ in SINCHEON_POINTS[:1]:
        if match_known_uncertain_point(lat, lon) is not None:
            mismatches.append({"label": label, "expected_uncertain": False})
    for label, lat, lon, _, _ in SINCHEON_POINTS[1:]:
        if match_known_uncertain_point(lat, lon) is None:
            mismatches.append({"label": label, "expected_uncertain": True})
    return {"clean": len(mismatches) == 0, "mismatches": mismatches}
