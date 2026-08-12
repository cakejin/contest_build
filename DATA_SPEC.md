# 데이터·파이프라인 기술 명세서

이 문서는 "어떤 데이터를 어디서 가져와서, 어떤 계산에 쓰고, 무엇이 나오는가"를 코드 기준으로 정리한다. 설계 의도(왜 이렇게 했는지)는 각 모듈의 docstring과 `HANDOVER.md`를, 계획과 다르게 확인된 사실은 `DEV_LOG.md`를 참조할 것 — 이 문서는 "지금 코드가 실제로 무엇을 하는가"만 다룬다.

---

## 1. 데이터 소스 인벤토리

| 구분 | 항목 | 형태 | 위치 | 갱신 방식 |
|---|---|---|---|---|
| 원자료(raw) | 홍수위험지도 SHP 6개(포항 남구 기왕최대 1개 + 대구 5개구 500년 빈도) | `.shp/.dbf/.prj/.shx` | `data/.../raw/` | 정적, 수동 다운로드(환경부), 코드가 변형하지 않음 |
| 큐레이션(curated) | 힌남노 2022 특보 타임라인 | JSON, 7개 이벤트 | `data/.../curated/hinnamno_2022/events.json` | 수작업(뉴스 출처 인용 필수) |
| 큐레이션(curated) | 대구 수성구 2026 특보 타임라인 | JSON, 7개 이벤트 | `data/.../curated/daegu_suseong_2026/events.json` | 수작업(뉴스 출처 인용 필수) |
| 합성(synthetic) | 포트폴리오 40건(6개 지역×6건+미매칭 4건) | JSON | `data/.../curated/portfolio/synthetic_portfolio.json` | 최초 1회 수작업 생성, 이후 지오코딩 결과만 write-back |
| 실시간 API | V-World Geocoder 2.0(주소↔좌표, 역지오코딩) | HTTP/JSON | `geocoding/vworld.py` | 저장 안 함, 매 호출 재조회 |
| 실시간 API | 건축HUB 건축물대장정보 `getBrTitleInfo` | HTTP/JSON | `building/brhub.py` | 저장 안 함, 매 호출 재조회 |
| 실시간 API | 기상청 특보 `WthrWrnInfoService/getWthrWrnList`(live 모드) | HTTP/JSON | `advisory/live.py` | 저장 안 함, 매 호출 재조회 |
| 감사로그(append-only) | 재심사 알림 큐 | JSONL | `data/.../audit/alert_queue_log.jsonl` | 프로그램이 계속 append |
| 감사로그(append-only) | 검토자 확인 클릭 로그 | JSONL | `data/.../audit/reviewer_ack_log.jsonl` | 프로그램이 계속 append |
| 폐기/미사용 | safemap GetMap(WMS 이미지) | — | — | HTTP 500 지속(DEV_LOG 2026-08-11), 코드에서 호출 안 함 |
| 폐기/미사용 | 한강홍수통제소 침수심 통계 API | — | — | 오퍼레이션명 미확인, 시도 자체 불가 |

---

## 2. 파이프라인 단계별 입력 → 계산 → 출력

### 2.1 지오코딩
- **입력**: 도로명주소(`str`)
- **데이터**: V-World Geocoder API(실시간, `request=getcoord&type=road`)
- **코드**: `geocoding/vworld.py::geocode_road_address`
- **출력**: `GeocodedAddress(lat, lon, refined_text, input_address)` — 매칭 실패 시 `None`(예외 아님)

