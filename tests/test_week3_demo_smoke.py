"""graph/week3_demo.py — Week3 Done기준 "주소입력→힌남노리플레이→심사메모"의 실물 증거.

전체 monkeypatch 체인(지오코딩·홍수·건물·시나리오·claude CLI)을 사용해 실제 네트워크·SHP
호출 없이 검증한다. 핵심은 "존재하지 않는 source_id를 인용한 잘못된 LLM mock"을 주입해도
memo.rejected_sentences가 채워지고 그 문장이 memo.sections에서 실제로 빠지는 것 —
이게 인용검증 게이트가 실제로 작동한다는 최종 증거다.
"""

from climate_risk.agents import memo_agent
from climate_risk.agents.building_agent import BuildingAgentOutput
from climate_risk.agents.flood_agent import FloodAgentOutput
from climate_risk.geocoding.vworld import GeocodedAddress
from climate_risk.graph import week3_demo
from climate_risk.scenario.eal import EALResult

_FAKE_GEOCODED = GeocodedAddress(
    lat=35.98768, lon=129.39979, refined_text="테스트 정제주소", input_address="테스트주소"
)


def _fake_flood(lat, lon, **kwargs):
    from climate_risk.gis.query import FloodRiskResult

    return FloodAgentOutput(
        flood=FloodRiskResult(
            coverage="IN_SCOPE",
            in_polygon=True,
            tier="내부",
            distance_to_polygon_m=0.0,
            freq_label="MAX",
            river_name="냉천",
            region_name="포항시 남구",
            source_shp_file="test.shp",
            license="공공누리4유형",
            methodology_disclaimer="test",
            uncertain=None,
        ),
        source_id="flood:test.shp",
        field_sources={"tier": "flood:test.shp"},
    )


def _fake_building(**kwargs):
    return BuildingAgentOutput(
        vulnerability_score=55.0,
        contributing_factors=[],
        source="test",
        source_id="building:test",
        missing_fields=[],
        status="OK",
        note=None,
    )


def _fake_scenario(flood, building, collateral_value, seed, n_iterations):
    from climate_risk.agents.scenario_agent import ScenarioAgentOutput

    eal = EALResult(
        EAL_mean=1000.0,
        EAL_p50=900.0,
        EAL_p95=2000.0,
        EAL_p99=2500.0,
        n_iterations=n_iterations,
        seed=seed,
        distribution_histogram_bins=None,
        methodology_note="test",
        status="OK",
        reason=None,
    )
    return ScenarioAgentOutput(eal=eal, source_id=f"scenario:mc:seed={seed}")


def _fake_portfolio_agent(advisory, portfolio_path=None, seed=None, n_iterations=None):
    from climate_risk.agents.portfolio_agent import PortfolioBatchResult

    _fake_portfolio_agent.calls.append({"seed": seed, "n_iterations": n_iterations})
    return PortfolioBatchResult(
        region_code=advisory.region_code,
        total_records=0,
        matched_count=0,
        skipped_ungeocoded_count=0,
        other_region_count=0,
        recalculated=[],
        alerts=[],
        severity_alerts=[],
        disclosure="test",
    )


_fake_portfolio_agent.calls = []


def _patch_common(monkeypatch):
    """week3_demo가 직접 부르는 지오코딩/3에이전트만 목킹한다. run_portfolio_agent는
    별도로 목킹한다 — 안 그러면 portfolio.recalc의 실제 3에이전트가 SHP 콜드로딩(약 75초)
    +건축HUB 실호출 6건을 라이브로 돌린다(test_portfolio_agent_smoke.py가 이미 그 경로를
    별도로 검증하므로 여기서 다시 라이브로 돌 필요가 없다)."""
    monkeypatch.setattr(week3_demo, "geocode_road_address", lambda address: _FAKE_GEOCODED)
    monkeypatch.setattr(week3_demo, "run_flood_agent", _fake_flood)
    monkeypatch.setattr(week3_demo, "run_building_agent", _fake_building)
    monkeypatch.setattr(week3_demo, "run_scenario_agent", _fake_scenario)
    monkeypatch.setattr(week3_demo, "run_portfolio_agent", _fake_portfolio_agent)


