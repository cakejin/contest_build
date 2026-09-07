# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

# 담보 기후리스크 여신심사 AI — 구현 저장소

담보 주소 1건 → 침수위험 판정·건물취약도·몬테카를로 EAL → 근거 인용 심사메모.
기상특보/재난문자 발효 시 해당 지역 담보만 재계산해 재심사 알림 큐에 올린다.
Python(계량 코어·에이전트) + FastAPI/SSE + React 데모 UI.

## 문서 지도 (역할이 다르니 섞지 말 것)
- **HANDOVER.md** — PM이 확정한 계획·근거. 요약 카드(상단 30줄)부터 읽고 필요한 절만 찾아본다. 여기 결정(스코프·LLM벤더·배포방식)은 재논의하지 않는다. 배경이 더 궁금하면 `../contest_research/plans/`·`../contest_research/decision/qna/`를 절대경로로 직접 열어도 된다(같은 컴퓨터의 리서치 저장소).
- **DEV_LOG.md** — "계획과 다르게 나온 것"만 시간순 기록. 구현 중 HANDOVER의 가정과 다른 게 확인되면 여기 남긴다(형식은 파일 상단). 여기 적는다고 계획이 자동으로 바뀌진 않는다 — PM이 읽고 판단한다. **코드 주석이 `DEV_LOG.md YYYY-MM-DD 참조`라고 가리키는 경우가 많으니, 이유가 궁금한 상수·우회로는 먼저 그 날짜 항목을 찾아볼 것.**
- **DATA_SPEC.md** — "지금 코드가 실제로 무엇을 하는가"(데이터 소스 인벤토리 + 파이프라인 단계별 입력→계산→출력). 계량식·가중치·AEP 값의 출처를 확인할 때.
- **PROGRESS.md** — 주차별 완료 상태와 각 항목의 실측 시연 근거.
- 이 저장소는 계획이 아니라 **실제 구현**을 담당한다. 아키텍처 방향을 바꾸고 싶으면 먼저 사용자와 논의할 것.

## 명령어

```powershell
# 의존성 (별도 venv 관례 없음 — 시스템 python 3.10+)
pip install -r requirements.txt

# 전체 테스트 (pytest.ini가 pythonpath=src, testpaths=tests를 설정)
pytest tests/ -q
pytest tests/test_coverage_gate.py -v                     # 파일 단위
pytest tests/test_eal_seed_reproducibility.py::test_same_seed_reproduces_identical_result -v   # 단일 테스트

# 단건 심사 (Week2 계량 코어만)
python scripts/run_assessment.py --address "경상북도 포항시 남구 인덕로 27" --collateral-value 500000000

# 통합 데모 (특보+메모+포트폴리오+ESG+평가지표+레드팀) — CLI 플래그는 scripts/_demo_cli.py 공통
python scripts/run_week4_demo.py --address "..." --collateral-value 500000000 \
    --region-code 27260 --mode replay --timeline-path data/.../daegu_suseong_2026/events.json
#   --mode: replay(큐레이션 JSON) | live(기상청 실시간) | historical(API허브 과거이력+재난문자) | disaster_msg

# 평가 대시보드 / 레드팀 차단 시연
python scripts/run_eval_dashboard.py --address "..." --collateral-value 500000000
python scripts/run_redteam_demo.py --reviewer-note "이 지역은 LTV 하향이 필요합니다"   # ForbiddenPhraseError로 차단되는 게 정상

# 알림 트리거 검증 하네스 (2단계: 캐시 생성=유일한 라이브 호출 / 평가=오프라인)
python scripts/fetch_alert_validation_cache.py
python scripts/run_alert_validation.py

# 웹 데모
uvicorn webapp.app:app --reload            # 백엔드(:8000) + webapp/static 정적 서빙
cd webapp/frontend && npm run dev           # 프론트 개발서버(/api는 :8000으로 프록시)
cd webapp/frontend && npm run build         # → webapp/static/ 로 빌드(백엔드가 서빙하는 그 경로)
cd webapp/frontend && npm run lint          # oxlint
```

**첫 호출 75초**: `gis/loader.py`의 SHP 콜드 로딩이 프로세스당 1회 발생한다(이후 호출은 ~0.4ms). 디스크 캐시(`config.GIS_LOAD_CACHE_PATH`)가 있어 재실행 사이에는 반복되지 않는다. 데모/테스트가 멈춘 것처럼 보여도 기다릴 것.