### 2.2 침수 위험 판정 (홍수 에이전트)
- **입력**: `lat, lon`
- **데이터**: SHP 6개(로컬, `functools.lru_cache`로 프로세스당 1회 로딩)
- **코드**: `gis/query.py::query_flood_risk` (얇은 래퍼: `agents/flood_agent.py::run_flood_agent`)
- **계산 순서**:
  1. WGS84 → EPSG:5186 좌표 변환
  2. bbox 커버리지 게이트(`gis/coverage.py::is_within_coverage`) — 6개 SHP의 대략적 범위 밖이면 즉시 `OUT_OF_SCOPE`
  3. STRtree로 bbox 후보 zone 추림 → 후보들에 대해 개별 `shapely.covers(point)` 직접 호출로 point-in-polygon 판정(STRtree의 predicate 질의 자체는 이 SHP들의 복잡한 다중파트 지오메트리에서 신뢰 불가로 확인됨, `DEV_LOG.md` 2026-08-09)
  4. 내부가 아니면 최근접 zone까지 거리로 tier 판정: 내부(0m) / 근접(≤100m) / 원거리(>100m)
  5. `gis/coverage.py::KNOWN_UNCERTAIN_POINTS`(신천 4개 지점 전용 수동 lookup)와 좌표 근접 매칭 — 판정보류 라벨을 별도 필드에 첨부(coverage/tier 자체는 그대로 정직 반환)
- **출력**: `FloodRiskResult(coverage, in_polygon, tier, distance_to_polygon_m, freq_label, river_name, region_name, source_shp_file, uncertain, ...)`

### 2.3 건물취약도 (건물 에이전트)
- **입력**: `lat/lon` 또는 `address` 또는 `PNU`
- **데이터**:
  1. V-World 역지오코딩(좌표 → 법정동코드+지번) — `building/address_resolver.py`
  2. 건축HUB `getBrTitleInfo`(구조재질·지하층수·사용승인일·주용도) — `building/brhub.py`
- **코드**: `building/vulnerability.py::compute_vulnerability`
- **계산**: `score = Σ wᵢ·f(항목ᵢ)` — 구조재질 35% + 지하층수 25% + 연식 20% + 주용도 20%(가중치는 문헌 미검증 초기 추정치, §4 참조). 결측 항목은 중간값 대입이 아니라 **남은 항목끼리 가중치 비례 재분배** 후 `status="PARTIAL"` 명시.
- **출력**: `BuildingVulnerabilityResult(vulnerability_score 0~100, contributing_factors, status OK/PARTIAL/FAILED)`

### 2.4 연간기대손실(EAL) 몬테카를로 (시나리오 에이전트)
- **입력**: `FloodRiskResult`, `vulnerability_score`, `collateral_value`, `seed`(기본 42), `n_iterations`(기본 10,000)
- **데이터**: 없음 — 파라메트릭 가정만 사용(§4 "미확보 데이터" 참조)
- **코드**: `scenario/eal.py::run_monte_carlo_eal`
- **계산**: `freq_label`→연간초과확률(AEP, 500년=1/500·기왕최대=1/200 잠정치) × `tier`별 배율·조건부 침수심 삼각분포 → `np.random.default_rng(seed)`로 사상발생 여부(베르누이)·침수심(삼각분포) 표본 추출 → 손상함수 `1-exp(-1.2·depth)` × 취약도 배율(0.4~1.0) × 담보가액 = 손실분포 → mean/p50/p95/p99 + 20-bin 히스토그램
- **출력**: `EALResult` — 입력 3종 중 하나라도 불충분하면 계산 자체를 안 하고 `status="INSUFFICIENT_INPUT"`
- **성능**: 순수 벡터화 numpy 연산 — 10,000회 기준 수 ms. **무거운 단계가 아니다**(아래 §3 참조).

### 2.5 특보 (advisory 에이전트)
- **입력**: `region_code`, `mode`(`replay`|`live`)
- **데이터**: replay=큐레이션 JSON(힌남노/대구수성구), live=기상청 API(실시간)
- **코드**: `agents/advisory_agent.py::run_advisory_agent`
- **계산**: `event_type ∈ {"특보","재난문자"}`인 이벤트가 하나라도 있으면 `trigger_event=True`(규칙기반, LLM 미관여 — CLAUDE.md 규칙2)
- **출력**: `AdvisoryAgentOutput(trigger_event, active_warnings, timeline, status)`

