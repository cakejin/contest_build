# 심사메모 이후 "재계산"에서 실제로 무엇을 계산하는가

이 문서는 `graph/week3_demo.py`가 심사메모 생성을 끝낸 뒤 실행하는 **포트폴리오 재계산 단계**가
무엇을 입력으로 받아 무엇을 계산하고 무엇을 내놓는지를 코드 기준으로 정리한다.
설계 의도는 `HANDOVER.md` §4.1, 계획과 달랐던 사실은 `DEV_LOG.md`(특히 2026-08-31·2026-09-03)를 참조.

---

## 0. 한 줄 요약

> 심사메모는 **입력한 담보 1건**에 대한 결과다. 그 다음 단계는 **같은 특보가 걸린 지역의 다른 담보들**을
> 꺼내와 홍수·건물취약도·EAL을 처음부터 다시 계산하고, "재심사가 필요할 수 있다"는 알림 큐 2종을 만드는 일이다.
> 재계산은 **담보 조건을 바꾸지 않는다** — 알림만 만든다.

---

## 1. 언제 실행되는가

`graph/week3_demo.py::run_week3_demo`의 실행 순서:

```
advisory(특보 조회) → geocode → flood → building → scenario(EAL) → memo(심사메모)
                                                                      ↓
                                              advisory.trigger_event == True 일 때만
                                                                      ↓
                                    portfolio(재계산)  ← 이 문서가 다루는 단계
```

- 특보가 없으면(`trigger_event=False`) 이 단계는 **아예 실행되지 않고** `portfolio_batch=None`이 된다.
  전체 포트폴리오 갱신은 이 트리거 경로의 책임이 아니라 정기 배치의 몫이다(HANDOVER §4.1 "혼합형 구조").
- 웹 데모에서는 이 단계 진입 시 SSE `progress` 이벤트(`stage="portfolio"`)가 나간다.
- 진입점: `agents/portfolio_agent.py::run_portfolio_agent`.

---

## 2. 재계산 5단계

### 2.1 지역 필터링 — `portfolio/filter.py::filter_by_region`

- **입력**: 포트폴리오 전체(`config.PORTFOLIO_DATA_PATH`의 JSON), 특보 지역코드 `advisory.region_code`
- **계산**: 레코드를 3개 버킷으로 가른다. `matched + skipped_ungeocoded + other_region == 전체`가 항상 성립.

  | 버킷                       | 의미                                                                                                |
  | -------------------------- | --------------------------------------------------------------------------------------------------- |
  | `matched`                  | 이번 특보 지역과 `region_code`가 일치 → 재계산 대상                                                 |
  | `skipped_ungeocoded_count` | `region_code`가 None — 지오코딩 실패 or SHP 커버리지 밖. **조용히 누락시키지 않고 센다**(설계원칙1) |
  | `other_region_count`       | 다른 지역 담보                                                                                      |

- **왜 전체가 아닌가**: 특보마다 수백 건 전체를 반복 계산하지 않는다는 것이 혼합형 구조의 핵심(HANDOVER §4.1).

### 2.2 서브셋 재계산 — `portfolio/recalc.py::recalc_subset`

매칭된 레코드마다 **단건 심사와 완전히 동일한 3개 에이전트 함수**를 다시 호출한다(파이프라인을 새로 만들지 않음).

| 순서 | 함수                                                                        | 다시 조회하는 것                                          | 산출                                                   |
| ---- | --------------------------------------------------------------------------- | --------------------------------------------------------- | ------------------------------------------------------ |
| 1    | `run_flood_agent(lat, lon)`                                                 | 로컬 SHP(프로세스 캐시 히트, 네트워크 없음)               | coverage / in_polygon / tier / 거리 / freq_label       |
| 2    | `run_building_agent(lat, lon)`                                              | V-World 역지오코딩 + 건축HUB 건축물대장 (**라이브 HTTP**) | `vulnerability_score`(0~100), status OK/PARTIAL/FAILED |
| 3    | `run_scenario_agent(flood, building, collateral_value, seed, n_iterations)` | 없음(파라메트릭)                                          | `EAL_mean/p50/p95/p99` + 히스토그램                    |

