# 시스템·인프라 구조 (소켓 / 저장소 / 프로세스 구성)

"이 시스템이 어떤 프로세스로 떠서, 무엇으로 통신하고, 데이터를 어디에 어떻게 보관하는가"를
코드 기준으로 정리한다. 계산 내용은 `DATA_SPEC.md`·`docs/RECALCULATION.md`, 설계 의도는
`HANDOVER.md`, 계획과 달랐던 사실은 `DEV_LOG.md` 참조.

> **먼저 알아둘 두 가지 (오해가 잦은 지점)**
> 1. **WebSocket을 쓰지 않는다.** 실시간 진행상황은 **SSE(Server-Sent Events)** 단방향 스트림이다.
> 2. **DBMS가 없다.** PostgreSQL·PostGIS·SQLite·Redis 어느 것도 쓰지 않는다 —
>    저장소는 전부 **로컬 파일**(SHP / JSON / JSONL / pickle)이다. PostGIS는 HANDOVER의
>    확장 로드맵 항목이고, 현재 구현은 그 폴백으로 설계된 로컬 shapely 경로 하나만 존재한다.

---

## 1. 배포 형태

- **로컬 실행 전용**(HANDOVER 2026-08-07 확정). 공인 IP·VPC·DNS·HTTPS 인증서·컨테이너 오케스트레이션이
  전부 불필요하며 실제로 사용하지 않는다.
- 서버 프로세스는 **단일 uvicorn 프로세스** 하나. 워커 다중화·로드밸런서·리버스 프록시 없음.
- 인증·세션·사용자 계정 개념이 없다(내부 도구 데모).
- OS는 Windows(개발 환경 기준), Python 3.10+.

```
┌──────────────────────────── 개발자 PC 1대 ─────────────────────────────┐
│                                                                       │
│  브라우저 ──HTTP/SSE──> uvicorn (FastAPI, :8000)                       │
│    │                      ├─ /            → webapp/static (Vite 빌드)  │
│    │                      ├─ /portfolio-map → webapp/portfolio_map.html │
│    │                      └─ /api/*        → climate_risk 패키지 호출   │
│    │                                  │                                │
│    └─(개발 시) Vite dev server :5173 ─┘ (/api 프록시 → 127.0.0.1:8000) │
│                                       │                                │
│                     ┌─────────────────┴──────────────────┐             │
│                     │                                    │             │
│              로컬 파일 저장소                       외부 공공 API        │
│         (SHP / JSON / JSONL / pickle)        (V-World·건축HUB·기상청·    │
│                                               safetydata·JUSO)          │
│                                       │                                │
│                                `claude -p` 서브프로세스 (메모 생성 시)   │
└───────────────────────────────────────────────────────────────────────┘
```

CLI 경로(`scripts/*.py`)는 서버를 거치지 않고 같은 `climate_risk` 패키지를 직접 호출하는 **별도 프로세스**다.
웹과 CLI는 코드를 공유하지만 프로세스·캐시는 공유하지 않는다.

---

## 2. 프로세스·포트

| 프로세스 | 기동 | 포트 | 역할 |
|---|---|---|---|
| FastAPI 백엔드 | `uvicorn webapp.app:app --reload` | 8000(기본) | API + 정적 파일 서빙 |
| Vite 개발 서버 | `cd webapp/frontend && npm run dev` | 5173(기본) | 프론트 HMR, `/api`를 8000으로 프록시 |
| CLI 데모/배치 | `python scripts/*.py` | — | 서버 없이 단독 실행 |
| LLM 호출 | FastAPI/CLI가 `subprocess`로 `claude -p` 실행 | — | 심사메모 문장 생성(요청당 1회) |

- 프론트를 `npm run build`하면 `webapp/static/`에 산출물이 떨어지고, 그때부터는 백엔드 하나만 띄우면 된다
  (`vite.config.ts`의 `outDir: '../static'`, `emptyOutDir: true`).