### 2.6 심사메모 (메모 에이전트 + 인용검증 게이트)
- **입력**: flood/building/scenario/advisory 4종 출력
- **데이터**: 없음(4종 출력을 재료로 LLM 프롬프트 구성)
- **코드**: `agents/memo_agent.py::run_memo_agent`
- **계산 순서**:
  1. `memo/source_registry.py::build_source_registry` — 4종 출력의 `source_id` 전부 수집(LLM이 인용할 수 있는 유일한 정답 집합)
  2. `llm/claude_cli.py::call_claude_structured` — `claude -p` CLI 서브프로세스로 Claude 호출(JSON 스키마 강제, Bash/Read/Write 등 도구 접근 차단)
  3. `memo/citation_gate.py::verify_citations` — LLM이 인용한 `source_id`가 레지스트리에 실제로 있는지 순수 문자열 대조(LLM의 "인용했다"는 주장을 신뢰하지 않음)
  4. `policy/forbidden_phrases.py` — 인용이 유효해도 금지어가 있으면 별도로 반려(독립된 검증축)
  5. 반려율 > 30%면 `memo/fallback_template.py`로 LLM 결과 전체 폐기 후 규칙기반 문장으로 대체
- **출력**: `MemoAgentOutput(sections, rejected_sentences, citation_failure_rate, fallback_used)`

### 2.7 포트폴리오 배치 재계산
- **트리거**: `advisory.trigger_event=True`일 때만 자동 실행(전체 정기배치와 분리)
- **데이터**: `synthetic_portfolio.json`(40건)
- **코드**: `agents/portfolio_agent.py::run_portfolio_agent`
- **계산 순서**:
  1. `portfolio/filter.py::filter_by_region` — `region_code` 매칭 서브셋만 추출(미지오코딩/타지역 건수도 별도 집계)
  2. `portfolio/recalc.py::recalc_subset` — 매칭분만 flood/building/scenario 재계산(`ThreadPoolExecutor`로 병렬화, seed는 레코드별 로컬 RNG라 스레드 안전)
  3. `portfolio/alerts.py::build_alert_queue` — `EAL_change_pct = (after-before)/before`, `|변화율| ≥ threshold_pct`(기본 20%)만 알림 큐 등재. LTV/금리 필드는 스키마에 아예 없음(회귀 테스트로 고정, 소급 불리 적용 금지 원칙).
- **출력**: `PortfolioBatchResult(matched_count, recalculated, alerts)` + `alert_queue_log.jsonl` 기록

### 2.8 ESG 추천
- **입력**: `portfolio_batch.alerts`
- **코드**: `policy/esg_recommendations.py::build_esg_recommendations`
- **계산**: 알림 큐에 오른 담보 전원에게 고정 4개 액션 문구(보험 확인·현장 점검·재해지원 연결·적응투자 우대)만 부여 — 조건부 위험 재판정이나 인상 방향 로직 자체가 코드에 없음
- **출력**: `ESGRecommendation(collateral_id, actions)`

### 2.9 평가지표 (`evaluation/metrics.py`)
| 지표 | 계산 |
|---|---|
| 인용률 | `memo.sections`/`rejected_sentences` 개수 비율 |
| 커버리지게이트 통과율 | `gis/golden_points.py` 8개 좌표 재질의 후 기대값(내부/근접/원거리) 대조 |
| EAL 재현성 | 동일 seed로 2회 재실행 후 `EALResult` 완전 일치 여부 |
| 금지어 부재 | 게이트를 이미 통과한 memo.sections를 다시 한번 재스캔(이중검증) |
| 판정보류 오분류 | 신천 4지점=판정보류로, 냉천 3지점+신천대로=판정보류 아님으로 나오는지 |

### 2.10 레드팀 체크 1·2·4·9 (`policy/redteam_checks.py`)
| # | 검증 방식 |
|---|---|
| 1(소급 불리 금지) | `AlertQueueEntry` 필드에 LTV/금리 관련 필드명이 없는지 + 입력 레코드가 계산 후에도 불변인지 |
| 2(특보-EAL 오연동 차단) | `inspect.signature(run_scenario_agent)`에 `advisory` 파라미터가 물리적으로 없는지 |
| 4(GIS 공백 위음성) | `coverage_gate_metric()` 재사용 |
| 9(블루라이닝 문구 유출) | 고정 적대적 문장 3개를 `forbidden_phrases` 필터에 실제로 통과시켜 잡히는지 |

