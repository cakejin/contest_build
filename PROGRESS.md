# 진행 상황 (주차별)

기준 문서: `HANDOVER.md` §⑦ 실행 순서(세션별 WBS·Definition of Done). 완료 기준(Done 기준)은 "코드 존재"가 아니라 "실제로 시연 가능한가"다 — 체크는 그 기준을 실측(테스트·라이브 호출)으로 충족했을 때만 넣는다.

체크 형식: `[x]` 완료 / `[ ]` 미착수 / `[~]` 진행 중(부분 완료)

---

## Week 0 — 착수 전 준비 (코딩 없음)

- [x] A1 스코프 확정 (냉천+신천남구 둘 다 메인) — 2026-08-07
- [x] A2 홍수위험지도 대구 빈도별 재시도·파일 확보
- [x] A3 LLM 벤더·리전 확정 (Anthropic API 직접 호출)
- [ ] B1 safemap GetMap 500 문의 발송 (1566-0025 / opendata_help@nia.or.kr) — 비차단, 병행 가능

**완료 기준**: SHP 경로 목록 확정 / API 키 확보 / safemap 문의 발송. → B1만 미완.

---

## Week 1 — GIS 가공 계층 스파이크 ✅ 완료 (2026-08-09)

- [x] shapely+pyproj+STRtree 로딩 (`src/climate_risk/gis/loader.py`)
- [x] `query_flood_risk(lat, lon, ...)` 구현 (`src/climate_risk/gis/query.py`)
- [x] 커버리지 게이트 — `OUT_OF_SCOPE` 명시 반환 (`src/climate_risk/gis/coverage.py`)
- [x] 신천 5개 지점(남구=확정, 나머지 4개=판정보류) 회귀 케이스 등록 (`tests/test_coverage_gate.py`)
- [x] V-World 지오코딩 연동 (`src/climate_risk/geocoding/vworld.py`) — 주소 API + 지명 검색 API 둘 다 실키 검증
- [x] 로더 idempotency 테스트 (`tests/test_loader_idempotent.py`)

**Done 기준 시연**: 인덕동 좌표 → "내부(0m)" / 임의 커버리지 밖 좌표(서울시청) → "OUT_OF_SCOPE" — `pytest tests/ -v`로 확인, 15개 테스트 전부 통과.

**Week 1 중 발견한 이슈**:
- STRtree `predicate="contains"/"covers"` 질의가 복잡한 다중 파트 폴리곤에서 개별 geometry의 `.covers()`와 다른 결과를 내는 버그 발견·수정 (`gis/query.py`, `DEV_LOG.md` 2026-08-09 참조). Week 2 이후 STRtree predicate 재사용 시 주의.
- "판정보류"는 거리 임계값 알고리즘이 아니라 PM의 수동 교차대조 판단(`DEV_LOG.md` 2026-08-09 참조) — `KNOWN_UNCERTAIN_POINTS`로 별도 lookup 처리.
- 신천 4개 판정보류 지점 중 대봉교·침산교는 지오코딩 좌표가 §1.11 원본 실측 거리와 1~3m 오차로 근접 일치, 수성교·신천동은 같은 tier(근접/원거리)이나 절대 거리 40~110m 차이(정확히 같은 지점인지 미확정) — `gis/coverage.py` 주석 참조.
- `query_flood_risk()`가 `regions` 인자 없이 호출될 때마다 SHP를 처음부터 재로딩(콜드 157.8초)하고 있었음 — HANDOVER §4.3이 전제한 "로컬 캐시로 즉시 전환"이 실제로는 없었던 것. Week1 테스트는 세션 스코프 fixture 덕에 우연히 안 걸렸음(실제 프로덕션 호출 경로는 테스트가 커버 안 하고 있었음). `functools.lru_cache`로 프로세스당 1회만 로딩하도록 수정(웜 0.0004초), `tests/test_query_caching.py`로 캐시 계약 회귀 등록. Week2·Week3 배치(300~500건) 착수 전 필수 전제였음 — 없었으면 배치 1회 약 8시간 소요. (`DEV_LOG.md` 2026-08-09 세 번째 항목 참조)

**보류 항목**: B1(safemap 문의)은 Week 4까지 회신 대기 가능, 지금 막는 것 없음.

---

