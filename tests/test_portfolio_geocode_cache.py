from climate_risk.agents.flood_agent import FloodAgentOutput
from climate_risk.config import FLOOD_SHP_SOURCES
from climate_risk.geocoding.vworld import GeocodedAddress
from climate_risk.gis.query import FloodRiskResult
from climate_risk.portfolio import geocode_cache
from climate_risk.portfolio.schema import PortfolioRecord

_POHANG_NAMGU_SHP = str(next(s.path for s in FLOOD_SHP_SOURCES if s.region_code == "47111"))


def _record(collateral_id="COL-001", lat=None, lon=None):
    return PortfolioRecord(
        collateral_id=collateral_id,
        address="테스트 주소",
        collateral_type="아파트",
        balance=100.0,
        collateral_value=200.0,
        ltv=0.5,
        score_before=50.0,
        eal_before=1000.0,
        lat=lat,
        lon=lon,
    )


def test_already_geocoded_record_is_not_recalled(monkeypatch):
    calls = []
    monkeypatch.setattr(
        geocode_cache,
        "geocode_road_address",
        lambda address: calls.append(address) or None,
    )

    record = _record(lat=35.0, lon=129.0)
    result = geocode_cache.ensure_geocoded([record])

    assert result == [record]
    assert calls == []


def test_successful_geocode_derives_region_code(monkeypatch):
    monkeypatch.setattr(
        geocode_cache,
        "geocode_road_address",
        lambda address: GeocodedAddress(lat=35.98768, lon=129.39979, refined_text="정제주소", input_address=address),
    )
    monkeypatch.setattr(
        geocode_cache,
        "run_flood_agent",
        lambda lat, lon: FloodAgentOutput(
            flood=FloodRiskResult(
                coverage="IN_SCOPE",
                in_polygon=True,
                tier="내부",
                distance_to_polygon_m=0.0,
                freq_label="MAX",
                river_name="냉천",
                region_name="포항시 남구",
                source_shp_file=_POHANG_NAMGU_SHP,
                license="공공누리4유형",
                methodology_disclaimer="test",
                uncertain=None,
            ),
            source_id=f"flood:{_POHANG_NAMGU_SHP}",
            field_sources={},
        ),
    )

    result = geocode_cache.ensure_geocoded([_record()])

    assert result[0].geocode_confidence == "OK"
    assert result[0].region_code == "47111"
    assert result[0].lat == 35.98768


def test_geocode_failure_does_not_raise_and_marks_failed(monkeypatch):
    monkeypatch.setattr(geocode_cache, "geocode_road_address", lambda address: None)

    result = geocode_cache.ensure_geocoded([_record()])

    assert result[0].geocode_confidence == "FAILED"
    assert result[0].lat is None
    assert result[0].region_code is None


def test_out_of_scope_geocode_success_leaves_region_code_none(monkeypatch):
    monkeypatch.setattr(
        geocode_cache,
        "geocode_road_address",
        lambda address: GeocodedAddress(lat=37.5665, lon=126.9780, refined_text="서울", input_address=address),
    )
    monkeypatch.setattr(
        geocode_cache,
        "run_flood_agent",
        lambda lat, lon: FloodAgentOutput(
            flood=FloodRiskResult(
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
            ),
            source_id="flood:out_of_scope",
            field_sources={},
        ),
    )

    result = geocode_cache.ensure_geocoded([_record()])

    assert result[0].geocode_confidence == "OK"  # 지오코딩 자체는 성공
    assert result[0].region_code is None  # 다만 커버리지 밖이라 지역필터 매칭 대상 아님