- **지오코딩은 다시 하지 않는다** — `scripts/geocode_portfolio.py`가 미리 채워둔 `lat/lon`을 재사용한다.
- **병렬**: `ThreadPoolExecutor(max_workers=8)`. 레코드마다 독립적인 blocking HTTP I/O라서다. seed는
  레코드별 `np.random.default_rng(seed)` 로컬 인스턴스에서만 쓰여 스레드 간 공유 상태가 없다.
- **`target_floor`(층별 노출도)는 넘기지 않는다** — 포트폴리오 레코드에 층 정보가 없으므로 건물 전체 스코어링.

### 2.3 EAL 변화율 알림 큐 — `portfolio/alerts.py::build_alert_queue`

- **계산**: `EAL_change_pct = (EAL_after - EAL_before) / EAL_before`
- **before/after의 정확한 의미**:
  - `EAL_before`·`score_before` = 포트폴리오 JSON에 박혀 있는 **최근 평가 시점 스냅샷**. 임의 숫자가 아니라
    `scripts/generate_portfolio.py`가 실제 에이전트를 1회 돌려 만든 값이다. 특보로 이 값이 움직이면 안 되므로 고정.
  - `EAL_after`·`score_after` = 방금 2.2에서 나온 신선한 값.
- **알림에서 빠지는 경우**(전부 의도된 것):

  | 조건                      | 처리                  | 이유                                                                 |
  | ------------------------- | --------------------- | -------------------------------------------------------------------- |
  | `EAL_before is None`      | 비교 불가 → 알림 없음 | 스냅샷 시점 커버리지 밖. 0으로 대체하면 "무(無)에서 급증"으로 오판됨 |
  | `EAL_after is None`       | 알림 없음             | `INSUFFICIENT_INPUT` — 입력이 불충분하면 EAL을 만들지 않는다         |
  | `before == 0, after == 0` | 알림 없음             | 변화 없음                                                            |
  | `before == 0, after > 0`  | `inf`로 기록          | JSONL 저장 시 `"inf"` 문자열로 치환(표준 JSON 유지)                  |
  | 변화율 절댓값 < 20%       | 알림 없음             | `config.EAL_ALERT_THRESHOLD_PCT`(잠정치)                             |

- **출력 스키마**(HANDOVER §4.1 그대로): `{collateral_id, score_before, score_after, EAL_before, EAL_after,
EAL_change_pct, threshold, geocode_confidence, insurance_covered}`.
  **LTV·금리 필드는 없다** — 보호규율 2항(소급 불리 적용 금지). 이 큐는 조건 변경이 아니라 알림이다.

### 2.4 심각도 알림 큐 — `portfolio/severity_alerts.py::build_severity_alert_queue`

2.3과 **완전히 독립된 별도 채널**이다(형제 모듈이지 확장이 아님). EAL 재계산 결과를 전혀 참조하지 않으므로
2.3이 0건이어도 여기는 채워질 수 있다.

- **① 지역 트리거**: `is_high_severity_event(event)` — 호우·태풍·홍수·폭풍해일 계열이면서 특보 레벨이
  경보 이상(`경보`/`중대경보`)이거나 재난문자가 `긴급재난`/`위급재난`일 때만 켜진다.
  (2026-09-03 규칙 교체 전에는 폭염·강풍 경보에도 켜져 오탐이 4배였다 — DEV_LOG (계속2)~(계속10).)