## Week 2 — 계량 코어 파이프라인 ✅ 완료 (2026-08-11)

- [x] 홍수 에이전트 (`src/climate_risk/agents/flood_agent.py`) — Week1 게이트 소비, source_id 태깅
- [x] 건물취약도 에이전트 (`src/climate_risk/agents/building_agent.py`, `building/`) — 초기 가중치 w1~w4로 진행(B2), 주소→건축HUB 코드 해석 포함
- [x] 시나리오 에이전트 (`src/climate_risk/agents/scenario_agent.py`, `scenario/eal.py`) — 몬테카를로 EAL, 시드 고정
- [x] LangGraph fan-out/fan-in 골격 (`src/climate_risk/graph/pipeline.py`, `graph/run.py`)

**Done 기준 시연**: `python scripts/run_assessment.py --address "..." --collateral-value ...` 실행 → EAL 분포(mean/p50/p95/p99) + tier + vulnerability_score가 JSON으로 출력됨을 실주소(포항 인덕동)로 라이브 확인. 동일 seed 2회 실행 결과 바이트 단위로 완전 동일(재현성 확인). 서울시청(SHP 커버리지 밖) 주소로는 flood=OUT_OF_SCOPE·EAL=null(사유 명시)이 반환되고 building 에이전트는 fan-out대로 독립적으로 정상 작동함을 확인. `pytest tests/ -v` 47개 전부 통과(Week1 15개 + Week2 신규 32개).

**절대 축소 금지**: EAL 시드 재현성(화이트박스 포지셔닝의 증거, §⑦ 잔여 리스크 참조) — 유지됨, `tests/test_eal_seed_reproducibility.py`로 회귀 고정.

**Week 2 중 발견한 이슈**: 건축HUB `getBrTitleInfo`의 주소→코드 해석 경로(sigunguCd·bjdongCd·platGbCd·bun·ji)가 연구 단계에 전혀 검증되지 않았던 부분이라 구현 착수 시 라이브 체크포인트로 확정(DEV_LOG.md 2026-08-11 참조) — V-World 역지오코딩(`type=parcel`)으로 해결, 애초 계획했던 별도 폴백 경로(수동 법정동코드 테이블 등)는 불필요해짐. serviceKey 이중 인코딩 함정(`.env`에 이미 percent-encoding된 키를 `urlencode()`에 다시 넣으면 400 에러)도 이 과정에서 발견·해결.

---

## Week 3 — LLM·특보·포트폴리오·규율 UI ✅ 완료 (2026-08-11)

- [x] 메모 에이전트 + 인용검증 게이트 (`src/climate_risk/agents/memo_agent.py`, `memo/`) — 인용 없는/미등록 source_id 문장 실제 차단, 고실패율(>30%) 시 규칙기반 폴백
- [x] 특보 에이전트 (`src/climate_risk/agents/advisory_agent.py`, `advisory/`) — 힌남노 2022-09 큐레이션 리플레이(실제 출처 URL 7건), 라이브 모드는 명시적 미구현 스텁
- [x] 포트폴리오 배치 재계산 (`src/climate_risk/portfolio/`, `agents/portfolio_agent.py`) — 지역필터링(경보지역만) + EAL 변화율 임계치(잠정 20%) 초과분만 알림 큐, LTV/금리 필드 없음(회귀 테스트로 고정)
- [x] HITL 워터마크 + 확인 클릭 감사로그 (`src/climate_risk/policy/disclosures.py`, `audit_log.py`) — CLI/JSON 확장으로 구현(웹 UI 아님, 사용자 결정)
- [x] 보호규율 문구 고정 (`policy/forbidden_phrases.py`) — 금지어 필터, 메모 에이전트 출력에 이중 검증(인용 유효성과 독립된 검증축)
- [x] 커버리지 게이트 UI 표기 확정 (`policy/coverage_labels.py`) — "판정보류(데이터 공백 — 위험 낮음 아님)"(OUT_OF_SCOPE는 별도 문구)