- 정적 파일 마운트는 **모든 `/api` 라우트를 등록한 뒤 마지막에** `/`에 붙는다(등록 순서로 충돌 회피).
- 정적 응답에는 `Cache-Control: no-store` 미들웨어가 붙는다 — 데모 수정 후 "고쳤는데 그대로"를 막기 위함.

---

## 3. "소켓" 구성 — SSE 단방향 스트림

### 3.1 무엇을 쓰는가

| 항목 | 값 |
|---|---|
| 프로토콜 | HTTP/1.1 `GET /api/assess?...` → `text/event-stream` (SSE) |
| 서버 구현 | `fastapi.responses.StreamingResponse` + 제너레이터 (`webapp/app.py`) |
| 클라이언트 | 브라우저 표준 `EventSource` (`webapp/frontend/src/api.ts::startAssessStream`) |
| 방향 | **서버 → 클라이언트 단방향**. 클라이언트 입력은 쿼리스트링으로만 전달 |
| WebSocket | **사용하지 않음** (`websockets` 의존성도 없음) |
| 이벤트 종류 | `progress`(여러 번), `result`(1회) |

### 3.2 왜 WebSocket이 아닌가

필요한 것이 "한 번의 평가 요청 동안 서버가 진행 단계를 밀어주는 것"뿐이고 클라이언트 → 서버 양방향
메시지가 없다. SSE는 브라우저 내장 `EventSource`만으로 끝나고 별도 라이브러리·핸드셰이크·재연결 정책이
필요 없다. 요청이 끝나면 스트림도 끝나는 **요청 수명 = 연결 수명** 모델이다.

### 3.3 요청 1건의 수명

```
브라우저 EventSource 연결
      │
      ├─ FastAPI가 queue.Queue 생성
      ├─ daemon threading.Thread 시작 → run_week4_demo(..., on_stage=콜백) 실행
      │        on_stage(stage, msg) 호출될 때마다 queue.put(SSE 문자열)
      │
      └─ 응답 제너레이터가 queue.get()으로 블로킹 대기하며 그대로 yield
                 …
         작업 완료 → queue.put(result 이벤트) → queue.put("__STREAM_DONE__")
                 → 제너레이터 break → 연결 종료 → 프론트가 source.close()
```

- **스레드 + Queue 브리지가 필요한 이유**: 계량 코어는 전부 동기·블로킹 코드(shapely 연산, `requests` HTTP,
  `subprocess`)라 async 이벤트 루프에서 그대로 돌리면 서버 전체가 멈춘다. 작업을 별도 스레드로 내보내고
  스트림 제너레이터는 큐만 소비한다.
- **진행 문구는 타이머 흉내가 아니다.** `graph/week3_demo.py::_notify`가 실제로 그 단계에 진입할 때만 불린다.
  SHP 캐시가 비어 있으면 "최초 로딩(약 75초)" 문구로 분기하는 것도 실제 캐시 상태(`lru_cache.cache_info()`)를 본 결과다.
- **예외도 스트림으로 나간다.** 작업 스레드가 예외를 잡아 `{"error": ...}` 형태의 `result` 이벤트로 보낸다 —
  연결이 조용히 끊기지 않는다.
- **취소**: 프론트가 `source.close()`를 호출해도 이미 시작된 백그라운드 스레드는 끝까지 돈다(취소 전파 없음).

### 3.4 SSE가 아닌 나머지 API

`/api/regions`, `/api/portfolio-list`, `/api/portfolio-map`, `/api/resolve-region`, `/api/address-search`는
평범한 동기 JSON 응답이다. 목록 규모가 작아 서버측 페이지네이션·검색 API를 두지 않고 전량을 한 번에 내려
프론트에서 필터링한다.

---

## 4. "DB" 구성 — 파일 기반 저장소 4종

DBMS는 없다. 저장소는 아래 4종이고 전부 `data/` 아래에 있으며 `data/`는 `.gitignore` 대상이다.