- **② 담보별 강수 2단계**: 지역이 켜지면 담보마다 최근접 지상관측소(ASOS·AWS)의 조회 창 내 최대 일강수를 본다.

  | 일강수           | 등급                                                                             |
  | ---------------- | -------------------------------------------------------------------------------- |
  | ≥ 180mm          | 심각                                                                             |
  | ≥ 110mm          | 주의                                                                             |
  | < 110mm          | 알림 없음                                                                        |
  | 조회 불가/미조회 | **강수미확인**(알림 유지) — 데이터 없음을 위험 없음으로 바꾸지 않는다(설계원칙1) |

  임계값 근거는 기상청 호우주의보(12h 110mm)·호우경보(12h 180mm)의 일강수 근사다 —
  12시간 기준을 24시간 누적에 대면 느슨해지는 방향임을 명시한다(`config.REASSESSMENT_RAIN_THRESHOLD_BASIS`).

- **강수 조회 창**은 모드에 따라 다르다: `historical`=조회 구간 그대로 / `live`=어제~오늘 /
  `replay`=**없음**(큐레이션 이벤트에 관측 시점이 없어 전원 "강수미확인").
- **엔트리에 EAL·LTV·금리·score 필드가 하나도 없다** — 특보 심각도가 금전 계산에 새어 들어갈 수 없음을
  스키마로 강제한 것이고, `policy/redteam_checks.py::check_scenario_severity_isolation()`이 회귀로 고정한다.

### 2.5 요약 1건 + 감사로그 — `summarize_severity_alerts` / `append_to_*_log`

- **요약**(`SeverityAlertSummary`): "매칭 N건 중 주의 a·심각 s·강수미확인 u" + 임계값·근거 + 대표 특보 1건.
  알림 피로를 줄이기 위해 대시보드·향후 푸시의 **최종 알림 단위**는 담보별 목록이 아니라 이 요약 1건이다.
- **로그**: 두 큐를 각각 다른 JSONL 파일에 append한다(`ALERT_QUEUE_LOG_PATH`, `SEVERITY_ALERT_QUEUE_LOG_PATH`).
  파일을 합치지 않는 것도 설계다 — 두 채널이 서로 다른 신호에서 나왔다는 사실을 로그 구조로도 보존한다.

---

## 3. 두 알림 채널 비교

|                      | EAL 변화율 알림 (`alerts.py`)       | 심각도 알림 (`severity_alerts.py`)                   |
| -------------------- | ----------------------------------- | ---------------------------------------------------- |
| 신호                 | 물리 데이터 재계산 결과의 변화      | 특보 종류·등급 + 실측 강수량                         |
| 트리거               | EAL 변화율 절댓값 ≥ 20%             | 호우·태풍·홍수·폭풍해일 경보 이상 → 담보별 110/180mm |
| 특보를 입력으로 받나 | **아니오**                          | 예                                                   |
| EAL/LTV/금리 필드    | EAL만 있음(LTV·금리 없음)           | **하나도 없음**                                      |
| 조용해지는 경우      | 재계산 결과가 스냅샷과 거의 같을 때 | 특보 없음·등급 미달, 또는 강수 110mm 미만            |
| 로그                 | `alert_queue_log.jsonl`             | `severity_alert_queue_log.jsonl`                     |

---

## 4. 재계산이 **하지 않는** 것 (오해 방지)

1. **특보를 EAL에 넣지 않는다.** `run_scenario_agent()`의 시그니처에는 advisory·severity 파라미터가 없다.
   특보가 아무리 심각해도 EAL이 그 이유로 움직일 통로가 구조적으로 없다(설계원칙2, 레드팀 체크로 고정).
2. **LTV·금리·회수 조건을 계산하거나 변경하지 않는다.** 알림 스키마에 필드 자체가 없다(보호규율 2항).
3. **심사메모를 다시 쓰지 않는다.** LLM(`llm/claude_cli.py`)은 이 배치 경로에서 호출되지 않는다 —
   1회당 약 $0.20·5~10초라 수백 건 배치에 부적합하고, 계량 코어만으로 충분하다(설계원칙5).
4. **지오코딩을 다시 하지 않는다**(캐시된 lat/lon 재사용).
5. **포트폴리오 JSON의 `*_before` 값을 갱신하지 않는다.** 재계산 결과는 알림 큐와 로그에만 남는다.

