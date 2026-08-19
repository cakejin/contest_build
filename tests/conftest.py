import pytest

from climate_risk.gis.loader import load_all_regions
from climate_risk.gis.query import FloodRiskResult


@pytest.fixture(scope="session")
def regions():
    """SHP 7개 전량 로딩 — 정점 수가 커서(냉천 SGG N330=68,971점) 세션당 1회만 로딩."""
    return load_all_regions()


@pytest.fixture
def in_scope_flood() -> FloodRiskResult:
    """scenario/eal.py 테스트용 최소 IN_SCOPE 홍수 판정 — 실제 SHP 조회 없이 구성."""
    return FloodRiskResult(
        coverage="IN_SCOPE",
        in_polygon=True,
        tier="내부",
        distance_to_polygon_m=0.0,
        freq_label="MAX",
        river_name="냉천",
        region_name="포항시 남구",
        source_shp_file="RFM_SGG_RGN_47111_MAX.shp",
        license="공공누리4유형",
        methodology_disclaimer="test",
        uncertain=None,
    )


@pytest.fixture
def out_of_scope_flood() -> FloodRiskResult:
    return FloodRiskResult(
        coverage="OUT_OF_SCOPE",
        in_polygon=None,
        tier=None,
        distance_to_polygon_m=None,
        freq_label=None,
        river_name=None,
        region_name=None,
        source_shp_file=None,
        license=None,
        methodology_disclaimer="test",
        uncertain=None,
    )
