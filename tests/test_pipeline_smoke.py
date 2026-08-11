"""graph/pipeline.py·graph/run.py 스모크 테스트 — 실제 SHP 75초 로딩·실API 호출 회피.

flood_agent/building_agent를 monkeypatch해 그래프가 실제로 fan-out(둘 다 START에서
병렬 실행 가능)/fan-in(scenario는 둘 다 끝나야 실행)하는지, 지오코딩 실패 시 그래프
자체가 실행되지 않는지만 검증한다.
"""

from climate_risk.agents.building_agent import BuildingAgentOutput
from climate_risk.agents.flood_agent import FloodAgentOutput
from climate_risk.geocoding.vworld import GeocodedAddress
from climate_risk.gis.query import FloodRiskResult
from climate_risk.graph import pipeline as pipeline_module
from climate_risk.graph import run as run_module

FAKE_GEOCODED = GeocodedAddress(
    lat=35.98768, lon=129.39979, refined_text="테스트 정제주소", input_address="테스트주소"
)

FAKE_FLOOD_OUTPUT = FloodAgentOutput(
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
    field_sources={"coverage": "flood:test.shp"},
)

FAKE_BUILDING_OUTPUT = BuildingAgentOutput(
    vulnerability_score=55.0,
    contributing_factors=[],
    source="test",
    source_id="building:test",
    missing_fields=[],
    status="OK",
    note=None,
)


def test_graph_fans_out_and_fans_in(monkeypatch):
    flood_calls = []
    building_calls = []

    def fake_flood_agent(lat, lon, **kwargs):
        flood_calls.append((lat, lon))
        return FAKE_FLOOD_OUTPUT

    def fake_building_agent(**kwargs):
        building_calls.append(kwargs)
        return FAKE_BUILDING_OUTPUT

    monkeypatch.setattr(pipeline_module, "run_flood_agent", fake_flood_agent)
    monkeypatch.setattr(pipeline_module, "run_building_agent", fake_building_agent)

    graph = pipeline_module.build_graph()
    final_state = graph.invoke(
        {
            "address": "테스트주소",
            "collateral_value": 5.0e8,
            "geocoded": FAKE_GEOCODED,
        }
    )

    assert flood_calls == [(FAKE_GEOCODED.lat, FAKE_GEOCODED.lon)]
    assert building_calls == [{"lat": FAKE_GEOCODED.lat, "lon": FAKE_GEOCODED.lon}]
    assert final_state["flood"] is FAKE_FLOOD_OUTPUT
    assert final_state["building"] is FAKE_BUILDING_OUTPUT
    # scenario 노드는 flood·building 둘 다 끝난 뒤에만 실행 가능 — 결과가 있다는 것 자체가
    # fan-in이 실제로 걸렸다는 증거(LangGraph가 두 선행 엣지를 전부 기다림).
    assert final_state["scenario"].eal.status == "OK"


def test_run_pipeline_short_circuits_on_geocode_failure(monkeypatch):
    monkeypatch.setattr(run_module, "geocode_road_address", lambda address: None)

    def _fail_if_called():
        raise AssertionError("지오코딩 실패 시 그래프가 실행되면 안 된다")

    monkeypatch.setattr(run_module, "build_graph", _fail_if_called)

    result = run_module.run_pipeline("존재하지않는주소", collateral_value=1.0)

    assert result["error"] == "주소 인식 실패 — 주소 수정 요청"


def test_run_pipeline_returns_json_ready_dict_on_success(monkeypatch):
    monkeypatch.setattr(run_module, "geocode_road_address", lambda address: FAKE_GEOCODED)
    monkeypatch.setattr(pipeline_module, "run_flood_agent", lambda lat, lon, **kwargs: FAKE_FLOOD_OUTPUT)
    monkeypatch.setattr(pipeline_module, "run_building_agent", lambda **kwargs: FAKE_BUILDING_OUTPUT)

    result = run_module.run_pipeline("테스트주소", collateral_value=5.0e8, seed=42)

    assert result["flood"]["flood"]["tier"] == "내부"
    assert result["building"]["vulnerability_score"] == 55.0
    assert result["scenario"]["eal"]["status"] == "OK"
    assert result["scenario"]["eal"]["seed"] == 42