| # | 종류 | 경로(`config.py` 상수) | 포맷 | 읽기 | 쓰기 | 수명 |
|---|---|---|---|---|---|---|
| 1 | 원자료 GIS | `RAW_DATA_DIR` (`FLOOD_SHP_SOURCES`) | SHP/DBF/PRJ/SHX | `gis/loader.py` | **없음(읽기 전용)** | 정적. 환경부에서 사람이 수동 다운로드 |
| 2 | 로딩 캐시 | `GIS_LOAD_CACHE_PATH` | pickle | `load_all_regions_cached` | 같은 함수 | 파생물. 지워도 재생성(75초) |
| 3 | 큐레이션·합성 데이터 | `CURATED_DATA_DIR` (포트폴리오, 특보 타임라인, 알림검증 라벨/캐시) | JSON | `portfolio/loader.py`, `advisory/curated_loader.py` | 배치 스크립트만 | 준영구. 사람이 관리 |
| 4 | 감사로그 | `AUDIT_LOG_PATH`, `ALERT_QUEUE_LOG_PATH`, `SEVERITY_ALERT_QUEUE_LOG_PATH`, `ADVISORY_LIVE_LOG_PATH` | JSONL | (조회 UI 없음) | **append-only** | 영구 누적 |

### 4.1 각 저장소의 성격

- **① SHP(원자료)**: 공공누리 4유형(출처표시·상업이용 금지·**변경금지**)이라 코드가 원본을 변형하지 않는다.
  파생 스코어의 대량 export·재배포 기능도 만들지 않는다(조회 API만 제공).
  좌표계는 EPSG:5186 원본 그대로 보관하고 질의 시 WGS84에서 변환해 들어간다.
- **② pickle 캐시**: SHP 콜드 로딩(polygonize + make_valid, 7개 합쳐 수 분)이 프로세스마다 반복되는 걸 막는다.
  SHP/DBF의 **mtime+size 매니페스트**와 캐시 포맷 버전으로 자동 무효화하며, 원본이 바뀌면 조용히 재로딩한다.
  임시파일에 쓴 뒤 교체하는 방식이라 중간에 죽어도 반쪽 캐시가 남지 않는다.
  (`tests/test_loader_idempotent.py`는 "진짜 재파싱"을 검증해야 하므로 의도적으로 이 캐시를 우회한다.)
- **③ 포트폴리오 JSON**: 이 시스템에서 유일하게 **읽고 쓰는** 업무 데이터다.
  - 쓰기 주체는 배치 스크립트뿐: `scripts/geocode_portfolio.py`(lat/lon·region_code 워밍업 write-back),
    `scripts/generate_portfolio.py`(신규 레코드 생성), `scripts/backfill_insurance_coverage.py`.
  - **웹 요청 경로는 이 파일에 쓰지 않는다** — 재계산 결과는 알림 큐와 로그로만 나간다(`docs/RECALCULATION.md` §4).
  - 파일 전체를 읽어 dataclass 리스트로 만들고, 저장 시 전체를 다시 쓴다(부분 갱신·트랜잭션 없음).
- **④ 감사로그(JSONL)**: 한 줄 = JSON 1건, append만 한다. 심사역 확인 클릭(`reviewer_ack_log`),
  EAL 알림 큐, 심각도 알림 큐, 라이브 특보 조회 이력(`advisory_live_log`)이 각각 **다른 파일**이다.
  두 알림 로그를 합치지 않는 것은 "서로 다른 신호에서 나왔다"는 사실을 구조로 보존하려는 설계다.
  기상청 라이브 API가 과거 조회를 지원하지 않으므로, `advisory_live_log`는 나중에 "그날 그 지역에 무슨
  특보가 있었는지"를 재구성할 수 있는 유일한 기록이 된다(현재 이걸 읽는 UI는 없다 — 축적만 한다).

### 4.2 캐시 계층 정리

