import pytest

from climate_risk.gis.loader import load_all_regions


@pytest.fixture(scope="session")
def regions():
    """SHP 6개 전량 로딩 — 정점 수가 커서(냉천 SGG N330=68,971점) 세션당 1회만 로딩."""
    return load_all_regions()