---

## 3. 왜 테스트가 오래 걸리는가 — 실측 원인 (몬테카를로 아님)

`pytest tests/ --durations=30` 실측 결과(144 테스트, 총 473.7초):

```
86.20s  test_redteam_scenarios.py::test_scenario4_coverage_gate_passes
79.89s  test_loader_idempotent.py::test_reload_yields_same_zone_counts
79.55s  test_loader_idempotent.py::test_reload_yields_same_geometry_hash
75.81s  test_evaluation_metrics.py::test_coverage_gate_metric_golden_set_all_pass
75.76s  test_loader_idempotent.py::test_all_configured_sources_load_without_error
74.32s  test_coverage_gate.py (session fixture setup)
0.36s   test_eal_insufficient_input.py (몬테카를로 관련 최상위)
...나머지 138개 테스트 전부 0.4초 미만
```

**EAL 몬테카를로는 원인이 아니다** — 순수 벡터화 numpy 연산이라 10,000회 반복도 밀리초 단위다(위 목록에서 가장 무거운 EAL 관련 테스트가 0.36초). 실제 원인은 **`gis/loader.py::load_all_regions()`(SHP 로딩 + `polygonize`+`make_valid`로 다중파트 폴리곤 재구성, 최대 3,236 parts)가 세션 중 최소 6번 독립적으로 재실행**되기 때문이다:

1. `conftest.py`의 `regions` 세션 픽스처가 1회 직접 로딩(74s)
2. `gis/query.py::_cached_default_regions()`(별도의 `functools.lru_cache(maxsize=1)`, 픽스처와 무관)가 `region_code` 없이 호출되는 첫 테스트(`test_evaluation_metrics.py`)에서 1회 콜드 로딩(76s)
3. `test_loader_idempotent.py`의 테스트 3개는 **재현성(idempotency) 검증이 목적이라 의도적으로 캐시를 안 쓰고** `load_all_regions()`를 매번 직접 호출 — 3회 콜드 로딩(80s×3)
4. `test_query_caching.py::test_default_regions_loaded_only_once`가 캐시 계약을 검증하려고 `_cached_default_regions.cache_clear()`를 호출(테스트 자체는 monkeypatch로 가짜 로더를 써서 빠르지만, **정리 코드가 캐시를 실제로 비워버림**) → 이후 이 캐시를 쓰는 다음 테스트(`test_redteam_scenarios.py`)가 다시 콜드 로딩을 떠안음(86s)

6번 × 75~86초 ≈ 450~515초 — 측정된 총 473.7초와 거의 정확히 일치한다. 나머지 138개 테스트는 전부 합쳐도 5초가 안 된다.

**개선하고 싶다면** (현재는 손대지 않았음, 필요 시 요청):
- `test_query_caching.py`의 정리 코드를 "비우기"가 아니라 "이전 상태 저장 후 복원"으로 바꾸면 5번이 사라짐
- `test_loader_idempotent.py`의 3개 테스트는 설계상 캐시를 못 쓰지만, `@pytest.mark.slow`로 분리해 평소엔 스킵하고 필요할 때만 돌리는 방법도 있음
- `_cached_default_regions()`와 `conftest.py`의 `regions` 픽스처를 하나로 통합하면 1번+2번의 중복도 없앨 수 있음(다만 원래 설계는 "픽스처로 명시 전달하는 경로는 재현성 검증을 위해 의도적으로 캐시를 우회"하는 것이므로 통합 시 그 취지가 사라지지 않는지 확인 필요)

---

## 4. 부족/미확보 데이터