def test_week3_demo_returns_all_expected_top_level_keys(monkeypatch):
    _patch_common(monkeypatch)
    monkeypatch.setattr(
        memo_agent,
        "call_claude_structured",
        lambda prompt, schema_path, model="sonnet": {
            "sections": [{"text": "정상 문장입니다.", "citations": ["flood:test.shp"]}]
        },
    )

    _fake_portfolio_agent.calls.clear()
    result = week3_demo.run_week3_demo(
        "테스트주소", collateral_value=5.0e8, seed=999, n_iterations=1234
    )

    for key in ("address", "geocoded", "advisory", "flood", "building", "scenario", "memo", "portfolio_batch", "coverage_label"):
        assert key in result, key

    assert result["advisory"]["trigger_event"] is True  # 실제 힌남노 큐레이션 데이터 사용
    assert result["portfolio_batch"] is not None  # trigger_event=True이므로 배치가 실행됨

    # 회귀 방지: 사용자가 지정한 --seed/--n-iterations가 포트폴리오 배치 재계산에도
    # 전달돼야 한다(단일 담보 시나리오에만 반영되고 배치는 기본값으로 도는 버그가 있었다).
    assert _fake_portfolio_agent.calls == [{"seed": 999, "n_iterations": 1234}]


def test_week3_demo_forwards_target_floor_to_building_agent(monkeypatch):
    """HANDOVER §⑧ — target_floor가 주어지면 run_building_agent에 flood 결과와 함께
    그대로 전달돼야 floor_exposure를 계산할 수 있다."""
    _patch_common(monkeypatch)
    monkeypatch.setattr(
        memo_agent,
        "call_claude_structured",
        lambda prompt, schema_path, model="sonnet": {
            "sections": [{"text": "정상 문장입니다.", "citations": ["flood:test.shp"]}]
        },
    )

    building_calls = []

    def spy_building(**kwargs):
        building_calls.append(kwargs)
        return _fake_building(**kwargs)

    monkeypatch.setattr(week3_demo, "run_building_agent", spy_building)

    target_floor = {"floor_type": "지상", "floor_no": 2}
    result = week3_demo.run_week3_demo(
        "테스트주소", collateral_value=5.0e8, target_floor=target_floor
    )

    assert "error" not in result
    assert building_calls[0]["target_floor"] == target_floor
    assert building_calls[0]["flood"] is not None


def test_week3_demo_short_circuits_on_geocode_failure(monkeypatch):
    monkeypatch.setattr(week3_demo, "geocode_road_address", lambda address: None)

    result = week3_demo.run_week3_demo("존재하지않는주소", collateral_value=1.0)

    assert result["error"] == "주소 인식 실패 — 주소 수정 요청"


def test_week3_demo_rejects_hallucinated_citation_and_excludes_it_from_memo(monkeypatch):
    """Done 기준의 최종 증거 — 존재하지 않는 source_id를 인용한 문장이 memo.sections에서
    실제로 빠지고 rejected_sentences에 남는지 end-to-end로 확인한다."""
    _patch_common(monkeypatch)
    monkeypatch.setattr(
        memo_agent,
        "call_claude_structured",
        lambda prompt, schema_path, model="sonnet": {
            "sections": [
                {"text": "근거 있는 문장 1입니다.", "citations": ["flood:test.shp"]},
                {"text": "근거 있는 문장 2입니다.", "citations": ["building:test"]},
                {"text": "근거 있는 문장 3입니다.", "citations": ["scenario:mc:seed=42"]},
                {"text": "근거 있는 문장 4입니다.", "citations": ["flood:test.shp"]},
                {"text": "지어낸 근거를 인용한 문장입니다.", "citations": ["flood:존재하지않는파일.shp"]},
            ]
        },
    )

    result = week3_demo.run_week3_demo("테스트주소", collateral_value=5.0e8)

    memo = result["memo"]
    section_texts = [s["text"] for s in memo["sections"]]
    assert "지어낸 근거를 인용한 문장입니다." not in section_texts
    assert memo["fallback_used"] is False  # 실패율 1/5=20% < 임계치 30%, 전체 폴백은 아님
    assert len(memo["rejected_sentences"]) == 1
    assert memo["rejected_sentences"][0]["reason"] == "UNKNOWN_SOURCE_ID"