**`data/`는 gitignore 대상이고 저장소에 없다** — 홍수위험지도 SHP는 자동 다운로드가 불가능한 수동 파일이고(공공누리 4유형), 큐레이션 타임라인·합성 포트폴리오·감사로그도 전부 여기 있다. `data/`가 없으면 GIS·데모·포트폴리오 테스트는 실행 불가다. 새 SHP를 추가할 땐 `config.py::FLOOD_SHP_SOURCES`에 항목만 추가하면 되고 질의 코드는 손대지 않는다(그 목록이 유일한 진실의 원천 — `SHP_FILENAME_TO_REGION_CODE`도 여기서 파생).

`.env`(gitignore)에 건축HUB·기상청·V-World·juso·safetydata 키가 들어있다. **serviceKey는 이미 percent-encoding된 값이므로 재인코딩 금지**(`urlencode()`에 다시 넣으면 400). safemap GetMap은 HTTP 500 고정으로 폐기 — 범례 API(`lgdInfo`)만 사용.

## 아키텍처

**계량 코어(화이트박스) ↔ LLM 계층이 엄격히 분리**된 것이 이 저장소의 뼈대다. 판정에 관여하는 코드는 전부 결정론적이고, LLM은 이미 계산된 값을 문장으로 옮기는 데만 쓰인다.

```
주소 → geocoding/vworld.py (그래프 밖 전처리 — 좌표 없으면 어떤 에이전트도 실행하지 않음)
     → graph/pipeline.py  LangGraph: flood → building → scenario  (순차; building이 flood의 tier/seg_code로 층별 노출도 계산)
         flood_agent    : gis/coverage.py 게이트 → gis/query.py point-in-polygon → tier(내부/근접/원거리)
         building_agent : V-World 역지오코딩 → 건축HUB 대장 → building/vulnerability.py 가중합
         scenario_agent : scenario/eal.py 몬테카를로(seed=42, 10,000회, numpy 벡터화)
     → graph/week3_demo.py  + advisory(특보) + memo(LLM) + portfolio(알림) 
     → graph/week4_demo.py  + ESG 추천 + evaluation 지표 + redteam 체크
```

- **에이전트는 얇은 래퍼**다. 실제 계산은 `gis/`·`building/`·`scenario/` 순수 함수에 있고 `agents/*.py`는 거기에 `source_id`·`field_sources` 태깅을 붙일 뿐이다. 이 태깅이 인용검증의 입력이 된다.
- **인용 이중화**: `memo/source_registry.py`가 에이전트 출력에서 인용 가능한 `source_id` 집합을 모으고, `memo/citation_gate.py`가 LLM 출력의 `citations`를 그 집합과 순수 문자열 대조한다(프롬프트 지시와 완전 독립 — 인젝션으로 지어낸 source_id도 여기서 걸린다). 실패율이 `CITATION_FAILURE_FALLBACK_THRESHOLD`(30%)를 넘으면 `memo/fallback_template.py` 규칙기반 메모로 폴백. `policy/forbidden_phrases.py`는 이와 독립된 두 번째 검증축.
- **LLM 호출 지점은 `llm/claude_cli.py` 단 하나** — `claude -p` 서브프로세스(`--bare` 금지, `--disallowedTools`로 Bash/Read/Write/WebFetch 차단, `--strict-mcp-config`). 1회 ~$0.20·5~10초라 배치 경로에서는 절대 호출하지 않는다.
- **알림 채널이 둘, 의도적으로 분리**돼 있다. `portfolio/alerts.py`는 EAL 변화율(≥20%) 기반, `portfolio/severity_alerts.py`는 특보 종류(호우·태풍·홍수·폭풍해일 경보 이상) + 담보별 최근접 관측소 일강수 2단계(110/180mm) 기반이다. 후자의 데이터클래스에는 EAL·LTV·금리·score 필드가 **하나도 없다** — 특보 심각도가 금전 계산에 섞이지 않는다는 설계원칙2를 스키마로 강제한 것이고, `policy/redteam_checks.py::check_scenario_severity_isolation()`이 회귀로 고정한다. 형제 모듈이지 확장이 아니므로 한쪽 로직을 다른 쪽에 합치지 말 것.
- **특보 조회는 4개 모드**가 서로 다른 API다: `advisory/replay.py`(큐레이션 JSON) / `advisory/live.py`(data.go.kr, "지금 시점"만 — 6일 초과 과거조회 구조적 불가) / `advisory/kma_historical.py`(apihub.kma.go.kr, 2004~현재 이력 — data.go.kr과 포털·키·구역코드가 전부 다름) / `advisory/disaster_msg.py`(safetydata 재난문자, 구·동 단위 세분화 + 산불·화재 포함, IP 화이트리스트 1개 제약).
- **잠정 상수는 이름을 붙여 `config.py`에 모아둔다**(가중치 w1~w4, AEP 매핑, 알림 임계치, 강수 110/180mm 등). 전부 "실측 캘리브레이션 대기" 표시가 붙은 값이며 근거 문자열도 같이 노출된다 — 코드 여기저기에 매직넘버로 흩어놓지 말 것.
- **webapp은 얇은 계층**: `webapp/app.py`는 `run_week4_demo`를 그대로 호출하고 `on_stage` 콜백을 SSE로 중계할 뿐, 판정 로직을 새로 만들지 않는다. 진행 문구는 타이머 흉내가 아니라 실제 단계 신호다. 프론트는 `webapp/frontend`(React+TS+Tailwind, Vite) → 빌드 산출물이 `webapp/static`.
- **GIS 주의**: 이 SHP들은 최대 3,236 파트짜리 다중파트 폴리곤이라 STRtree의 `predicate=` 질의가 틀린 결과를 낸다. bbox 후보 필터링에만 STRtree를 쓰고 covers 판정은 개별 shapely 객체에 직접 호출하는 패턴을 반드시 따를 것(DEV_LOG 2026-08-09).

