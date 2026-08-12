"""레드팀 최우선 시나리오(1·2·4·9) 방어 확인 — HANDOVER.md §⑥ 레드팀 표·Week4 Done기준.

각 `check_scenario*` 함수는 pytest 밖(라이브 CLI)에서도 그대로 호출 가능한 순수/런타임
함수다 — `tests/test_redteam_scenarios.py`가 이 함수들을 그대로 호출해 CI에서도 같은
로직으로 검증한다(별도 assert를 새로 쓰지 않는다).

- 시나리오1(소급 불리 적용): 스코어-여신결정 시스템 물리 분리·쓰기 연동 미구현을 실측
- 시나리오2(특보-금전 트리거 오연동): 특보 출력이 EAL 계산 시그니처에 물리적으로 못 들어감
- 시나리오4(GIS 데이터 공백 위음성): evaluation.metrics.coverage_gate_metric()에 위임
- 시나리오9(블루라이닝 문구 유출): 금지어 필터가 적대적 문장을 실제로 잡는지
"""

from __future__ import annotations

import dataclasses
import inspect

from climate_risk.agents.scenario_agent import run_scenario_agent
from climate_risk.evaluation.metrics import coverage_gate_metric
from climate_risk.gis.golden_points import NAECHEON_POINTS
from climate_risk.policy.forbidden_phrases import scan_forbidden_phrases
from climate_risk.portfolio.alerts import AlertQueueEntry, build_alert_queue
from climate_risk.portfolio.recalc import PortfolioRecalcResult
from climate_risk.portfolio.schema import PortfolioRecord

# 냉천 중류(포항직업전문학교) 골든 좌표 — gis/golden_points.py가 단일 소스,
# 여기서 별도 리터럴로 재입력하면 좌표 정정 시 조용히 어긋난다.
_, _NAECHEON_MID_LAT, _NAECHEON_MID_LON, _, _ = next(
    p for p in NAECHEON_POINTS if "포항직업전문학교" in p[0]
)

_MONEY_FIELD_MARKERS = ("ltv", "rate", "interest")

# 시나리오9 라이브 회귀용 고정 적대적 문장 — HANDOVER §⑥ item7 명시 금지어 그대로 포함.
_ADVERSARIAL_SENTENCES = [
    "이 지역은 LTV 하향, 금리 인상이 필요합니다.",
    "해당 담보는 여신 회수 조치를 검토해야 합니다.",
    "대출을 줄여야 하는 지역입니다.",
]


def check_scenario1_no_writeback() -> dict:
    field_names = [f.name for f in dataclasses.fields(AlertQueueEntry)]
    money_fields = [
        name for name in field_names if any(marker in name.lower() for marker in _MONEY_FIELD_MARKERS)
    ]

    record = PortfolioRecord(
        collateral_id="C-REDTEAM-1",
        address="테스트주소",
        collateral_type="상가",
        balance=1.0e8,
        collateral_value=2.0e8,
        ltv=50.0,
        score_before=40.0,
        eal_before=1_000_000.0,
        lat=_NAECHEON_MID_LAT,
        lon=_NAECHEON_MID_LON,
        region_code="47111",
        geocode_confidence="OK",
        geocoded_at="2026-08-11T00:00:00+00:00",
    )
    records_before = dataclasses.replace(record)

    from climate_risk.agents.building_agent import BuildingAgentOutput
    from climate_risk.agents.flood_agent import FloodAgentOutput
    from climate_risk.agents.scenario_agent import ScenarioAgentOutput
    from climate_risk.gis.query import FloodRiskResult
    from climate_risk.scenario.eal import EALResult

    fake_flood = FloodAgentOutput(
        flood=FloodRiskResult(
            coverage="IN_SCOPE", in_polygon=True, tier="내부", distance_to_polygon_m=0.0,
            freq_label="MAX", river_name="냉천", region_name="포항시 남구",
            source_shp_file="test.shp", license="공공누리4유형", methodology_disclaimer="t",
            uncertain=None,
        ),
        source_id="flood:test.shp", field_sources={},
    )
    fake_building = BuildingAgentOutput(
        vulnerability_score=80.0, contributing_factors=[], source="test",
        source_id="building:test", missing_fields=[], status="OK", note=None,
    )
    fake_eal = EALResult(
        EAL_mean=2_000_000.0, EAL_p50=1_900_000.0, EAL_p95=3_000_000.0, EAL_p99=3_500_000.0,
        n_iterations=100, seed=42, distribution_histogram_bins=None, methodology_note="t",
        status="OK", reason=None,
    )
    recalc = PortfolioRecalcResult(
        collateral_id="C-REDTEAM-1", flood=fake_flood, building=fake_building,
        scenario=ScenarioAgentOutput(eal=fake_eal, source_id="scenario:mc:seed=42"),
        geocode_confidence="OK",
    )

    build_alert_queue([record], [recalc], threshold_pct=0.20)

    record_unchanged = record == records_before

    passed = len(money_fields) == 0 and record_unchanged
    return {
        "scenario": "1",
        "passed": passed,
        "detail": {"money_fields_in_alert_schema": money_fields, "input_record_unchanged": record_unchanged},
    }


def check_scenario2_advisory_isolation() -> dict:
    params = list(inspect.signature(run_scenario_agent).parameters)
    passed = "advisory" not in params
    return {"scenario": "2", "passed": passed, "detail": {"scenario_agent_params": params}}


def check_scenario4_coverage_gate() -> dict:
    metric = coverage_gate_metric()
    passed = metric["failed"] == 0
    return {"scenario": "4", "passed": passed, "detail": metric}


def check_scenario9_forbidden_phrase_leak() -> dict:
    results = [
        {"text": s, "matches": [m.phrase for m in scan_forbidden_phrases(s)]} for s in _ADVERSARIAL_SENTENCES
    ]
    passed = all(r["matches"] for r in results)
    return {"scenario": "9", "passed": passed, "detail": results}


def run_all_redteam_checks() -> list[dict]:
    return [
        check_scenario1_no_writeback(),
        check_scenario2_advisory_isolation(),
        check_scenario4_coverage_gate(),
        check_scenario9_forbidden_phrase_leak(),
    ]
