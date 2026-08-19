"""geocoding/juso.py — 도로명주소 자동완성 검색 회귀 테스트. `_fetch_juso_json`이
유일한 HTTP 호출 지점이라 이것만 monkeypatch하면 네트워크 없이 검증 가능."""

import pytest

from climate_risk.geocoding import juso


def _fake_response(items, error_code="0"):
    return {"results": {"common": {"errorCode": error_code}, "juso": items}}


def test_short_keyword_returns_empty_without_calling_api(monkeypatch):
    def _boom(keyword, count):
        raise AssertionError("2자 미만 키워드는 API를 호출하면 안 됨")

    monkeypatch.setattr(juso, "_fetch_juso_json", _boom)

    assert juso.search_road_addresses("대") == []


def test_filters_out_addresses_outside_coverage_prefixes(monkeypatch):
    items = [
        {"roadAddr": "대구광역시 북구 침산로 10", "bdNm": "테스트빌라"},
        {"roadAddr": "대전광역시 유성구 대학로 1", "bdNm": "무관지역"},
        {"roadAddr": "경상북도 포항시 남구 인덕로 27", "bdNm": ""},
    ]
    monkeypatch.setattr(juso, "_fetch_juso_json", lambda keyword, count: _fake_response(items))

    results = juso.search_road_addresses("빌라")

    addresses = [r.road_address for r in results]
    assert "대구광역시 북구 침산로 10" in addresses
    assert "경상북도 포항시 남구 인덕로 27" in addresses
    assert "대전광역시 유성구 대학로 1" not in addresses
    assert len(results) == 2


def test_deduplicates_identical_road_addresses(monkeypatch):
    items = [
        {"roadAddr": "대구광역시 북구 침산로 10", "bdNm": "A"},
        {"roadAddr": "대구광역시 북구 침산로 10", "bdNm": "A"},
    ]
    monkeypatch.setattr(juso, "_fetch_juso_json", lambda keyword, count: _fake_response(items))

    results = juso.search_road_addresses("침산로")

    assert len(results) == 1


def test_missing_building_name_becomes_none(monkeypatch):
    items = [{"roadAddr": "대구광역시 북구 침산로 10", "bdNm": ""}]
    monkeypatch.setattr(juso, "_fetch_juso_json", lambda keyword, count: _fake_response(items))

    results = juso.search_road_addresses("침산로")

    assert results[0].building_name is None


def test_non_zero_error_code_raises(monkeypatch):
    monkeypatch.setattr(
        juso, "_fetch_juso_json", lambda keyword, count: _fake_response([], error_code="E0001")
    )

    with pytest.raises(juso.JusoSearchError):
        juso.search_road_addresses("침산로")