## 지켜야 할 설계 원칙 (위반 시 서사 붕괴 — HANDOVER.md ①·④·⑥)
1. **데이터 없음 ≠ 위험 없음**: 커버리지 밖이면 조용히 "안전"으로 처리하지 말고 `OUT_OF_SCOPE`/판정보류를 명시 반환한다. 강수 관측 실패도 마찬가지로 "강수미확인" 등급을 유지한다.
2. **금전적 트리거는 관측 원자료에만 앵커링**: 특보는 "알림" 트리거로만 쓰고 EAL·LTV·금리 계산에 직접 연결하지 않는다.
3. **소급 불리 적용 금지**: 기존 차주의 LTV 하향·금리 인상·회수 트리거로 쓰지 않는다. 인센티브는 인하 방향만 구현한다.
4. **인용 강제**: 심사메모의 모든 문장은 `source_id`를 가져야 하고, 인용 없는 문장은 렌더링을 차단한다(모델 출력만으로 판단하지 말고 별도 검증 레이어로 이중화).
5. **계량 코어는 화이트박스**: 홍수·건물취약도·EAL 계산에 LLM/블랙박스 ML을 쓰지 않는다 — 전부 결정론적 함수·공간질의·몬테카를로로 재현 가능해야 한다.

**절대 축소 금지 4항**: 커버리지 게이트 / 인용검증 게이트 / 보호규율 문구 고정 / EAL 시드 재현성.

## 테스트 규율
- 신천 5개 지점(남구=확정, 나머지 4개=판정보류)을 커버리지 게이트 회귀 테스트로 고정 등록 — 매번 같은 결과(`OUT_OF_SCOPE` 등)가 나오는지 확인한다.
- EAL은 시드 고정 재현성 테스트 필수(같은 시드로 재실행 시 같은 값).
- 인용 검증 레이어는 "인용 없는 문장은 반드시 차단됨"을 실제로 확인하는 테스트를 둔다.
- **라이브 API를 테스트에서 직접 호출하지 않는다** — `flood_marks_validation`·`alert_validation`처럼 "라이브 호출은 fetch 스크립트 1개로 격리하고 캐시 JSON을 테스트가 읽는" 관례를 따른다.
- 트리거 규칙·임계값을 바꾸는 실험은 **후보와 라벨 정책을 첫 실행 전에 사전 등록**한 뒤 돌린다(`evaluation/trigger_candidates.py`, DEV_LOG 2026-09-03 항목들) — 결과를 보고 후보를 고르는 체리피킹을 구조적으로 막기 위한 관례.

## 커밋
- 이 저장소는 독립 git 저장소다(`contest_research`와 무관). 커밋은 사용자가 명시적으로 요청할 때만 한다.
