"""loader.py 재적재 idempotency — gis/loader.py 모듈 docstring이 참조하는 테스트.

동일 SHP를 반복 로딩해도 동일 레코드 수·동일 geometry 해시가 나와야 한다
(HANDOVER.md §4.3 idempotent 로딩 요구사항의 로컬 경로 구현).

2026-08-19 최적화(DEV_LOG.md 참조): 이전엔 idempotency 비교 두 테스트가 각자
`load_all_regions()`를 따로(콜드 로딩 2회 중복) 불렀고, 세 번째 테스트도 또 불러서
파일 하나가 SHP 7개 콜드 로딩을 3번 반복했다 — 전체 스위트가 유독 느려지는 주된
원인이었다(다른 세션이 이 파일 포함 4개 파일만으로 75분을 기록한 적 있음).
pytest 전문가 가이드의 표준 패턴("비싼 읽기전용 setup은 세션당 1회, 여러 테스트가
공유")대로 재로딩 결과를 세션 픽스처(`reloaded_regions`)로 분리해 세션당 1회만
로딩하도록 고쳤다 — 검증 내용(baseline `regions` vs 재로딩 결과 비교)은 그대로다.
"""

import pytest

from climate_risk.config import FLOOD_SHP_SOURCES
from climate_risk.gis.loader import load_all_regions, region_geometry_hash


@pytest.fixture(scope="session")
def reloaded_regions():
    """`regions`(conftest.py)와 별개로 다시 한 번 콜드 로딩한 결과 — idempotency
    비교의 "두 번째 로드". 읽기 전용으로만 쓰이므로 세션 스코프로 공유해도 테스트 간
    오염 위험이 없다."""
    return load_all_regions()


def test_reload_yields_same_zone_counts(regions, reloaded_regions):
    assert len(reloaded_regions) == len(regions)
    for original, again in zip(regions, reloaded_regions):
        assert len(again.zones) == len(original.zones)
        assert again.skipped_null_seg_codes == original.skipped_null_seg_codes


def test_reload_yields_same_geometry_hash(regions, reloaded_regions):
    for original, again in zip(regions, reloaded_regions):
        assert region_geometry_hash(again) == region_geometry_hash(original)


def test_all_configured_sources_load_without_error(regions):
    # `regions`(세션 픽스처)가 이미 이 시점까지 성공적으로 로딩됐다는 것 자체가
    # "설정된 소스가 전부 에러 없이 로딩된다"는 걸 증명한다 — 또 한 번 콜드 로딩할
    # 필요가 없다(이전엔 여기서도 `load_all_regions()`를 새로 불러 낭비였다).
    assert len(regions) == len(FLOOD_SHP_SOURCES)
    assert all(region.zones for region in regions), "SHP 소스 중 zones가 빈 것이 있음"
