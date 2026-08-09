# 개발 로그 (계획과 다르게 나온 것만)

HANDOVER.md의 가정·설계가 실제 구현 중 다르게 확인되면 여기에 적는다. 코드 커밋 메시지에 담을 내용이 아니라 **"이거 나중에 contest_research 쪽 계획 문서를 고쳐야 할 수도 있다"** 싶은 것만 남긴다. PM이 읽고 반영 여부를 직접 판단한다 — 여기 적었다고 자동으로 계획이 바뀌는 건 아니다.

각 항목 형식:
```
## YYYY-MM-DD — 한 줄 요약
**계획(HANDOVER.md 기준)**: 원래 뭐라고 돼 있었는지
**실제**: 구현하면서 확인된 것
**영향**: 그래서 뭘 다시 봐야 하는지 (해당 없으면 생략)
```

---

## 2026-08-09 — "판정보류"는 거리 임계값 규칙이 아니라 신천 5지점 전용 수동 주석

**계획(HANDOVER.md 기준)**: ⑦ "커버리지 게이트 ↔ 신천 판정보류 표기 정합성" — "커버리지 게이트는 이미 기술 설계로 완성돼 있다(§4.3 `flood_data_coverage` 테이블 + `OUT_OF_SCOPE` 반환, 신천 판정보류 지점을 고정 회귀 케이스로 등록). 남은 작업은 '표기 문구 확정'이라는 좁은 범위다." — 즉 신천 4개 지점을 `OUT_OF_SCOPE`로 판정하는 로직이 이미 존재하고 라벨링만 남았다는 전제.

**실제**: Week 1 설계 중 원본 실측 거리값을 대조해보니, 냉천 비교점(냉천교 38.4m·오어지 90.2m, 문서상 "판정보류 아님")과 신천 판정보류 4개(침산교 36.4m·대봉교 50.1m·수성교 99.4m·신천동 395.6m) 사이에 거리 하나로 두 그룹을 가르는 임계값이 존재하지 않는다(냉천교 38.4m와 침산교 36.4m는 사실상 동일). "판정보류"는 point-in-polygon 거리에서 파생된 알고리즘 속성이 아니라, PM이 신천 각 지점을 인접 5개 구 SHP 파일 전부에 교차대조(자기 구 파일 대비 타 구 파일 값이 수백~수천m씩 들쭉날쭉)한 뒤 내린 정성적 판단이었다. 냉천은 파일이 1개뿐이라 애초에 이런 교차검증 자체가 불가능했다.

**영향**: 구현은 커버리지 게이트를 2단으로 분리 — ①행정구역/SHP 범위 밖이면 일반화 가능한 알고리즘 규칙으로 `OUT_OF_SCOPE` ②범위 안이면 거리와 무관하게 tier·거리를 있는 그대로 반환. "판정보류" 라벨은 신천 4개 좌표 전용 소규모 수동 lookup으로 분리 처리(지오메트리 알고리즘과 무관). PM은 HANDOVER §⑦·§4.3의 "커버리지 게이트가 판정보류까지 이미 처리한다"는 표현을 "판정보류는 거리 규칙이 아니라 수동 확인 대상 지점 목록"으로 수정할지 판단 필요.

## 2026-08-09 — STRtree의 predicate 질의("contains"/"covers")가 복잡한 다중 파트 폴리곤에서 개별 geometry의 `.covers()`와 다른(틀린) 결과를 냄

**계획(HANDOVER.md 기준)**: 명시적 계획 없음 — `gis/query.py` 구현 중 커버리지 게이트 회귀 테스트(신천 5지점)를 돌리다 발견.

**실제**: 인덕동(§1.10, 0.0m·내부 확인)·신천대로/봉덕동(§1.11, 0.0m·내부 확인) 좌표로 회귀 테스트를 돌리니 `in_polygon=False`인데 `distance=0.0`이 나오는 모순이 발생. 디버깅 결과 `zone.geom.covers(point)`(개별 shapely geometry에 직접 호출)는 `True`를 정확히 반환하는데, 같은 geometry를 담은 `STRtree(...).query(point, predicate="covers")`는 그 zone을 후보로도 못 찾음. 이 SHP들은 `loader.py`의 `_shape_to_geometry()`가 `polygonize()`+`make_valid()`로 재구성한 매우 복잡한 다중 파트 지오메트리(최대 3,236 parts)라, GEOS의 STRtree 내부 prepared-geometry 판정이 이런 위상에서 신뢰할 수 없는 것으로 보임(원인은 GEOS 내부 구현 — 더 깊이 파지 않음).

**영향**: `gis/query.py`를 STRtree는 bbox 후보 필터링(predicate 없는 `tree.query(point)`)에만 쓰고, 실제 covers 판정은 후보들에 대해 개별 shapely `.covers()` 직접 호출로 수정(커밋에 포함). 이후 GIS 코드(Week2 건물취약도 공간질의 등)에서도 STRtree predicate 질의를 쓸 경우 이 SHP들에 대해서는 신뢰하지 말 것 — bbox 필터 + 직접 geometry 메서드 패턴을 그대로 따를 것.

## 2026-08-09 — `query_flood_risk()`가 매 호출마다 SHP를 재로딩(캐시 없음) — HANDOVER가 전제한 "로컬 캐시"가 실제로는 없었음

**계획(HANDOVER.md 기준)**: §4.3 폴백 설계 "PostGIS 연결 실패 시 로컬 shapely+STRtree **캐시**로 즉시 전환"(HANDOVER.md:159) — 로컬(shapely) 경로는 이미 캐시된 상태로 대기하고 있다가 즉시 전환 가능하다는 전제.

**실제**: Week1 스파이크 구현에서 `query_flood_risk(lat, lon)`을 `regions` 인자 없이 호출하면 매번 `load_all_regions()`을 처음부터 다시 실행했다 — 실측 콜드 호출 157.8초(6개 SHP를 pyshp로 읽고 최대 68,971점짜리 다중파트 폴리곤을 `polygonize()`+`make_valid()`로 재구성하는 비용, `gis/loader.py` `_shape_to_geometry` 참조). `regions`를 넘겨도 STRtree는 매 호출 재빌드됐으나 이쪽은 29개 zone 기준 0.001초로 무시 가능한 수준이었다. Week1 테스트가 이를 못 잡은 이유는 `conftest.py`의 `regions` fixture가 `scope="session"`이라 우연히 1회만 로딩했기 때문 — 실제 프로덕션 경로(`regions` 미지정 호출)는 테스트가 커버하지 않고 있었다.

**영향**: `gis/query.py`에 `_cached_default_regions()`(`functools.lru_cache(maxsize=1)`)를 추가해 `regions` 미지정 호출은 프로세스당 1회만 로딩하도록 수정, `tests/test_query_caching.py`로 캐시 계약을 회귀 테스트에 고정. 수정 후 실측: 1회차 74.4초(SHP 로딩 비용 자체는 여전히 존재, 프로세스 시작 후 1번만), 이후 호출 평균 0.0004초. Week2(홍수 에이전트 반복 호출)·Week3(포트폴리오 300~500건 배치, HANDOVER.md:78·507) 착수 전 필수 전제였음 — 캐싱 없이 배치를 돌렸다면 300건 기준 약 8시간 소요로 데모 불가능했을 것.
