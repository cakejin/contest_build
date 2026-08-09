"""loader.py 재적재 idempotency — gis/loader.py 모듈 docstring이 참조하는 테스트.

동일 SHP를 반복 로딩해도 동일 레코드 수·동일 geometry 해시가 나와야 한다
(HANDOVER.md §4.3 idempotent 로딩 요구사항의 로컬 경로 구현).
"""

from climate_risk.config import FLOOD_SHP_SOURCES
from climate_risk.gis.loader import load_all_regions, region_geometry_hash


def test_reload_yields_same_zone_counts(regions):
    reloaded = load_all_regions()
    assert len(reloaded) == len(regions)
    for original, again in zip(regions, reloaded):
        assert len(again.zones) == len(original.zones)
        assert again.skipped_null_seg_codes == original.skipped_null_seg_codes


def test_reload_yields_same_geometry_hash(regions):
    reloaded = load_all_regions()
    for original, again in zip(regions, reloaded):
        assert region_geometry_hash(again) == region_geometry_hash(original)


def test_all_configured_sources_load_without_error():
    loaded = load_all_regions()
    assert len(loaded) == len(FLOOD_SHP_SOURCES)
    assert all(region.zones for region in loaded), "SHP 소스 중 zones가 빈 것이 있음"