**Done 기준 시연**: `python scripts/run_week3_demo.py --address "경상북도 포항시 남구 인덕로 27" --collateral-value 500000000` 라이브 실행 → 힌남노 7개 이벤트 리플레이(trigger_event=True) → 근거 인용 심사메모 11개 문장(전부 유효 인용, rejected_sentences=0) → 포트폴리오 40건 중 6건 지역매칭, 2건 재심사 알림(EAL 변화율 +49~+49%) 전부 확인. 인용 없는/지어낸 source_id 인용 문장이 실제로 차단되는 것은 `tests/test_week3_demo_smoke.py`로 회귀 고정. `pytest tests/ -v` 전체 통과(Week1~2 47개 + Week3 신규 84개).

**LLM 호출 메커니즘 변경**: HANDOVER §A3 "Anthropic API 직접 호출" 대신 API 키 미발급 상태로 `claude -p` CLI 서브프로세스 호출 채택(같은 Claude 모델, 벤더 결정과 배치되지 않음) — 상세는 `DEV_LOG.md` 2026-08-11 참조.

**절대 축소 금지**: 인용검증 게이트, 보호규율 문구 고정. — 둘 다 유지됨.

---

## Week 4 — 평가·레드팀·컴플라이언스 마감·리허설·버퍼 ✅ 완료 (2026-08-11)

- [x] 평가 대시보드 최소셋 (`src/climate_risk/evaluation/metrics.py`) — 인용률·커버리지게이트 통과율·EAL 재현성·금지어 부재·판정보류 오분류 여부 5개 지표, `scripts/run_eval_dashboard.py`로 라이브 실행
- [x] 레드팀 최우선 시나리오(1·2·4·9) 방어 확인 (`src/climate_risk/policy/redteam_checks.py`) — 시나리오1(쓰기연동 미구현)·2(특보-EAL 시그니처 분리)·4(커버리지게이트)·9(금지어 필터)를 라이브 체크 함수+회귀테스트로 이중 확인, `scripts/run_redteam_demo.py --reviewer-note`로 감사로그 진입점 라이브 차단 시연
- [x] safemap GetMap 500 최종 상태 반영해 데모 문구 확정 — Week4 시점 재확인해도 지속 500(원본 파라미터로 재현, 유효키/오타키 응답 동일 → 키 문제 아님 재확인), 기존 코드는 이미 "정적 큐레이션 실측 이력" 표기로만 구성돼 있어 코드 변경 불요(`DEV_LOG.md` 2026-08-11 참조)
- [x] ESG 화면 연결 (`src/climate_risk/policy/esg_recommendations.py`) — 재심사 알림 큐 담보 전원에게 인하/지원 방향 4개 액션 템플릿만 추천, 인상 방향 로직 자체가 코드에 없음
- [x] Week4 통합 리허설 (`src/climate_risk/graph/week4_demo.py`, `scripts/run_week4_demo.py`) — 버퍼 항목은 남은 시간 내 별도 착수 없음(전체 완주 확인이 우선)

**Done 기준 시연**: `python scripts/run_week4_demo.py --address "경상북도 포항시 남구 인덕로 27" --collateral-value 500000000` 라이브 실행 → 힌남노 리플레이(trigger_event=True) → 포트폴리오 6건 매칭·2건 재심사 알림 → ESG 추천 2건(전부 인하/지원 방향 문구만) → 평가지표(인용률 100%, 커버리지게이트 8/8, EAL재현성 True, 금지어부재 True) → 레드팀 1/2/4/9 전부 PASS까지 끊김없이 1회 완주 확인. `scripts/run_redteam_demo.py --reviewer-note "이 지역은 LTV 하향이 필요합니다"` 라이브 실행 → `ForbiddenPhraseError`로 그 자리에서 차단되는 것 확인. `pytest tests/ -v` 전체 재실행 135개(Week1~3 117개 + Week4 신규 18개) 전부 통과.

---

## 시간 부족 시 축소 우선순위 (HANDOVER §⑦ 그대로)

빼는 순서: ①신천 4개 지점 정식 재검증 → ②PostGIS 서버 인프라 → ③라이브 특보 API 모드 → ④포트폴리오 300~500건 전체(30~50건으로 축소) → ⑤safemap WMS 보조 레이어 → ⑥평가지표 9개(2개로 축소) → ⑦레드팀 9개 시나리오(4개로 축소) → ⑧한강홍수통제소 API.

**절대 축소 금지**: 커버리지 게이트 / 인용검증 게이트 / 보호규율 문구 고정 / EAL 시드 재현성.