| 계층 | 위치 | 범위 | 무효화 |
|---|---|---|---|
| SHP 파싱 결과 | `gis/query.py::_cached_default_regions` (`lru_cache(maxsize=1)`) | 프로세스 1개 | 프로세스 종료 |
| SHP 파싱 결과 | `GIS_LOAD_CACHE_PATH` (pickle) | 머신 전역 | 원본 mtime/size·포맷 버전 |
| 지오코딩 결과 | 포트폴리오 JSON의 `lat/lon/geocoded_at` | 영구 | 스크립트 재실행 |
| 알림검증용 API 응답 | `ALERT_VALIDATION_DIR` 하위 JSON | 영구 | `fetch_alert_validation_cache.py` 재실행 |

첫 호출 75초 → 이후 약 0.4ms가 이 캐시들의 효과다. 캐시가 없던 시절 300건 배치는 약 8시간이 걸렸다(DEV_LOG 2026-08-09).

---

## 5. 외부 의존 (네트워크 경계)

| 대상 | 포털/호스트 | 키 상수 | 호출 지점 | 제약 |
|---|---|---|---|---|
| 지오코딩·역지오코딩 | V-World | `VWORLD_API_KEY` | `geocoding/vworld.py` | 일 3만건 |
| 건축물대장 | 건축HUB(data.go.kr) | `DATA_GO_KR_API_KEY` | `building/brhub.py` | 일 1만건. serviceKey **재인코딩 금지** |
| 기상특보(실시간) | data.go.kr | `DATA_GO_KR_API_KEY` | `advisory/live.py` | "지금 시점"만. 6일 초과 과거조회 구조적 불가 |
| 기상특보(과거 이력)·지상관측 | apihub.kma.go.kr | `KMA_API_HUB_KEY` | `advisory/kma_historical.py`, `kma_observation.py` | **위와 다른 포털·다른 키·다른 구역코드**. API별 활용신청 필요 |
| 재난문자 | safetydata.go.kr | `SAFETYDATA_DISASTER_MSG_API_KEY` | `advisory/disaster_msg.py` | **IP 화이트리스트 1개만 등록 가능** — 등록 IP가 아니면 거부 |
| 도로명주소 검색 | business.juso.go.kr | `JUSO_API_KEY` | `geocoding/juso.py` | 개발 승인키(유효기간 제한). 실패해도 자동완성만 degrade |
| LLM | 로컬 `claude` CLI | (`.env` 아님, CLI 세션 인증) | `llm/claude_cli.py` | 요청당 약 $0.20·5~10초 |

- 키는 전부 `.env`(gitignore)에서 `config.py`가 로드한다. 코드에 키가 하드코딩된 곳은 없다.
- **폐기된 소스**: safemap GetMap(WMS 이미지)은 HTTP 500 고정으로 호출하지 않는다 — 범례 API만 사용.
- 테스트는 라이브 API를 직접 부르지 않는다. 라이브 호출은 fetch 스크립트 1개로 격리하고 테스트는 캐시 JSON을 읽는다.

### 5.1 LLM 호출의 보안 경계

`claude -p` 서브프로세스는 프롬프트 인젝션 방어를 위해 다음이 강제된다:
`--disallowedTools`로 Bash/Read/Write/Edit/NotebookEdit/WebFetch/WebSearch 차단, `--strict-mcp-config`로
외부 MCP 서버 차단, 응답은 `--json-schema`로 구조 검증. `--bare`는 OAuth 세션 인증을 읽지 못해 쓰지 않는다.
메모 생성이라는 좁은 텍스트 변환에 파일시스템·네트워크 부작용을 허용할 이유가 없다.

---

## 6. 동시성 모델

| 지점 | 방식 |
|---|---|
| 웹 요청 1건 | FastAPI 동기 핸들러 + **요청마다 daemon 스레드 1개**(SSE 작업용) |
| 포트폴리오 재계산 | `ThreadPoolExecutor(max_workers=8)` — 레코드별 독립 blocking HTTP I/O |
| 몬테카를로 | 스레드 없음. 레코드마다 로컬 `np.random.default_rng(seed)` (공유 상태 없음 → 재현성 보존) |
| SHP 캐시 | 프로세스 단위 `lru_cache` 공유(읽기 전용) |

