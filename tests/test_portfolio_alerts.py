from climate_risk.agents.building_agent import BuildingAgentOutput
from climate_risk.agents.flood_agent import FloodAgentOutput
from climate_risk.agents.scenario_agent import ScenarioAgentOutput
from climate_risk.portfolio.alerts import AlertQueueEntry, build_alert_queue
from climate_risk.portfolio.recalc import PortfolioRecalcResult
from climate_risk.portfolio.schema import PortfolioRecord
from climate_risk.scenario.eal import EALResult


def _record(collateral_id, eal_before):
    return PortfolioRecord(
        collateral_id=collateral_id,
        address="테스트",
        collateral_type="아파트",
        balance=100.0,
        collateral_value=200.0,
        ltv=0.5,
        score_before=50.0,
        eal_before=eal_before,
        region_code="47111",
        geocode_confidence="OK",
    )


def _recalc_result(collateral_id, eal_after, score_after=60.0):
    building = BuildingAgentOutput(
        vulnerability_score=score_after,
        contributing_factors=[],
        source="test",
        source_id="building:test",
        missing_fields=[],
        status="OK",
        note=None,
    )
    eal = EALResult(
        EAL_mean=eal_after,
        EAL_p50=eal_after,
        EAL_p95=eal_after,
        EAL_p99=eal_after,
        n_iterations=100,
        seed=42,
        distribution_histogram_bins=None,
        methodology_note="test",
        status="OK",
        reason=None,
    )
    scenario = ScenarioAgentOutput(eal=eal, source_id="scenario:mc:seed=42")
    return PortfolioRecalcResult(
        collateral_id=collateral_id,
        flood=None,  # 이 테스트는 flood/building 세부값을 안 씀
        building=building,
        scenario=scenario,
        geocode_confidence="OK",
    )


def test_change_above_threshold_generates_alert():
    records = [_record("COL-001", eal_before=1000.0)]
    results = [_recalc_result("COL-001", eal_after=1300.0)]  # +30% > 기본 임계치 20%

    alerts = build_alert_queue(records, results, threshold_pct=0.20)

    assert len(alerts) == 1
    assert alerts[0].collateral_id == "COL-001"
    assert abs(alerts[0].EAL_change_pct - 0.30) < 1e-9


def test_change_below_threshold_no_alert():
    records = [_record("COL-001", eal_before=1000.0)]
    results = [_recalc_result("COL-001", eal_after=1050.0)]  # +5% < 20%

    alerts = build_alert_queue(records, results, threshold_pct=0.20)

    assert alerts == []


def test_zero_change_no_alert():
    records = [_record("COL-001", eal_before=1000.0)]
    results = [_recalc_result("COL-001", eal_after=1000.0)]

    alerts = build_alert_queue(records, results, threshold_pct=0.20)

    assert alerts == []


def test_insufficient_input_eal_after_none_is_not_alerted():
    records = [_record("COL-001", eal_before=1000.0)]
    result = _recalc_result("COL-001", eal_after=1300.0)
    insufficient_eal = EALResult(
        EAL_mean=None,
        EAL_p50=None,
        EAL_p95=None,
        EAL_p99=None,
        n_iterations=100,
        seed=42,
        distribution_histogram_bins=None,
        methodology_note="test",
        status="INSUFFICIENT_INPUT",
        reason="입력 데이터 불충분",
    )
    result = PortfolioRecalcResult(
        collateral_id="COL-001",
        flood=None,
        building=result.building,
        scenario=ScenarioAgentOutput(eal=insufficient_eal, source_id="scenario:mc:seed=42"),
        geocode_confidence="OK",
    )

    alerts = build_alert_queue(records, [result], threshold_pct=0.20)

    assert alerts == []


def test_alert_entry_has_no_ltv_or_rate_fields():
    """규칙3(소급 불리 적용 금지)의 회귀 방지 — 알림 스키마에 LTV/금리/회수 관련 필드가
    구조적으로 존재하지 않는지 고정한다."""
    field_names = {f.name for f in AlertQueueEntry.__dataclass_fields__.values()}

    forbidden_keywords = {"ltv", "rate", "recall", "interest"}
    for field_name in field_names:
        assert not any(kw in field_name.lower() for kw in forbidden_keywords), field_name

    expected = {
        "collateral_id",
        "score_before",
        "score_after",
        "EAL_before",
        "EAL_after",
        "EAL_change_pct",
        "threshold",
        "geocode_confidence",
        "insurance_covered",  # 2026-08-18 추가 — HANDOVER §③ "보험 커버리지 미확인" 문구 근거화
    }
    assert field_names == expected
