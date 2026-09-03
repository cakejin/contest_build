import json

from climate_risk.advisory.schema import AdvisoryEvent
from climate_risk.agents.advisory_agent import AdvisoryAgentOutput
from climate_risk.agents.building_agent import BuildingAgentOutput
from climate_risk.agents.flood_agent import FloodAgentOutput
from climate_risk.agents.portfolio_agent import run_portfolio_agent
from climate_risk.agents.scenario_agent import ScenarioAgentOutput
from climate_risk.portfolio import recalc
from climate_risk.scenario.eal import EALResult


def _write_portfolio(tmp_path):
    records = [
        {
            "collateral_id": "COL-001",
            "address": "테스트1",
            "collateral_type": "아파트",
            "balance": 100.0,
            "collateral_value": 200.0,
            "ltv": 0.5,
            "score_before": 50.0,
            "eal_before": 1000.0,
            "lat": 35.0,
            "lon": 129.0,
            "region_code": "47111",
            "geocode_confidence": "OK",
            "geocoded_at": "2026-08-11T00:00:00+00:00",
        },
        {
            "collateral_id": "COL-002",
            "address": "테스트2",
            "collateral_type": "아파트",
            "balance": 100.0,
            "collateral_value": 200.0,
            "ltv": 0.5,
            "score_before": 50.0,
            "eal_before": 1000.0,
            "lat": None,
            "lon": None,
            "region_code": None,
            "geocode_confidence": "FAILED",
            "geocoded_at": "2026-08-11T00:00:00+00:00",
        },
        {
            "collateral_id": "COL-003",
            "address": "테스트3",
            "collateral_type": "아파트",
            "balance": 100.0,
            "collateral_value": 200.0,
            "ltv": 0.5,
            "score_before": 50.0,
            "eal_before": 1000.0,
            "lat": 35.8,
            "lon": 128.6,
            "region_code": "27200",
            "geocode_confidence": "OK",
            "geocoded_at": "2026-08-11T00:00:00+00:00",
        },
    ]
    path = tmp_path / "portfolio.json"
    path.write_text(json.dumps({"records": records}, ensure_ascii=False), encoding="utf-8")
    return path


def _advisory_output():
    event = AdvisoryEvent(
        event_id="e1",
        issued_at="2022-09-06T06:00:00+09:00",
        time_precision="approximate",
        event_type="특보",
        warning_type="태풍경보",
        description="테스트",
        source_url="https://example.com",
        target_region_text="테스트",
    )
    return AdvisoryAgentOutput(
        active_warnings=[{"type": "태풍경보", "issued_at": event.issued_at, "source_url": event.source_url}],
        trigger_event=True,
        mode="replay",
        timeline=[event],
        region_code="47111",
        status="OK",
        source_id="advisory:curated:test",
    )


def test_portfolio_agent_end_to_end_with_mocked_agents(monkeypatch, in_scope_flood, tmp_path):
    def fake_flood(lat, lon, **kwargs):
        return FloodAgentOutput(flood=in_scope_flood, source_id="flood:test.shp", field_sources={})

    def fake_building(**kwargs):
        return BuildingAgentOutput(
            vulnerability_score=70.0,
            contributing_factors=[],
            source="test",
            source_id="building:test",
            missing_fields=[],
            status="OK",
            note=None,
        )

    def fake_scenario(flood, building, collateral_value, seed, n_iterations):
        eal = EALResult(
            EAL_mean=1500.0,
            EAL_p50=1200.0,
            EAL_p95=3000.0,
            EAL_p99=4000.0,
            n_iterations=n_iterations,
            seed=seed,
            distribution_histogram_bins=None,
            methodology_note="test",
            status="OK",
            reason=None,
        )
        return ScenarioAgentOutput(eal=eal, source_id=f"scenario:mc:seed={seed}")

    monkeypatch.setattr(recalc, "run_flood_agent", fake_flood)
    monkeypatch.setattr(recalc, "run_building_agent", fake_building)
    monkeypatch.setattr(recalc, "run_scenario_agent", fake_scenario)

    portfolio_path = _write_portfolio(tmp_path)
    alert_log_path = tmp_path / "alerts.jsonl"
    severity_alert_log_path = tmp_path / "severity_alerts.jsonl"

    result = run_portfolio_agent(
        _advisory_output(),
        portfolio_path=portfolio_path,
        threshold_pct=0.20,
        alert_log_path=alert_log_path,
        severity_alert_log_path=severity_alert_log_path,
    )

    assert result.total_records == 3
    assert result.matched_count == 1  # COL-001만 region_code=47111
    assert result.skipped_ungeocoded_count == 1  # COL-002 (FAILED)
    assert result.other_region_count == 1  # COL-003 (27200)
    assert result.matched_count + result.skipped_ungeocoded_count + result.other_region_count == 3

    # eal_before=1000 -> eal_after=1500: +50% > 20% 임계치 -> 알림 발생
    assert len(result.alerts) == 1
    assert result.alerts[0].collateral_id == "COL-001"

    assert alert_log_path.exists()
    logged = [json.loads(line) for line in alert_log_path.read_text(encoding="utf-8").splitlines()]
    assert len(logged) == 1

    # _advisory_output()의 이벤트는 severity_level 미지정(None)이라 심각도 채널은
    # EAL 채널(위 alerts)과 별개로 비어 있어야 한다 — 두 채널이 서로 다른 신호에서
    # 나온다는 걸 여기서도 확인.
    assert result.severity_alerts == []
