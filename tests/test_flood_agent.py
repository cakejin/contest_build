"""agents/flood_agent.py — query_flood_risk() 위 source_id 태깅 래퍼 검증.

새 판정 로직은 없다(그건 test_coverage_gate.py가 이미 커버) — 여기서는 오직
"결과 필드마다 올바른 source_id가 붙는가"만 검증한다. 좌표는 test_coverage_gate.py와
동일한 Week1 확정 좌표를 재사용(SSOT 유지).
"""

from climate_risk.agents.flood_agent import run_flood_agent

INDEOKDONG_LAT, INDEOKDONG_LON = 35.98768, 129.39979  # 냉천 중류·인덕동, IN_SCOPE
SEOUL_CITY_HALL_LAT, SEOUL_CITY_HALL_LON = 37.5665, 126.9780  # OUT_OF_SCOPE
CHIMSAN_BRIDGE_LAT, CHIMSAN_BRIDGE_LON = 35.900975, 128.592748  # 신천 판정보류 지점


def test_in_scope_result_tags_shp_source_id(regions):
    output = run_flood_agent(INDEOKDONG_LAT, INDEOKDONG_LON, regions=regions)

    assert output.flood.coverage == "IN_SCOPE"
    assert output.source_id == f"flood:{output.flood.source_shp_file}"
    for field in (
        "coverage",
        "in_polygon",
        "tier",
        "distance_to_polygon_m",
        "freq_label",
        "river_name",
        "region_name",
        "methodology_disclaimer",
        "seg_code",
    ):
        assert output.field_sources[field] == output.source_id, field


def test_out_of_scope_result_tags_out_of_scope_source_id(regions):
    output = run_flood_agent(SEOUL_CITY_HALL_LAT, SEOUL_CITY_HALL_LON, regions=regions)

    assert output.flood.coverage == "OUT_OF_SCOPE"
    assert output.source_id == "flood:out_of_scope"
    assert output.field_sources == {"coverage": "flood:out_of_scope"}


def test_uncertain_point_field_source_reuses_source_doc(regions):
    output = run_flood_agent(CHIMSAN_BRIDGE_LAT, CHIMSAN_BRIDGE_LON, regions=regions)

    assert output.flood.uncertain is not None
    assert output.field_sources["uncertain"] == output.flood.uncertain.source_doc