| 항목 | 현재 상태 | 영향 |
|---|---|---|
| 기상청 30년 확률강우량 통계 원자료 | 미확보 — `scenario/eal.py`가 freq_label/tier 기반 파라메트릭 근사로 대체(잠정치, methodology_note로 항상 명시) | EAL 절대값의 신뢰구간을 학술적으로 주장할 수 없음, 상대비교(재심사 트리거)용으로는 충분 |
| 건물취약도 가중치 w1~w4 | 문헌 근거 없는 초기 추정치(HANDOVER B2) | 점수 자체의 절대적 정확도 미검증, 구조는 화이트박스라 추후 캘리브레이션 용이 |
| 한강홍수통제소 침수심 통계 API | 오퍼레이션명 미확인 — 시도 자체 불가 | 침수심 실측 보정 소스 하나가 통째로 없음 |
| safemap GetMap(WMS 이미지) | HTTP 500 지속 확정(키 무관) | 지도 시각 오버레이 불가, SHP point-in-polygon이 유일 경로(이미 그렇게 구현됨) |
| 실 고객 포트폴리오 | 40건 전부 합성(실존 도로명만 사용, 지오코딩 검증 완료) | 상용화 시 실 데이터 연동 필요 |
| 대구 신천 "기왕최대" 빈도 SHP | 없음(500년 빈도만 존재 — 냉천은 반대로 기왕최대만 있고 500년 없음, 정부 원본 제작 빈도 자체가 지역마다 다름) | 두 지역의 침수 tier 계산 기준(AEP)이 실제로는 다른 재현주기를 쓰고 있다는 점을 이해하고 비교해야 함 |
| 신천 4개 판정보류 지점 정식 재검증 | PM 수동 교차대조 기반 lookup(`KNOWN_UNCERTAIN_POINTS`), 알고리즘화 안 됨 | 새 좌표에 일반화 불가 — 이 4개 지점 전용 |

---

## 5. 데이터 관리 현황 & DB 도입 여부

**현재 방식**: 전부 플랫파일(SHP/JSON) + 프로세스 수명 동안만 유효한 in-memory `functools.lru_cache`. 프로세스 재시작 시 캐시는 사라지고 SHP는 다시 콜드 로딩(75~160초)된다. 지오코딩·건축HUB 결과는 아예 저장하지 않고 매 요청마다 재호출한다(포트폴리오 웜업 스크립트만 예외적으로 좌표를 원본 JSON에 write-back). 감사로그는 append-only JSONL이라 조회/집계 기능이 없다.

**지금 규모(SHP 6개 15MB, 포트폴리오 40건)에서는 이 방식이 실제로 더 단순하고 빠르다** — DB를 지금 도입할 필요는 없다고 판단된다. 다만 아래 세 가지 지점에서 DB(또는 영속 저장소)가 실질적 가치를 내기 시작한다:

1. **SHP → PostGIS**: 프로세스 재시작마다 75~160초 콜드로딩을 없애고, 여러 프로세스(웹서버 다중 워커 등)가 로딩 비용을 나눠 갖지 않고 공유할 수 있음. HANDOVER 원안에도 있었으나 Week1에 "shapely 인프로세스로 충분, 필요 시에만 전환"으로 보류됨(B5) — 지금 이 성능 문제가 프로덕션에서도 재현된다면 재검토할 타이밍.
2. **지오코딩/건축HUB 결과 영속 캐시**: 현재는 매 프로세스마다 재조회 — 같은 주소를 반복 조회하면 유료/쿼터 제한 API를 불필요하게 다시 호출한다(`portfolio/geocode_cache.py`가 포트폴리오 레코드에 한해 절반만 이 문제를 이미 인지·해결한 상태). SQLite 정도로도 충분한 규모.
3. **감사로그 쿼리화**: `alert_queue_log.jsonl`에 "이번 달 알림 몇 건" 같은 질의를 하려면 지금은 파일을 직접 파싱해야 한다 — 조회 패턴이 실제로 필요해지면 SQLite/파일 기반 DB로 옮기는 것으로 충분(서버형 DB까지는 불필요해 보임).

**결론**: 지금 당장은 불필요. 상용화 단계로 갈 때 우선순위는 ① SHP→PostGIS(콜드로딩 제거) ② 지오코딩/건축HUB 영속 캐시(API 비용 절감) ③ 감사로그 쿼리화 순으로 검토하는 것을 권장.
