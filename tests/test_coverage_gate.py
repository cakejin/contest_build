"""커버리지 게이트 회귀 테스트 — CLAUDE.md 테스트 규율:

"신천 5개 지점(남구=확정, 나머지 4개=판정보류)을 커버리지 게이트 회귀 테스트로
고정 등록 — 매번 같은 결과(OUT_OF_SCOPE 등)가 나오는지 확인한다."

좌표 출처:
- 냉천 3지점: contest_research §1.10 (PM 직접 실측, WGS84 좌표 원본 그대로).
- 신천 5지점: 남구(신천대로·봉덕동)는 §1.11 "내부(0.0m)" 서술을 만족하는 신천대로
  선형 위 좌표(V-World 지명 검색으로 확보, point-in-polygon으로 0.0m 직접 확인).
  나머지 4개(판정보류)는 gis/coverage.py KNOWN_UNCERTAIN_POINTS와 동일 좌표
  (근거·검증 방법은 그 모듈 주석 참조).
- 거제시 4지점(2026-08-19 추가): PM 현장 실측 기록이 없어 SHP 대표점(내부 1개)+
  V-World 지명 검색 POI(근접·원거리 3개)로 대체 확보 — 출처·검증 방법은
  gis/golden_points.py GEOJE_POINTS 주석 참조.
"""

import pytest

from climate_risk.gis.coverage import match_known_uncertain_point
from climate_risk.gis.golden_points import GEOJE_POINTS, NAECHEON_POINTS, SINCHEON_POINTS
from climate_risk.gis.query import query_flood_risk


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


@pytest.mark.parametrize("label,lat,lon,expected_in_polygon,expected_tier", GEOJE_POINTS)
def test_geoje_coverage_gate_regression(
    regions, label, lat, lon, expected_in_polygon, expected_tier
):
    result = query_flood_risk(lat, lon, regions=regions)
    assert result.coverage == "IN_SCOPE", label
    assert result.in_polygon is expected_in_polygon, label
    assert result.tier == expected_tier, label
    assert result.region_name == "거제시", label


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
