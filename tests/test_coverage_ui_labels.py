"""policy/coverage_labels.py — Week1 확정 좌표(test_flood_agent.py와 동일 SSOT)로
3가지 라벨 분기(정상/판정보류/커버리지밖)를 확인한다."""

from climate_risk.agents.flood_agent import run_flood_agent
from climate_risk.policy.coverage_labels import label_for_flood_result
from climate_risk.policy.disclosures import OUT_OF_SCOPE_LABEL, UNCERTAIN_COVERAGE_LABEL

INDEOKDONG_LAT, INDEOKDONG_LON = 35.98768, 129.39979  # IN_SCOPE, 판정보류 아님
SEOUL_CITY_HALL_LAT, SEOUL_CITY_HALL_LON = 37.5665, 126.9780  # OUT_OF_SCOPE
CHIMSAN_BRIDGE_LAT, CHIMSAN_BRIDGE_LON = 35.900975, 128.592748  # 신천 판정보류


def test_confirmed_in_scope_point_has_no_label(regions):
    output = run_flood_agent(INDEOKDONG_LAT, INDEOKDONG_LON, regions=regions)
    assert label_for_flood_result(output.flood) is None


def test_out_of_scope_point_gets_out_of_scope_label(regions):
    output = run_flood_agent(SEOUL_CITY_HALL_LAT, SEOUL_CITY_HALL_LON, regions=regions)
    assert label_for_flood_result(output.flood) == OUT_OF_SCOPE_LABEL


def test_uncertain_point_gets_uncertain_label(regions):
    output = run_flood_agent(CHIMSAN_BRIDGE_LAT, CHIMSAN_BRIDGE_LON, regions=regions)
    assert label_for_flood_result(output.flood) == UNCERTAIN_COVERAGE_LABEL
