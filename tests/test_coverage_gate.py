"""커버리지 게이트 회귀 테스트 — CLAUDE.md 테스트 규율:

"신천 5개 지점(남구=확정, 나머지 4개=판정보류)을 커버리지 게이트 회귀 테스트로
고정 등록 — 매번 같은 결과(OUT_OF_SCOPE 등)가 나오는지 확인한다."

좌표 출처:
- 냉천 3지점: contest_research §1.10 (PM 직접 실측, WGS84 좌표 원본 그대로).
- 신천 5지점: 남구(신천대로·봉덕동)는 §1.11 "내부(0.0m)" 서술을 만족하는 신천대로
  선형 위 좌표(V-World 지명 검색으로 확보, point-in-polygon으로 0.0m 직접 확인).
  나머지 4개(판정보류)는 gis/coverage.py KNOWN_UNCERTAIN_POINTS와 동일 좌표
  (근거·검증 방법은 그 모듈 주석 참조).
"""

import pytest

from climate_risk.gis.coverage import match_known_uncertain_point
from climate_risk.gis.query import TIER_FAR, TIER_INNER, TIER_NEAR, query_flood_risk

NAECHEON_POINTS = [
    # (label, lat, lon, expected in_polygon, expected tier)
    ("오어지(냉천 발원지)", 35.92159, 129.37452, False, TIER_NEAR),
    ("포항직업전문학교(냉천 중류·인덕동)", 35.98768, 129.39979, True, TIER_INNER),
    ("냉천교(냉천 하류·청림동)", 35.99347, 129.40130, False, TIER_NEAR),
]

SINCHEON_POINTS = [
    ("신천대로(봉덕동·남구, 확정)", 35.833993, 128.605565, True, TIER_INNER),
    ("대봉교(중구·남구 경계, 판정보류)", 35.854937, 128.606197, False, TIER_NEAR),
    ("수성교(수성동, 판정보류)", 35.861410, 128.608928, False, TIER_NEAR),
    ("신천동(신천역 인근, 판정보류)", 35.874481, 128.616722, False, TIER_FAR),
    ("침산교(신천-금호강 합류부, 판정보류)", 35.900975, 128.592748, False, TIER_NEAR),
]


@pytest.mark.parametrize("label,lat,lon,expected_in_polygon,expected_tier", NAECHEON_POINTS)
def test_naecheon_coverage_gate_regression(
    regions, label, lat, lon, expected_in_polygon, expected_tier
):
    result = query_flood_risk(lat, lon, regions=regions)
    assert result.coverage == "IN_SCOPE", label
    assert result.in_polygon is expected_in_polygon, label
    assert result.tier == expected_tier, label


@pytest.mark.parametrize("label,lat,lon,expected_in_polygon,expected_tier", SINCHEON_POINTS)
def test_sincheon_coverage_gate_regression(
    regions, label, lat, lon, expected_in_polygon, expected_tier
):
    result = query_flood_risk(lat, lon, regions=regions)
    assert result.coverage == "IN_SCOPE", label
    assert result.in_polygon is expected_in_polygon, label
    assert result.tier == expected_tier, label


def test_sincheon_uncertain_points_flagged():
    for label, lat, lon, _, _ in SINCHEON_POINTS[1:]:
        assert match_known_uncertain_point(lat, lon) is not None, label


def test_sincheon_confirmed_point_not_flagged_uncertain():
    label, lat, lon, _, _ = SINCHEON_POINTS[0]
    assert match_known_uncertain_point(lat, lon) is None, label


def test_naecheon_points_not_flagged_uncertain():
    for label, lat, lon, _, _ in NAECHEON_POINTS:
        assert match_known_uncertain_point(lat, lon) is None, label


def test_out_of_scope_coordinate_returns_out_of_scope(regions):
    """좌표가 로딩된 SHP 커버리지 밖(서울시청)이면 OUT_OF_SCOPE — "데이터 없음≠위험 없음"."""
    seoul_city_hall_lat, seoul_city_hall_lon = 37.5665, 126.9780
    result = query_flood_risk(seoul_city_hall_lat, seoul_city_hall_lon, regions=regions)
    assert result.coverage == "OUT_OF_SCOPE"
    assert result.in_polygon is None
    assert result.tier is None
