"""_cached_default_regions() 캐싱 동작 검증 — gis/query.py 모듈 docstring 참조.

실측(2026-08-09): load_all_regions() 콜드 호출 157.8초. query_flood_risk()가
regions 인자 없이 호출될 때마다 이걸 반복하면 Week2·Week3 배치·라이브 데모에서
감당 불가(호출 1건당 95초 이상). 실제 SHP를 다시 로딩하는 테스트는 무거우므로,
여기서는 load_all_regions_cached를 monkeypatch해 호출 횟수만 세어 "두 번째
호출부터는 재로딩하지 않는다"는 캐싱 계약만 검증한다.

2026-08-19: gis/query.py가 디스크 캐시 함수 load_all_regions_cached()를 쓰도록
바뀌어(gis/loader.py) monkeypatch 대상도 그에 맞춰 이름을 바꿨다 — 이 테스트가
검증하는 건 여전히 "같은 프로세스 내 lru_cache가 두 번째 호출을 막는지"이고,
디스크 캐시 자체의 정확성은 별도로 확인함(수동 검증: cold 651.5s → warm 0.46s).
"""

import climate_risk.gis.query as query_module


def test_default_regions_loaded_only_once(monkeypatch):
    query_module._cached_default_regions.cache_clear()
    call_count = 0

    def fake_load_all_regions_cached():
        nonlocal call_count
        call_count += 1
        return []

    monkeypatch.setattr(query_module, "load_all_regions_cached", fake_load_all_regions_cached)

    first = query_module._cached_default_regions()
    second = query_module._cached_default_regions()

    assert call_count == 1, "두 번째 호출에서도 load_all_regions_cached()가 다시 실행됨 — 캐시 미적용"
    assert first is second

    query_module._cached_default_regions.cache_clear()