- 서버는 **단일 프로세스 1워커** 전제다. 워커를 늘리면 프로세스마다 SHP 캐시(수백 MB급 지오메트리)가
  중복 적재되고 콜드 로딩도 워커 수만큼 발생한다.
- 재현성은 워커/스레드 수와 무관하다 — seed가 호출마다 로컬 RNG로만 쓰이기 때문.

---

## 7. 현재 구조의 한계 (알려진 것만)

1. **JSONL 동시 append에 락이 없다.** 서버와 CLI 배치를 동시에 돌리면 같은 로그 파일에 두 프로세스가
   append한다. 실사용에서 문제를 관측한 적은 없으나 보장된 동작도 아니다 — 다중 프로세스 운영 전에 확인 필요.
2. **포트폴리오 JSON은 전체 덮어쓰기**라 동시 write-back에 안전하지 않다(현재는 배치 스크립트 단독 실행 전제).
3. **인증·권한·감사 조회 UI가 없다.** 감사로그는 쌓이기만 하고 읽는 화면이 없다.
4. **스트림 취소가 전파되지 않는다.** 브라우저가 연결을 끊어도 백그라운드 작업은 완주한다.
5. **PostGIS 경로는 구현되지 않았다.** HANDOVER가 "PostGIS 실패 시 로컬 폴백"으로 설계했던 것 중
   로컬 경로만 존재한다(축소 우선순위 ②로 명시적으로 제외됨).

---

## 8. 사람이 채워야 할 빈칸 (아직 결정·검증되지 않음)

아래는 코드에서 확인할 수 없는 항목이라 비워둔다. 결정되면 이 절을 채우고, 계획과 어긋나면 `DEV_LOG.md`에도 남길 것.

### 8.1 운영 환경 전환 시 인프라
- [ ] 실제 은행 환경 배포 형태(온프레·VPC·망분리 여부):
- [ ] 서버 사양·워커 수·프로세스 관리(systemd/서비스 등록 여부):
- [ ] HTTPS·인증(SSO/AD 연동) 요구사항:

### 8.2 저장소 전환
- [ ] 파일 → DB 전환 시점과 대상(포트폴리오/감사로그 중 무엇부터):
- [ ] DBMS 후보와 선정 근거(PostGIS 필요성 포함):
- [ ] 감사로그 보존기간·백업·접근권한 정책:

### 8.3 알림 채널 확장
- [ ] 푸시/카카오 등 외부 채널 연동 여부와 발송 빈도 제한 설계:
- [ ] 심각도 요약 알림의 수신자·에스컬레이션 규칙:

### 8.4 운영·관측
- [ ] 로그 수집·모니터링 도구:
- [ ] 외부 API 장애 시 폴백 정책(현재는 실패를 그대로 표기):
- [ ] 정기 배치 스케줄러(현재 스케줄러 없음 — 수동 실행):

---

## 9. 관련 파일

| 구분 | 경로 |
|---|---|
| 웹 백엔드(SSE 포함) | `webapp/app.py` |
| 프론트 SSE 클라이언트 | `webapp/frontend/src/api.ts` |
| 프론트 빌드 설정(outDir/프록시) | `webapp/frontend/vite.config.ts` |
| 경로·키·상수 단일 소스 | `src/climate_risk/config.py` |
| SHP 로딩·디스크 캐시 | `src/climate_risk/gis/loader.py` |
| 프로세스 캐시 | `src/climate_risk/gis/query.py` |
| 파일 저장소 I/O | `portfolio/loader.py`, `portfolio/alerts.py`, `portfolio/severity_alerts.py`, `policy/audit_log.py` |
| 웹 계약 회귀 테스트 | `tests/test_webapp_endpoints.py`, `tests/test_webapp_progress_hook.py` |
