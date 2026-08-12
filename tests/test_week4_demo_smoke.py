"""graph/week4_demo.py — Week4 Done기준 "주소입력→힌남노리플레이→포트폴리오재계산→
ESG추천까지 끊김없이 1회 완주"의 실물 증거. tests/test_week3_demo_smoke.py와 동일한
monkeypatch 체인을 재사용해 실제 네트워크·SHP 호출 없이 검증한다."""

from climate_risk.agents import memo_agent
from climate_risk.graph import week3_demo, week4_demo
from tests.test_week3_demo_smoke import _patch_common


def test_week4_demo_adds_esg_eval_and_redteam_keys(monkeypatch):
    _patch_common(monkeypatch)
    monkeypatch.setattr(
        memo_agent,
        "call_claude_structured",
        lambda prompt, schema_path, model="sonnet": {
            "sections": [{"text": "정상 문장입니다.", "citations": ["flood:test.shp"]}]
        },
    )
    monkeypatch.setattr(week4_demo, "run_week3_demo", week3_demo.run_week3_demo)

    result = week4_demo.run_week4_demo("테스트주소", collateral_value=5.0e8)

    for key in ("esg_recommendations", "eval_metrics", "redteam_checks"):
        assert key in result, key

    # trigger_event=True(실제 힌남노 데이터)이므로 portfolio_batch가 있지만 fake_portfolio_agent가
    # alerts=[]를 반환하므로(test_week3_demo_smoke._fake_portfolio_agent) ESG 추천도 빈 리스트.
    assert result["esg_recommendations"] == []

    assert result["eval_metrics"]["eal_reproducibility"]["reproducible"] is True
    assert result["eval_metrics"]["coverage_gate"]["failed"] == 0

    redteam_scenarios = [c["scenario"] for c in result["redteam_checks"]]
    assert redteam_scenarios == ["1", "2", "4", "9"]
    assert all(c["passed"] for c in result["redteam_checks"])


def test_week4_demo_short_circuits_on_geocode_failure(monkeypatch):
    monkeypatch.setattr(week3_demo, "geocode_road_address", lambda address: None)

    result = week4_demo.run_week4_demo("존재하지않는주소", collateral_value=1.0)

    assert result["error"] == "주소 인식 실패 — 주소 수정 요청"
    assert "esg_recommendations" not in result
