"""graph/pipeline.py·graph/run.py 스모크 테스트 — 실제 SHP 75초 로딩·실API 호출 회피.

flood_agent/building_agent를 monkeypatch해 그래프가 flood→building→scenario 순서로
실행되는지(building이 floor_exposure 계산을 위해 flood 결과를 받는지, HANDOVER §⑧),
지오코딩 실패 시 그래프 자체가 실행되지 않는지를 검증한다.
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


def test_graph_runs_flood_before_building_and_feeds_scenario(monkeypatch):
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
    # building_agent가 flood 결과를 받아야 HANDOVER §⑧ floor_exposure를 계산할 수 있다
    # (target_floor 미입력이므로 여기선 flood만 확인 — floor_exposure 계산 자체는
    # test_pipeline_floor_exposure_wiring이 별도로 검증).
    assert building_calls == [
        {"lat": FAKE_GEOCODED.lat, "lon": FAKE_GEOCODED.lon, "target_floor": None, "flood": FAKE_FLOOD_OUTPUT}
    ]
    assert final_state["flood"] is FAKE_FLOOD_OUTPUT
    assert final_state["building"] is FAKE_BUILDING_OUTPUT
    assert final_state["scenario"].eal.status == "OK"


def test_graph_passes_target_floor_through_to_building_agent(monkeypatch):
    building_calls = []

    def fake_building_agent(**kwargs):
        building_calls.append(kwargs)
        return FAKE_BUILDING_OUTPUT

    monkeypatch.setattr(pipeline_module, "run_flood_agent", lambda lat, lon, **kwargs: FAKE_FLOOD_OUTPUT)
    monkeypatch.setattr(pipeline_module, "run_building_agent", fake_building_agent)

    graph = pipeline_module.build_graph()
    target_floor = {"floor_type": "지상", "floor_no": 2}
    graph.invoke(
        {
            "address": "테스트주소",
            "collateral_value": 5.0e8,
            "geocoded": FAKE_GEOCODED,
            "target_floor": target_floor,
        }
    )

    assert building_calls == [
        {"lat": FAKE_GEOCODED.lat, "lon": FAKE_GEOCODED.lon, "target_floor": target_floor, "flood": FAKE_FLOOD_OUTPUT}
    ]


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


def test_run_pipeline_forwards_target_floor_to_building_agent(monkeypatch):
    building_calls = []

    def fake_building_agent(**kwargs):
        building_calls.append(kwargs)
        return FAKE_BUILDING_OUTPUT

    monkeypatch.setattr(run_module, "geocode_road_address", lambda address: FAKE_GEOCODED)
    monkeypatch.setattr(pipeline_module, "run_flood_agent", lambda lat, lon, **kwargs: FAKE_FLOOD_OUTPUT)
    monkeypatch.setattr(pipeline_module, "run_building_agent", fake_building_agent)

    target_floor = {"floor_type": "지하", "floor_no": 1}
    run_module.run_pipeline("테스트주소", collateral_value=5.0e8, target_floor=target_floor)

    assert building_calls[0]["target_floor"] == target_floor