---

## 5. 실측으로 확인된 한계 (반드시 함께 설명할 것)

`DEV_LOG.md` 2026-08-31 항목에 실사건 재현 기록이 있다.

- 거제 2026-08 실호우(관측 이래 최대 968.1mm, 고현천 범람으로 담보 밀집 상권 침수, 특별재난지역 선포)를
  이 시스템으로 재현했을 때 **EAL 변화율 알림은 한 건도 뜨지 않았다.**
  - "원거리" tier 담보는 발생확률이 낮아 EAL이 항상 정확히 0(0→0, 변화율 계산 불가)
  - "내부/근접" tier 담보는 `eal_after`가 `eal_before`와 바이트 단위로 동일(변화율 0.0%)
  - 근본 원인: EAL은 좌표+건축물대장+고정 seed만 보는 **정적 모델**이라 특보로 값이 바뀔 통로가 없다.
- 힌남노 리플레이 데모의 "+49%" 사례도 태풍 심각도가 반영된 것이 아니라, 재계산 시점 건축HUB 라이브 응답이
  포트폴리오 생성 시점과 달라진 **데이터 드리프트**로 설명된다.
- **그래서 심각도 알림 채널(2.4)이 생겼다.** EAL 코어와 특보-금전 분리 원칙은 그대로 둔 채,
  이미 파싱해두고 버리던 특보 등급·재난문자 등급을 별도 채널로 흘려보낸 것이다.
  같은 거제 사건을 historical 모드로 재조회하면 매칭 담보 전원에 심각도 알림이 생성된다.

> 정리하면: **EAL 변화율 채널은 "물건 데이터가 바뀌었는가"를 보고, 심각도 채널이 "지금 이 지역에 실제로
> 심각한 일이 벌어졌는가"를 본다.** 전자만으로 재해를 감지할 수 있다고 설명하면 실사건과 어긋난다.

---

## 6. 관련 파일·테스트·로그

| 구분                            | 경로                                                                                                                                                                                    |
| ------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 오케스트레이션                  | `src/climate_risk/agents/portfolio_agent.py`                                                                                                                                            |
| 필터 / 재계산 / 두 알림 큐      | `portfolio/filter.py`, `portfolio/recalc.py`, `portfolio/alerts.py`, `portfolio/severity_alerts.py`                                                                                     |
| 레코드 스키마(before 값의 의미) | `portfolio/schema.py`                                                                                                                                                                   |
| 강수 관측                       | `advisory/kma_observation.py`                                                                                                                                                           |
| 임계값·경로 상수                | `config.py` (`EAL_ALERT_THRESHOLD_PCT`, `REASSESSMENT_RAIN_THRESHOLD_*`)                                                                                                                |
| 테스트                          | `tests/test_portfolio_filter.py`, `test_portfolio_alerts.py`, `test_severity_alerts.py`, `test_portfolio_recalc_smoke.py`, `test_portfolio_agent_smoke.py`, `test_redteam_scenarios.py` |
| 로그(append-only)               | `data/.../audit/alert_queue_log.jsonl`, `.../severity_alert_queue_log.jsonl`                                                                                                            |

---

## 7. 직접 재현하기

```powershell
# 특보 트리거 → 재계산까지 한 번에 (리플레이)
python scripts/run_week4_demo.py --address "경상북도 포항시 남구 인덕로 27" --collateral-value 500000000

# 실사건 과거 이력으로 (거제 2026-08 호우) — 심각도 알림 채널이 켜지는 경로
python scripts/run_week4_demo.py --address "<거제 담보 주소>" --collateral-value 500000000 `
    --region-code 48310 --mode historical --historical-start 2026-08-17 --historical-end 2026-08-19
```

출력 JSON의 `portfolio_batch` 키가 이 문서가 설명한 전부다:
`matched_count` / `skipped_ungeocoded_count` / `other_region_count` / `recalculated[]` / `alerts[]` /
`severity_alerts[]` / `severity_summary`.
