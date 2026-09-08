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

## 2026-08-11 — 건축HUB `getBrTitleInfo` 주소→코드 해석 경로, 실호출로 확정(연구 단계 미검증 항목)

**계획(HANDOVER.md 기준)**: §4.2 2.3 "입력: 주소 또는 PNU" — `getBrTitleInfo`가 실제로는 자유 주소가 아니라 `sigunguCd`+`bjdongCd`+`platGbCd`+`bun`+`ji` 5개 코드를 요구한다는 사실 자체가 연구 단계 문서 어디에도 언급이 없었고, 이 코드로의 변환 경로는 전혀 실증되지 않은 상태였다(연구 단계 "실키 검증 완료"는 코드를 수동으로 넣은 API 자체 호출만 검증한 것). Week2 계획 단계에서 "라이브 체크포인트 필요"로 명시해두고 시작.

**실제**: 3가지가 실호출로 확인됨.
1. **주소→코드 해석**: Week1이 쓰는 V-World 주소 API의 순방향(`request=getcoord`, road/parcel 타입) 응답에는 법정동코드가 비어있거나(`level4LC=""`, road 타입) 도로명코드가 들어가(`level4LC="3303039"`, road 타입 역지오코딩) 쓸 수 없었다. 대신 **역지오코딩**(`request=getAddress`, `type=parcel`, `point=lon,lat`)을 좌표에 호출하면 `structure.level4LC`가 정확히 10자리(`sigunguCd(5)+bjdongCd(5)`, 예: "4711111200" = 포항 남구 47111 + 인덕동 11200)로 나오고 `structure.level5`가 지번("222-5")으로 나온다 — 이 조합이 실제로 `getBrTitleInfo`를 통과함을 확인(아래 3번). `sigunguCd`가 `config.py`의 `FLOOD_SHP_SOURCES.region_code`와 정확히 일치(47111, 27200)하는 것도 교차 확인됨.
2. **serviceKey 이중 인코딩 함정**: `DATA_GO_KR_API_KEY`가 `.env`에 이미 percent-encoding된 채로 저장돼 있다(`%` 문자 포함 확인). `urllib.parse.urlencode()`에 다른 파라미터와 같이 넣으면 이중 인코딩되어 `getBrTitleInfo`가 400(`NO_OPENAPI_SERVICE_ERROR`, 오도하는 메시지)을 반환했다 — serviceKey는 다른 파라미터와 분리해 raw로 쿼리스트링에 붙여야 정상 동작(`resultCode: "00"`).
3. **엔드포인트·필드명**: `https://apis.data.go.kr/1613000/BldRgstHubService/getBrTitleInfo`가 정확한 경로로 확정(HANDOVER 초안 추정과 일치). 응답 `body.items.item`은 항상 리스트(데이터 없어도 `[]`, 단건이어도 `[{...}]`) — 딕셔너리/리스트 혼용 걱정 불필요. `strctCdNm`·`mainPurpsCdNm`·`ugrndFlrCnt`·`grndFlrCnt`·`useAprDay` 필드명 전부 확인됨(building/vulnerability.py가 기대한 그대로). 레코드 없음(임야·존재하지 않는 지번)도 `resultCode: "00"`+`totalCount: "0"`로 정상 응답(예외 아님) — "예상된 부재→None" 관례 그대로 적용 가능.
4. **지번 파싱 주의사항(신규 발견)**: 대구 신천 남구·봉덕동 좌표(Week1 확정 좌표)로 테스트하니 `level5`가 "1617-1천"처럼 숫자가 아닌 접미사("천")를 포함하는 경우가 있었다 — 지번을 "-"로 split 후 그대로 4자리 zero-pad하면 `ji="001천"`(비숫자)이 되어 API 호출이 깨진다. `bun`/`ji`는 각각 앞쪽 숫자만 추출(비숫자 접미사 제거) 후 zero-pad해야 한다. (이 좌표 자체가 신천대로 위라 건물이 없는 지점일 가능성이 높아 이 특정 케이스의 최종 응답이 "빈 결과"인 것 자체는 정상일 수 있음 — 그러나 파싱 버그는 별개로 반드시 고쳐야 함.)

**영향**: `building/address_resolver.py`는 (a) 순방향 도로명주소 지오코딩(Week1 `geocode_road_address()`, 미변경) → (b) 그 결과 좌표로 V-World 역지오코딩(`type=parcel`) 자체 호출 → (c) `level4LC[:5]`/`level4LC[5:10]`/`level5`(숫자만 추출) 파싱 순서로 구현한다. 애초 계획서의 "Path 1(`req/data` feature query)"·"Path 2(수동 법정동코드 테이블)" 폴백은 불필요해짐 — Path 0(역지오코딩)만으로 충분히 해결됨. `platGbCd`는 응답 `text`의 "산" 접두어 유무로 판정(대지=0 확정, 산=1 잠정 — 산 지목 실호출 검증은 못 함, 데모 대상 주소가 전부 대지이므로 실무 영향 낮음).

## 2026-08-11 — 메모 에이전트 LLM 호출을 Anthropic API 직접 호출이 아니라 `claude -p` CLI 서브프로세스로 구현

**계획(HANDOVER.md 기준)**: §4.5 기술스택 "LLM(핵심): Claude 계열, **Anthropic API 직접 호출**"(⑦ A3, 2026-08-07 확정) — `anthropic` Python SDK로 API 키를 발급받아 직접 호출하는 것을 전제.

**실제**: Week3 착수 시점에 별도 `ANTHROPIC_API_KEY` 발급 없이, 이미 인증된 Claude Code CLI(`claude`)를 `subprocess`로 호출하는 방식을 채택(사용자 지시, "배포 목적 아니니 claude -p 어떤지"). 실측으로 확인된 것 3가지:
1. `--json-schema`는 파일 경로가 아니라 **인라인 JSON 문자열**을 받는다(경로를 넘기면 파싱 에러).
2. `--bare`(hooks·CLAUDE.md·memory 오버헤드 제거, 저비용)는 "Anthropic auth is strictly ANTHROPIC_API_KEY or apiKeyHelper"라 OAuth 세션 인증을 읽지 않아 "Not logged in" 에러가 남 — API 키가 없는 이 저장소 조건과 정면 충돌. 결국 `--bare` 없이 일반 모드로 세션 인증을 재사용(호출당 실측 비용 약 $0.20, 5~10초, CLAUDE.md 컨텍스트 로딩 포함).
3. 프롬프트 인젝션 방어를 위해 `--disallowedTools`(Bash/Read/Write/Edit/WebFetch/WebSearch 차단)+`--strict-mcp-config`로 부작용 있는 도구 접근을 원천 차단.
4. Windows에서 `subprocess.run(text=True)`가 로케일 기본 코드페이지(cp949)로 디코드해 UTF-8 한글 출력이 깨지는 문제(Week1 stdout 이슈와 같은 계열) — `encoding="utf-8"` 명시로 해결.

**영향**: 같은 Claude 모델(sonnet)을 호출하는 것이므로 벤더·리전 결정(HANDOVER §A3)과는 배치되지 않는다 — 호출 메커니즘(SDK 직접 호출 vs CLI 서브프로세스)의 차이일 뿐이다. `src/climate_risk/llm/claude_cli.py`가 이 저장소에서 `claude` 바이너리를 호출하는 유일한 지점. 상용화 단계에서 실제 Anthropic API 키 발급 전환이 필요하다면 이 모듈 하나만 교체하면 된다(호출부인 `agents/memo_agent.py`는 `call_claude_structured(prompt, schema_path) -> dict` 인터페이스에만 의존). PM은 HANDOVER §4.5의 "Anthropic API 직접 호출" 문구를 "Claude Code CLI 경유(데모 단계) → 상용화 시 API 직접 전환"으로 수정할지 판단 필요.

## 2026-08-11 — 합성 포트폴리오 주소는 실존 도로명 확인 후 채택(임의 조합 도로명은 지오코딩 실패율 높음)

**계획(HANDOVER.md 기준)**: 명시적 계획 없음 — HANDOVER §③은 "대구·경북 실주소 기반" 합성 포트폴리오만 요구, 주소 생성 방법론은 미지정.

**실제**: 처음에 "동+길"(예: "대잠동길", "청림동길") 식으로 실존 여부를 확인하지 않고 조합한 도로명으로 40건을 생성했더니 V-World 지오코딩 성공률이 27.5%(11/40)에 그쳤다. 라이브 지오코딩으로 사전 검증한 실존 도로명(포항 남구 인덕로·냉천로, 대구 남구 대봉로, 중구 동성로, 수성구 동대구로, 동구 동촌로, 북구 침산로)으로 교체하니 40/40 성공. 추가로 대구 남구의 "대명로"는 실존 도로이고 지오코딩 자체는 성공하지만 좌표가 신천 SHP 커버리지 bbox 밖에 위치해(대명로가 신천에서 먼 서쪽 구간까지 뻗어있음) `region_code`가 매칭되지 않는 사례를 발견 — "대봉로"(신천에 실제로 인접)로 교체해 해결. 또한 `eal_before`(합성 스냅샷)를 실제 모델과 무관한 순수 난수로 생성했더니 재계산 시 EAL이 -80%대로 급변해 비현실적이었음 — 실제 계산된 EAL 근방(±35%)으로 스냅샷을 잡도록 수정해 자연스러운 재심사 알림(±20~50%대)이 나오도록 조정.

**영향**: 향후 포트폴리오 규모를 확대(300~500건, HANDOVER §③)할 때도 임의 도로명 조합이 아니라 반드시 라이브 지오코딩+홍수 에이전트로 사전 검증한 실존 주소만 사용해야 한다. `data/climate-collateral-underwriting-ai/curated/portfolio/synthetic_portfolio.json`이 현재 40건(6개 커버리지 지역×6건+커버리지 밖 대조군 4건) 전부 지오코딩·region_code 확인 완료 상태로 저장돼 있다.

## 2026-08-11 — safemap GetMap(`IF_0092_WMS`) 500, Week4 시점 재확인해도 지속 — 최종 상태로 확정

**계획(HANDOVER.md 기준)**: §⑦ "Week4(최종 판정 반영): 이 시점까지 500이 지속되면, 데모·기획서에서 '실시간 침수흔적 오버레이' 문구를 전부 제거하고 '정적 큐레이션 실측 이력 데이터 기반'으로 정직 표기". contest_research/plans/data-security §1.8이 2026-08-05 세션까지 확인한 상태(키 A는 `openapi2/lgdInfo`로 승인·정상 작동 확정, `openapi2/IF_0092_WMS`(GetMap)는 실키·오타키·문서예시 bbox 셋 다 동일하게 HTTP 500)를 그대로 이어받아 Week1~3은 이 엔드포인트에 의존하지 않고 진행했다.

**실제**: Week4 시점(오늘, 2026-08-11)에 정확한 원본 파라미터(`serviceKey, srs, bbox, format, width, height, transparent`, contest_research §1.8 §1.8 표 그대로)로 재호출. ① 범례 API(`openapi2/lgdInfo`)는 여전히 `resultCode: "00", NORMAL_SERVICE` 정상 — 키 A는 계속 유효. ② GetMap(`openapi2/IF_0092_WMS`)은 여전히 HTTP 500, 이번엔 구조화된 JSON 에러 본문(`resultCode: "30", resultMsg: "SERVICE_KEY_IS_NOT_REGISTERED_ERROR"`)을 반환 — 2026-08-05 세션까지는 몰랐던 새 정보. 그런데 **유효한 키 A와 고의로 틀리게 만든 키(`WRONGKEY123`)를 각각 넣어도 완전히 동일한 500 + 동일한 에러 메시지**가 나온다(같은 세션에서 직접 재확인) — 즉 "SERVICE_KEY_IS_NOT_REGISTERED_ERROR"라는 메시지 텍스트는 이 특정 키의 등록 상태를 가리키는 게 아니라, 이 엔드포인트가 키 값과 무관하게 항상 내보내는 고정 에러로 판단된다(§1.8의 "500이 미승인 신호가 아니라는 강한 증거" 결론과 동일한 패턴, 텍스트만 더 구체화됨).

**영향**: safemap GetMap은 최종적으로 **"지속 500 — 미해소"**로 확정한다. 계획대로 데모·기획서에서 "실시간 침수흔적 오버레이" 표현은 쓰지 않는다 — 코드 확인 결과 `policy/disclosures.py`·`policy/coverage_labels.py` 어디에도 이미 이 표현이 없어(Week1~3부터 정적 큐레이션 `flood_history_events` 기반으로만 설계됨) 이번 확정으로 인한 코드 변경은 없다. WMS 오버레이 통합(스트레치)은 구현하지 않는다. PM은 safemap 고객지원 문의(B1, 1566-0025/opendata_help@nia.or.kr) 결과가 오면 이 항목을 갱신할지 판단하면 된다 — 데모 완주 자체는 이 항목에 의존하지 않는다.

## 2026-08-12 — HANDOVER.md §⑦ PM 항목 B6(포항 외 지역 특보 리플레이 데이터셋) 해결

**계획(HANDOVER.md 기준)**: §⑦ PM 항목 B6 "대구·경북 지역 최근 5년 기상특보/침수 이력 후보 조사 — 힌남노(포항) 외 추가 리플레이 데이터셋용... 날짜 미정, 지금 조사하지 않음"으로 명시적으로 미착수 상태였고, 방법론 주의사항(2026-08-07 PM 지적)이 붙어 있었다: (1) 후보 날짜는 시스템 출력과 무관한 객관적 외부 기준으로 먼저 선정 (2) 임계치는 날짜를 보기 전에 먼저 확정 (3) 결과가 깔끔하지 않아도 정직하게 제시. Week4까지 이 항목은 착수되지 않았고, 대구 5개 SHP 지역(남구·중구·수성구·동구·북구) 포트폴리오 데이터는 있지만 그 지역에 대한 특보 트리거가 항상 `STATUS_NO_CURATED_DATA_FOR_REGION`으로 막혀 있었다(`agents/advisory_agent.py`).

**실제**: 사용자 요청(2026-08-12, "포항 외 지역 알람 예시 보여달라")으로 착수. 방법론 그대로 따름 — "대구 신천 범람 침수", "대구광역시 호우특보 기록적 폭우 최근 5년 수해" 등 일반 키워드로 먼저 검색해(우리 시스템이 뭘 반환하는지 보지 않고) 후보를 추렸다. 검색 결과 가장 뚜렷하게 두드러진 사건은 2026-07-17~18 대구 수성구 지산동 집중호우: 시간당 89mm, 지산1동 일강수량 183.5mm, 전국 최초 "재난성 호우 긴급재난문자" 발송(22:10), 신천동로 10시간 전면통제(20:20~익일 06:30), 산사태주의보(20:27), 침수신고 100건 초과, 인명피해 없음. 여러 독립 언론사(영남일보·이엔뉴스·서울신문·다음뉴스) 보도가 서로 시각·수치를 교차 확인해준다. 진앙인 수성구(region_code=27260)는 5개 대구 SHP 커버리지 중 하나이자 포트폴리오에 이미 6건이 등록돼 있어 별도 데이터 추가 없이 바로 시연 가능했다.

**영향**: `data/climate-collateral-underwriting-ai/curated/daegu_suseong_2026/events.json`(7개 이벤트, 전부 source_url 有) 신규 작성, `config.py`에 `DAEGU_SUSEONG_2026_TIMELINE_PATH` 추가, `tests/test_advisory_agent.py::test_replay_mode_against_real_daegu_suseong_data`로 회귀 고정. 힌남노와 달리 이 사건은 인명피해가 없어 `event_type="인명피해"` 이벤트를 억지로 만들지 않았다(방법론 (3) "깔끔하지 않아도 정직하게" 준수) — 대신 "현장상황"으로 피해신고 건수만 정직하게 기록. 침수 신고 건수는 기사마다 71건/100건 초과로 다르게 보도돼(`disclaimer` 필드에 명시) 그중 한 기사(영남일보)의 수치만 그대로 인용했다. PM은 HANDOVER.md §⑦ B6 항목을 "완료"로 갱신할지, 그리고 시간 여유가 있다면 §④ 4.1.1 정기 배치처럼 이 두 번째 리플레이 지역을 데모 스크립트 기본 시나리오에 포함할지 판단 필요.

## 2026-08-18 — 담보 포트폴리오를 8종 담보유형×40건(목표) 구조로 확대 — 실주소 부족으로 5종 미달, 스키마도 변경

**계획(HANDOVER.md 기준)**: §② 항목7 "여신 포트폴리오 — 합성 데이터 300~500건", data-security_...md §4는 담보유형을 "아파트45%/단독·다가구20%/상가20%/공장·창고15%"(4개 버킷) 비율로 구상했고, 실제 구현은 그중 30~50건 소표본(§③)만 만든 상태였다(아파트16·단독주택12·근린생활시설6·공장6, 총 40건). `eal_before`는 스키마상 `float`(non-null)로, 커버리지 밖 대조군 4건조차 실제로는 산출 불가능한 임의 숫자가 채워져 있었다.

**실제**: 사용자 요청으로 담보유형을 건물취약도 에이전트가 실제로 차등 계산하는 8개 주용도 전부(`building/vulnerability.py`의 `_USE_SCORES`: 단독주택·다가구주택·공동주택·아파트·근린생활시설·업무시설·창고·공장)로 확장하고 유형당 40건을 목표로 잡았다. "실주소만 사용, 무작위 생성 금지" 원칙을 지키기 위해 두 가지 실주소 발굴 경로를 새로 만들었다: ① V-World 지명(POI) 검색(`search_place`)으로 대구·포항 내 실존 법인·시설명 발굴(`scripts/discover_collateral_addresses.py`) — 아파트·근린생활시설·업무시설·창고·공장에는 잘 통했다. ② 단독주택·다가구주택·공동주택은 이름 붙은 POI가 거의 없어(discover 결과 6~7건뿐) 별도로 대구·포항 11개 실제 주거밀집 법정동에 좌표 격자(5×5, ~200m 간격)를 놓고 V-World 역지오코딩+건축HUB `getBrTitleInfo`를 라이브로 조회해 실제로 존재하는 지번만 채택하는 방식(`scripts/grid_scan_residential.py`)을 새로 만들었다 — 좌표 자체는 격자로 생성하지만 결과로 채택하는 것은 그 좌표에 실제로 등록된 건물의 실제 주용도뿐이라 원칙 위반이 아니라고 판단했다. 사용자가 주소 범위를 "대구·포항으로만" 명시적으로 제한해 인접 경북 시군(경주 등)의 POI 결과는 전부 제외했다. `scripts/generate_portfolio.py`가 후보를 유형별로 취합해 기존 COL-001~040은 그대로 두고 COL-041부터 이어 붙였고, 신규 레코드마다 홍수·건물취약도·시나리오 에이전트를 실제로 1회씩 라이브 실행해 `score_before`/`eal_before`를 산출했다(임의 숫자 아님).

이 과정에서 커버리지 밖(6개 SHP 지역 밖) 담보가 실제로 상당수 나온다는 게 확인됐다 — 특히 창고·공장·업무시설은 냉천·신천 유역보다 성서산업단지 등 우리 커버리지 밖 지역에 실제로 더 많이 몰려있었다. 기존 `eal_before: float`(non-null) 스키마로는 이 경우를 표현할 수 없어(원래도 커버리지 밖 대조군 4건에 산출 불가능한 임의 숫자가 들어있던 것 자체가 CLAUDE.md 원칙1 위반이었다) `PortfolioRecord.score_before`/`eal_before`를 `float | None`으로 변경하고 `portfolio/alerts.py`의 `_eal_change_pct`가 `None`을 정직하게 통과시키도록 고쳤다(이미 `build_alert_queue`가 `change_pct is None`이면 알림 대상에서 제외하고 있어 하위 로직 변경은 불필요).

최종 결과(210건, 목표 320건): 아파트 40/단독주택 40/근린생활시설 40 — 목표 달성. 공장 29·창고 23·업무시설 22·공동주택 10·다가구주택 6 — 대구·포항 범위 안에서 V-World POI+건축HUB로 검증 가능한 실주소가 이 이상 나오지 않아 정직하게 미달로 남겼다(무작위 생성으로 채우지 않음). `pytest tests/ -q` 148개 전부 통과(1018초 — 라이브 API 호출 포함이라 평소보다 느림).

**영향**: PM은 (1) 대구·포항 범위를 유지한 채 210건으로 확정할지, 다른 발굴 경로(예: 도로명주소 API 별도 키 발급 후 도로 단위 전수조사)로 미달 5종을 더 채울지, 아니면 그 5종 목표치를 40에서 낮출지 결정 필요. (2) `contest_research/plans/data-security_...md` §4의 "4개 버킷 비율" 스펙은 이번에 8개 버킷으로 대체됐으므로 계획 문서 갱신 여부 판단 필요. (3) 신규 스크립트 3개(`discover_collateral_addresses.py`/`grid_scan_residential.py`/`generate_portfolio.py`)와 중간 산출물(`data/.../portfolio/_address_candidates.json`·`_grid_scan_candidates.json`·`_generation_report.json`)은 재현·감사용으로 보존했다 — `data/`가 `.gitignore` 대상이라 git 이력에는 안 남는다.

**추가(같은 날, 2026-08-18 오후) — 도로명주소 검색API 도입으로 미달분 보강**: 사용자가 `business.juso.go.kr`에서 도로명주소 검색API(`jstRoadNmAddrApiSearch`) 개발 승인키를 직접 발급받아 제공(`JUSO_API_KEY`, `.env`·`config.py`에 추가) — 본인인증 없이 즉시 발급되는 키라 유효기간이 제한적임에 유의. V-World POI 검색·격자 스캔은 "이름 붙은 시설"·"단독주택류"에는 강했지만 공동주택(연립·다세대)·다가구주택·업무시설·창고·공장은 여전히 부족했는데, 도로명주소 검색API는 국가 표준 주소 DB 전체를 키워드로 검색해줘 훨씬 큰 후보 풀을 준다("대구 빌라" 한 키워드로만 2,670건 매칭) — 단, 키워드 매칭이 느슨해 타 지역 결과가 섞이므로 응답의 `roadAddr`가 실제로 "대구광역시"/"경상북도 포항시"로 시작하는지 재확인 필수(`scripts/discover_via_juso.py`). 이 신규 후보를 기존 `_address_candidates.json`에 병합해 재생성한 결과 8종 중 7종(아파트·단독주택·근린생활시설·공동주택·다가구주택·업무시설·공장)이 목표 40건을 달성했고, **창고만 36건**(대구·포항 범위 안에서 여러 키워드 조합으로도 더 이상 신규 실주소가 안 잡혀 정직하게 미달로 확정)으로 남았다. 최종 **316건**. 이 과정에서 `scripts/generate_portfolio.py`의 재실행 안전성 버그(이미 소진된 후보를 다음 라운드에서 다시 뽑아 담보 레코드가 중복될 뻔한 문제)를 발견해 `existing`에 이미 쓰인 주소를 후보 풀에서 제외하는 필터를 추가했다 — 이후 몇 차례의 반복 실행(discover→generate)이 안전하게 idempotent해졌다. `tests/test_portfolio_loader.py`의 총 건수 assertion을 316으로 갱신, `pytest tests/ -q` 전체 재실행 통과 확인.

**혼동 방지 메모(사용자 질문에서 확인된 오해)**: `JUSO_API_KEY`(도로명주소 검색API)는 **포트폴리오 배치 생성 스크립트 3개(`discover_via_juso.py` 등)에만 쓰인다** — 라이브 단건 조회 화면(`webapp/app.py`)이나 시연 스크립트에는 연결돼 있지 않다. 시연 중 임의의 실주소를 입력하는 것은 이 키와 무관하게 **처음부터 V-World 지오코더**(`geocoding/vworld.py`)로 가능했다(대한민국 실주소 전체가 대상, SHP 6개 커버리지 밖이면 `OUT_OF_SCOPE`를 정직하게 반환할 뿐 — 이건 버그가 아니라 커버리지 게이트 설계). 즉 JUSO API를 새로 붙였다고 해서 시연에서 "아무 주소나 입력 가능"해진 게 아니다 — 그 능력은 원래부터 있었다. JUSO API를 라이브 주소 입력창의 자동완성용으로 실제 연결하는 것은 아직 별도로 하지 않은 로드맵 항목이다.

## 2026-08-18 — 보험가입여부(`insurance_covered`) 필드 추가 — HANDOVER §③ 약속과 실제 구현 사이의 공백 발견·해소

**계획(HANDOVER.md 기준)**: §③ 최소 데모 시나리오 2번 "클라이맥스 — 힌남노 리플레이"가 "고위험 담보 상위 10건 · 재심사 트리거 · **보험 커버리지 미확인 3건**" 알림을 명시적으로 약속한다. §④ 4.1의 알림 큐 스키마(`{collateral_id, score_before, score_after, EAL_before, EAL_after, EAL_change_pct, threshold, geocode_confidence}`)에는 보험 관련 필드가 원래 없다.

**실제**: 코드 확인 결과 `policy/esg_recommendations.py`가 알림 큐에 오른 담보 전원에게 무조건 "보험 가입 여부 확인 권장" 액션을 붙이고 있었을 뿐, 실제 가입 여부 데이터 자체가 없어 "미확인 N건"이라는 구체적 숫자를 셀 방법이 처음부터 없었다 — §③ 문구가 실현 불가능한 상태였다. `PortfolioRecord`에 `insurance_covered: bool | None`(합성 데이터, 가입 확률 70% 잠정치)을 추가하고, `AlertQueueEntry`·`recommend_actions_for_alert()`가 이 값을 읽어 이미 가입 확인된 담보에는 보험 확인 액션을 빼도록 바꿨다. `count_insurance_unconfirmed()`로 §③ 문구의 N을 실제로 계산해 `graph/week4_demo.py` 결과(`insurance_unconfirmed_count`)와 웹 데모(`PortfolioCard.tsx`)에 노출.

**영향**: 기존 316건에는 `scripts/backfill_insurance_coverage.py`(시드 고정 재현 가능)로 소급 적용(가입 228건=72.2%). `generate_portfolio.py`도 향후 신규 레코드에 동일 로직을 적용하도록 갱신. `AlertQueueEntry`에 항목이 하나 늘어 `test_portfolio_alerts.py::test_alert_entry_has_no_ltv_or_rate_fields`의 필드 화이트리스트를 갱신했다(금지어 검사는 그대로 통과 — "insurance_covered"는 ltv/rate/recall/interest 어느 것도 포함하지 않음). `pytest tests/ -q` 151개(148+신규 3개) 전부 통과. 웹 프론트(`webapp/frontend`)도 재빌드해 `webapp/static/` 갱신함.

## 2026-08-18 — HANDOVER §⑧(층별 리스크 차등화) 계량 코어 구현 — 그래프/CLI/웹 UI 연동은 다음 단계로 이월

**계획(HANDOVER.md 기준)**: §⑧ 전체(판정 로직 pseudocode, 데이터소스 2종, 기존 파이프라인 통합점 옵션A/B)가 연구 저장소에서 2026-08-17/18 반영됐으나 이 저장소엔 미착수 상태였다.

**실제**: §⑧이 "실호출로 검증 완료"라 주장한 두 가지를 이 저장소에서도 직접 재검증했다 — ① `getBrFlrOulnInfo`를 포항 남구 인덕로 27(지상만 있는 건물)과 대구의 지하층 보유 건물 두 곳에 실호출해 `flrGbCd`: "10"=지하/"20"=지상, `mainAtchGbCd`: "0"=주건축물 매핑을 직접 확인(추정치 아님). ② `address_resolver.py`의 `platGbCd="1"`(산) 텍스트 파싱이 애초에 맞았음을 재확인(로직 변경 없음, 주석의 "미검증" 문구만 갱신).

구현한 것:
- `gis/query.py`: `FloodRiskResult.seg_code` 노출(`loader.py`가 이미 읽고 있던 걸 스키마에만 안 태우고 있었음). 인덕동 확정지점 실측값 `N331`(0.5~1.0m) 확인.
- `building/brhub.py`: `fetch_br_floor_info()` 신규 — `mainAtchGbCd=="0"`(주건축물)만 필터링(§⑧이 경고한 "부속건축물 층정보 오사용 버그" 원천 차단).
- `scenario/floor_exposure.py`(신규 모듈): `determine_floor_flood_exposure()` — §⑧ pseudocode 그대로(로직 변경 없이 그대로 옮김). `apply_floor_adjustment()` — 옵션A(권고안) 구현: 층별 리스크 등급을 건물 전체 취약도 점수와 같은 축(0~100)으로 변환해 50:50 가중평균(근거문헌 없는 잠정 가중치, w1~w4와 동일 성격).
- `agents/building_agent.py`: `target_floor`·`flood` 선택 파라미터 추가, `BuildingAgentOutput.floor_exposure` 필드 추가 — 둘 다 미입력 시 기존 동작과 100% 동일(회귀 테스트로 고정).
- `agents/scenario_agent.py`: `apply_floor_adjustment()`를 EAL 계산 직전에 삽입 — `floor_exposure`가 없으면 기존 EAL과 정확히 동일한 값이 나옴을 테스트로 확인.

**이번 패스에서 의도적으로 안 한 것(다음 단계 후보)**: `graph/pipeline.py`(LangGraph)의 `building_node`는 현재 `flood_node`와 완전 병렬(fan-out)인데, `floor_exposure` 계산은 flood 결과가 있어야 해서 이 기능을 실제로 쓰려면 두 노드를 순차 실행하거나 그래프를 조건부로 바꿔야 한다 — 이번엔 계량 코어(`building_agent`를 직접 `flood=`·`target_floor=` 인자로 호출하는 경로)만 완성했고, `graph/pipeline.py`·`week3_demo.py`·CLI 스크립트·웹 데모 UI에 실제 층수 입력 폼을 연결하는 작업은 하지 않았다 — 급하게 얹으면 지금 통과 중인 그래프 fan-out 구조·테스트를 깨뜨릴 위험이 있어 별도 작업으로 분리하는 게 안전하다고 판단.

**영향**: PM은 이 계량 코어를 실제 사용자 입력 경로(웹 폼 "층수 입력" 필드 등)까지 연결할지, 아니면 §⑧을 "계량 코어는 준비됨, UI 연동은 로드맵"으로 발표 자료에 반영할지 판단 필요. 신규 테스트(`test_floor_exposure.py`·`test_scenario_agent.py` + `test_building_agent_resolution.py` 추가분) 포함 `pytest tests/ -q` 전체 재확인 필요(실행 중).

## 2026-08-18 — §⑧ 그래프/CLI/웹 UI 연동 완료 — `graph/pipeline.py` fan-out을 순차 실행으로 변경

**계획(HANDOVER.md 기준)**: §4.1 아키텍처 다이어그램은 홍수·특보·건물취약도 3에이전트 "병렬 fan-out"을 명시한다(`graph/pipeline.py`는 그중 홍수·건물 2개를 병렬로 구현해둔 상태였음). 같은 날 앞선 항목("계량 코어 구현")은 이 병렬 구조 때문에 floor_exposure 연동을 "두 노드를 순차 실행하거나 그래프를 조건부로 바꿔야 한다"며 다음 단계로 이월해뒀다.

**실제**: 두 옵션(순차화 vs LangGraph 조건부 라우팅) 중 순차화를 채택해 `graph/pipeline.py`의 `flood→building→scenario` 순차 엣지로 변경했다(기존 `START→flood`·`START→building` 병렬 fan-out 제거). 조건부 라우팅(`target_floor` 유무에 따라 병렬/순차 분기)도 검토했으나, DEV_LOG 2026-08-09 항목이 이미 확인한 대로 `query_flood_risk()`가 프로세스당 1회(콜드 74초) 이후로는 `lru_cache`로 0.0004초 수준이라 순차화의 상시 비용이 무시할 수준이라 판단해 더 단순한 쪽을 택했다. 이제 `target_floor` 미입력(기존 경로)이어도 flood 결과가 항상 building_agent로 전달되지만, `_compute_floor_exposure()`가 `target_floor is None`이면 즉시 `None`을 반환하므로(수정 없음, 기존 로직 그대로) 기존 결과값은 100% 동일하다 — 회귀 테스트(`test_pipeline_smoke.py`)로 확인.

나머지 연동:
- `graph/run.py`·`graph/week3_demo.py`·`graph/week4_demo.py`: `target_floor: dict | None = None` 파라미터 추가, `run_building_agent(flood=..., target_floor=...)`로 관통.
- `scripts/_demo_cli.py`(Week3/4 CLI 공통)·`scripts/run_assessment.py`(Week2 CLI): `--floor-type {지상,지하}`·`--floor-no` 플래그 추가.
- `webapp/app.py`: `/api/assess`에 `floor_type`/`floor_no` 쿼리 파라미터 추가 → `target_floor` dict로 조립해 `run_week4_demo`에 전달.
- `webapp/frontend`: `AssessForm`에 층 유형·층수 입력 추가(미입력 시 기존 동작), `BuildingCard`에 층별 리스크 등급(고위험/중위험/저위험) 표시 섹션 추가. `tsc --noEmit`·`npm run build` 통과, `webapp/static/` 재생성 완료.
- `memo/source_registry.py`: `building.floor_exposure`가 있으면 기존 `building.source_id` 레코드의 `value_repr`에 `floor_risk_tier`/`basis`/`reason`을 병기(새 source_id를 만들지 않음) — 메모 에이전트가 같은 인용 규율로 층별 리스크 문장을 생성할 수 있게 됨(HANDOVER §⑧ "메모 에이전트" 통합점 반영).

**영향**: `portfolio/recalc.py`(포트폴리오 배치 재계산)는 의도적으로 그대로 뒀다 — 합성 포트폴리오 레코드에 층수 데이터가 없어 `target_floor`를 넘길 입력 자체가 없고, 미입력이므로 기존 배치 결과에 영향 없음(층수 필드를 포트폴리오 스키마에 추가하는 것은 별도 로드맵). 신규/수정 테스트 8개(`test_pipeline_smoke.py` 2개 신규+1개 이름변경, `test_week3_demo_smoke.py` 1개 신규, `test_memo_source_registry.py` 1개 신규) 포함 `pytest tests/ -q` 170개 전체 통과(800초). 커밋 완료(`bc05504`).

## 2026-08-18 — 웹 데모 사용 중 발견한 설계 공백 2건 — "지역 프리셋" UX 설계 논의 정리

로컬 서버(uvicorn)로 실제 데모 화면을 써보던 중 사용자가 두 가지를 지적했다. HANDOVER.md에 명시된 계획은 아니고 웹 데모(§⑤ 기능5 "포트폴리오 익스포저 지도 대시보드")를 실제로 만지면서 나온 UX 설계 이슈라 여기 정리한다.

**1) 오래된 프로세스로 인한 일시적 장애(참고용, 코드 버그 아님)**: 서버가 `insurance_covered` 필드 추가(오전 커밋 9bd3901) 이전부터 떠 있던 프로세스(2026-08-12 시작)였고, uvicorn을 `--reload` 없이 띄워서 코드가 바뀌어도 재시작 전까진 반영이 안 됐다 — 그래서 최신 데이터(JSON엔 필드 있음)를 옛날 클래스 정의(필드 모름)에 넣으려다 `TypeError`가 났다. 프로세스 재시작으로 해결, 코드 문제 아님. 데모 진행자가 로컬 서버를 코드 변경 후 재시작 안 하면 재발할 수 있다는 점만 기록.

**2) "지역 프리셋" 드롭다운이 3개뿐인 이유와 구조적 불일치 — 실제 설계 문제**:
- **왜 3개뿐인가**: 포트폴리오·SHP 커버리지는 6개 구(포항 남구·대구 남구·중구·수성구·동구·북구) 전부 있지만, "특보 리플레이" 프리셋은 **사람이 뉴스를 찾아 손으로 정리한 큐레이션 타임라인(source_url 필수)이 있는 지역만** 만들 수 있다 — 지금 존재하는 건 힌남노(포항 남구)·대구 수성구 2026 집중호우 2건뿐(DEV_LOG 2026-08-12 항목). 나머지 4개 구는 단건 주소 조회는 이미 되지만(SHP 데이터 있음) "재생할 과거 사건 기록"이 없어 리플레이 프리셋이 없다. 라이브 모드는 기상청 API로 "지금 이 순간"만 조회하고 결과를 저장하지 않으므로, 과거를 재구성할 방법 자체가 원래 없었다(`advisory/live.py` — 기상청 API가 6일 초과 과거 조회를 애초에 거부함, 2026-08-12 실측 확인).
- **불일치 버그**: 담보 평가(침수·건물·EAL) 결과는 주소창 텍스트를 그대로 지오코딩해 계산하므로 프리셋과 무관하게 동작하지만, 포트폴리오 재심사 알림 섹션은 프리셋의 `region_code`만 보고 주소창 내용을 전혀 참조하지 않는다 — 프리셋을 "포항 힌남노"로 둔 채 대구 주소를 입력하면 위 결과는 대구 기준, 아래 포트폴리오 알림은 포항 기준으로 나오는 모순이 생긴다.
- **사용자 제안(채택)**: 라이브 모드 조회 결과를 매번 로그로 적재해두면(현재는 안 함) 나중에 "날짜+지역"으로 과거 특보를 재구성할 수 있어, 손으로 큐레이션한 2건짜리 하드코딩 프리셋 목록 대신 "날짜 선택 → 그 시점 실제 발효 특보 자동 매칭" 방식으로 갈 수 있다는 아이디어 — 정확한 방향이라 채택. 다만 지금 당장은 로그가 비어있어(시스템이 실제로 운영된 적이 없어) 3번(날짜 기반 UI)은 로그가 쌓인 뒤에나 의미가 있다.

**합의된 착수 순서**(이번 세션에서 순차 구현):
1. 라이브 특보 조회 결과를 append-only 로그로 적재(`advisory/live_log.py` 신규) — 미래의 날짜 기반 재생을 위한 축적 시작
2. 주소 입력을 프리셋에서 완전히 디커플링 — 입력된 주소를 지오코딩→region_code 자동 감지해 담보 평가·포트폴리오 알림이 항상 같은 지역 기준으로 일관되게 동작하도록 수정 + 도로명주소 자동완성(JUSO API, `discover_via_juso.py`가 이미 검증해둔 키·엔드포인트 재사용) 붙이기
3. (2에서 새로 생긴 region 자동감지 기반) "날짜 선택 → 특보 자동 매칭" 리플레이 화면으로 하드코딩 프리셋 대체 — 로그가 어느 정도 쌓인 뒤 착수(지금 시작하면 빈 로그로 시작)
4. (로드맵) 6개 구 외 지역으로 SHP·포트폴리오 확장 여부는 별도 판단

## 2026-08-18(계속) — 위 1·2번 구현 완료

**1) 라이브 특보 로그 적재**: `advisory/live_log.py` 신규(`append_live_query_log`/`read_live_advisory_log`, append-only JSONL). `agents/advisory_agent.py::run_advisory_agent()`가 `mode="live"`일 때 세 분기(OK·UNKNOWN_REGION·UPSTREAM_ERROR) 전부에서 조회 시각·region_code·원본 이벤트(`AdvisoryEvent` 전체 필드)를 로그에 남기도록 수정 — 실패했다는 사실 자체도 정직하게 기록한다(설계원칙1과 같은 정신). `config.ADVISORY_LIVE_LOG_PATH`(`data/.../audit/advisory_live_log.jsonl`) 신규. `run_advisory_agent(..., live_log_path=...)` 파라미터로 오버라이드 가능(`portfolio_agent.alert_log_path`와 동일 관례) — 기존 `test_advisory_agent.py`의 라이브 모드 테스트 3개는 `tmp_path`로 실제 감사 로그를 오염시키지 않도록 갱신, 로그 적재 자체를 검증하는 신규 테스트 2개 추가.

**2) 주소-프리셋 디커플링 + region 자동감지 + JUSO 자동완성**: 웹 데모에서 "포항 힌남노 프리셋을 선택한 채 대구 주소를 입력하면 담보 평가는 대구 기준, 포트폴리오 알림은 포항 기준으로 나오는" 불일치 버그를 근본 수정.
- `geocoding/juso.py` 신규 — `scripts/discover_via_juso.py`가 검증해둔 JUSO API(엔드포인트·커버리지 필터)를 라이브 사용자 입력 자동완성에 실제로 연결(그날 오후 DEV_LOG가 "아직 안 한 로드맵"으로 남겨둔 항목).
- `webapp/app.py`에 `/api/resolve-region`(주소→지오코딩→홍수 에이전트로 region_code·coverage·큐레이션 리플레이 존재 여부 감지) · `/api/address-search`(JUSO 프록시, 실패 시 빈 배열로 조용히 degrade) 신규 엔드포인트 추가. `_CURATED_REPLAY_BY_REGION`은 기존 `_REGION_PRESETS`에서 파생(새 진실의 원천을 만들지 않음).
- 프론트: `AddressField.tsx` 신규(자동완성 드롭다운 + 디바운스 지역 감지, `value` prop 변화 단일 경로로 트리거 — 직접 타이핑이든 자동완성 선택이든 "예시 주소로 채우기" 드롭다운이든 전부 같은 경로를 타서 감지 누락을 원천 차단). `AssessForm.tsx`에 감지된 지역 뱃지 + (큐레이션 리플레이가 있을 때만) "리플레이로 재생" 체크박스 표시. `App.tsx`는 이제 `region_code`/`mode`/`timeline_path`를 프리셋이 아니라 `detectedRegion`(AddressField가 알려준 감지 결과)에서만 유도한다 — 기존 "지역 프리셋" 드롭다운은 라벨을 "예시 주소로 채우기"로 바꾸고 주소창을 채우는 용도로만 남김.
- 신규 테스트: `test_geocoding_juso.py`(5개), `test_advisory_live_log.py`(3개), `test_advisory_agent.py` 추가분(2개), `test_webapp_endpoints.py`(8개, FastAPI TestClient로 두 신규 엔드포인트 검증) — `webapp/`이 패키지가 아니라 `sys.path` 삽입으로 임포트해야 해서 그 패턴을 테스트 파일에 그대로 재현.

**검증**: `pytest tests/ -q` 188개 전체 통과(2692초 — 이번 회차는 라이브 JUSO API 실호출 확인(수동 curl)까지 곁들여서 평소보다 오래 걸림, 스위트 자체는 전부 monkeypatch로 격리돼 있어 시간 증가는 스위트 문제가 아님). 프론트 `tsc --noEmit`·`npm run build` 통과, `webapp/static/` 재생성. 로컬 서버로 힌남노(포항 남구, region_code=47111, curated_replay 있음)와 대구 북구(27230, SHP·라이브는 있으나 curated_replay 없음) 두 케이스 다 실제 호출로 동작 확인.

**영향**: `_REGION_PRESETS`의 `daegu-suseong-live` 항목(수성구 라이브 전용 프리셋)은 이제 사실상 중복이다 — 수성구 주소를 입력하면 자동감지로 리플레이/라이브 토글이 뜨므로 별도 프리셋 없이도 라이브를 고를 수 있다. 지우진 않았다(예시 주소 채우기 용도로는 여전히 유효, 정리는 PM 판단). Step 3(날짜 기반 리플레이 UI)은 착수 안 함 — 로그가 실사용으로 쌓인 뒤 진행.

## 2026-08-19 — 기상청 API허브(apihub.kma.go.kr) 조사·통합 — 3단계(날짜 기반 과거 조회)의 핵심 데이터 소스 확보

**계획(HANDOVER.md 기준)**: 명시적 계획 없음 — 위 §④의 "Step 3(날짜 기반 리플레이)은 로그가 쌓인 뒤 진행"이라는 결론에 대해, 사용자가 "우리 로그를 쌓기 전에 기상청 자체에 과거 특보 아카이브가 이미 있지 않은지 먼저 조사해보자"고 제안 — 리서치 결과 실제로 있었다.

**실제(사용자와 실시간으로 계정 가입·활용신청을 거치며 확인)**:
1. `data.go.kr`의 `WthrWrnInfoService`(`advisory/live.py`가 씀)와 `apihub.kma.go.kr`(기상청 자체 포털, 국가기후데이터센터 운영)은 **완전히 별개의 인증 체계**다. `.env`의 `KMA_API_HUB_KEY`는 이미 있었지만(연구 단계부터 존재) 실사용된 적이 없었다.
2. **API마다 개별 "활용신청" 승인이 필요하다** — 계정 키가 있어도 안 된다는 걸 실측으로 확인(403 `"활용신청이 필요한 API 입니다"`). 최초엔 "계정 자체가 막혔다"고 오판했으나(같은 계정으로 이미 승인된 "기상정보 API"는 되고 "특보자료 API"는 안 되는 것으로 API별 개별승인임을 재확인), 사용자가 직접 "특보자료 API"(`wrn_met_data.php`)와 "특보구역 API"(`wrn_reg.php`)에 활용신청 → 즉시 승인.
3. **"기상정보 API"(`wrn_inf_rpt.php`)는 우리가 원하는 게 아니었다** — 자유서술형 예보관 브리핑 텍스트(파싱 부적합). 진짜 필요한 건 "특보자료 API"(`wrn_met_data.php`, `TM_FC`/`TM_EF`/`REG_ID`/`WRN`/`LVL`/`CMD` 정형 필드)였다 — 이건 API 목록 화면에서 사용자가 실제로 캡처해 붙여준 화면 내용으로 정정됨(제가 원격으로 문서 페이지를 읽었을 때는 계속 다른 API끼리 필드를 혼동했음 — 이번 조사 전체에서 사용자가 직접 화면을 보고 붙여준 내용이 제 원격 문서 읽기보다 일관되게 더 정확했다).
4. **2004-06-30 ~ 현재까지 정형 이력 조회 가능**, 실제로 힌남노(2022-09-06, 포항)와 대구 수성구(2026-07-17/18) 두 실이벤트 전부 실호출로 재현·교차검증 완료(기존 큐레이션 데이터와 시각·전개가 정합적).
5. **대구 5개구는 이 API로도 개별 구분 불가** — 기존에 알려진 제약(`REGION_CODE_TO_KMA_STN_ID`)이 재확인됨. 다만 **특보구역 코드가 2026-05-31 13:30에 개편**돼(달성군·군위군 분리, 대구 도심 구역은 `L1070100`→`L1140100`, 이름도 "대구광역시"→"대구중부"로 변경) REG_ID를 하드코딩하면 개편 이후 날짜에서 틀린 값을 낸다는 걸 확인 — `resolve_region_zone()`이 이름 접두어+상위구역+유효기간으로 동적 매칭하도록 구현.
6. **IP 화이트리스트 이슈(별개 포털, `safetydata.go.kr` 재난문자 API 가입 중 발견)**: 사용자가 평소 쓰는 공용 와이파이가 아니라 특정 IP 1개만 등록 가능해, 사용자가 폰 핫스팟으로 전환해 그 IP를 등록함 — Claude Code의 Bash 도구와 PowerShell 도구가 서로 다른 네트워크 경로로 나가는(다른 공인 IP로 보이는) 것도 이 과정에서 확인됨(Bash: 고정 샌드박스 경로, PowerShell: 실제 호스트 경로). 사용자가 "평소엔 공용 와이파이를 쓰니, 이 API 호출 전엔 핫스팟으로 바꾸라고 알려주는 기능이 필요하다"고 요청 — 3단계에서 IP 제한 오류를 명확한 안내 메시지로 번역하는 처리를 넣기로 함(아직 미구현, 재난문자 API 승인 대기 중이라 통합 보류).

**구현한 것**: `src/climate_risk/advisory/kma_historical.py`(신규) — `query_historical_warnings(region_code, start, end, as_of=None)`이 특보구역 조회→(날짜 인식) 매핑→특보이력 조회 순으로 오케스트레이션. `WRN_CODE_LABELS`/`LVL_CODE_LABELS`/`CMD_CODE_LABELS` 코드 사전, `resolve_region_zone()`(이름 접두어+상위구역+유효기간 매칭, 개편 전후 대응), 활용신청 미승인(HTTP 403)·네트워크 오류·구역 매칭 실패 3종을 각각 명시적 상태로 반환(조용히 빈 값 처리 안 함, 설계원칙1과 같은 정신). `config.py`에 `KMA_WRN_MET_DATA_URL`/`KMA_WRN_REG_URL` 추가. 테스트(`tests/test_kma_historical.py`, 13개, 실측 캡처 데이터를 fixture로 사용) 전부 통과 + 실제 API로 힌남노 데이터 재조회까지 최종 검증 완료(9/5 21:00 태풍주의보 발표→9/6 00:00 경보 격상→12:00 주의보 하향→13:00 폭풍해일주의보 변경/태풍주의보 해제→18:00 폭풍해일 해제 — 기존 큐레이션 서사와 정합).

**영향**: 재난문자 API(`safetydata.go.kr`, 구 단위 세분화 가능성 있어 보완 소스로 조사 중)는 활용신청 승인 대기 중이라 이번 범위에 포함 안 함 — 승인되면 같은 패턴(별도 모듈, `query_historical_warnings`와 나란히)으로 추가 예정. `advisory_agent.py`/webapp/프론트엔드에 이 모듈을 실제로 연결하는 작업(3단계 UI, "날짜 선택→과거 특보 자동 매칭")은 아직 안 함 — 계량 코어(이 모듈)만 완성된 상태, HANDOVER §⑧ 때와 같은 패턴("계량 코어 먼저, UI 연동은 다음 단계"). `pytest tests/ -q` 전체 재확인 필요(부분 실행만 완료).

## 2026-08-19(계속) — `pytest tests/ -q` 전체 재확인 완료(201개 전부 통과) + 위 3단계(날짜 기반 특보 조회) UI 연동 완료

**세션 시작 시 재난문자 API 승인 여부 확인**: 위 항목이 "승인되면 통합 여부를 사용자에게 확인" 조건을 남겨뒀던 것에 따라 세션 시작 시 먼저 확인 — 사용자 답변 "아직 대기 중". 따라서 이번 작업 범위에서 재난문자 API 통합은 계속 제외.

**실제**: `mode="historical"`을 `advisory_agent.py`에 `replay`/`live`와 나란한 세 번째 분기로 추가 — `query_historical_warnings(region_code, historical_start, historical_end)`를 호출해 `HistoricalWarningEvent`를 기존 `AdvisoryEvent`로 변환(`_historical_event_to_advisory_event`)한다. 이렇게 하면 인용 레지스트리(`memo/source_registry.py::_advisory_records`)가 `advisory.timeline`을 순회하는 기존 로직을 전혀 손대지 않고도 과거 특보 이력이 심사메모에 그대로 인용 가능해진다(새 진실의 원천을 안 만드는 SS8 때와 같은 패턴). `kma_historical.py`의 3가지 실패 상태(`ACTIVATION_REQUIRED`/`NO_ZONE_MATCH`/`UPSTREAM_ERROR`)는 조용히 빈 값으로 뭉개지 않고 `STATUS_HISTORICAL_*` 3종으로 각각 번역해 반환한다(설계원칙1과 같은 정신).

**날짜 구간 설계 — "그 날짜 하나"가 아니라 [start, end] 구간을 그대로 받는다**: 기상청 API허브 특보자료 API 자체가 구간 조회만 지원해서(`kma_historical.query_historical_warnings`), "사용자가 날짜 하나를 고르면 앞뒤로 며칠씩 버퍼를 얹어 조회한다" 같은 임의 휴리스틱을 만들지 않고 호출부(CLI `--historical-start`/`--historical-end`, 웹 UI 시작일·종료일 date input 2개)가 구간을 명시하도록 설계했다 — 이 프로젝트가 지금까지 반복해서 지켜온 "검증 안 된 규칙을 만들지 않는다" 원칙과 같은 결로 판단.

**연동 범위**: `agents/advisory_agent.py`(핵심 분기) → `graph/week3_demo.py`/`week4_demo.py`(historical_start/historical_end 관통) → `scripts/_demo_cli.py`(`--mode historical --historical-start YYYY-MM-DD --historical-end YYYY-MM-DD`) → `webapp/app.py`(`/api/assess`에 `historical_start`/`historical_end` 쿼리 파라미터, `_parse_kst_date()`로 "YYYY-MM-DD"→KST datetime 변환) → 프론트(`App.tsx`가 기존 `useReplay: boolean`을 `warningMode: 'replay'|'live'|'historical'` 3택 상태로 대체, `AssessForm.tsx`의 지역 감지 뱃지 영역에 드롭다운+조건부 날짜 2개 입력 추가). `scripts/run_assessment.py`(Week2 CLI, `graph/run.py::run_pipeline`)는 애초에 advisory 에이전트를 호출하지 않아 변경 대상 아님.

**검증**: 신규 테스트 7개(`test_advisory_agent.py` 5개 — 정상 변환·활용신청 미승인·구역 매칭 실패·업스트림 오류·start/end 미입력 시 ValueError, `test_webapp_endpoints.py` 2개 — `_parse_kst_date` 시작/종료 시각) 포함 `pytest tests/ -q` 208개 전체 통과(418초). 프론트 `tsc --noEmit`·`npm run build` 통과, `webapp/static/` 재생성(구 해시 자산 자동 정리 확인). 로컬 서버(uvicorn, 기존 프로세스 재시작)로 `/api/assess?mode=historical&historical_start=2022-09-05&historical_end=2022-09-07`(포항 남구, 힌남노)을 실제 기상청 API허브로 curl 호출 — 이벤트 7건(태풍 예비특보→주의보→경보→하향→폭풍해일주의보 변경/태풍주의보 해제→폭풍해일 해제)이 기존 큐레이션 서사와 정합적으로 반환됨을 확인, `historical_start`/`historical_end` 둘 다 미지정 시에도 서버가 죽지 않고 `{"error": "...historical_start/historical_end가 모두 필요합니다"}`로 정직하게 degrade함을 확인. **다만 브라우저로 실제 드롭다운·날짜 입력 UI 조작은 확인하지 못함**(이번 세션엔 claude-in-chrome 확장이 연결되지 않아 — 사용자가 설치를 미완료 상태로 남겨둠) — API 계약과 타입은 전부 맞물려 있음을 확인했으나 시각적 렌더링·클릭 동작은 미검증 상태로 다음 세션에 확인 권장.

**영향**: 로드맵 착수 순서(1·2·3단계, 위 §④ 참조)가 전부 완료됐다 — 남은 건 (a) 재난문자 API 승인 시 보완 소스 통합, (b) 로그(`advisory/live_log.py`)가 실사용으로 쌓인 뒤 "라이브 로그 기반 자동 리플레이"로 더 발전시킬지 PM 판단, (c) 브라우저로 새 드롭다운·날짜 입력 UI 시각 확인(claude-in-chrome 연결 후).

## 2026-08-19(계속) — 7번째 지역(경상남도 거제시) 추가 — HANDOVER §④ 6개구 스코프 밖 확장

**계획(HANDOVER.md 기준)**: 명시적 계획 없음 — HANDOVER는 포항 남구·대구 5개구(총 6개 SGG) 스코프를 전제로 확정됐고, 위 2026-08-18 항목 마지막에 "(로드맵) 6개 구 외 지역으로 SHP·포트폴리오 확장 여부는 별도 판단"으로 미결 상태로 남겨뒀다. 이번엔 사용자가 직접 "포항 말고 거제도도 추가하고 싶다"고 요청.

**실제**: 기존 6개 SHP와 동일 출처(`data.floodmap.go.kr` 홍수위험지도 정보제공포털, 지방하천 하천범람지도)에서 사용자가 거제시 SHP 6개 빈도(50/80/100/200/500년+기왕최대)를 직접 다운로드해 `data/raw/`에 추가. 등록 전 두 가지를 확인·결정했다:
1. **"하천 이름" 라벨이 냉천/신천 패턴과 다르다**: 냉천(포항 남구)·신천(대구 5개구)은 각 구를 흐르는 대표 하천 하나가 뚜렷했지만, 거제시는 지방하천이 17개소(연초천·산양천·둔덕천·고현천 등)이고 이 SHP 1개가 시 전역의 여러 하천 침수구역을 함께 담고 있다(세그먼트 bbox 실측 확인 — N333 세그먼트 하나가 21km 범위를 가로지름, 특정 하천 하나의 범위가 아님). "고현천" 등 단일 하천명으로 라벨링하면 부정확해 `river_name="거제시 관내 지방하천(다수)"`로 일반화 표기했다.
2. **6개 빈도 중 1개만 등록**: `query_flood_risk()`가 좌표당 폴리곤 1개만 선택하는 구조라(비교·선택 로직 없음) 같은 region_code에 여러 빈도를 동시 등록하면 겹치는 좌표에서 어느 빈도가 선택될지 비결정적이 된다(EAL의 발생확률 입력이 흔들림 — 금전 계산에 영향). 사용자 확인 후 신천과 동일 기준인 500년으로 등록(`AEP_BY_FREQ_LABEL`에 이미 정의된 값 그대로 재사용, 새 잠정치 추가 안 함). 나머지 5개 빈도 SHP는 `data/raw/`에 보관만 되고 미사용 — 필요 시 나중에 다른 방식(예: 지역당 다중 빈도 지원 구조로 리팩터)으로 활용 가능.

`config.py`에 `FloodShpSource(region_code="48310", region_name="거제시", ...)` 추가(SHP 7개 전량). 골든 좌표는 냉천/신천과 달리 PM 현장 실측 기록이 없어 두 경로로 확보: ① `shapely.representative_point()`로 최대 면적 세그먼트(N333) 내부가 보장된 좌표 1개(EPSG:5186→WGS84 역변환) ② V-World 지명 검색(`search_place`)으로 확보한 실제 POI 3개 — "독봉교"(2026년 고현천 홍수 "심각단계" 실제 보도 지점, 경남신문·톱스타뉴스), "고현천"(하천 POI 자체), "거제시청"(하천에서 먼 대조군). 전부 실측 `query_flood_risk()` 호출로 tier·거리 확인 후 `gis/golden_points.py`에 `GEOJE_POINTS`로 고정(`tests/test_coverage_gate.py`에 신천·냉천과 동일 패턴의 회귀 테스트 추가). `evaluation/metrics.py`의 `coverage_gate_metric()`/`coverage_uncertain_point_metric()`도 골든셋에 `GEOJE_POINTS` 포함하도록 갱신(총 8→12).

**놓칠 뻔한 지점**: `geocoding/juso.py`의 라이브 웹 주소 자동완성이 `_ALLOWED_PREFIXES = ("대구광역시", "경상북도 포항시")`로 하드코딩돼 있어, `config.py`(SHP 등록)만 고치고 이걸 놓치면 홍수 위험 조회 자체는 되는데 자동완성 드롭다운에서만 거제 주소가 안 뜨는 조용한 불일치가 생길 뻔했다 — 홍수 SHP 등록은 `SHP_FILENAME_TO_REGION_CODE`(FLOOD_SHP_SOURCES에서 자동 유도)라 config.py 추가만으로 전파되지만, 이 필터는 별도 진실의 원천이라 수동으로 맞춰야 한다는 점을 모듈 주석에 남겨둠. `_REGION_PRESETS`(webapp/app.py, "예시 주소로 채우기" 드롭다운)는 건드리지 않음 — 2026-08-18 주소-프리셋 디커플링 이후 프리셋은 예시 채우기 용도일 뿐이라 거제 항목 없이도 거제 주소를 직접 입력하면 정상 동작.

**의도적으로 안 한 것**: 특보(경보) 조회(`advisory/kma_historical.py`의 `REGION_CODE_TO_KMA_ZONE`, `advisory/live.py`의 `REGION_CODE_TO_KMA_STN_ID`)에는 거제 항목을 추가하지 않았다 — 이건 기상청 API허브에 거제 특보구역 REG_ID를 실호출로 확인해야 하는 별도 작업(냉천/신천 때와 동일한 종류의 검증 필요)이라 이번 스코프에서 제외. 현재 거제 주소는 담보 평가(침수·건물·EAL)는 되지만 특보 리플레이/라이브 조회는 `UNKNOWN_REGION`으로 나올 것 — 필요시 다음 단계로 분리.

**검증**: `pytest tests/test_coverage_gate.py tests/test_loader_idempotent.py tests/test_query_caching.py tests/test_flood_agent.py`(23개, GEOJE_POINTS 4개 포함) + `tests/test_geocoding_juso.py tests/test_evaluation_metrics.py tests/test_redteam_scenarios.py`(16개) 전부 통과. 전체 스위트(`pytest tests/ -q`) 재확인은 아직 안 함(SHP 7개 콜드 로딩이 파일당 세션 fixture 재로딩 시 매우 느려짐 — 위 두 배치만도 각각 75분·5분 소요, 라이브 API 호출 포함 전체 스위트는 훨씬 오래 걸릴 것으로 예상) — 다음 세션에서 전체 재확인 권장.

**영향**: PM은 (1) HANDOVER.md의 "포항·대구 6개구" 스코프 문구를 "포항·대구·거제 7개 지역"으로 갱신할지, (2) 특보 조회(3번째 지역 추가)를 별도 착수할지, (3) 미사용 5개 빈도 SHP(거제)를 나중에 다중 빈도 지원 구조로 활용할지 판단 필요. 포트폴리오(`synthetic_portfolio.json`)에는 거제 담보를 추가하지 않았다 — 요청받지 않은 범위.

## 2026-08-19(계속) — 제품 정체성 논의: "이 도구가 사후 대응(reactive)만 하는 것 아닌가?" — 설계엔 사전 대응 층이 있으나 데모가 그걸 안 보여줌

**계획(HANDOVER.md 기준)**: 명시적 버그 아님 — 사용자가 웹 데모(특보 리플레이 위주)를 써보고 "이 시스템이 결국 특보 터지면 사후적으로 알림만 주는 도구 아니냐, LTV·금리도 못 건드리는데 은행이 실제로 뭘 할 수 있냐, 위험지역을 사전에 미리 추려야 하는 거 아니냐"는 근본적인 제품 가치 의구심을 제기.

**실제(확인 결과)**: HANDOVER.md 설계 자체는 이미 사전/사후 2개 층으로 나뉘어 있었다:
1. **사전 — 물건 단위 라이브 조회**(§③ 시나리오1): 신규 담보 심사 시 특보 여부와 무관하게 아무 때나 즉시 조회·스코어링. 오늘 만든 "신규 담보 조회" 탭이 정확히 이 경로.
2. **사전 — 정기 배치**(§4.1.1): 월 1회 포트폴리오 전체 위험 재계산, 월/분기 1회 담보가치·LTV 종합점검, 분기/반기 1회 장기 시나리오 재평가. **사용자가 요구한 "미리 위험지역을 추리는" 기능이 정확히 이것** — 다만 HANDOVER §4.1.1이 처음부터 "이 정기 배치의 스케줄러 자체는 해커톤 데모에서 라이브로 구동하지 않는다"고 MVP 범위에서 명시적으로 잘라둔 상태라, **지금까지 이 저장소 어디에도 구현된 적이 없다**(코드·테스트 전무 확인).
3. **사후 — 특보 트리거 재계산**(§4.1, 힌남노 리플레이): 오늘까지 만든 기능 대부분이 여기 쏠려있다 — 데모의 "클라이맥스" 시나리오라 가장 공들여 만들어졌고, 그래서 처음 써보면 "이 도구=특보 대응 도구"로 보인다.
4. LTV·금리를 시스템이 자동으로 못 건드리는 건 능력 부족이 아니라 **의도된 규제 방어선**(HANDOVER §①④⑥ 블루라이닝 방지 — 무디스·S&P 등 상용 기후리스크 툴도 동일 원칙, "점수는 주되 결정은 사람"). 은행이 실제로 하는 액션은 "보험 확인·현장점검·전환금융 추천"(이미 화면에 있음) — 최종 조건 변경은 심사역이 별도 여신 시스템에서 사람이 함.

**영향**: 사용자와 두 갈래로 보완하기로 합의:
1. **정기 배치(사전 포트폴리오 전체 재점검) 실제 구현** — HANDOVER §4.1.1이 로드맵으로만 남겨뒀던 걸 실제로 만들어서 "위험지역을 미리 추린다"는 이 프로젝트의 절반(사전 대응)을 눈에 보이게 시연 가능하게 만든다. 후속 세션 착수 시 확인할 것: (a) "배치를 실제로 매월 자동 실행"까지는 필요 없고 "지금 누르면 316건 전체를 다시 스코어링해서 위험도 상위 목록을 보여주는 화면"이면 데모 목적엔 충분할 가능성 — 스케줄러(cron) 자체 구현이 필요한지는 사용자와 재확인. (b) 기존 `portfolio/recalc.py::recalc_subset()`이 "지역 필터링된 서브셋"을 재계산하는 함수라 이미 있음 — 정기 배치는 필터링 없이 전체 316건에 그대로 적용하면 재사용 가능할 것으로 보임(콜드 스타트 이후엔 SHP 캐시가 있어 성능도 무리 없을 것). (c) "위험도 상위 N건" 정렬·표시, 그리고 이게 특보 트리거 재계산과 어떻게 화면상 구분되는지 UX 설계 필요.
2. **내러티브/문구 정리** — 발표 자료·화면 문구에 "이 도구는 ①신규 심사(사전) ②정기 점검(사전) ③특보 대응(사후) 세 가지를 한다"는 걸 명확히 표현. 코드보다 문서·카피 작업.

두 작업 다 필요하다고 확인됐으나 **아직 착수 전** — 다음 세션에서 이어갈 것. 우선순위·구체 화면 설계는 착수 시 사용자와 다시 확인.

**참고**: 오늘 오후 "주소 입력 2모드 분리"(신규 담보 조회/기존 포트폴리오 조회 탭) 작업 중 plan mode로 별도 보류해둔 "EAL에 LTV 반영 여부" 논의(`C:\Users\eujin\.claude\plans\keen-gliding-lagoon.md` 참조)와는 결이 다른 논의다 — 저건 "EAL 계산식 자체를 바꿀지"였고, 이건 "이 도구의 사전/사후 기능 균형을 어떻게 시연할지"다. 둘 다 미해결로 남아있음.

## 2026-08-19(계속) — "기존 포트폴리오 조회" 탭 버그 수정 + 거제 담보 154건 신규 생성(316→470건)

**1) 포트폴리오 선택기 재선택 버그**: 사용자가 "기존 포트폴리오 조회에서 담보가액이 다 똑같다"고 리포트 — 실제로는 데이터 문제가 아니라 `PortfolioPicker.tsx` 버그였다. 항목 선택 시 검색창에 `"COL-001 — 주소..."` 형태의 라벨을 채워넣었는데, 이 문자열이 어떤 실제 주소·담보ID와도 부분일치하지 않아 **두 번째 항목부터는 검색 결과가 하나도 안 뜨고 조용히 첫 선택값에 고정**돼 있었다. 선택 후 검색창은 비우고(재검색 가능하게) 선택 결과는 별도 캡션("선택됨: COL-XXX — 주소 (금액)")으로 보여주도록 수정. 실제 포트폴리오 데이터 자체는 담보유형별로 충분히 다양함을 직접 확인(아파트 240만~/공장 2.8억~8억 등).

**2) 거제 담보 포트폴리오 확장**: 사용자가 "거제에 대해서도 가상 데이터를 만들어두고 싶다"고 요청(거제시 SHP는 이전 세션에서 이미 추가됐으나 포트폴리오 담보는 미생성 상태였음, 위 2026-08-19 "거제시 SHP 추가" 항목 참조). 기존 대구·포항 파이프라인(`discover_collateral_addresses.py`/`discover_via_juso.py`/`grid_scan_residential.py`/`generate_portfolio.py`)을 건드리지 않고 **완전히 별도의 거제 전용 스크립트 3개**를 새로 만들었다:
- `scripts/discover_geoje_addresses.py`(V-World POI 검색, 8종) — `_geoje_address_candidates.json`에 저장
- `scripts/discover_geoje_via_juso.py`(도로명주소 검색API 보완) — 같은 파일에 병합
- `scripts/generate_geoje_portfolio.py`(실제 침수·건물·EAL 라이브 계산 → PortfolioRecord 생성) — 유형당 목표 20건(사용자가 "가상 데이터를 만들어두고 싶다"고만 요청했지 대구·포항 수준의 전면 확장을 요청한 건 아니라 40건이 아닌 20건으로 판단, 2026-08-19)

**실제 결과**: POI+JUSO 합산 후보 아파트 60/공동주택 60/단독주택 60(POI만으론 2건뿐이었으나 JUSO로 대거 보완)/다가구주택 57/근린생활시설 55/업무시설 38/창고 19/공장 23건 확보. 생성 결과 **154건 신규**(아파트·공동주택·단독주택·다가구주택·근린생활시설·업무시설 6종은 20건씩 달성, 창고 15건·공장 19건만 후보 부족으로 미달) — **전부 IN_SCOPE**(거제시는 SHP 1개가 시 전역을 커버해 커버리지 밖이 거의 안 나옴, 대구·포항의 여러 SHP 조각과 다른 지형). 최종 포트폴리오 **316 → 470건**.

**의도적으로 안 한 것**: 대구·포항처럼 "부족분만 채우기" 로직(`generate_portfolio.py`의 shortfall-fill)을 재사용하지 않고 신규 스크립트로 분리한 이유 — 기존 스크립트를 거제까지 다루도록 고치면 기존 316건 생성 로직·후보 파일에 손댈 위험이 있어, 완전히 독립된 산출물(별도 후보 파일·별도 생성 스크립트)로 안전하게 분리했다.

**검증**: `tests/test_portfolio_loader.py`의 총 건수 assertion을 470으로 갱신. 포트폴리오 관련 테스트 27개(`test_portfolio_loader.py`/`test_portfolio_agent_smoke.py`/`test_portfolio_filter.py`/`test_portfolio_alerts.py`/`test_portfolio_geocode_cache.py`/`test_webapp_endpoints.py`) 전부 통과. 전체 스위트(`pytest tests/ -q`) 재확인 필요(아직 실행 안 함 — 이번 세션에 이미 여러 번 26분+ 걸린 전례가 있어 다음 체크포인트에서 실행 권장). 프론트 `tsc --noEmit`·`npm run build` 통과, `webapp/static/` 재생성, 서버 재시작 완료.

**영향**: PM은 (1) 거제 특보 조회(라이브/과거 이력)는 여전히 미구현 상태임을 재확인할 것 — 위 2026-08-19 "거제시 SHP 추가" 항목이 이미 명시했듯 `REGION_CODE_TO_KMA_STN_ID`/`REGION_CODE_TO_KMA_ZONE`에 거제 항목이 없어 담보 평가(침수·건물·EAL)는 되지만 포트폴리오 알림 트리거(특보 발효 감지)는 거제 지역에서 작동하지 않는다. (2) 거제 창고·공장 미달분(각 5·1건)을 더 채울지는 후보 발굴 방법을 추가로 고민해야 함(대구·포항 때처럼 다른 키워드 조합 시도 가능).

## 2026-08-19(계속) — 거제 특보 조회(라이브+과거 이력) 연동 완료 — 위 미구현 항목 해소

**계획**: 바로 위 항목이 "거제 특보 조회는 미구현"이라고 명시해뒀던 것 — 사용자가 즉시 "거제 특보 조회도 연동해줘"라고 요청해 착수.

**실제**: 두 API 각각에 거제(48310) 항목을 실측으로 확인해 추가했다.
1. **라이브(`advisory/live.py`, data.go.kr WthrWrnInfoService)**: `stnId=159`(부산지방기상청)를 추가했는데, 이번엔 포항(138)처럼 "표준 관측지점 번호 추정"이 아니라 **실제 데이터로 교차검증**했다 — `kma_historical.py`(기상청 API허브)로 거제 REG_ID(L1082200)의 힌남노 당시 실제 발효 기록을 조회해보니 발표관서(STN) 필드가 정확히 `159`로 찍혀있었다(기상청 API허브의 STN=발표관서 코드와 data.go.kr의 stnId가 같은 코드 공간임을 활용). 라이브 조회로 실제 활성 특보(오늘 폭염주의보)도 정상 반환됨을 재확인 — `verified=True`.
2. **과거 이력(`advisory/kma_historical.py`, apihub.kma.go.kr)**: `wrn_reg.php` 재조회로 "경상남도"(L1080000, 전국 직계 자식) 아래 "거제"(L1082200, "거제시")를 찾아 `REGION_CODE_TO_KMA_ZONE`에 추가. 거제는 SHP가 시 전체를 하나로 커버하는 것과 마찬가지로 이 특보구역도 시 전체와 1:1 대응 — 대구 5개구 같은 세분화 문제가 없다.

**검증**: `run_advisory_agent(region_code="48310", mode="live")`·`mode="historical"`(힌남노 구간) 둘 다 실제 API로 호출해 정상 결과 확인(라이브: 폭염주의보 1건, 과거: 태풍·강풍 경보 이력 6건 — 대구·포항 사례와 유사하게 경보 격상/하향 시퀀스가 자연스럽게 나옴). 신규 테스트 3개(`test_advisory_live.py`·`test_kma_historical.py`) 포함 관련 스위트 39개 통과. `/api/resolve-region`로 실제 거제 주소 조회해 `live_supported: true` 확인(서버 재시작 필요했음 — 코드 변경 후 재시작 안 하면 반영 안 되는 문제가 이번 세션에서도 여러 번 반복됨, 매번 주의 필요).

**사소한 사고**: 테스트 파일(`tests/test_advisory_live.py`) 작성 중 내가 안 쓴 `assert result.stn_id_verified is False`라는 줄이 파일에 끼어들어 테스트가 실패했다 — 다른 세션이 같은 파일을 동시에 건드렸을 가능성이 있음(이번 세션 내내 병렬 세션이 여러 파일을 동시 수정하는 정황이 반복 관찰됨). 즉시 제거해 해결, 실제 코드 로직 문제는 아니었음.

**영향**: 6개 지역(포항·대구 5개구) + 거제 = **7개 지역 전부 담보 평가·특보 조회(라이브+과거) 완전 연동** 완료. 남은 미구현: 거제 큐레이션 리플레이 이벤트는 없음(`curated_replay: null`로 정직하게 표시) — 필요하면 힌남노·수성구처럼 거제의 실제 재해 사건을 조사해 큐레이션 데이터를 만드는 것도 로드맵 후보.

## 2026-08-19(계속) — SHP 콜드 로딩 디스크 캐시 추가 — 프로세스 재시작마다 반복되던 비용 제거

**계획**: 2026-08-09 항목("query_flood_risk 캐시 없음")에서 이미 `_cached_default_regions()`(`lru_cache`)로 프로세스 내 재호출은 해결했었다. 하지만 이 캐시는 **프로세스 수명 동안만** 유효 — 서버를 재시작하거나 pytest를 새로 띄울 때마다(이번 세션에서 반복 관찰: 4개 파일만으로 75분 걸린 사례, `test_loader_idempotent.py` 리팩터 후에도 여전히 26분+) 여전히 SHP 7개(거제 추가로 냉천1+신천5+거제1) 콜드 로딩을 처음부터 반복했다. HANDOVER.md §4.3이 전제한 "로컬 캐시로 즉시 전환"이 실제로는 세션 경계를 못 넘는 얕은 캐시였던 셈.

**실제**: `gis/loader.py`에 `load_all_regions_cached()`를 추가 — SHP+dbf 파일의 (경로, mtime_ns, size)로 구성한 manifest와 포맷 버전을 피클로 함께 저장, 원본이 안 바뀌었으면 디스크 캐시를 그대로 반환하고 바뀌었으면(또는 버전 불일치) 자동으로 재로딩 후 캐시 갱신. `gis/query.py::_cached_default_regions()`와 `tests/conftest.py`의 `regions` 세션 픽스처가 이걸 쓰도록 전환. 캐시 파일은 `data/.cache/`(gitignore 대상)에 저장되어 git 이력에 안 남음.

**의도적으로 캐시를 안 쓴 곳**: `tests/test_loader_idempotent.py`의 `reloaded_regions`는 여전히 `load_all_regions()`(비캐시)을 직접 호출한다 — "동일 SHP를 진짜로 다시 파싱해도 동일 결과가 나오는가"를 검증하는 게 그 테스트의 존재 이유라, 디스크 캐시를 쓰면 검증 의미가 없어짐(사용자와 사전에 합의한 설계 제약).

**검증**: 콜드 실측 651.5초(7개 SHP, 거제 추가로 2026-08-09 당시 6개·157.8초보다 늘어남) → 캐시 히트 시 0.46초. `test_query_caching.py`가 monkeypatch 대상 이름(`load_all_regions`→`load_all_regions_cached`)을 안 맞춰 1건 실패했던 것 수정 후 전체 스위트(`pytest tests/ -q`) **219개 전부 통과, 136.95초**(이전 26분~90분+ 대비 대폭 단축) — 남은 133초는 위 의도적 비캐시 재파싱(`test_loader_idempotent.py`) 몫.

**영향**: 없음(설계 변경 아님) — HANDOVER §4.3의 "로컬 캐시" 의도를 프로세스 경계까지 실제로 충족시키는 구현 보강. 참고로 PM이 SHP 원본 파일을 교체하는 경우 캐시가 mtime/size 변경으로 자동 무효화되니 별도 조치 불필요.

## 2026-08-20 — 재난문자 API(safetydata.go.kr) 승인 확인 + 키 등록 + IP 화이트리스트 에러 실측 확인, body 스키마는 아직 미검증

**계획**: 2026-08-19 항목이 "승인 대기 중, 승인되면 같은 패턴으로 추가 예정"으로 남겨둔 것 — 세션 시작 시 재확인했더니 사용자가 "승인됨"이라며 키를 전달.

**실제**: `SAFETYDATA_DISASTER_MSG_API_KEY`(.env)·`SAFETYDATA_DISASTER_MSG_URL`(config.py, `DSSP-IF-00247`)로 등록 후 실호출로 검증 시작.

1. **egress IP 불일치를 먼저 발견**: PowerShell로 확인한 현재 공인 IP(`211.196.39.156`)가 safetydata.go.kr 화이트리스트 등록 IP(`172.22.112.1`, 사설 대역 — 이전 접속 환경에서 감지된 값으로 추정)와 달랐다. 실호출 결과 예상대로 `resultCode="32", resultMsg="UNREGISTERED IP ERROR"`(HTTP 200 안에 에러가 실림, HTTPError 아님)를 확인.
2. **"핫스팟이 정답"이라는 특정 네트워크 전제는 틀렸다는 사용자 정정**: 최초 구현에서 안내 문구·모듈 주석에 "폰 핫스팟으로 전환"이라고 못박았으나, 사용자가 "IP는 그때 인터넷 연결 상황에 따라 바로 바뀔 수 있어서 핫스팟이어야 한다는 얘기는 빼라"고 정정 — 등록 IP 자체가 고정돼 있지 않으므로 특정 네트워크를 처방하지 않고 "safetydata.go.kr에서 등록 IP를 확인하고 그 IP를 쓰는 네트워크로 전환하거나 재등록하라"로 일반화했다.

**구현한 것**: `src/climate_risk/advisory/disaster_msg.py`(신규) — `query_disaster_messages(params)`가 응답 봉투(`{header:{resultCode,resultMsg,errorMsg}, body}`)를 파싱해 `STATUS_OK`/`STATUS_UNREGISTERED_IP`/`STATUS_UPSTREAM_ERROR` 3종으로 명시 분류한다(kma_historical.py와 동일한 조용히-안-삼키는 패턴). **body 필드 파싱(실제 재난문자 레코드에 구·행정동 단위 지역 필드가 있는지 포함)은 아직 구현하지 않았다** — 성공 응답을 한 번도 실제로 못 봐서(화이트리스트 IP 불일치로 막힘) 필드명을 추측해서 파싱 로직을 만들지 않는다는 이 저장소 관례를 그대로 따름. 성공 시 `raw_body`에 원본 dict/list를 그대로 반환해두어, 나중에 등록 IP로 재시도했을 때 그 값을 보고 파싱 로직을 채울 수 있게 했다. success resultCode가 "00"일 거라는 가정도 미검증이라고 docstring에 명시(틀려도 STATUS_UPSTREAM_ERROR로 안전하게 실패하도록 설계 — 잘못된 코드를 성공으로 오판할 위험 없음).

**검증**: 신규 테스트 4개(`test_disaster_msg.py`) — IP 미등록 에러가 원시 코드가 아니라 안내문으로 번역되는지(및 "핫스팟" 문구가 없는지), 알 수 없는 resultCode가 조용히 성공 처리되지 않는지, 네트워크 오류·성공 케이스(raw_body 통과) — 전부 통과. IP 미등록 fixture는 2026-08-20 실측 캡처 그대로 사용.

**영향**: `advisory_agent.py`에는 아직 연결하지 않음 — body 스키마(특히 지역 필드가 구 단위인지)를 실제로 봐야 `mode="disaster_msg"` 같은 통합 여부를 판단할 수 있다. PM은 (1) 등록 IP를 현재 접속 환경으로 갱신(또는 그 IP를 쓰는 네트워크로 전환)해 실제 body를 한 번 받아볼 것, (2) 받은 뒤 "구 단위 세분화 가능성" 가설이 맞는지 확인 후 다음 단계(body 파싱 구현 + advisory_agent 통합 여부) 진행.

## 2026-08-20(계속) — 재난문자 body 스키마 확보(구·동 단위 세분화 가설 확인됨) + 산불/화재 알림 트리거 추가 + advisory_agent 자동 병합까지 완료(A안 완주)

**계획**: 위 항목의 "PM 판단 필요" 2가지 — 사용자가 IP를 재등록해 즉시 성공 응답 확보, 이어서 "산불/화재도 알림에 추가하고 싶다"는 신규 요청(사용자, 2026-08-20). B안(화재를 홍수처럼 EAL 정량 리스크 축으로 추가, 산불위험지도+건물 화재취약도+화재 전용 몬테카를로 필요)과 범위를 명확히 분리 — **이번 세션은 A안(재난문자를 홍수 특보와 동일한 성격의 "알림 트리거"로만 사용)까지만**, B안은 완전히 별도 이니셔티브로 미착수.

**실제**:

1. **IP 재등록 후 실제 body 스키마 확보**: 사용자가 safetydata.go.kr에 현재 IP로 재등록 → 1분 전파 대기 후 재시도 → `resultCode="00"` 성공. 필드: `SN`·`CRT_DT`("YYYY/MM/DD HH:MM:SS")·`MSG_CN`·`RCPTN_RGN_NM`·`EMRG_STEP_NM`·`DST_SE_NM`·`REG_YMD`·`MDFCN_YMD`. **가설 확인됨** — `RCPTN_RGN_NM`이 실제로 시/군/구 단위, 심지어 읍/면/동까지 세분화된다(예: "대구광역시 수성구 지산동", 2026-07-17 실제 집중호우 재난문자). 대구 5개구가 쉼표구분 리스트로 개별 나열되는 경우도 확인(`"대구광역시 남구,대구광역시 달서구,...,대구광역시 수성구,..."`) — 기상청 특보 API 2종이 못 하는 대구 개별 구 구분이 재난문자로는 된다.
2. **요청 파라미터 확정**: 사용자가 safetydata.go.kr API 상세 페이지에서 직접 캡처해준 공식 스펙으로 확정(제가 원격 문서 읽기로 여러 번 잘못 짚었던 것과 대비, kma_historical.py 때와 같은 패턴) — `crtDt`("조회시작일자", 하한만 있고 종료일 파라미터는 없음)·`rgnNm`("지역명(시도명, 시군구명)", 서버측 지역 필터). 실측으로 추가 확인: crtDt 하한은 걸리지만 **응답이 날짜순 정렬이 아니다**(레코드가 뒤섞여 옴) — 그래서 상한(end)은 클라이언트에서 직접 필터링해야 한다. `rgnNm`은 부분일치라 "대구광역시 수성구" 하나만 넘겨도 해당 구가 들어간 쉼표구분 다중지역 레코드까지 다 걸려온다.
3. **사용자 신규 요청 — 산불/화재 알림 트리거 추가(A안)**: DST_SE_NM 공식 전체 목록(사용자가 캡처해준 스펙에 포함 — AI·가뭄·가축질병·강풍·건조·교통·교통사고·교통통제·금융·기타·대설·미세먼지·민방공·붕괴·산불·산사태·수도·안개·에너지·전염병·정전·지진·지진해일·태풍·테러·통신·폭발·폭염·풍랑·한파·호우·홍수·화재·환경오염사고·황사, 34종)에 실제로 "산불"·"화재"가 있음을 확인(2025년 봄 포항 인근 동해안 산불 실측 데이터로 재검증). `RELEVANT_DST_SE_NM` 화이트리스트(호우·홍수·태풍·강풍·대설·산사태·풍랑·폭풍해일·산불·화재)로 담보 물리적 손상과 무관한 카테고리(폭염·황사·교통통제·가축질병 등)를 걸러낸다 — 이 필터링은 disaster_msg.py에서만 필요하다(KMA 특보 API 2종은 애초에 기상특보만 주니 이런 필터가 필요 없었음).
4. **advisory_agent 통합 — 별도 mode + historical 모드 자동 병합 둘 다**: `mode="disaster_msg"`를 독립 모드로 추가(재난문자 단독 조회, IP 미등록/지역 미매핑/페이지 상한/업스트림 오류 4종 명시 상태 반환 — 조용히 안 뭉갬). 웹 UI가 이미 "리플레이/라이브/특정날짜" 드롭다운을 걷어내고 `query_date` 필드 하나로 단순화된 상태였던 것(다른 세션 작업, DEV_LOG 참조)과 맞물려, 재난문자를 위한 새 UI 요소를 추가하는 대신 **`historical` 모드가 재난문자를 큐레이션 뉴스 병합과 같은 방식으로 자동으로 함께 조회**하도록 결정(사용자 선택, 2026-08-20). `_disaster_msg_supplemental_events()`가 이 보강 조회를 담당하며, 실패해도(IP 미등록 등) historical 모드 자체(KMA 결과)는 깨지지 않는다 — KMA가 이미 성공한 1차 데이터이므로 보강 조회 실패는 "판정 불가"가 아니라 "보강 정보 없음"으로 처리(설계원칙1이 보호하는 홍수 커버리지 게이트와는 다른 층위).
5. **매핑 메커니즘은 이미 범용이라 새로 만들 게 없었음**: 포트폴리오 재계산(`portfolio_agent.py`)이 `advisory.region_code`로 `PortfolioRecord.region_code`를 단순 exact-match하는 mode-무관 로직이라, disaster_msg 모드가 같은 SGG 코드 규칙으로 region_code를 채우기만 하면 자동으로 맞물린다. `graph/week3_demo.py`/`week4_demo.py`도 이미 `mode` 문자열을 그대로 통과시키는 구조라 손댈 게 없었다 — CLI(`scripts/_demo_cli.py`)에 `--mode disaster_msg` 선택지만 추가.

**놓칠 뻔한 것 — 기존 historical 테스트가 자동으로 실제 네트워크를 호출할 뻔함**: `historical` 모드에 재난문자 자동 병합을 추가하면서, 재난문자 mock을 안 걸어둔 기존 historical 테스트 3개가 이제 매번 실제 safetydata.go.kr을 호출하게 되는 걸 뒤늦게 알아챔 — 전부 빈 성공 응답(`_DM_EMPTY_OK_SAMPLE`)으로 mock 추가해 테스트 격리 복구.

**검증**: 신규/수정 테스트 총 6개(disaster_msg.py 파싱·지역매칭·필터링 관련 6개 + advisory_agent 통합 5개 + 기존 3개 mock 보강) 포함 `pytest tests/ -q` 237개 전체 통과(227초). **로컬 서버(uvicorn) 재시작 후 실제 `/api/assess` 호출로 최종 검증**: (a) 대구 수성구 2026-07-17 — KMA 2건+큐레이션 8건+재난문자 4건=14건 정상 병합, source_url 3종(apihub.kma.go.kr·뉴스 4개사·safetydata.go.kr) 전부 확인. (b) 포항 남구 2025-03-25(동해안 산불 실제 사건) — 강풍주의보 1건+산불 재난문자 5건=6건, **`trigger_event=True` → `portfolio_batch.matched_count=58`**(포항 남구 담보 58건이 실제로 재계산 대상으로 잡힘) — "산불 재난문자→알림 트리거→포트폴리오 재계산" 전체 체인이 실제 데이터로 끝까지 동작함을 확인.

**영향**: A안(재난문자를 홍수 특보와 동일한 성격의 알림 트리거로 사용, 산불/화재 포함) 완주. B안(화재를 EAL 정량 리스크 축으로 추가)은 사용자와 명시적으로 분리 확인했고 미착수 — 필요 시 별도 세션에서 데이터 소스 확보부터 새로 설계해야 함. `webapp/app.py`·프론트엔드는 이미 `historical` 모드 경로를 쓰고 있어 이번 통합에 코드 변경이 전혀 필요 없었다(자동 병합이 `advisory_agent.py` 내부에서 일어나므로). PM은 (1) `disaster_msg` 단독 모드(현재 CLI에서만 노출)를 웹 UI에도 노출할지, (2) `RELEVANT_DST_SE_NM` 화이트리스트 구성(특히 지진·지진해일·붕괴·폭발·테러 제외 판단)이 적절한지 검토 필요.

## 2026-08-23 — B안(화재를 EAL 정량 리스크 축으로 확장) 보류 확정 — 로드맵 기록만, 착수 안 함

**계획**: 명시적 계획 없음 — 위 2026-08-20 항목이 A안 완주 시점에 B안을 "완전히 별도 이니셔티브로 미착수"라고만 남겨뒀던 것에 대해, 사용자가 직접 서버로 화재 트리거를 확인해보며 "지금 우리가 가진 자료가 홍수·하천범람 위주라, 화재로 하려면 화재 피해지역·발화지 같은 별도 공간데이터가 필요해 보인다"고 스스로 짚고 지금 당장은 미룬다고 확정. 착수는 안 하고 기록만 남겨달라는 요청.

**실제**: B안이 실제로 필요로 하는 것을 정리(홍수 파이프라인과 대응시켜서):

| 홍수(이미 있음) | 화재(B안에 필요, 현재 없음) |
|---|---|
| 환경부 홍수위험지도 SHP(폴리곤, `gis/loader.py`가 로딩) | 산불 발화지·피해지역 공간데이터(예: 산림청 산불통계, 국가공간정보포털 산불피해지 폴리곤 등 — 아직 조사 안 함) |
| `gis/query.py` point-in-polygon 커버리지 게이트 | 화재판 커버리지 게이트(같은 구조 재사용 가능성 있으나 미검증) |
| `building/vulnerability.py` 건물취약도(구조·층수·용도 등) | 건물 화재취약도 모델(건축자재·인접 산림 거리 등 다른 변수 필요 — 근거 문헌 조사부터 필요) |
| `scenario/eal.py` 몬테카를로 EAL | 화재 전용 몬테카를로 EAL 항목(발생확률 추정 방식부터 새로 설계) |

**영향**: 코드 변경 없음(순수 기록용 항목). B안은 "필요 데이터 소스 확보 → 커버리지 게이트 설계 → 건물 화재취약도 모델 → 화재 EAL"까지 홍수 HANDOVER Week1~2와 동일한 규모의 별도 스파이크가 필요하다는 게 이번에 명확해졌다 — 착수 시점엔 이 표를 출발점으로 데이터 소스 조사부터 다시 시작할 것. 지금 완성된 A안(재난문자 알림 트리거, 위 2026-08-20 항목)은 그대로 유지·운영하면 되고 B안 착수 여부와 무관하다.

## 2026-08-26 — safemap 침수흔적도(A2SM_FLUDMARKS_WI) WFS 엔드포인트 살아있음 확인 — 실측 침수흔적 교차검증·내수침수 분류의 후보 데이터소스 발견 (조사만, 미착수)

**계획(HANDOVER.md 기준)**: §4.3 "safemap `openapi2/IF_0092_WMS`(GetMap 이미지)가 키 유효성과 무관하게 HTTP 500 고정... GetFeatureInfo도 이 API 설계에 구조적으로 존재하지 않는다"는 결론으로 safemap 라이브 경로를 사실상 폐기했다(범례 API `lgdInfo`만 예외적으로 사용, HANDOVER.md:13·197). `gis/query.py`의 `METHODOLOGY_DISCLAIMER`는 "실측 침수흔적 이력과 교차 등급화해 참고"를 권고 문구로 이미 담고 있으나, 이를 뒷받침할 실제 데이터소스는 조사된 적이 없었다.

**실제**: 사용자가 외부 블로그(safemap `geo.safemap.go.kr` WMS 활용기)와 safemap 웹뷰어(`www.safemap.go.kr/main/smap_renewal.do`, "침수흔적도" 레이어)를 검토해달라고 요청. 블로그가 쓴 `geo.safemap.go.kr` 엔드포인트는 브라우저로 직접 접속해도 연결 자체가 안 됐다(폐기/변경 추정). 대신 safemap 웹뷰어에서 "침수흔적도" 레이어를 켜고 브라우저 네트워크 요청을 직접 관찰해, HANDOVER가 폐기 판정한 것과는 **다른, 현재 살아있는 엔드포인트**를 확인했다:

- `https://www.safemap.go.kr/geoserver_pos/safemap/wms` — `GetMap` 200 정상, `GetFeatureInfo`도 GeoJSON으로 정상 응답 확인(HANDOVER의 "GetFeatureInfo 없음" 결론은 이미 폐기된 `openapi2/IF_0092_WMS`에 대한 것이었고, 이 엔드포인트는 별개의 표준 GeoServer임).
- `https://www.safemap.go.kr/geoserver_pos/safemap/wfs` — 표준 GeoServer WFS 2.0.0. `GetCapabilities`로 150개 피처타입 확인. 그중 `safemap:A2SM_FLUDMARKS_WI`를 `GetFeature`(`outputFormat=application/json`)로 조회하니 **전국 52,832건**의 실측 침수흔적 폴리곤이 반환됨(표본 3건 직접 확인). 필드: `flud_nm`(사건명, 예 "07.09.~07.19. 호우")·`exmn_year`/`flud_year`(연도)·`avg_fldwtl`(평균침수심)·`flud_ar`(침수면적㎡)·`sat_date`/`end_date`(침수 기간)·`ctprvn_cd`/`sgg_cd`/`emd_cd`(행정동코드 — 건축HUB와 동일 코드 체계)·`flud_nm2`(침수원인 분류 — 표본 3건 전부 "내수배제 불량"). 좌표계는 EPSG:3857(우리 SHP 원본은 EPSG:5186, 재투영 필요).

**영향**: 두 가지 미해결 항목에 대한 유력 후보 데이터소스를 확보했다(코드 변경 없음, 착수 안 함).

1. **실측 침수흔적 교차검증** — `METHODOLOGY_DISCLAIMER`가 권고만 하고 실제 구현이 없던 부분. 현재 `flood_history_events`(`data/curated/hinnamno_2022` 등)는 개별 사건 뉴스 기사를 수동 큐레이션한 서사 타임라인일 뿐, `A2SM_FLUDMARKS_WI` 같은 전국 단위 실측 폴리곤 골든셋이 아니다. 5만 건대 표본이면 현재 골든셋(6~10개 지점, HANDOVER 미해결 항목 6번의 "통계적 유의성 낮음" 한계)을 크게 개선할 여지가 있다.
2. **내수침수(배수관 역류형 도심침수) 분류 가능성** — `flud_nm2`="내수배제 불량" 값이 실제로 존재해, 화재(B안)와 동급 규모로 예상됐던 완전히 새로운 스파이크 없이 **기존 필드로 하천범람/내수침수를 구분**할 여지가 보인다(단, 우리가 현재 쓰는 환경부 홍수위험지도처럼 미래 예측용 시뮬레이션이 아니라 과거 실측 이력이라는 점에서 성격이 다르다 — EAL 계산에 바로 대체 투입할 수 있는 데이터는 아님).

**미확인(착수 전 반드시 재확인 필요)**: `flud_nm2`의 전체 값 종류·정확한 분류 기준(표본 3건뿐), 대구·포항·거제 커버리지 여부, 데이터 최신 연도, 재사용 라이선스 조건(공식 data.go.kr 등록 없이 GeoServer를 직접 호출한 것이라 공공누리 유형 등 미확인 — SHP처럼 공공누리 4유형이면 대량 활용에 제약 가능), `A2SM_FLUDMARKS_WI` 외 유사 피처타입(`_SIM`·`_SIM12`·`19`·`_old`)과의 관계. 실제 연동 설계·구현은 전혀 시작하지 않았다 — 착수 여부는 PM 판단 필요.

## 2026-08-26 (후속) — 실측 침수흔적 오프라인 교차검증(스코프 A) 구현 — recall 34.7% 측정, EAL/대시보드/API는 무변경

**계획**: 위 항목의 미확인 사항 재조사 결과를 사용자에게 보고한 뒤, 리스크가 다른 3단계 스코프(A. 오프라인 검증만 / B. 대시보드 참고표시 추가 / C. EAL 계산에 직접 투입)를 제시했다. 사용자가 "A만" 진행을 명시적으로 선택 — 프로덕션 코드 경로(`FloodRiskResult` 스키마·EAL·대시보드·라이브 API 호출)는 건드리지 않고, 우리 SHP tier 판정이 실측 침수 이력과 얼마나 일치하는지 오프라인으로 재는 것까지만 스코프.

**실제**: 미확인 항목 재조사(브라우저로 safemap WFS 직접 호출):
- `flud_nm2`는 통제 어휘가 아니라 자유서술 텍스트임을 확인(800건 표본에 30종 이상 변형·오탈자). 우리 6개 지역으로 좁히면 실제로는 11종으로 수렴.
- 우리 등록 6개 지역 중 3곳(포항 남구 63건·거제시 11건·대구 수성구 6건, 총 80건)에 실측 기록 있음 — 나머지 4곳(대구 남구·중구·동구·북구)은 0건("데이터 없음"이지 "안전"이 아님, 정직하게 기록).
- 포항 남구 63건 중 62건이 정확히 우리 데모가 쓰는 "2022.09.06~09.07 제11호 태풍 힌남노" 사건 — 지점별 실측 침수심(`avg_fldwtl`, cm)까지 있어 데모 시나리오와 직접 대조 가능.
- `A2SM_FLUDMARKS_SIM`(9만 건, 침수심·면적만 있고 원인·사건명 없음)은 시뮬레이션 데이터로 확인 — 실측 대조에는 부적합, `_WI`가 맞는 타입임을 재확인.

구현(신규 파일만 추가, 기존 파일은 `evaluation/metrics.py` import 1줄 + 함수 1개 추가 외 무변경):
- `data/.../curated/flood_marks_validation/A2SM_FLUDMARKS_WI_target_regions.json` — 80건 원본(좌표는 EPSG:3857 폴리곤 정점 단순평균→EPSG:4326 역변환 근사, 정밀 area-weighted centroid 아님). 라이선스 미확인 상태를 파일 자체에 `license_note`로 명시, 재배포 금지 원칙 기재.
- `src/climate_risk/evaluation/flood_marks.py` — 로더 + `classify_flud_cause()`(키워드 매칭으로 하천범람/내수배제/혼합/해안범람/미분류 5분류, 근거 없으면 "미분류"로 정직하게 남김).
- `src/climate_risk/evaluation/metrics.py::flood_marks_recall_metric()` — `coverage_gate_metric()`과 달리 '정답'이 없는 recall 측정. region별·cause_category별 breakdown.
- `tests/test_flood_marks_validation.py` — recall 수치 자체는 assert하지 않고(설계상 의도적), 데이터 무결성·파이프라인 무결성·OUT_OF_SCOPE 지역 분포(거제시에만 국한)만 회귀로 고정. 9개 전부 통과.

**측정 결과(2026-08-26, 실측)**: 80건 중 75건 IN_SCOPE·5건 OUT_OF_SCOPE(전부 거제시 — 해안범람 3건+저지대침수 2건, 거제 SHP가 "지방하천 17개소"만 커버해 해안선 자체가 원래 커버리지 밖이라 정상 동작). **overall recall 34.7%(26/75)** — 지역별 편차가 큼: 대구 수성구 100%(6/6) · 포항 남구 28.6%(18/63) · 거제시(스코프 내) 33.3%(2/6). 원인 카테고리별로도 편차: 순수 "내수배제" 85.7%(6/7)로 오히려 높은데, 힌남노 기록 대부분을 차지하는 "혼합"(하천+내수배제 동시) 카테고리는 26.6%(17/64)로 낮음. "해안범람"(태풍 월파) 3건은 전부 OUT_OF_SCOPE — 이건 결함이 아니라 우리 하천범람지도가 애초에 다루지 않는 별개 재해 메커니즘이라는 스코프 경계가 실측으로도 확인된 것.

**영향**: (1) 골든셋을 6~10개(사람이 직접 확인) → 80개(실측 이력 기반)로 확장하는 목표는 달성. (2) 다만 recall 34.7%(특히 힌남노 "혼합" 카테고리 26.6%)는 낮은 편으로, "우리 SHP가 실제 침수 범위를 얼마나 담아내는가"에 대한 첫 정량적 반증 자료다 — 힌남노 당시 포항 시가지 전역에 번진 실제 침수 범위가 우리가 쓰는 단일 하천(냉천) "기왕최대 빈도" 시뮬레이션 폴리곤보다 훨씬 넓었을 가능성을 시사하지만, **원인 분석은 아직 하지 않았다**(SHP 폴리곤 자체의 지리적 범위 vs 실제 침수 발생 지점의 공간 분포를 직접 겹쳐보는 작업이 다음 단계). (3) 내수침수(스코프 밖 논의였던 항목)는 여전히 EAL에 반영 안 함 — 이번 구현은 오프라인 측정 지표 하나를 추가한 것뿐, 프로덕션 판정 로직·API·대시보드는 전혀 바뀌지 않았다. (4) 라이선스 미확인 상태는 그대로 남아있음 — 이 검증 결과를 제안서 등 외부 문서에 인용하기 전에 반드시 확인 필요.

**미확인(다음 조사 필요)**: recall이 낮게 나온 원인(SHP 지리적 범위 protocol 부족 vs 우리 tier 임계값(근접≤100m)이 너무 타이트 vs 둘 다), B(대시보드 참고표시)·C(EAL 투입) 스코프 착수 여부, 라이선스.

## 2026-08-26 (후속2) — recall 34.7% 저조 원인 규명: "내수배제라서"가 아니라 SHP 지리적 커버리지 협소가 원인

**계획**: 위 항목 "미확인" 1번(recall 저조 원인)을 사용자가 바로 지적 — "혹시 내수배제해서 recall이 낮게 나온 거 아니냐"는 가설을 갖고 조사 요청.

**실제**: 두 단계로 조사했다.

1. **region×cause_category 교차표 확인 결과, 가설 자체를 검증할 수 없는 데이터 구조임이 드러남.** 대구 수성구 6건은 전부 "내수배제"(idx5, "내수_방재시설 용량부족") 단일 원인이고, 포항 남구 63건 중 61건은 전부 "혼합"(idx0, "하천 수위 상승으로 인한 역류 및 내수배제 불량") 단일 원인이다 — 즉 원인 카테고리가 지역과 거의 완전히 confound돼 있다. 이전 항목에서 "순수 내수배제 recall 85.7%"로 보였던 건 실은 "대구 수성구 recall≈100%"가 다른 라벨로 나타난 것일 뿐, 포항 남구 안에서 원인별 recall 차이를 비교할 대조군이 사실상 없다(61/63건이 동일 원인 텍스트).

2. **그래서 포항 남구 63건을 개별적으로 파고들어(`query_flood_risk`의 `distance_to_polygon_m`·실측 침수심까지) hit(18건)와 miss(45건)를 직접 비교**:
   - 폴리곤까지 거리: hit 평균 4.1m(0~53.2m, 전부 폴리곤 안쪽에 가까움) vs **miss 평균 2,317.5m(106.3m~9,798.7m)** — miss 45건 중 300m 이내(임계값을 조금만 늘리면 잡힐 near-miss)는 6건(13%)뿐이고, 나머지 39건(87%)은 수백m~최대 9.8km나 떨어져 있다.
   - 실측 침수심: hit 평균 7.2cm vs miss 평균 10.5cm — miss가 오히려 더 깊다(최대 73cm짜리 심각한 침수도 4.2km 밖에서 통째로 놓침). "사소한 침수만 놓친다"는 설명도 성립하지 않는다.

**결론**: 원인은 침수 메커니즘(내수배제 vs 하천범람)이 아니라 **SHP(냉천, 환경부 "기왕최대 빈도" 단일 하천 시뮬레이션)의 지리적 범위 자체가 힌남노 때 포항 남구 전역에 번진 실제 침수 범위보다 훨씬 좁다**는 것. tier 임계값(근접≤100m) 조정으로는 miss의 13%만 회복 가능하고, 87%는 임계값과 무관하게 폴리곤 자체가 그 지점을 담고 있지 않아서 발생한다 — point-in-polygon 로직의 버그가 아니라 입력 데이터(SHP)의 공간적 커버리지 한계다.

**영향**: (1) `flood_marks_recall_metric()`·`gis/query.py` 등 코드 수정 없음 — 이 조사는 "왜 낮게 나왔는지"를 밝히는 순수 분석이었다. (2) "recall이 낮다"는 우리 point-in-polygon 알고리즘의 결함이 아니라 "냉천 1개 하천 시뮬레이션만으로는 힌남노급 도시침수의 실제 공간 범위를 못 담는다"는, 데이터 소스 자체의 한계라는 게 명확해졌다 — 제안서·발표에서 이 결과를 인용할 경우 "알고리즘 문제"가 아니라 "커버리지 확장이 필요한 데이터 문제"로 정확히 서술해야 한다. (3) 사용자가 "이게 우리가 수정할 수 없는 사항이냐"고 재질문 — 답은 "SHP 자체(공식 시뮬레이션 결과물)는 우리가 못 고치지만, 완전히 손 못 대는 건 아니다": ⓐ 포항 남구에 냉천 외 다른 하천/소하천 SHP가 환경부·data.go.kr에 더 있는지 확인이 안 된 상태(현재 냉천 1개만 다운로드돼 있음, 데이터 확보 과제) ⓑ 오늘 확보한 A2SM_FLUDMARKS 실측 데이터 자체를 "SHP 시뮬레이션은 못 잡지만 과거 실제로 침수된 적 있는 지점"이라는 별도 참고 레이어로 대시보드에 얹는 방법(위 "설계 스코프 B"에 해당, EAL 계산에는 안 섞음 — 아직 미착수) ⓒ tier 임계값 조정은 13%만 회복하는 낮은 효용이라 우선순위 낮음. 착수 여부는 아직 결정 안 됨.

**미확인**: 포항 남구·거제시·대구 수성구 각각에 냉천/현재 SHP 외 추가로 다운로드 가능한 하천범람지도가 있는지(환경부 홍수위험지도 정보제공포털 재조사 필요), 위 ⓑ 방향 착수 여부.

## 2026-08-26 (후속3) — SHP 커버리지 협소 한계 보류 확정 — 로드맵 기록만, 착수 안 함

**계획**: 명시적 계획 없음 — 위 두 항목(recall 34.7% 측정, 저조 원인 규명)에 이어 사용자가 "일단은 지금 한계를 정확히 기록하고 보류해두자"고 확정. 착수는 안 하고 기록만 남겨달라는 요청(2026-08-23 화재 B안 보류 항목과 동일한 성격의 요청).

**실제**: 지금까지 규명된 한계를 한 문장으로 고정한다 — **"우리 홍수 위험 판정은 각 지역에 등록된 SHP(현재는 지역당 하천 1개, 특정 빈도 시뮬레이션)의 지리적 범위 안에서만 정확하고, 그 범위 밖은 실제로 침수된 지점이라도 '원거리'로 과소평가될 수 있다."** 실측 근거: 포항 남구 힌남노 기록 63건 중 45건(71.4%)을 우리 SHP가 놓쳤고, 그중 87%(39건)는 폴리곤에서 수백m~9.8km 떨어진 진짜 커버리지 밖이었다(tier 임계값 문제가 아님, `flood_marks_recall_metric()`으로 재현 가능·`tests/test_flood_marks_validation.py` 회귀 고정됨). 이 한계는 신천 4개 지점 "판정보류"(coverage.py KNOWN_UNCERTAIN_POINTS)와는 다른 축이다 — 판정보류는 "경계가 애매한 개별 좌표"이고, 이번 건은 "SHP가 아예 담지 않는 지리적 범위"라는 구조적 한계다.

해결 후보 3가지(전부 미착수, 우선순위 순):
| 후보 | 내용 | 상태 |
|---|---|---|
| a. 추가 SHP 확보 | 포항 남구 등에 냉천 외 다른 하천/소하천 SHP가 환경부·data.go.kr에 더 있는지 조사 → 있으면 `config.py` FLOOD_SHP_SOURCES에 항목만 추가(코드 변경 불요, 거제 추가 전례와 동일 패턴) | 미조사 |
| b. 실측 침수흔적 참고 레이어 | `A2SM_FLUDMARKS_WI`(오늘 확보)를 SHP tier와 별도로 "과거 실측 침수 이력 있음" 참고 표시로 대시보드에 추가 — EAL 계산엔 안 섞음(위험 신호·금전 조건 분리 원칙 유지) | 미착수(설계 스코프 B) |
| c. tier 임계값 조정 | 근접 임계값(100m)을 늘림 | 검토했으나 miss의 13%만 회복해 효용 낮음 — 우선순위 최하 |

**영향**: 코드 변경 없음(순수 기록용 항목). `flood_marks_recall_metric()`·검증 데이터셋·테스트는 이미 구현되어 남아있고(위 항목들 참조), 이 metric 자체가 앞으로 SHP 커버리지가 실제로 넓어졌을 때(위 a 착수 시) "개선됐는지"를 다시 잴 수 있는 재사용 가능한 회귀 도구로 남는다. 제안서·발표 자료에 이 recall 결과를 인용할 경우, "판정 알고리즘의 정확도" 문제가 아니라 "SHP 데이터 커버리지 확장이 필요하다"는 정직한 로드맵 항목으로 서술할 것 — HANDOVER.md §확장성 원칙("하천/지역 수를 하드코딩하지 않는다")과 같은 방향의 다음 확장 지점이다.

## 2026-08-31 — 거제 2026-08 실호우 사건으로 "재심사 알림" 메커니즘이 재해 심각도에 반응하지 않음을 실측 확인 — 사실조사 결론: 진행

**배경**: 발표 자료 준비 중 "8/18 거제시 옥포로 기준 시뮬레이션이 왜 재심사 알림을 안 띄우는지" 확인 요청이 있어, 실제 코드로 직접 재현 조사함(2026-08-31 세션).

**조사 1 — 코드 재현**: 거제(48310) 포트폴리오 레코드 전체(옥포로 원거리 tier 8건, 고현천로 등 내부/근접 tier 12건)를 현재 코드로 다시 계산해 `eal_before`와 대조. 옥포로는 SHP 폴리곤에서 1.6~1.9km 떨어진 "원거리" tier라 발생확률이 0.01%로 떨어져 EAL이 항상 정확히 0(0→0, 변화율 계산 불가). 고현천로 등 "내부"/"근접"(거리 0~91m) 레코드는 라이브 건축HUB 호출이 성공하는 한 `eal_after`가 `eal_before`와 바이트 단위로 완전히 동일(변화율 0.0%) — 근본 원인은 `run_scenario_agent()`가 특보/재난문자 데이터를 아예 입력으로 받지 않는 순수 정적(좌표+건물등록정보+고정seed) 모델이기 때문. 특보가 아무리 심각해도 재계산 결과가 바뀔 통로가 구조적으로 없음. (힌남노 리플레이 데모의 "+49%" 사례도 재현해본 결과, 실제로는 재계산 시점 건축HUB 라이브 응답이 포트폴리오 생성 시점과 달라진 데이터 드리프트로 설명되며 태풍 심각도가 반영된 것이 아님 — 부록: 별도 확인 필요 시 이 세션 기록 참조.)

**조사 2 — 실제 피해 사실조사(뉴스 검색, 2026-08-31 기준)**: 2026-08-15~19 거제시에 최대 968.1mm(관측 이래 최대) 폭우, 8/17 6시간 509.9mm·1시간 124.5mm 기록. 고현천이 8/17 새벽 범람해 거제 최대 상권인 고현동 시외버스터미널 일대 완전 침수(포트폴리오의 고현천로 담보 위치와 정확히 일치하는 지역). 산사태로 사망 1명·부상 3명(옥포동 아파트 산사태 인명피해 포함 — 단, 이건 하천범람이 아니라 산사태이므로 본 시스템의 홍수위험지도로는 원천적으로 포착 불가한 재해유형). 208세대 335명 대피, 1,500호 단전. 2026-08-21 행정안전부가 거제시 전역을 특별재난지역으로 우선 선포, 잠정 피해액 거제 270억원(통영 포함 433억원). 출처: 파이낸셜뉴스([전 직원 투입 피해복구](https://www.fnnews.com/news/202608172022003733), [고현동 상권 르포](https://www.fnnews.com/news/202608181423080683)), 경남신문([고현천 범람](http://www.knnews.co.kr/news/articleView.php?idxno=1548764)), YTN([침수 피해상황](https://www.ytn.co.kr/_ln/0103_202608171501561559)), 조세일보([특별재난지역 선포·피해액 433억](http://www.joseilbo.com/news/htmls/2026/08/20260821574272.html)).

**결론**: 진행 — 담보물 밀집 지역(고현동 상권)에서 실제로 심각한 하천범람 피해가 확인됐고, 이 사건을 이 시스템으로 재현했을 때 재심사 알림이 전혀 뜨지 않음을 실증했다. "특보 발효 시 포트폴리오를 실시간 재계산해 위험 변화를 감지한다"는 데모 서사와 실제 동작 사이에 실사건으로 입증된 간극이 있다.

**영향**: EAL 계산 코어(화이트박스 물리 모델, CLAUDE.md 설계원칙5)와 특보-금전 분리 원칙(CLAUDE.md 설계원칙2)은 그대로 유지한 채, 특보/재난문자의 심각도(`lvl_label`: 예비/주의보/경보/중대경보, `emrg_step_nm`: 안전안내/긴급재난/위급재난 — 현재 `advisory_agent.py`가 이미 파싱해두고도 트리거 boolean으로만 뭉개서 버리는 값)를 EAL과 별도의 독립 알림 채널(`portfolio/severity_alerts.py`, 신규)로 흘려보내는 작업을 진행한다 — 상세 설계는 `C:\Users\eujin\.claude\plans\gleaming-beaming-pebble.md` 참조. 산사태 등 하천범람 밖 재해유형은 이번 채널로도 EAL 정량화까지는 안 되지만(로드맵 항목, §6과 동일 성격), 재난문자 자체는 발송되므로 "심각도 알림"은 뜰 수 있음 — 이 구분(정량화 불가 ≠ 알림 불가)도 발표 시 정직하게 설명할 것.

## 2026-08-31(계속) — 심각도 기반 알림 채널 구현 완료

**실제**: 위 계획대로 `portfolio/severity_alerts.py`(신규 모듈, `SeverityAlertQueueEntry`+`build_severity_alert_queue`)를 EAL 알림(`portfolio/alerts.py`)과 완전히 분리된 형제 모듈로 구현. `AdvisoryEvent`에 `severity_level` 옵션 필드(기본 None) 추가, `advisory_agent.py`가 historical 이벤트엔 `lvl_label`을, disaster_msg 이벤트엔 `emrg_step_nm`을 채워 넣고 `is_high_severity_event()`(허용목록 `HIGH_SEVERITY_LEVELS = {"경보","중대경보","긴급재난","위급재난"}`)로 판정. `portfolio_agent.py`가 기존 EAL 알림 큐 계산 옆에 이 채널을 나란히 호출(`PortfolioBatchResult.severity_alerts` 신규 필드, 별도 로그 `SEVERITY_ALERT_QUEUE_LOG_PATH`). 레드팀 체크 5번째(`check_scenario_severity_isolation`)를 추가해 `run_scenario_agent` 시그니처에 advisory/severity 파라미터가 여전히 없음을 회귀 테스트로 고정 — EAL 금전 계산 경로는 안 건드렸다는 코드 레벨 증거.

실사건으로 직접 재현 검증: 거제(48310) 2026-08-17~19 historical 조회(실제 API, 55개 이벤트) → `filter_by_region` 매칭 154건 전원에 대해 심각도 알림 154건 생성 확인 — 이전엔 항상 조용했던 옥포로(원거리 tier, EAL 0→0)·고현천로(내부/근접 tier, EAL 변화율 0%) 레코드 모두 포함.

신규 테스트 `tests/test_severity_alerts.py`(7개, 구조적 회귀 테스트로 EAL/LTV/rate/score 필드 부재 확인 포함) + 기존 `test_redteam_scenarios.py`/`test_week4_demo_smoke.py`의 "레드팀 4종" 하드코딩 리스트를 5종으로 갱신. `pytest tests/ -q` 전체 재실행 **258개 전부 통과**(기존 249 + 신규 9).

**영향**: proposal.docx·PPT의 "레드팀 시나리오 4종"·"자동 테스트 237/249개" 등 숫자 표기를 이번 변경(258개, 레드팀 5종)에 맞춰 갱신 필요 — 다음 세션(PPT 내용 수정 단계)에서 반영. 웹 UI(`webapp/frontend`)에 `severity_alerts` 배열을 표시하는 작업은 이번 범위 밖으로 남겨둠(백엔드 타입 계약은 깨지지 않으므로 후속 작업으로 미룸).

## 2026-08-31(계속) — 심각도 알림 웹 UI 연동 + proposal.docx·PPT 반영 완료

**실제**: 위에서 "후속 작업으로 미뤄둔" 웹 UI 연동을 완료했다. `webapp/frontend/src/types.ts`에 `SeverityAlert` 타입과 `PortfolioBatch.severity_alerts` 필드 추가, `PortfolioCard.tsx`에 "특보 심각도 알림 — EAL 변화와 무관한 별도 채널" 섹션 신규 추가(심각도 배지·근거 텍스트·출처 링크·영향 담보ID 칩, 알림이 없을 때도 이유를 명시). `npx tsc -b`·`npm run build` 통과, `webapp/static/`에 반영.

실제로 로컬 서버(uvicorn)를 띄우고 `/api/assess`에 "경상남도 거제시 고현천로 52", `query_date=2026-08-17`로 라이브 요청을 보내 SSE 응답에 `severity_alerts`(긴급재난/disaster_msg)가 실제로 담겨 나오는 것까지 확인 — 백엔드 계산→API 응답→프론트엔드 타입까지 전 구간 실측 검증.

`proposal_climate-collateral-underwriting-ai.docx`(2.2 처리흐름 함수/파일 표, 지오코딩 도로명 단위 좌표 예시 표 추가)와 PPT(기술데모가이드) 양쪽에 이번 세션 발견·구현 내용을 반영 완료: 테스트 수 237→258, 골든셋 구성 정정(냉천1·신천5·거제6 → 냉천3·신천5·거제4), 레드팀 4종→5종, 실사건 재현 3건→4건(거제호우 추가), 슬라이드6(금융소비자보호) 신규 작성, 슬라이드4·5 궁금증 3건을 발표자 노트 Q&A로 해소.

**영향**: 코드 변경 없음(문서·UI 반영 기록). 다음 단계는 PPT에 힌남노·대구수성구·거제 3개 실사건의 대시보드 캡처 화면을 넣는 작업 — §03 대시보드 슬라이드군과는 별도로, "실사건 검증" 전용 섹션을 새로 구성할 예정.

## 2026-08-31(계속2) — PPT "실사건 검증" 섹션(3슬라이드) 실제 대시보드 캡처로 완성

**실제**: 로컬 uvicorn 서버(127.0.0.1:8080)를 띄우고 Chrome 브라우저 자동화로 3개 시나리오를 실제로 조회·캡처했다(mock/삽화가 아닌 진짜 화면):
- 힌남노(포항 인덕로 27, 2022-09-06 historical) — EAL 알림 발생(COL-003 +48.8%, COL-004 +49.6%), 특보 심각도 알림은 미발생(큐레이션 이벤트에 severity_level이 안 채워지는 현재 구현의 한계를 그대로 노출·정직하게 캡션에 명시).
- 대구 수성구(동대구로 3, 2026-07-17) — EAL 알림 0건(기존 설계대로), 신규 특보 심각도 알림이 "호우 경보 변경"을 잡아 매칭 23건 전원에게 발생 — 두 채널이 독립적으로 작동함을 시각적으로 증명하는 가장 좋은 사례.
- 거제(고현천로 52, 2026-08-17) — EAL 알림 0건(정적 모델의 구조적 한계), 특보 심각도 알림이 재난문자 "긴급재난"을 잡아 매칭 154건 전원에게 발생 — 이번 세션에 발견·구현한 공백이 실제로 메워졌다는 증거.

과정에서 실측된 것: (1) 프론트엔드가 이전 결과를 못 지우고 새 제출을 놓치는 경우가 있었다 — 원인은 클릭 좌표가 폼 레이아웃 변화(지역감지 문구 줄바꿈 등)로 밀려 "평가 실행" 버튼을 빗맞힌 것이었다(코드 버그 아님, 자동화 클릭 좌표 문제) — element ref 기반 클릭으로 전환해 해결. (2) 건축HUB 라이브 API가 이번에도 종종 FAILED로 응답했다(같은 좌표 재시도 시 성공) — 기존에 문서화된 라이브 API 변동성과 일치.

`webapp/frontend`는 이번에 코드 변경 없음(이미 완료된 상태를 그대로 사용). PPT에 새 슬라이드 3장(20~22쪽, "실사건 검증 1~3/3") 추가, 각 슬라이드에 실제 캡처 2장(담보평가 결과 + 포트폴리오·심각도 알림 카드)과 3줄 캡션. Q&A 슬라이드 페이지 번호를 20→23으로 갱신.

**영향**: 코드 변경 없음(PPT 산출물). 다음은 PPT 전체 디자인 정리 단계(사용자 요청 순서상 마지막 단계) — 새로 추가한 3슬라이드는 실제 스크린샷을 그대로 붙인 실용적 레이아웃이라, §03 대시보드의 삽화 스타일과는 결이 다르다는 점을 디자인 단계에서 감안할 것.

## 2026-09-03 — 재심사 알림 트리거 재설계 논의: "건축물 데이터 변화"는 피해 라벨로 쓸 수 없다 — 후보 파라미터 4분면 검증 하네스로 진행

**계획(HANDOVER.md 기준)**: §4.4(line 294) "알림 정밀도(트리거 오탐 방지 검증)" — 골든셋(실측 침수흔적·이력 지점)과 대조해 알림 정밀도·누락률을 산출한다는 지표가 스펙으로만 있고 미구현 상태였다. §4.6 항목7은 재심사 알림 임계치(EAL 변화율 20%)를 "잠정치, 실측 캘리브레이션 필요"로 남겨뒀다.

**배경(사용자 문제 제기)**: 2026-08-31 조사로 현재 "재심사 알림"(EAL 변화율 ≥20%)이 재해 심각도가 아니라 건축HUB 라이브 응답 드리프트에만 반응한다는 게 드러났다. "재난 후 건축물 데이터가 바뀌어야 알림이 가는 구조면 실시간 경보가 아무 소용이 없다"는 지적. 사용자 제안: ①사후 검증으로 피해 확인된 사건을 추리고 ②새 파라미터 후보를 그 사건들에 대입해 ③(후보 켜짐/안켜짐)×(정답 켜짐/안켜짐) 4분면으로 후보마다 검증해 적절한 피처를 고른다.

**실제(코드 탐색으로 확인)**:
1. **포트폴리오 레코드에 건물 스냅샷이 없다.** `PortfolioRecord`(portfolio/schema.py)는 `score_before`/`eal_before` 숫자만 저장하고, 구조·층수·연식·용도는 `scripts/generate_portfolio.py`가 `score_before` 추출 후 버린다. "건축물 데이터가 바뀌었다"를 사후에 재구성할 근거 자체가 저장소 어디에도 없다.
2. **`eal_before`는 2026-08에 생성됐다.** 힌남노(2022-09)에서 EAL 알림이 켜진 것(COL-003 +48.8%, COL-004 +49.6%, `audit/alert_queue_log.jsonl`)은 2022년 피해를 반영할 수 없고, 생성 이후 건축HUB 응답이 달라진 드리프트다. 같은 로그의 COL-001은 취약도 63.4→27.6(EAL −81%)으로 오히려 하락 — 피해 방향도 아니다.
3. 현재 EAL 알림이 켜진 사건은 힌남노 1건뿐. 대구 수성구 2026-07(침수신고 100건+)·거제 2026-08(특별재난지역, 잠정 피해액 270억)은 0건.
4. 독립적인 피해 확인 근거는 이미 있다: 실측 침수흔적 `A2SM_FLUDMARKS_WI` 80건(포항 남구 62건=힌남노, 단 `flud_year` 연 단위 필드뿐이고 2026 데이터 없음), 큐레이션 뉴스 타임라인 2건(source_url 필수), 거제 특별재난지역 선포 보도(2026-08-31 항목의 URL 4개).
5. 후보 파라미터 재료는 전부 이미 파싱돼 `AdvisoryEvent` 한 타입에 담긴다: 특보 종류(`WRN_CODE_LABELS` 13종)·등급(예비/주의보/경보/중대경보)·명령(발표/변경/해제…), 재난문자 긴급단계(안전안내/긴급재난/위급재난)·재해유형(`RELEVANT_DST_SE_NM` 10종)·본문 200자·수신지역(동 단위)·발송시각. 강수량 관측(AWS/ASOS)·하천 수위는 코드·키·활용신청 전부 없음. KMA 특보자료 API의 `GRD`/`CNT`/`TM_IN` 필드는 응답에 있지만 현재 버린다(`kma_historical._parse_wrn_met_data`).

**질문 1(사용자) — 정답 열을 "건축물 변화만"으로 둘 때와 둘 다 둘 때 결과가 어떻게 달라지는지 짐작해달라**: (측정 전 짐작, 실측은 하네스 결과 항목 참조)

| 사건 | 건축물 변화 라벨 | 독립 근거 라벨 |
|---|---|---|
| 힌남노 2022-09 포항 남구 | 양성 | 양성 |
| 대구 수성구 2026-07-17 | 음성 | 양성 |
| 거제 2026-08-17 | 음성 | 양성 |
| 대구 2026-08-19 폭염주의보 등 라이브 로그 특보 | 음성 | 음성 |
| 기상청 이력 API 과거 경보 수십 건 | 음성 | 음성 또는 미확인 |

| 후보 | 독립 근거 기준 | 건축물 변화 기준 |
|---|---|---|
| 현행 트리거(특보·재난문자 아무거나) | TP 3, FP 전부 | TP 1, FP 전부 |
| 현행 심각도 채널(경보·긴급재난 이상) | TP 3, FP=폭염·강풍경보 | TP 1, 수성구·거제가 FP로 집계 |
| 수문 특보만(호우·태풍·홍수·폭풍해일 경보) | TP 3, FN 0, FP 소수 | TP 1, FP 2+ |
| 태풍 특보만 | TP 1, **FN 2(수성구·거제 누락)** | TP 1, FP 0 → **최적으로 뽑힘** |

결론: 건축물 변화 라벨만 쓰면 양성이 1건이라 recall에 단계가 없고, 진짜 재해 2건이 오탐으로 계산돼 후보 선정이 뒤집힌다("태풍 특보만"이 최적으로 뽑혀 270억 피해 거제를 놓침). 둘 다 열로 두면 이 뒤집힘이 표에서 드러나므로 건축물 열은 **병기용**으로 남기되, **후보 선정은 독립 근거 열로만** 한다.

**질문 2(사용자) — "후보를 여러 개 만들어 하나씩 검증하며 정답과 가장 비슷한 것으로 추린다"에 대한 의견**: 방향은 맞고 조건 3개를 붙인다. ①양성이 3건뿐이라 "가장 비슷한 후보"는 과적합된다 — 음성 표본을 크게(기상청 API허브 이력 2004~로 7개 지역 과거 경보 에피소드 수십 건) 확보해 후보 간 차이는 FP 축에서 가르고, recall은 3건 전부 잡는지로만 본다. ②후보와 임계값은 결과를 보기 전에 목록으로 고정한다(2026-08-12 항목의 방법론과 동일) — 결과가 지저분해도 그대로 기록. ③하나씩 손으로 돌리지 않고 후보를 순수 함수로 등록해 사건×후보 전체를 한 표에서 일괄 계산한다(검토는 하나씩, 계산은 일괄). 추가 지표로 "지역당 연간 알림 횟수"(알림 피로 프록시, HANDOVER 멘토 피드백 "오탐·과다경보로 심사역이 외면할 리스크")를 같이 본다.

**사용자 결정(2026-09-03)**: 정답 라벨은 **독립 근거로 선정, 건축물(현행 EAL 알림) 열은 병기**. 후보 범위는 **기존 데이터만 먼저** — 강수량 관측 API(API허브 지상관측 활용신청 필요)는 별도 단계로 분리.

**영향**: 평가 전용 하네스(`evaluation/alert_validation.py`·`evaluation/trigger_candidates.py`·`metrics.py::alert_trigger_precision_metric`·`scripts/fetch_alert_validation_cache.py`·`scripts/run_alert_validation.py`)를 구현한다 — `portfolio/alerts.py`·`severity_alerts.py`·`scenario/eal.py`·`portfolio_agent.py`·`advisory_agent.py`는 손대지 않는다. 검증 결과를 보고 어떤 후보를 프로덕션 트리거로 채택할지는 다음 단계에서 사용자가 결정한다. PM은 (1) HANDOVER §4.4 "알림 정밀도" 지표의 골든셋 정의를 "실측 침수흔적 지점"에서 "출처 명시 피해 확인 사건(지역×기간) + 참고용 현행 EAL 알림 열"로 갱신할지, (2) §4.6 항목7의 "임계치 캘리브레이션"을 이 하네스 결과에 연결할지 판단 필요. 상세 설계는 `C:\Users\eujin\.claude\plans\snappy-wiggling-moonbeam.md`.

## 2026-09-03(계속) — 트리거 후보 4분면 검증: 후보 7개·상수·클러스터링 규칙·라벨 정책 **사전 등록**(첫 실행 전 고정)

**계획**: 위 항목의 사용자 결정에 따라 하네스 구현 착수. 2026-08-12 항목의 방법론("임계치는 날짜를 보기 전에 먼저 확정, 결과가 깔끔하지 않아도 정직하게 제시")을 그대로 적용해, **검증 결과를 단 한 번도 보기 전에** 후보 목록과 모든 상수를 여기 고정한다. 이후 후보를 추가하려면 이 항목을 고치지 말고 날짜를 붙여 뒤에 append한다.

**후보(`evaluation/trigger_candidates.py`, 전부 `list[AdvisoryEvent] -> bool` 순수 함수)**:
| id | 규칙 | 재난문자 의존 |
|---|---|---|
| C0_any_advisory | 현행 `trigger_event`: event_type ∈ {특보, 재난문자} 1건 이상 | 아니오 |
| C1_high_severity_any | 현행 심각도 채널: `is_high_severity_event` 1건 이상(경보·중대경보·긴급재난·위급재난) | 아니오 |
| C2_hydro_high_severity | 특보: warning_type에 호우/태풍/홍수/폭풍해일 ∧ 등급 ∈ {경보, 중대경보}; 또는 재난문자: 재해유형 ∈ {호우, 홍수, 태풍} ∧ 단계 ∈ {긴급재난, 위급재난} | 아니오 |
| C3_disaster_msg_damage_keyword | 재난문자 본문에 침수/범람/대피/역류 | 예 |
| C4_disaster_msg_burst | `RELEVANT_DST_SE_NM` 재난문자 ≥3건이 어떤 24h 슬라이딩 창 안 | 예 |
| C5_warning_level_physical | 경보 이상 특보 중 폭염/한파/황사/건조/열대야/안개 제외(강풍·풍랑·대설은 포함) | 아니오 |
| C6_hydro_high_severity_or_burst | C2 ∨ C4 (유일한 결합 후보 — 두 소스가 독립) | 예 |

후보 선정 기준은 "물리적으로 담보 침수와 연결되는 관측 원자료인가"이지 "양성 3건을 맞히는가"가 아니다. 강수량 관측치는 사용자 결정대로 이번 목록에 없다.

**에피소드 클러스터링(`evaluation/alert_validation.py`, 음성 표본 마이닝용)**: 기상청 API허브 특보 이력을 zone group(포항 47111 / 거제 48310 / 대구 5개구 통합 "daegu" — 특보구역이 하나라 5중 집계 방지) 단위로 2004-07-01부터 조회해 `tm_ef` 정렬 후 인접 간격 >48h면 새 에피소드. 창 = 첫 발효일 −1일 ~ 마지막 발효일 +1일. peak 등급은 발표/대치/연장/변경(cmd 1·2·5·6) 행만으로 산정(해제 계열 제외). 만료 sentinel(연도≥2100) 행 제외.

**라벨 정책(`labeled_events.json`)**: `damage_confirmed`는 true/false/"unknown". true/false는 독립 근거(실측 침수흔적·뉴스·특별재난지역 선포) evidence ≥1건 + source_url(http) 필수, "unknown"은 label_note 필수. 연 단위뿐인 침수흔적(`flud_year`)은 그 지역·연도에 호우/태풍/폭풍해일 경보 에피소드가 **정확히 1개**일 때만 true 근거로 인정, 아니면 unknown. `eal_alert_fired`(현행 EAL 알림)는 참고 열 — 후보 함수 시그니처에 들어갈 통로가 없다.

**지표(`metrics.py::alert_trigger_precision_metric`)**: 사건×후보 4분면(TP/FN/TN/FP, unknown은 별도 집계), precision/recall(분모 0이면 None), 알림 피로 프록시 = 전체 KMA 에피소드(2005-01-01~캐시 종료일)에 후보를 적용한 "zone group당 연간 알림 횟수" — 에피소드 타임라인엔 재난문자가 없어 재난문자 의존 후보(C3·C4·C6)는 **하한**. `eal_alert_reference`는 같은 산술을 참고 열에 적용한 것으로 후보가 아니다.

**영향**: 코드·데이터 파일 신규 추가만(프로덕션 트리거 경로 무변경). 결과는 다음 항목에 표 그대로 기록한다.

## 2026-09-03(계속2) — 트리거 후보 4분면 검증 **첫 실행 결과** — 수문 특보 경보 이상(C2)이 recall 1.0·오탐 최소·알림 피로 최저, 현행 심각도 채널(C1)은 폭염·강풍 경보로 오탐 4배

**계획**: 위 사전 등록 항목의 후보 7개·규칙을 그대로 두고, 라벨 사건 23건에 대입했다. 사전 등록 후 결과를 보기 전까지 후보·상수는 손대지 않았고, 라벨 정책만 한 항목 추가했다(아래 "음성 라벨 규칙" — 이것도 표를 보기 전에 확정).

**데이터(전부 `data/.../curated/alert_validation/`, gitignore 대상 — 재현은 `scripts/fetch_alert_validation_cache.py` 재실행)**:
- KMA 특보 이력 캐시(2026-09-03 15:36 fetch): 포항 2,338행·거제 2,390행·대구 1,572행(각 2004-07~2026-09-03, 연 단위 chunk 23~24개). 2004·2005년 chunk는 `NO_ZONE_MATCH`(특보구역 유효기간이 2006년부터) — 캐시 경고 6건으로 노출, 데이터 손실 아님. 대구 2026-05-31 구역 개편은 chunk 분할로 처리됨(구 L1070100→신 L1140100 행 모두 확보).
- 재난문자 캐시: 샌드박스(Bash) 경로는 IP 미등록이라 PowerShell(호스트) 경로로 조회 — 23건 전부 `OK`. **단 재난문자 API의 실제 데이터는 2024-07-09부터만 존재**(가장 이른 레코드) — 2022 힌남노·2019 미탁·2020 마이삭 등엔 재난문자가 0건이라, 재난문자 의존 후보(C3·C4·C6)의 FN은 신호 실패가 아니라 데이터 부재다.
- 라벨 사건 23건: 양성 8·음성 7·unknown 8. 큐레이션 3건(힌남노·수성구·거제 2026) + 라이브 로그 폭염 3건 + KMA 마이닝 경보 에피소드 17건(2015년 이후 수문·강풍 경보 에피소드 중 뉴스 검색 가능한 것). 라벨링은 이 세션(구현자)이 웹 검색으로 했고 근거 URL을 전부 기록 — **사용자 검토 필요**(특히 나무위키·위키백과만 근거인 힌남노 대구·카눈 거제 2건, 규칙(b)로 음성 처리한 폭염·강풍 5건).
- 음성 라벨 규칙(표 보기 전 확정, 라벨 파일 `label_policy`에 기재): (a) 에피소드 보도가 있으나 건물 침수 언급 없이 강풍·농작물·대피만 보도 → 그 기사 근거로 false. (b) 창 안에 강수성 특보가 전혀 없고(폭염·강풍만) 뉴스 검색(검색일 명시)에 침수 보도 없음 → 기상청 기록 URL 근거로 false. 둘 다 아니면 unknown. "피해 미확인"이지 "피해 없음 증명"이 아님을 정책에 명시.

**결과(`python scripts/run_alert_validation.py`, 2026-09-03)**:

| 후보 | TP | FN | TN | FP | unk발화 | unk침묵 | precision | recall | 알림/zone·년(2005~) |
|---|---|---|---|---|---|---|---|---|---|
| C0 현행 트리거(특보·재난문자 아무거나) | 8 | 0 | 0 | 7 | 8 | 0 | 0.53 | 1.00 | **34.04** |
| C1 현행 심각도 채널(경보·긴급재난 이상) | 8 | 0 | 3 | 4 | 8 | 0 | 0.67 | 1.00 | 6.43 |
| **C2 수문 특보 경보 이상 ∨ 수문 재난문자 긴급재난** | 8 | 0 | 5 | 2 | 8 | 0 | **0.80** | **1.00** | **1.78** |
| C3 재난문자 본문 피해 키워드 | 5 | 3 | 6 | 1 | 1 | 7 | 0.83 | 0.62 | 0.00(하한) |
| C4 재난문자 24h 3건 이상 | 4 | 4 | 7 | 0 | 1 | 7 | 1.00 | 0.50 | 0.00(하한) |
| C5 경보 이상(비물리 제외, 강풍·풍랑·대설 포함) | 8 | 0 | 3 | 4 | 8 | 0 | 0.67 | 1.00 | 2.17 |
| C6 C2 ∨ C4 | 8 | 0 | 5 | 2 | 8 | 0 | 0.80 | 1.00 | 1.78(하한) |
| (참고) 현행 EAL 알림 | 1 | 2 | 0 | 0 | – | – | 1.00 | 0.33 | – (미기록 20건) |

사건별 발화(X) 매트릭스 요약:
- **양성 8건 전부** C1·C2·C5가 잡았다(힌남노 태풍경보 09-06 00:00, 수성구 호우경보 07-17 21:50, 거제 호우경보 08-16/17, 미탁 태풍·호우경보, 마이삭 태풍경보, 2024-07 거제·대구 호우경보, 힌남노 대구 태풍경보).
- C2의 FP 2건은 둘 다 **태풍경보는 났지만 건물 침수는 없었던 사건**(난마돌 2022-09 포항, 카눈 2023-08 거제). 태풍경보 자체가 침수 실현 여부를 못 가른다 — 강수량 관측치(사용자 결정으로 이번 범위 밖)가 필요한 지점.
- C1·C5의 추가 FP 2건은 강풍경보 단독 에피소드(포항 2020-03, 거제 2025-04). 라이브 로그의 폭염 3건은 KMA 이력(대구중부 L1140100·거제 L1082200)에서는 주의보 행만 있어 C1도 침묵(TN) — 라이브 로그의 "폭염경보 변경"(stnId=143 피드)과 이력 API의 구역별 행이 일치하지 않는 사례로, 라벨 note에 기록. 그래도 전체 이력 2,213개 에피소드 기준으로는 C1이 폭염·강풍 경보마다 켜져 알림 피로 지표가 C2의 약 3.6배(6.43 vs 1.78).
- C3·C4는 재난문자가 존재하는 2024-07 이후 양성 4건(수성구·거제 2026, 거제·대구 2024-07)은 4/4 잡았고, 그 이전 사건은 데이터 부재로 전부 FN. C3의 FP 1건은 거제 2026-08-31 폭염 창에 낀 호우 안전안내 문자("침수 우려" 예보성 문구) — 키워드가 예보와 관측을 구분 못 한다.
- 현행 EAL 알림(참고 열)은 기록된 3건 중 힌남노 1건만 양성 — 건축HUB 드리프트 우연(DEV_LOG 2026-08-31)이라 recall 0.33도 실질적으로는 0에 가깝다.
- unknown 8건(콩레이·차바·하이선 포항, 힌남노·미탁 거제, 2023-07 포항·대구, 2025-07 대구)은 전부 수문 경보 에피소드라 C1·C2·C5가 발화한다 — 이 8건이 실제로는 음성이었다면 C2 precision은 0.80→0.44까지 떨어질 수 있다. 라벨 보강이 다음 정확도 향상 지점.

**해석(후보 채택은 사용자 결정 사항, 여기선 수치 사실만)**: 사전 등록 기준("물리적으로 침수와 연결되는 원자료")에 가장 부합하는 C2가 양성 전부를 잡으면서 알림 빈도를 현행 심각도 채널의 약 28%(1.78/6.43)로 줄인다. 남은 오탐은 "경보 등급"이 강수량·수위 실현을 대리하지 못하는 구조적 한계로, 후보 규칙을 더 조여서 해결되는 게 아니라 강수량 관측 소스(API허브 지상관측, 활용신청 필요)를 다음 단계에서 붙여야 줄어든다. 재난문자 계열(C3·C4)은 데이터가 있는 구간에선 정밀도가 높으나 2024-07 이전 이력이 없어 단독 트리거로는 부적합, C2와의 결합(C6)이 현재 데이터로는 C2와 동일.

**구현**: `evaluation/alert_validation.py`(라벨셋·캐시 로더·48h 에피소드 클러스터링)·`evaluation/trigger_candidates.py`(사전 등록 후보 7개)·`metrics.py::alert_trigger_precision_metric`(HANDOVER §4.4 "알림 정밀도" 첫 구현)·`scripts/fetch_alert_validation_cache.py`(라이브, 유일한 네트워크 지점)·`scripts/run_alert_validation.py`(오프라인, `--emit-episode-skeleton`으로 라벨링 스텁)·`scripts/run_eval_dashboard.py --alert-validation`·`config.ALERT_VALIDATION_DIR`·`tests/test_alert_validation.py`(23개: 사전 등록 동결·후보 순수 로직·클러스터링·라벨 계약·오프라인 지표 불변식 — 수치는 assert 안 함). `KMA_API_HUB_KEY`/`SAFETYDATA_DISASTER_MSG_API_KEY`를 비운 채 실행해 오프라인 동작 확인. 레드팀 5종 전부 PASS(프로덕션 트리거 경로 무변경 — `run_scenario_agent` 시그니처 그대로). `pytest tests/ -q` **280개 전부 통과**(기존 258 + 신규 22, 244초).

**영향**: (1) 사용자가 라벨 23건(특히 위 검토 필요 7건)을 검토한 뒤 C2 채택 여부를 결정한다 — 채택 시 `portfolio/severity_alerts.py`의 `is_high_severity_event` 허용목록을 C2 규칙으로 바꾸는 건 별도 작업(이번엔 안 함). (2) 강수량 관측 API(기상청 API허브 지상관측) 활용신청 후 C7 이후 후보를 **append**로 추가(사전 등록 규율 유지). (3) unknown 8건의 라벨 보강(지역 뉴스 아카이브·재해연보)이 precision 신뢰도를 가장 크게 올린다. (4) PM은 HANDOVER §4.4 "알림 정밀도" 지표 정의를 이 하네스(사건 단위 4분면 + 알림 피로)로 갱신할지 판단. (5) 재난문자 API 이력이 2024-07부터라는 사실은 §② 데이터 표에 추가할 만한 제약.

## 2026-09-03(계속3) — 3단계 분리 검증 프로토콜 + 기본 피쳐(atom) 11개·2개 조합 **사전 등록** — 건축물 변경 라벨은 제외 확정

**계획**: 사용자 결정(2026-09-03): ①"건축물 데이터 변경" 라벨은 제외(스냅샷 부재·대장이 피해를 기록하지 않음, 앞 항목 참조). ②피쳐를 하나씩이 아니라 2개 이상 조합했을 때 정확도·오탐이 개선되면 그것도 후보로. ③사건 단위 3단계 분리 — **1단계** 힌남노(포항 2022-09)로 피쳐 선정 → **2단계** 다른 홍수·태풍·호우 사건으로 오탐 없이 알림이 가는지 검증 → **3단계** 거제 2026-08 호우로 최종 테스트 — 를 먼저 일관되게 성립하는지 확인. 담보 단위 분리(2안)는 설명 후 보류.

**프로토콜(`metrics.py::staged_alert_validation_metric`)**: 1단계 = 앵커(힌남노)가 켜져야 하고, 같은 zone group·같은 해(포항 2022)의 다른 라벨 사건에서 FP 0(현재 라벨 음성은 난마돌 1건), 같은 해 라벨 없는 에피소드 45개에서 켜진 횟수는 알림 피로로 병기. 2단계 = 앵커·1단계·홀드아웃을 뺀 라벨 사건 전부(양성 6·음성 6·unknown 8 예상)에서 FN 0, FP 기록. 3단계 = 거제 2026-08 홀드아웃이 켜지는지. 통과 = 세 단계 전부. 정렬 = 통과 → 2단계 FP → unknown 발화 → 전체 이력 알림 피로.

**기본 피쳐 11개(`evaluation/trigger_features.py`)**: A1 특보 경보 이상(종류 무관) · A2 수문 특보 경보 이상 · A3 수문 특보 주의보 이상 · A4 폭풍해일 특보(주의보 이상) · A5 태풍 경보 이상 · A6 호우 경보 이상 · A7 수문 경보 지속 ≥12h · A8 수문 특보 종류 ≥2(주의보 이상) · A9 수문 재난문자 긴급재난 이상 · A10 재난문자 본문 피해 키워드 · A11 재난문자 24h 내 3건 이상. 조합 = atom 2개의 AND/OR 전부 55쌍×2 = 110개(3개 이상 조합은 안 만듦 — 양성이 한 자리 수라 조합이 늘수록 우연히 맞는 후보가 반드시 생김). 기존 C0~C6도 같은 표에 넣는다.

**정직하게 남기는 사전 등록의 한계**: 이 atom들은 C0~C6 첫 결과표를 본 뒤에 정의됐다. 특히 A4(폭풍해일)는 힌남노·난마돌 타임라인을 직접 대조해(둘 다 태풍경보 12~15h, 폭풍해일 주의보만 힌남노에 있음) 넣은 것이라 **1단계는 사실상 사후 정의**다. 실질적 검증은 2단계(다른 지역·다른 해)와 3단계(거제 2026)뿐이며, 1단계 통과 자체를 근거로 삼지 않는다. 또 포항 2022 에피소드 47개 중 수문 경보는 힌남노·난마돌 둘뿐이라 특보 등급·종류·지속시간만으로는 둘을 못 가른다는 게 이미 확인된 상태 — 폭풍해일 없이 1단계를 통과하는 특보 피쳐는 없을 것으로 예상하며, 결과가 그렇게 나오면 그대로 기록한다.

**영향**: 코드 추가만(`trigger_features.py` 신규, `metrics.py`·`scripts/run_alert_validation.py --staged --combos` 확장, 테스트). 프로덕션 무변경. 결과는 다음 항목.

## 2026-09-03(계속4) — 3단계 분리 검증 결과: **128개 후보 중 3단계 전부 통과 0개** — 태풍경보 단독 사건의 침수 여부는 특보·재난문자 필드로 갈라지지 않음

**계획**: 위 사전 등록 프로토콜 그대로 실행(`python scripts/run_alert_validation.py --staged --combos`). 피쳐는 정형 API 원자료(기상청 특보 이력·재난문자)만 사용(`exclude_news_derived=True`) — 큐레이션(뉴스) 이벤트는 라벨에만 쓰고 타임라인에서 뺐다. 실행 전 수정 2건: ①지속시간(A7) 계산이 "예비특보" 행을 종료로 오인해 난마돌 태풍경보를 15h가 아닌 9h로 세던 것 수정(예비 행 제외). ②힌남노 타임라인에 뉴스 기반 큐레이션 재난문자가 섞여 C3/A10이 켜지던 것을 위 뉴스 제외로 차단.

**단계 구성**: 1단계 = 힌남노(앵커) + 포항 2022 라벨 사건(난마돌 1건, 음성) + 포항 2022 미라벨 에피소드 45개(알림 피로). 2단계 = 나머지 라벨 사건 20건(양성 6·음성 6·unknown 8). 3단계 = 거제 2026-08 홀드아웃. 후보 = C0~C6(7) + atom 11 + 2개 조합 110 = 128.

**결과**:
| 단계 | 통과 후보 수 | 통과한 것들의 공통점 |
|---|---|---|
| 1단계(힌남노 켜짐 ∧ 난마돌 안 켜짐) | 22 | 전부 A4(폭풍해일) 또는 A8(수문 종류≥2)을 포함 — 힌남노에만 있는 폭풍해일 주의보가 유일한 구분자 |
| 2단계(양성 6건 FN 0) | 42 | 전부 A1·A2·A3(경보/수문 특보) 계열 — 폭풍해일·복수 종류 없는 내륙 호우 사건까지 잡으려면 이쪽이어야 함 |
| 3단계(거제 2026 켜짐) | 95 | 호우경보 25h + 재난문자 58건이라 대부분 켜짐 |
| **1∩2∩3** | **0** | — |

가장 가까운 후보들(2/3 통과):
- `A2`(=C2, 수문 특보 경보 이상): 2·3단계 통과, 2단계 FP 1(카눈), 알림 1.78/zone·년. 1단계 실패 — 난마돌(태풍경보 15h, 침수 없음)에서 켜짐.
- `A4|A6`(폭풍해일 ∨ 호우경보): 1·3단계 통과, 2단계 FP 0이지만 FN 2 — 마이삭 거제 2020(태풍경보 13h, 사등면 10여 가구 침수)·힌남노 대구(태풍경보 12h, 지하주차장 침수)를 놓침.
- `A5|A11`(태풍경보 ∨ 재난문자 폭주): 2·3단계 통과, 알림 0.71/zone·년(하한)으로 가장 조용하지만 1단계 실패(난마돌).

**핵심 발견 — 태풍경보 단독 4건이 특보 필드로 동일하다**: 양성 마이삭 거제(태풍경보 13h)·힌남노 대구(12h) vs 음성 난마돌 포항(15h)·카눈 거제(17.5h). 네 사건 모두 "태풍경보 + 강풍/호우 주의보"뿐이고 등급·종류·지속시간·명령 어느 필드로도 갈라지지 않는다. 실제 차이는 강수량(힌남노 포항 시간당 110mm vs 난마돌 포항 강수 미미)이며 이건 특보 원자료에 없다. 재난문자는 2024-07 이후에만 있어 2022·2020 사건엔 쓸 수 없다. 즉 **"힌남노로 고른 피쳐가 다른 태풍 사건에서도 오탐 없이 맞는다"는 명제는 현재 원자료로는 성립하지 않는다** — 사전 등록 항목에서 예상한 대로 결과가 나왔고 그대로 기록한다.

**조합의 효과**: 2개 조합이 단일 피쳐보다 나아진 지점은 두 곳뿐. ①OR로 폭풍해일을 붙이면(`A4|A6`) 2단계 FP가 1→0으로 줄지만 FN이 2 생김(정밀도↔재현율 교환일 뿐 정보가 늘지 않음). ②`A5|A11`은 알림 빈도를 1.78→0.71로 줄이지만 재난문자 의존이라 2024-07 이전엔 하한. AND 조합은 전부 FN을 늘리기만 했다. 3개 이상 조합은 사전 등록대로 만들지 않았다.

**해석(채택은 사용자 결정)**: 특보·재난문자 필드만으로는 "언제 알림을 낼지"의 후보로 C2(=A2)가 여전히 최선이지만, 1단계(같은 지역·같은 해 태풍 사건 간 구분)를 통과하는 피쳐는 없다. 강수량 관측(기상청 API허브 지상관측 ASOS/AWS 시간강수, 활용신청 필요)이 다음 피쳐 후보이며, 그때 A12 이후로 append한다. 태풍경보 단독 4건(마이삭·힌남노 대구·난마돌·카눈)이 그 피쳐의 1차 판별 테스트셋이 된다.

**구현**: `evaluation/trigger_features.py`(atom 11·조합 110), `metrics.py::staged_alert_validation_metric`(단계 분할·통과 판정·정렬: 통과 단계 수→2단계 FN→FP→unknown 발화→알림 피로), `scripts/run_alert_validation.py --staged --combos --top N --anchor --holdout`. 테스트 5개 추가(`tests/test_alert_validation.py`, 총 27개: atom·조합 동결·AND/OR 의미·A7 지속시간·단계 분할 불변식). 프로덕션 무변경. `pytest tests/ -q` 전체 285개 통과.

## 2026-09-03(계속5) — 기상청 API허브 지상관측 API 3종 활용신청 승인·실호출 확인 — 강수량이 힌남노/난마돌은 가르지만 마이삭/카눈은 못 가름

**계획**: 위 (계속4) 결론에 따라 사용자가 API허브에서 ①종관기상관측(ASOS) 시간자료 기간조회 `kma_sfctm3.php` ②방재기상관측(AWS) 시간통계 `awsh.php` ④AWS 일통계 `sfc_aws_day.php` 활용신청(2026-09-03 승인). ③ASOS 시점조회 `kma_sfctm2.php`는 보류.

**실호출 확인(2026-09-03, `KMA_API_HUB_KEY`, 전부 HTTP 200·EUC-KR)**:
1. `kma_sfctm3.php?tm1&tm2&stn&help=1`: 컬럼 41개 문서화됨. 강수는 `RN`(강수량 mm — **4~10월은 1시간, 11~3월은 3시간 강수량이며 3·6·…·24시 외엔 결측 표출**), `RN_DAY`(해당 시각까지 일강수 누적, 통계표), `RN_JUN`(같은 값의 전문 입력본), `RN_INT`(강수강도, "관측하는 곳이 별로 없음"). 결측은 `-9`. `tm1==tm2`로 단일 시각 조회가 되므로 **③은 불필요**. 이력은 1904년부터(문서) — 라벨 사건 전부 커버.
2. `awsh.php?var=RN&tm&stn`: `RN_HR1`·`RN_DAY`·`RN_60M_MAX`·`RN_15M_MAX`와 각각의 시간차(`_MI`)·자료수(`_QCM`), `RE_SUM`(60분 중 강수있음 분수 합). **`tm1`/`tm2`를 넘겨도 무시되고 항상 최근 30일(721행)이 돌아온다**(문서엔 없음, 실측) — 과거 특정 시각은 `tm` 단일 조회를 시간마다 반복해야 함. 결측 `-99`.
3. `sfc_aws_day.php?obs=rn_day&tm1&tm2&stn=0`: 전국 714지점의 `TM STN LON LAT HT VAL` + 문서에 없는 7번째 토큰(지점명). 위경도가 있어 **관측소↔우리 지역 매핑의 진실의 원천**으로 쓸 수 있다.

**관측소 매핑(골든 좌표 기준 haversine)**: 포항 남구 인덕동 ← AWS 995 오천 1.0km, ASOS 138 포항 12.3km. 대구 봉덕동 ← AWS 860 신암 5.8km, ASOS 143 대구 6.5km(845 대구북구·846 대구서구 8km대, 수성구 지산동 AWS는 목록에 없음). 거제 고현 ← AWS 313 양지암 3.6km, ASOS 294 거제 9.3km. **AWS 995 오천은 2019·2022년 시각 조회 시 "입력하신 지점번호가 없습니다"** — 지점 존재 기간이 지점마다 달라 과거 사건엔 ASOS로 후퇴해야 함(지점별 개시일은 미확인).

**핵심 사건 실측(ASOS, 최대 1시간 강수 / 최대 일강수 mm)**:
| 사건 | 라벨 | stn | 최대 1h | 일강수 |
|---|---|---|---|---|
| 힌남노 포항 2022-09-06 | 양성 | 138 | **77.0**(05시) | 342.4 |
| 난마돌 포항 2022-09-19 | 음성 | 138 | 6.0 | 36.7 |
| 미탁 포항 2019-10-02 | 양성 | 138 | 38.7 | 309.2 |
| 하이선 포항 2020-09-07 | unknown | 138 | 22.6 | 103.4 |
| 콩레이 포항 2018-10-06 | unknown | 138 | 25.9 | 179.4 |
| 차바 포항 2016-10-05 | unknown | 138 | 45.3 | 155.3 |
| 수성구 호우 대구 2026-07-17 | 양성 | 143 | 33.9 | 116.6 (지산동 실제 89mm/h — ASOS는 6.5km 밖) |
| 힌남노 대구 2022-09-06 | 양성 | 143 | 15.6 | 81.1 |
| 대구 2024-07-09 | 양성 | 143 | 44.4 | 190.8 |
| 마이삭 거제 2020-09-03 | 양성 | 294 | 40.7 | 85.3 |
| 카눈 거제 2023-08-10 | 음성 | 294 | 39.4 | 162.1 |
| 미탁 거제 2019-10-02 | unknown | 294 | 59.5 | 168.0 |
| 거제 2024-07-14 | 양성 | 294 | 38.5 | 147.6 |
| 힌남노 거제 2022-09-06 | unknown | 294 | 40.3 | 144.0 |
| 거제 2026-08-17 | 양성(홀드아웃) | 294 | **116.8**(03시) | 654.3 |
AWS 양지암(313) 단일 시각: 카눈 08-10 12:00 RN_DAY 111.5·60분최대 23.0 / 마이삭 09-03 03:00 RN_DAY 18.5·60분최대 7.0 / 2026-08-17 06:00 RN_DAY 361.5·60분최대 69.0.

**해석**: 강수량은 (계속4)의 태풍경보 단독 4건 중 **힌남노(77mm/h)·난마돌(6mm/h)은 확실히 가르지만, 마이삭 거제(40.7, 양성)·카눈 거제(39.4, 음성)는 못 가른다** — 양지암 AWS로는 카눈이 오히려 더 많이 왔다. 마이삭의 사등면 들막마을 침수(해안 마을)는 강우보다 폭풍해일·강풍 쪽 메커니즘일 가능성이 있어, 강수량 피쳐만으로 오탐 2건이 0이 되지는 않는다. 또 힌남노 대구(15.6mm/h·81mm, 양성)처럼 낮은 강수에서도 지하주차장 침수가 났으므로, 임계값을 낮추면 카눈이 들어오고 높이면 힌남노 대구·마이삭을 놓친다 — 임계값 후보(예: 1h≥30 / 일≥100)는 사전 등록 후 라벨 23건 전체로 재야 한다(아직 안 함).

**정직하게 모르는 것**: ASOS `PT`·`WC`·`WP`·`WW`·`ST_GD` 코드 의미("관측정책과 문의"), `RN_DAY`와 `RN_JUN`이 다를 때 어느 쪽이 정본인지, 겨울철 3시간 강수 표출 규칙의 정확한 경계, `awsh` 값이 QC 완료본인지, `_QCM`이 60 미만일 때 값 신뢰도, AWS 지점별 관측 개시일, `sfc_aws_day`의 714지점 중 ASOS/AWS 구분 기준(번호 <300이 ASOS로 보이나 미확인), 일통계의 집계 경계(00~24 KST 추정).

**영향**: 코드 변경 없음(조사 항목). 다음 단계 착수 시: `advisory/kma_observation.py`(신규, ASOS 기간조회 + AWS 단일시각 반복 조회 + 관측소 매핑 상수) → 강수 피쳐 A12~(1h·일강수 임계값, ASOS/AWS 각각) 사전 등록 → 라벨 사건 캐시에 강수 시계열 추가 → 3단계 재실행. 심각도 채널 규칙 변경은 그 뒤 사용자 결정.

## 2026-09-03(계속6) — 강수 관측 피쳐 A12~A17 **사전 등록** + 관측 모듈·캐시 설계 (재실행 전 고정)

**계획**: 사용자 결정 "API로 추가한 데이터를 피쳐로 넣어 같은 3단계 검증을 다시 돌린다". (계속5)에서 실측값 몇 개(힌남노 77·난마돌 6·마이삭 41·카눈 39·힌남노 대구 16 mm/h)를 이미 봤으므로 이 임계값들은 완전한 사전 등록이 아니다 — 그래서 임계값은 실측 표가 아니라 **기상청 기준**(극한호우 재난문자 1시간 50mm, 호우경보 12시간 180mm 등)에서 따온 값으로 잡고, 두 단계씩 두어 "어느 쪽이 맞는지"를 표가 말하게 한다.

**피쳐(`evaluation/trigger_features.py`, `requires_rainfall=True`)**: A12 ASOS 1시간 ≥30mm · A13 ASOS 1시간 ≥50mm · A14 ASOS 일강수 ≥100mm · A15 ASOS 일강수 ≥150mm · A16 최근접 AWS 60분 최대 ≥30mm · A17 최근접 AWS 일강수 ≥100mm. atom 17개 → 2개 조합 272개, 기존 C0~C6 포함 총 296개 후보.

**데이터(`advisory/kma_observation.py` 신규, 캐시 `alert_validation/rainfall/{event_id}.json`)**: 사건 창마다 ①ASOS 시간자료(`kma_sfctm3`, 지역 ASOS 1곳: 포항 138·대구 143·거제 294) ②최근접 AWS 일통계(`sfc_aws_day`, 오천 995·신암 860·양지암 313) ③최근접 AWS 시간통계(`awsh`, ASOS 최대강수 시각 ±3시간 7회 단일조회 — 기간 파라미터가 무시되는 실측 한계 때문). 관측값은 `event_type="강수관측"`·`event_id="obs-…"`·`description="RN_1H=77.0;RN_DAY=342.4"` 고정 포맷의 AdvisoryEvent로 타임라인에 병합해 후보 함수 계약(`list[AdvisoryEvent] -> bool`)을 유지한다. 결측은 `NA`로 두고 0으로 바꾸지 않는다. **알림 피로 지표는 강수 의존 후보에 대해 계산하지 않는다**(전체 KMA 에피소드 2,213개에 강수 캐시가 없음 — `fatigue_not_computed=True`).

**알려진 한계(결과 해석 시 감안)**: ASOS `RN`은 11~3월 3시간값(겨울 사건은 일강수만 유효). AWS 오천(995)은 2019·2022년에 지점이 없어 포항 과거 사건의 A16·A17은 결측→False. 수성구 지산동엔 AWS가 없어 대구는 신암(5.8km)·ASOS 대구(6.5km)로 대신한다(2026-07 지산동 89mm/h가 ASOS엔 33.9로 잡힘).

**영향**: 코드 추가만. 프로덕션 무변경. 결과는 다음 항목에 강수 추가 전(계속4)과 나란히 기록한다.

## 2026-09-03(계속7) — 강수 피쳐 추가 후 3단계 재실행 결과: **오탐+미탐 합계는 2건 그대로, 오류의 종류가 바뀜** — 강수 단독(A12)이 1단계를 처음 통과, 3단계 전부 통과는 여전히 0개

**계획**: (계속6) 사전 등록대로 `scripts/fetch_alert_validation_cache.py --rainfall`(사건 23건 강수 캐시, 2026-09-03) → `run_alert_validation.py --staged --combos`(후보 296개). 캐시 상태: ASOS 시간자료 23/23 OK. AWS 양지암(313)·신암(860) 시간·일통계 OK. **AWS 오천(995)은 포항 사건 9건 전부 `NO_SUCH_STATION`·일통계 0행** — 2026-08-17 전국 목록엔 있으나 stn 지정 조회가 안 됨(지점 개시일 또는 API 지점 체계 문제, 미해결). 그래서 포항의 A16·A17은 전부 결측→False.

**강수 atom 발화 매트릭스(양성 8·음성 7)**: A12(ASOS 1h≥30)는 양성 8건 중 7건 발화(힌남노 대구 15.6mm/h만 미발화), 음성 7건 중 카눈 거제(39.4mm/h·162mm)만 발화 — 난마돌(6mm/h)·폭염 3건·강풍 2건은 전부 꺼짐. A13(1h≥50)은 힌남노·거제 2026만. A14(일≥100)는 마이삭(85mm)·힌남노 대구(81mm)를 놓침. A16·A17(AWS)은 2024년 이후 거제·대구 사건에서만 켜짐(데이터 있는 곳에서는 A12와 같은 판정).

**결과 비교(강수 전 → 후)**:
| 항목 | 강수 전(128개 후보) | 강수 후(296개 후보) |
|---|---|---|
| 1단계 통과(힌남노 켜짐 ∧ 난마돌 꺼짐) | 22개(전부 폭풍해일·종류≥2 포함) | 102개(강수 atom 포함 조합이 대거 추가) |
| 2단계 통과(양성 6건 FN 0) | 42개 | 64개 |
| 1∩2 | 0 | **0** |
| 3단계 전부 통과 | 0 | **0** |
| 전체 라벨 기준 최소 오탐+미탐 | 2 (A2: FP 난마돌·카눈) | 2 (A12 등: FN 힌남노 대구·FP 카눈) |

**핵심**: 강수량은 (계속4)에서 못 갈랐던 힌남노/난마돌을 **명확히 가른다**(77 vs 6 mm/h) — 그래서 `A12`, `A2&A12`, `A1&A12` 같은 후보가 1단계를 처음 통과했다. 그러나 2단계에서 새 오류 1건(힌남노 대구, 15.6mm/h·81mm에 지하주차장 침수)이 생기고 카눈 거제(39.4mm/h·162mm, 라벨 음성)가 남아, 합계는 여전히 2다. 즉 **오탐 2 → 오탐 1 + 미탐 1**로 바뀌었다. OR 조합(`A2|A12` 등)은 A2의 오탐을 그대로 물려받고, AND 조합(`A2&A12`)은 A12와 같은 오류를 낸다 — 조합이 정보를 더하지 못했다.

**남은 오류 2건의 성격(라벨 재검토 대상)**: ①힌남노 대구는 ASOS 대구(6.5km)가 15.6mm/h인데 각산동 지하주차장이 침수됐다 — 국지 강우이거나 배수 문제일 수 있고, 근거가 나무위키뿐이라 라벨 자체가 약하다. ②카눈 거제는 ASOS 거제 162mm/일·양지암 111.5mm/일로 적지 않은 비가 왔는데 위키백과 "시설피해 18건(나무·유리창)"만으로 음성 처리했다 — 실제 침수가 있었다면 라벨이 틀린 것이고, 그러면 A12는 오탐 0·미탐 1이 된다. 두 건 모두 사용자 검토가 필요하다고 (계속2)에서 이미 표시했던 사건이다.

**알림 피로**: 강수 의존 후보는 전체 KMA 에피소드 2,213개에 강수 캐시가 없어 계산하지 않았다(`fatigue_not_computed`). 필요하면 ASOS 시간자료를 연 단위로 3개 지점에 대해 마이닝(약 800회 호출)하면 같은 축에서 비교 가능 — 미착수.

**해석(채택은 사용자 결정)**: 특보 필드만으로는 원리상 불가능했던 "같은 해 같은 지역 태풍 사건 간 구분"이 강수량으로 가능해졌다는 점이 이번 추가의 실질적 개선이다. 수치상 오류 합계가 줄지 않은 이유는 남은 2건이 라벨 불확실성과 국지성(관측소 6.5km 거리)에 걸려 있기 때문이며, 다음 단계는 규칙 추가가 아니라 (a) 이 2건 라벨 재검토, (b) 대구 동구·수성구 인근 AWS 지점 확보(신암 5.8km보다 가까운 지점 탐색), (c) 강수 후보의 알림 피로 계산이다.

**구현**: `advisory/kma_observation.py`(신규, HTTP seam `_fetch_raw` 1곳), `alert_validation.py`(강수 캐시·AdvisoryEvent 인코딩), `trigger_features.py`(A12~A17, `requires_rainfall`), `metrics.py`(강수 병합·`rainfall_missing`·`fatigue_not_computed`), `fetch_alert_validation_cache.py --rainfall`. 테스트 28개(`tests/test_alert_validation.py`, 강수 atom 파서·결측 처리·17개 동결 추가). 프로덕션 무변경. `pytest tests/ -q` 전체 286개 통과.

**추가 발견(같은 세션, 대시보드 확인 요청 중)**: 8/31(계속2) 캡처에서 힌남노 심각도 알림이 꺼진 원인은 "큐레이션 이벤트에 severity_level 없음"이 아니라 **웹 API의 조회 창**이다 — `webapp/app.py`가 `query_date` 하루(`historical_start`~+1일)를 `wrn_met_data`의 **발표시각(TM_FC)** 기준으로 조회하는데, 힌남노 태풍경보는 2022-09-05 22:00 발표·09-06 00:00 발효라 09-06 조회에서 빠진다(캐시 `kma-historical-L1072400-202209052200-T36` 확인). 거제 2026은 호우경보가 조회 당일 발표라 잡혔다. 프로덕션 수정 여부(조회 창 확장 또는 발효시각 필터, 심각도 채널 규칙 A2 교체, EAL 채널 명칭 조정)는 사용자 결정 대기 — 아직 코드 변경 없음.

## 2026-09-03(계속8) — 담보별 재심사 알림 규칙 + 임계값 110/180mm **사전 등록** — "사건 심각도 = 지역 내 알림 담보 수"로 표기하기 위한 설계 (1·2단계, 평가 전용)

**배경(사용자 결정, 2026-09-03)**: 3단계 검증 결과 지역 단위 트리거는 A2(수문 특보 경보 이상)가 최선이지만, 지역이 켜지면 현행 심각도 채널은 **그 지역 담보 전부**에 알림을 낸다(거제 154건은 거제 담보가 154건이라서지 심각해서가 아님). 사용자는 "사태가 심각한지는 재심사 알림 담보가 몇 개인지로 보여주면 충분하다"고 방향을 정했다 — 그러려면 알림이 담보별 조건으로 걸러져야 한다. 실제 포트폴리오로 미리 세어본 결과(같은 날 실측): 침수 tier(내부·근접)만 쓰면 세 사건 모두 지역 담보의 30% 안팎으로 같아 심각도를 못 나타내고, **담보에서 가장 가까운 AWS 관측소의 일강수**를 쓰면 포항 58/58·거제 154/154·수성구 14/23(≥100mm) 또는 0/23(≥150mm)으로 사건 심각도가 건수에 실렸다(수성구 안에서도 담보별 48~117mm로 갈림 — 관측소 700여 곳의 공간 해상도 덕).

**담보별 규칙(사전 등록)**: 지역 트리거 A2가 켜진 사건에서, 담보 좌표에 **가장 가까운 지상관측소(ASOS·AWS 통합 목록)의 사건 창 내 최대 일강수**가 임계값 이상이면 그 담보에 재심사 알림. 관측소 목록은 `sfc_aws_day.php`(stn=0, 위경도 포함)를 창의 날짜마다 조회해 지점별 최대값으로 만든다. 부수 변형으로 "∧ 침수 tier ∈ {내부, 근접}"도 같이 센다(표에 병기, 채택 기준은 아님).

**임계값과 그 근거(사용자 지시로 명시)**: 둥근 숫자(100·150)를 쓰지 않고 **기상청 호우특보 발령 기준**에 맞춘다.
| 단계 | 기상청 기준 | 등록 임계값(일강수 근사) | 근거 |
|---|---|---|---|
| 주의 | 호우주의보: 12시간 강우량 110mm 이상 | **110mm** | "주의보를 낼 만한 비가 이 담보 근처 관측소에 실제로 기록됐다" |
| 심각 | 호우경보: 12시간 강우량 180mm 이상 | **180mm** | "경보를 낼 만한 비가 이 담보 근처 관측소에 실제로 기록됐다" |
기상청 기준은 12시간 누적이고 우리 값은 일(24시간) 누적이라 근사다 — 같은 mm를 24시간에 대면 기준이 느슨해지는 방향(보수적이지 않음)이라는 점을 명시한다. 이 값을 고른 이유는 발표에서 "왜 150이냐"가 아니라 "기상청이 경보를 내는 강수량이 그 담보 옆에서 관측됐는가"로 설명하기 위해서다. (계속5)·(계속7)에서 이미 본 실측값(포항 342·거제 654·수성구 117)과 무관하게 정했지만, 그 값을 본 뒤에 정했다는 사실은 남긴다. 결과가 이 임계값으로 깔끔하지 않아도 그대로 기록한다.

**지표(`metrics.py::collateral_alert_count_metric`, 신규)**: 라벨 사건 23건마다 (a) 프로덕션과 같은 필터(`PortfolioRecord.region_code == 사건 region_code`, 대구는 대표 코드 27260만)로 매칭 담보 수, (b) A2 켜짐 여부, (c) 임계값 110/180 각각의 알림 담보 수와 tier 병기 변형, (d) 담보별 최근접 관측소 강수의 분포(최소/중앙/최대)·거리. 라벨이 음성인 사건(난마돌·카눈·폭염·강풍)에서 알림 담보가 몇 건 켜지는지가 오탐 근거가 된다.

**영향**: 1·2단계는 평가 전용(캐시 `alert_validation/station_rainfall/{event_id}.json` 신규, 지표·스크립트·테스트 추가) — 대시보드 무변경. 3단계(프로덕션 반영: 심각도 채널 규칙 A2 교체·담보별 필터·조회 창 확장·라이브 등급 파싱)는 이 표를 본 뒤 사용자가 다시 결정.

## 2026-09-03(계속9) — 담보별 알림 건수 첫 실행 결과: 110/180mm 규칙으로 "포항·거제는 전부, 수성구는 소수·0건"이 실측으로 나옴 — 카눈 오탐은 180mm에서 0건

**계획**: (계속8) 사전 등록 규칙·임계값 그대로. `fetch_alert_validation_cache.py --station-rainfall`(사건 23건 × 창 날짜마다 전국 관측소 일강수, 2016년 682지점~2026년 726지점, 전부 OK) → `run_alert_validation.py --collateral-counts`. 담보 매칭은 프로덕션 필터와 동일(`region_code` 완전일치 — 대구 사건은 대표 코드 27260 담보 23건만, 폭염 2건은 27200·27140이라 52·36건). 담보→관측소 거리 중앙값 1.7~5.1km.

**결과(매칭 담보 중 알림 담보 수, A2 켜진 사건만 / 괄호는 ∧ 침수 tier 내부·근접 변형)**:
| 사건 | 라벨 | 매칭 | A2 | ≥110mm | ≥180mm | 담보별 강수 최소/중앙/최대 |
|---|---|---|---|---|---|---|
| **힌남노 포항** | 양성 | 58 | X | **58**(17) | **58**(17) | 322/342/342 |
| **수성구 2026-07** | 양성 | 23 | X | **14**(7) | **0**(0) | 48/110/117 |
| **거제 2026-08** | 양성 | 154 | X | **154**(39) | **154**(39) | 242/654/654 |
| 미탁 포항 2019 | 양성 | 58 | X | 35(7) | 32(6) | 0/309/309 |
| 마이삭 거제 2020 | 양성 | 154 | X | 0 | 0 | 19/85/85 |
| 거제 2024-07 | 양성 | 154 | X | 146(39) | 9(2) | 62/148/230 |
| 대구 2024-07 | 양성 | 23 | X | 20(7) | 20(7) | 88/191/196 |
| 힌남노 대구 | 양성 | 23 | X | 0 | 0 | 80/81/87 |
| 난마돌 포항 | 음성 | 58 | X | 0 | 0 | 37/37/63 |
| 카눈 거제 | 음성 | 154 | X | 149(39) | **0** | 74/162/162 |
| 폭염 3건·강풍 2건 | 음성 | 36~154 | . | 0 | 0 | 0~38 |
| 콩레이·차바 포항 | unknown | 58 | X | 58 | 0 | 150~179 |
| 힌남노·미탁 거제 | unknown | 154 | X | 104·115 | 0 | 144·170 |
| 하이선·2023-07 포항, 2023·2025-07 대구 | unknown | 23~58 | X | 0 | 0 | 11~104 |

**읽기**: ①사용자가 원한 그림이 그대로 나왔다 — 힌남노·거제는 담보 전부, 수성구는 110mm에서 14건·180mm에서 0건. ②음성 사건은 180mm에서 전부 0건(카눈 149→0, 난마돌 0, 폭염·강풍 0). 110mm에서는 카눈이 149건 켜져 이 임계값의 오탐이 남는다 — 단 카눈 라벨(위키 "시설피해 18건") 자체가 재검토 대상. ③양성 중 마이삭 거제(85mm)·힌남노 대구(81mm)는 두 임계값 모두 0건 — 실제 피해 규모(10여 가구·신고 111건)가 작았던 사건이라 "건수 = 심각도" 표기 아래에선 모순이 아니지만, 지역 트리거(A2)는 켜져 있으므로 "지역 주의, 담보 알림 0건"으로 표시된다. ④tier 병기 변형은 세 사건 모두 30% 안팎으로 일정해 심각도를 못 나타냄(계속8 예상과 일치) — 채택하지 않는다. ⑤미탁 포항이 58건 중 35건인 것은 관측소별 차이(최소 0mm 지점 존재) 때문 — 담보 위치별로 다른 값을 받는다는 규칙의 의도된 동작.

**임계값 판단 재료(채택은 사용자)**: 180mm는 음성 0건·수성구 0건으로 가장 깨끗하지만 거제 2024(주택침수 12건)가 9건으로 줄고 마이삭·힌남노 대구는 0. 110mm는 수성구 14건·거제 2024 146건을 살리지만 카눈 149건이 남는다. 두 값을 주의/심각 2단계로 같이 쓰면 "카눈: 주의 149·심각 0 / 수성구: 주의 14·심각 0 / 거제: 주의 154·심각 154"로 구분된다.

**사용자 추가 방향(2026-09-03, 실무 알림 피로)**: 담보별 알림을 개별 발송하면 포항 58건 같은 사건에서 심사역이 피로하므로, **트리거 발동 시 재계산 후 지역별 "알림 담보 n/N건(심각 s건)" 요약 1건만 최종 발송하고 세부는 심사역이 대시보드에서 조회**하는 구조로 간다. 현재 대시보드는 지역 카드 단위라 이 구조와 맞고, 개별 푸시는 애초에 없다(HANDOVER 로드맵의 카카오·푸시 연동은 이 요약 1건을 보내는 것으로 설계). 3단계(프로덕션) 착수 시 이 형태로 구현한다 — 지금은 방향만 기록.

**구현**: `evaluation/collateral_counts.py`(신규: 관측소 캐시·최근접 관측소·담보 판정·지표), `fetch_alert_validation_cache.py --station-rainfall`, `run_alert_validation.py --collateral-counts`, 테스트 4개 추가(`tests/test_alert_validation.py` 총 32개: 임계값 110/180 동결, 결측 관측소 제외, 강수·tier 변형 계수, 오프라인 불변식). 프로덕션 무변경.

## 2026-09-03(계속10) — **3단계 프로덕션 반영**: 재심사 알림 규칙을 "특보 종류 + 담보별 강수 2단계(110/180mm)"로 교체, 조회 창·실시간 등급 파싱 수정, 대시보드 표기 변경

**계획(사용자 결정, 2026-09-03)**: (계속9) 표를 본 뒤 "110·180 2단계로 3단계 프로덕션 반영" 확정. 임계값은 심사역이 화면에서 바꾸는 값이 아니라 **설정 상수**(`config.py`, EAL 임계값과 같은 관례)로 두고 대시보드에 값과 근거를 표기한다. 최종 알림 단위는 지역별 요약 1건(매칭 N건 중 주의 a·심각 s)이고 담보별 목록은 심사역이 펼쳐 본다(알림 피로 방지).

**바뀐 것(프로덕션)**:
1. `agents/advisory_agent.py::is_high_severity_event` — 종류 조건 추가(검증 후보 A2): 특보는 호우·태풍·홍수·폭풍해일 ∧ 경보 이상, 재난문자는 호우·홍수·태풍 ∧ 긴급재난 이상. 폭염·강풍 경보는 더 이상 켜지지 않는다. 2026-08-31 최초 규칙(등급만)은 `evaluation/trigger_candidates.py`의 C1로 고정해 검증표가 조용히 바뀌지 않게 했다.
2. `portfolio/severity_alerts.py` — 담보별 2단계: 지역이 켜지면 담보 좌표에 가장 가까운 지상관측소(ASOS·AWS, `advisory/kma_observation.py::fetch_station_rainfall_window`가 창의 날짜별 전국 일강수를 합침)의 창 내 최대 일강수로 ≥110mm 주의 / ≥180mm 심각, 110 미만은 알림 없음. **관측을 못 받으면(창 미지정·API 실패·좌표 없음) 전원 "강수미확인"으로 알림 유지**(설계원칙1). `SeverityAlertQueueEntry`에 `alert_tier·rain_mm·rain_station·rain_station_km` 추가(금전 필드 없음 — 레드팀 `severity_isolation` 그대로 통과), `SeverityAlertSummary`(요약 1건) 신설 → `PortfolioBatchResult.severity_summary`.
3. `agents/portfolio_agent.py` — `observation_window`·`station_rainfall_fetcher`(테스트 주입 seam) 파라미터. 창이 None이면 네트워크 호출 없음(기존 호출부·테스트 호환). `graph/week3_demo.py`가 historical은 조회 구간, live는 어제~오늘을 창으로 넘긴다(replay는 None).
4. `advisory/live.py` — 실시간 특보 제목에서 등급("경보"/"주의보")을 파싱해 `severity_level`을 채운다(이전엔 None이라 실시간 모드에서 지역 트리거가 절대 안 켜졌음).
5. `webapp/app.py` — `query_date` 조회 창을 **하루 앞으로 확장**(조회일−1일 00:00 ~ 조회일+1일 00:00). 기상청 이력 API가 발표시각으로 거르므로 전날 밤 발표된 경보(힌남노 09-05 22:00 발표)가 빠지던 문제 해결.
6. 프론트(`PortfolioCard.tsx`·`types.ts`) — 섹션 제목을 "재심사 알림 — 특보·강수 기반"으로, 요약 줄("지역 매칭 N건 중 재심사 알림 n건 · 심각 s · 주의 a") + 임계값·근거 표기 + 담보별 목록은 `<details>`로 접음. 기존 EAL 변화율 표는 "건물 등록정보 변경 감지 — EAL 재계산 변화율 ≥20%"로 이름을 바꿔 보조 채널로 내림(계산은 무변경). `npm run build` 통과, `webapp/static/` 갱신.
7. `config.py` — `REASSESSMENT_RAIN_THRESHOLD_ADVISORY_MM=110`, `_WARNING_MM=180`, `_BASIS`(기상청 호우주의보·경보 12h 기준의 일강수 근사, 24h 누적에 대면 느슨해지는 방향임을 주석에 명시).

**안 바뀐 것**: `scenario/eal.py`·`portfolio/alerts.py`·`portfolio/recalc.py` — EAL·LTV·금리 계산과 건축HUB 드리프트 감지 로직은 그대로(이름만 보조 채널로). `run_scenario_agent` 시그니처 무변경.

**발표용 표 1 — 3사건(사용자 요청으로 명시 기록, (계속9) 실측)**:
| 사건 | 지역 담보 | 재심사 알림(≥110mm 주의 이상) | 그중 심각(≥180mm) | 담보별 일강수 최소/중앙/최대 | 현행(변경 전) EAL 알림 |
|---|---|---|---|---|---|
| 힌남노 포항 2022-09 | 58 | **58** | **58** | 322/342/342 | 2(드리프트) |
| 대구 수성구 2026-07 | 23 | **14** | **0** | 48/110/117 | 0 |
| 거제 2026-08 | 154 | **154** | **154** | 242/654/654 | 0 |

**발표용 표 2 — 라벨 사건 전체(A2가 켜진 사건만 담보 알림 가능, (계속9) 실측)**:
| 사건 | 라벨 | 담보 | 주의 이상(≥110) | 심각(≥180) |
|---|---|---|---|---|
| 미탁 포항 2019 | 피해 | 58 | 35 | 32 |
| 마이삭 거제 2020 | 피해 | 154 | 0 | 0 |
| 거제 2024-07 | 피해 | 154 | 146 | 9 |
| 대구 2024-07 | 피해 | 23 | 20 | 20 |
| 힌남노 대구 2022 | 피해 | 23 | 0 | 0 |
| 난마돌 포항 2022 | 없음 | 58 | 0 | 0 |
| 카눈 거제 2023 | 없음(재검토) | 154 | 149 | 0 |
| 폭염 3건·강풍 2건 | 없음 | 36~154 | 0(지역 트리거 꺼짐) | 0 |
| 콩레이·차바 포항, 힌남노·미탁 거제 | 미확인 | 58·154 | 58·58·104·115 | 0 |
| 하이선·2023-07 포항, 2023·2025-07 대구 | 미확인 | 23~58 | 0 | 0 |

**검증**: 신규·수정 테스트 — `test_severity_alerts.py`(종류 조건·임계값·담보별 등급·강수미확인 유지·요약), `test_advisory_live.py`(등급 파싱), `test_portfolio_agent_smoke.py`(주입 fetcher로 등급·요약, 창 없으면 호출 없음), `test_webapp_endpoints.py`(창 확장), `test_week3_demo_smoke.py`(모의 함수 시그니처), `test_alert_validation.py`(C1 고정·프로덕션=C2 동일성). `pytest tests/ -q` 전체 **295개 통과**(프로덕션 변경 후, 커밋 8753c05 시점).

**영향**: PM은 (1) HANDOVER §4.1 "임계치 초과분만 알림"의 임계치 정의를 "EAL 변화율"에서 "특보 종류 + 담보별 강수 110/180mm"로 갱신할지, (2) PPT·proposal의 재심사 알림 설명·캡처를 새 화면으로 교체할지 판단. 실사용 확인(로컬 서버에서 힌남노·수성구·거제 3건 조회)은 다음 단계.

**실사건 재현(같은 세션, 실제 기상청·재난문자 API + 건축HUB 라이브 재계산, 웹 API와 동일한 확장 창)**:
| 사건 | 지역 트리거(대표 이벤트) | 매칭 | 재심사 알림 | 심각 | 주의 | 강수 조회 | 건물 변경 감지(EAL) |
|---|---|---|---|---|---|---|---|
| 힌남노 포항 2022-09-06 | 태풍 경보 변경(09-05 22:00 발표 → 확장 창 덕에 포착) | 58 | **58** | 58 | 0 | OK | 1 |
| 대구 수성구 2026-07-17 | 호우 경보 변경(07-17 21:50) | 23 | **14** | 0 | 14 | OK | 0 |
| 거제 2026-08-17 | 호우 경보 변경(08-17 10:40) | 154 | **154** | 154 | 0 | OK | 0 |
(계속9)의 오프라인 검증표와 동일 — 변경 전엔 힌남노에서 심각도 알림이 0건(조회 창 문제)·거제 EAL 알림 0건이던 것이, 이제 세 사건 모두 같은 규칙으로 켜지고 건수가 피해 규모를 따라간다.

## 2026-09-07 — 멘토 피드백(대시보드) 반영: 단계별 부분 결과 스트리밍 + 포트폴리오 재계산을 심사메모보다 먼저 실행 + 결과 화면 "요약 강조·상세 접기" 구조

**계획(HANDOVER.md 기준)**: ④ 데이터 흐름은 "3에이전트 병렬 fan-out → 시나리오 → 메모 에이전트 → (트리거 시) 포트폴리오 재계산" 순서였고, 웹 데모(`webapp/app.py`)는 진행 단계 메시지만 SSE로 중계하고 **모든 단계가 끝난 뒤 결과를 한 번에** 내려줬다. 결과 화면은 침수·건물·EAL·메모·특보·포트폴리오 6개 카드를 전부 펼친 채 세로로 나열.

**실제(멘토 피드백 4건, 2026-09-07)**: ① "결과가 전부 끝나야 나오는 게 답답하다" ② "심사메모 후 포트폴리오 재계산이 뭘 재계산하는지 화면에서 안 읽힌다" ③ 인프라·소켓·DB 구성 질문 ④ "글이 한눈에 안 들어온다 — 핵심 강조, 상세는 펼쳐보기로".
- 실측: 힌남노 리플레이(포항 인덕로 27, 2022-09-06) 1회 조회 시 advisory 0.8초 → flood 1.2초 → building 6.8초 → scenario 6.8초 → **memo(LLM, `claude -p`) 86초** → portfolio 95초. 즉 심사역이 볼 수 있는 침수·건물·EAL 값은 7초 만에 다 나와 있는데 LLM 메모 때문에 90초 가까이 화면이 비어 있었다 — ①의 원인.
- 구현: `graph/week3_demo.py`에 `on_partial(stage, payload)` 훅 추가(기본값 None, 기존 CLI·테스트 동작 불변). 각 에이전트 완료 즉시 `dataclasses.asdict` 산출물을 넘기고, `webapp/app.py`가 SSE `partial` 이벤트로 중계. 프론트는 도착한 카드부터 그리고 나머지는 "계산 중" 자리표시자. 최종 `result` 이벤트 값과 부분 결과 값이 동일함을 `tests/test_webapp_progress_hook.py`로 고정.
- **파이프라인 순서 변경**: 포트폴리오 재계산(약 8초)을 메모(약 80초)보다 먼저 돌린다. 두 단계는 서로 의존하지 않는다(메모는 flood/building/scenario/advisory만, 포트폴리오는 advisory만 읽음). 재심사 알림이 LLM 완료까지 가려져 있을 이유가 없어서다. HANDOVER ④의 "메모 → 포트폴리오" 서술 순서와 달라졌으나 계산 로직·결과값은 동일 — 발표자료의 흐름도 순서를 맞출지는 PM 판단.
- ②는 UI 표기 문제로 판단: 재계산의 뜻("특보 지역 담보 N건의 침수·건물·EAL을 지금 원자료로 다시 계산해 스냅샷과 비교")을 카드 제목·요약·본문 첫 줄에 명시했고, EAL 변화율 채널의 제목 "건물 등록정보 변경 감지"를 "EAL 재계산 변화 — 스냅샷 대비"로 바꿨다(2026-09-03 검증에서 건축물 변경은 피해 라벨로 못 쓴다고 결론 났는데 제목이 그 채널을 주 알림처럼 보이게 하고 있었음).
- ④: 상단 KPI 4타일 + 심사메모 기본 펼침 + 나머지 카드 접기 구조로 한 차례 구현했다가 **되돌렸다**(2026-09-07, 사용자 결정) — 색 띠 카드 등이 "AI스럽다"는 피드백으로 디자인 방향을 다시 잡는 중이며, 후보 A~H를 Claude 디자인 캔버스("심사 대시보드 디자인 방향")에 모아 검토 중. 앱 화면은 변경 전 카드 구성을 유지하고, 단계별 자리표시자("계산 중")만 기존 카드 모양으로 추가했다. 확정되면 별도 항목으로 기록.

**영향**: HANDOVER ④ 흐름도의 메모/포트폴리오 순서 서술과 발표 PPT 캡처(DEV_LOG 2026-08-31 계속2의 "실사건 검증" 3슬라이드는 이전 레이아웃 캡처)를 새 화면으로 갱신할지 PM 판단. ③(인프라 질문)에 대한 답은 코드에 이미 있는 사실이라 여기 적지 않음 — PostGIS는 HANDOVER B5대로 미도입(shapely 인프로세스 + 디스크 pickle 캐시), DB 없이 JSON/JSONL 파일, 소켓은 WebSocket이 아니라 SSE(단방향 HTTP 스트림).

## 2026-09-08 — 입력 폼 UX 수정: 주소 미리 채움 제거, 조회 기준 세그먼트 + 사건 칩, 층 구분 세그먼트(네이티브 select 제거)

**계획(HANDOVER.md 기준)**: 웹 데모 폼에 대한 명시적 설계 없음. 2026-08-19 사용자 결정으로 "리플레이/라이브/특정날짜" 3택 드롭다운을 "조회 날짜" 한 칸으로 단순화했었음.

**실제**: UX 점검(2026-09-07, 프론트엔드 현직자 피드백 포함)에서 ① 첫 화면에 예시 주소가 실제 값처럼 미리 채워져 있음 ② "조회 날짜" 한 칸에 지금/과거 두 모드가 숨어 있어 첫 방문자가 의미를 모름 ③ 층 구분 `<select>`가 OS 네이티브 드롭다운이라 화면과 모양이 어긋남 ④ 라벨에 내부 문서 참조(HANDOVER §⑧)가 노출됨을 확인.
- 주소는 빈 칸 + 회색 예시 + "예시 주소 넣기" 링크(프리셋 첫 항목).
- "조회 기준" 세그먼트(지금 시점 특보 / 과거 사건 재현). 과거를 고르면 날짜 입력 + 사건 칩(힌남노·포항 2022-09-06, 집중호우·대구 수성구 2026-07-18, 집중호우·거제 2026-08-17). 칩은 날짜를 채우고 주소가 비어 있으면 그 사건의 예시 주소도 채운다. 백엔드 판단 방식(query_date 유무로 mode 결정)은 그대로.
- `/api/regions` 프리셋에 `sample_date`·`chip_label` 추가, 거제 2026-08 실호우 항목 신설(고현천 8/17 범람 — 2026-08-31 항목 참조). 기존 필드는 유지.
- 층 구분은 세그먼트 버튼 3개(미입력/지상/지하) + 층수 입력. 날짜 입력은 네이티브 달력 유지.
- 라벨에 1·2·3 순서 번호, 담보가액 옆 "= 4억원" 환산, 버튼 아래 소요시간 예고, 결과 빈 상태를 3단계 안내로.
- 검증: 헤드리스 브라우저로 세그먼트 → 힌남노 칩 → 주소·날짜 자동 채움 → 지역 감지 → 층 세그먼트까지 실제 조작 확인. `pytest tests/test_webapp_*.py` 22개 통과.

**영향**: 발표 시연 순서를 "예시 주소 넣기 → 과거 사건 재현 → 힌남노 칩 → 평가 실행"으로 잡으면 클릭 3번으로 끝난다. uvicorn `--reload`가 `webapp/app.py` 변경을 감지하지 못하는 경우가 있었음(src/ 아래는 감지) — 프리셋을 바꾸면 서버를 수동 재시작할 것.

## 2026-09-08(계속) — 결과 화면 ①단계: 순서·섹션 골격을 확정안(결론 → 요약 → 권고 조치 → 근거)으로 교체

**계획(HANDOVER.md 기준)**: 웹 결과 화면은 침수 → 건물 → EAL → 메모 → 특보 → 포트폴리오 카드 6장 세로 나열(2026-08-12 발표용 UI). 화면 구성에 대한 설계 규정은 없음.

**실제**: 멘토·프론트엔드 현직자 피드백(결론이 맨 아래, 카드 나열, 글 과다)을 디자인 캔버스("심사 대시보드 디자인 방향" 1~11p)에서 검토한 뒤 사용자가 11p 확정안(9p 보고서형 스타일 + 10p 토스 분석 탭 순서)을 선택. 4단계 중 ①만 반영:
- 순서: 1 결론 → 2 요약 → 3 권고 조치 → 4 침수 → 5 건물 → 6 손실 → 7 특보·알림 → 8 근거 원문. 번호 섹션(`components/Section.tsx`) + 앵커 탭.
- 1 결론: 재심사 알림 배너(severity_summary의 대표 사건·매칭/알림 건수·임계값) + 한 줄 판정(침수 tier·취약도·EAL과 담보가액 대비 %) + 행동 버튼. **심사역 확인 버튼은 ④ 전까지 비활성**.
- 2 요약: 키|값|배지 3열 행(배지는 오른쪽 열로 통일). 3 권고 조치: `policy/disclosures.py::ACTION_PHRASE_TEMPLATES`를 `/api/assess` 응답 `action_templates`로 그대로 노출(프론트가 문구를 새로 만들지 않음 — 보호규율 문구 고정), 번호 목록 + 응답 값으로만 만든 "왜" 한 줄, 체크박스 없음(읽기 전용).
- 4~8: 기존 카드 컴포넌트에 `bare` 옵션을 붙여 섹션 안에 껍데기 없이 재사용. 새 계산·새 값 없음(③에서).
- 담보가액은 응답에 없어 제출 시 폼 값을 `SubmittedMeta.collateralValue`로 들고 가 비율 계산에 씀.

**영향**: HANDOVER·PPT의 결과 화면 캡처는 이전 레이아웃 — 갱신 여부는 PM 판단. ②(근거 토글·출처 이동) ③(새 값 7종) ④(심사역 확인 → 감사로그 API)는 순서대로 진행 예정.

## 2026-09-08(계속2) — 결과 화면 ②단계: 근거 섹션 토글·출처 이동, 결론 사건 문구 축약

**계획(HANDOVER.md 기준)**: 해당 없음(위 ①단계 항목의 후속).

**실제**: 근거 섹션(4~8)을 "쉬운 한 문장 + 핵심 값"만 열어두고 표·산식·출처·재현 정보는 네이티브 `<details>` 토글(`components/Details.tsx`) 안으로 옮김.
- 4 침수: 배지 + 문장 + 하천·거리·빈도 3행 / 토글: 방법론 유의사항(methodology_disclaimer)·커버리지·SHP 파일명·라이선스·source_id.
- 5 건물: 점수·상태 + "가장 큰 요인" 문장 + 층별 리스크 / 토글: 요인 표(기여 열 추가)·가중치·출처. 실패·결측 사유는 접지 않음.
- 6 손실: 문장(담보가액 대비 %) + 평균·p95/p99 + 히스토그램 / 토글: methodology_note·시드·반복수·source_id.
- 7 특보·알림: 특보 한 문장 / 토글: 이력 전체. 재심사 알림 한 문장 + 대표 사건 / 토글: 담보별 목록·임계값. EAL 재계산 변화 표는 토글로.
- 8 근거 원문: 문장은 열어두고 인용은 짧은 칩(접두어:파일명) / 토글: 문장별 source_id 원문.
- 2 요약에 "출처 보기" 토글(침수·건물·손실·특보 출처 한 줄씩). 결론 배너의 대표 사건은 괄호 앞까지만 + 발효시각 `YYYY-MM-DD HH:mm`.
- 새 계산·새 값 없음. 화면에 노출되는 SHP 절대경로는 파일명으로 축약(전체는 title).

**영향**: 없음(표시 계층만). ③(새 값 7종)에서 침수심 등급·요인 기여도·건축물대장 확장 필드 등을 같은 자리에 채울 예정.

## 2026-09-08(계속3) — 결과 화면 ③단계: 표시용 값 7종 추가 — 그중 적응 투자 전후 EAL·침수흔적 근접·소요시간은 새 결정론 계산

**계획(HANDOVER.md 기준)**: ⑥ 보호형 사용 규율 3항 "인센티브는 인하 방향만(차수판·방수 설비 등 적응 투자 시 우대)" — 우대의 근거 수치를 어떻게 낼지는 미정. §⑧ 층별 리스크에서 SEG_CODE 침수심 등급을 계산에만 쓰고 화면 표기는 없었음. 실측 침수흔적(safemap A2SM_FLUDMARKS_WI)은 평가지표(recall)에만 사용.

**실제(디자인 캔버스 11p 확정안 반영, 멘토·현직자 피드백 "없는 수치는 확장 가능성으로, 있는 데이터는 최대한")**:
1. **적응 투자 전후 EAL(신규 결정론 규칙)** — `scenario/eal.py::run_monte_carlo_eal(barrier_height_m=…)`: 같은 난수열에서 침수심만 `max(0, depth − h)`로 낮춰 재실행. `h=0`이면 기존 결과와 바이트 단위 동일(회귀 테스트). `agents/scenario_agent.py`가 `config.ADAPTATION_BARRIER_HEIGHTS_M=(0.3, 0.5, 1.0)`로 3개 시나리오를 `adaptation`에 붙임. 실측(COL-004): 776,202 → 599,012(0.3m, −22.8%) / 456,648(0.5m, −41.2%) / 149,999(1.0m, −80.7%). **문헌 근거 없는 잠정 규칙**이며 `ADAPTATION_ASSUMPTION_NOTE`를 화면에 항상 같이 표시. 우대 안내(인하 방향)의 참고치일 뿐 LTV·금리 계산에 연결하지 않음(설계원칙 2·3 유지, redteam 회귀 통과).
2. **실측 침수흔적 근접 요약** — `evaluation/flood_marks.py::summarize_flood_marks_near`: 좌표 기준 최근접 1건(거리·연도·원인·평균 침수)과 반경 500m/2km 건수. 좌표·원본 레코드는 응답에 넣지 않음(파일의 license_note: 재배포 금지). 파일 없으면 None → 화면 "데이터 없음(위험 낮음 아님)".
3. **단계별 소요시간** — `webapp/app.py::_stage_durations`: on_stage 실제 호출 시각 차이. `alert_latency_seconds` = 특보 조회 시작 → 포트폴리오 재계산 완료(다음 단계 시작). 실측 15초 안팎. 라이브 모드에서 "특보 발표시각 기준"으로 재정의하는 건 미구현(현재 정의는 조회 시작 기준임을 화면에 명시).
4. 침수심 등급 범위 — `scenario/floor_exposure.py::depth_class_summary`: SEG_CODE → "1.0~2.0m" 등, tier가 내부가 아니면 reliable=False(가장 가까운 폴리곤의 등급).
5. 요인별 기여도 — 이미 응답에 있던 `contribution`을 타일로 표시.
6. 건축물대장 요약 — `BuildingAgentOutput.registry`(연면적·건축면적·지상/지하층·높이·지붕·내진설계·사용승인)를 건축HUB raw에서 추림. 취약도 계산엔 미사용.
7. 특보 타임라인 — `advisory.timeline` + 백엔드가 고른 `trigger_event_ids`(규칙은 `is_high_severity_event` 하나)로 SVG 타임라인.

**영향**: HANDOVER ⑥ 3항의 "우대"에 참고 수치(적응 투자 전후 EAL)가 생겼으니 기획서·PPT의 보호 조치 장면에 반영할지 PM 판단. 이 규칙은 캘리브레이션 대기 잠정치(`config.py`에 상수·근거 문자열로 고정, 다른 잠정 상수와 같은 관례). 회귀: `tests/test_step3_display_values.py` 6개 + 기존 46개 통과.

## 2026-09-08(계속4) — 결과 화면 확정안 v2.1 반영: 결론 카드 + 흰 패널 한 장(권고 조치 → 요약 → 근거) 골격

**계획(HANDOVER.md 기준)**: 해당 없음(위 ①~③ 항목의 후속).

**실제**: 디자인 캔버스 11p 확정안 v2.1(사용자 결정) — 1 결론만 번호 카드로 두고, 그 아래는 토스증권 분석 탭 흐름을 대입한 흰 패널 한 장(`components/Panel.tsx`) 안에 "제목 + 출처(회색) + 쉬운 한 문장 + 시각 1개 + 표" 골격으로 섹션을 세로로 이어 붙임. 순서는 **결론 → 권고 조치 → 요약 → 침수 → 건물 → 손실 → 특보·알림 → 근거 원문**(권고 조치를 요약보다 위로 올린 것은 사용자 결정 — 심사역이 할 일이 먼저, 근거는 검증용). 섹션 탭은 번호 없이 앵커 이동. 요약에 응답 값으로 만든 한 줄(준공연도·구조·층수·용도 + 위치/건물 리스크 비교)을 추가하고, 요약 행의 배지는 오른쪽 끝 열로 통일. 새 계산·새 값 없음(①~③ 값 그대로).

**영향**: 발표자료의 결과 화면 캡처 갱신 여부는 PM 판단. ④(심사역 확인 → 감사로그 API) 남음.

## 2026-09-08(계속5) — 대시보드 3단 레이아웃(토스형): 왼쪽 폼 · 가운데 내부 스크롤 결과 상자 · 오른쪽 진행상황

**계획(HANDOVER.md 기준)**: 해당 없음(결과 화면 확정안 v2.1의 후속, 사용자 결정 — 디자인 캔버스 12p 3안 "토스형" 확정).

**실제**: `App.tsx` 메인 그리드를 `320px | 1fr | 260px` 3열(1200px 미만은 세로 스택)로 바꾸고, 양쪽 열은 sticky. 가운데 `ResultSection`이 스크롤 상자를 직접 소유(높이 = 창 높이 − 헤더, `overflow-y: auto`) — 페이지 스크롤은 움직이지 않는다. 상자 상단에 새 `ResultTopBar`가 고정: 1줄은 담보 한 줄(주소·담보가액·조회일·처리초) + 결론 배지 4개(재심사 알림·침수 tier·취약도·EAL, 미도착 단계는 "계산 중"), 2줄은 밑줄형 목차 탭(결론·권고 조치·요약·침수·건물·손실·특보·알림·근거 원문). 탭 클릭은 상자 내부 `scrollTo`, 현재 섹션은 상자 스크롤 위치로 계산해 밑줄 이동. 기존 `TargetBanner`·탭 칩 행은 제거(상단 고정 줄이 대체). 오른쪽 `ProgressList`는 단계 짧은 라벨 + 결과 도착 후 단계별 실측 초(`timings`, 새 계산 아님 — 백엔드 on_stage 시각 차이)와 완료 줄. `ProgressItem`에 `stage` 추가. 헤드리스 Edge 1440×900 확인: 진행 중/완료/탭 클릭 후(요약 밑줄, 상자 scrollTop 663, 페이지 scrollY 0).

**영향**: 백엔드 변경 없음, 새 계산 없음. 추가 수정은 사용자와 재논의 예정(내부 스크롤 상자에서 마우스 휠이 상자 밖에서 걸리는 문제는 상자 높이를 뷰포트에 맞춰 완화). ④(심사역 확인 → 감사로그 API) 남음.

## 2026-09-08(계속6) — 왼쪽 폼 카드 높이를 가운데 결과 상자와 동일하게 고정 + 폼 압축(토스증권 주문하기 폼 참고)

**계획(HANDOVER.md 기준)**: 해당 없음((계속5) 3단 레이아웃의 후속, 사용자 지적 — 왼쪽 담보 평가 카드가 가운데 상자보다 항상 길고 과거 사건 재현에서는 더 길어져 페이지가 스크롤됨).

**실제**: 실측(1440×900) 왼쪽 카드 643px(지금 시점)/819px(과거 재현) vs 가운데 상자 약 715px, 사용자 창(약 750px)에서는 상자가 더 작아져 기본 모드에서도 넘침. 토스증권을 헤드리스로 여러 창 크기에서 확인: 창이 낮아져도 종목정보·주문하기 두 상자를 같은 높이로 두고 내용을 자르며, 주문하기 폼은 라벨 왼쪽/컨트롤 오른쪽 2열. 이를 따라 (1) `AssessForm`이 `height`(= 가운데 상자 높이)를 받아 카드 고정 높이, 헤더 / 스크롤 가능한 필드 영역 / 바닥 고정 평가 실행 버튼 구조. (2) 압축: 신규·기존 토글 → 헤더 오른쪽 텍스트 탭, 과거 사건 재현은 사건 칩이 주 조작이고 날짜 입력란은 "날짜 직접 입력"을 눌러야 펼침(칩과 안 맞는 날짜가 이미 있으면 펼친 채), 담보가액·담보 층 행을 2열로, 입력 높이 42→38px, 버튼 아래 소요시간 안내와 두 줄 주소 안내 삭제(같은 내용이 가운데 빈 상태에 있음). (3) 빈 상태·오류 상태 결과 카드도 같은 높이. 실측 1440×760: 왼쪽=가운데 575px, 폼 내부 스크롤 0, 페이지 스크롤 0(과거 재현·실행 중·완료 모두). 오른쪽 진행상황 카드는 내용 높이 그대로(미결정 — 나중에 최근 조회 목록 자리 후보).

**영향**: 백엔드·계산 변경 없음. 토스처럼 창 폭 1200px 아래에서 오른쪽 열을 접는 중간 단계 반응형은 미구현(현재는 1200px 미만이면 세로 스택). 디자인 캔버스 4p(입력 폼)·12p 캡처와 어긋남 — 갱신 여부는 사용자 판단.

## 2026-09-08(계속7) — 침수 노출 단면도(10p·11p 목업의 SVG) 추가 + 900~1199px에서 진행상황 열을 토스식 아이콘 레일로

**계획(HANDOVER.md 기준)**: 해당 없음((계속5)(계속6)의 후속, 사용자 결정 — 오른쪽 진행상황 카드는 현재 높이 유지, 1200px 미만은 토스증권처럼).

**실제**: (1) 목업 10p·11p에 있던 "시각 1개"(침수 단면도)가 앱 반영 ①~③에서 빠져 있었음 — 기존 카드를 bare로 재사용하며 값만 추가한 탓, 다른 이유 없음. 새 `FloodCrossSection.tsx`: 지표선 위로 침수심 등급 하한(진하게)·상한(연하게, 점선) 띠, 건물 상자 안에 심사 대상 층 바닥선(`building.floor_exposure.floor_elevation_m`)과 층 노출 등급, 층 미입력 시 "층을 입력하면 층별 노출도를 계산해요". 값은 전부 응답에 있는 것(`flood_depth_class`, `floor_exposure`), 새 계산 없음. 범위 안 + 등급 있을 때만 그리며 커버리지 밖·판정보류는 단면도 없이 문구만(원칙1). 1200px 이상은 단면도 왼쪽 + 값 표 오른쪽 2열, 그 아래는 세로. `SubmittedMeta`에 층 입력값 추가(라벨용). (2) 그리드 3단계: 900px 미만 세로 스택 / 900~1199px `300px | 1fr | 56px`(오른쪽은 아이콘 레일 — 실행 중 점 깜빡임 + 현재 단계 짧은 라벨, 클릭 시 진행상황 패널이 결과 상자 위에 겹쳐 열림; 가운데를 더 좁히지 않으려고 밀지 않고 덮음) / 1200px 이상 기존 3열. 레일 패널이 가운데 상단 고정 줄(z-10) 아래로 깔리는 문제는 오른쪽 열에 z-30. 실측 1000×800: 왼쪽=가운데 615px, 레일·패널 정상. 단계 라벨은 `lib/stages.ts`로 모음.

**영향**: 백엔드 변경 없음. 디자인 캔버스 12p에는 900~1199px 레일 안이 없음(앱이 먼저) — 캔버스 갱신 여부는 사용자 판단.

## 2026-09-09 — 대시보드 보고서형 미니멀 정리: 여백 확대, 카드·테두리·그림자 제거, 글꼴 Pretendard

**계획(HANDOVER.md 기준)**: 해당 없음(2026-09-08 (계속5)~(계속7) 3단 레이아웃의 후속, 사용자 결정 — "보고서 같은 산출물이니 여백을 넉넉히, 불필요한 border·card 디자인을 빼고 미니멀하게" 의견 반영).

**실제**:
- 바탕: 그라데이션 → 평평한 한 색(`#f4f5f5`). 상단 민트 그라데이션 배너·회색 출처 줄·그림자를 걷어내고 제목 한 줄(아이콘·제목·부제 + 오른쪽 출처·지도 링크)로. 브랜드 민트는 아이콘·링크·버튼·배지에만 남김.
- 가운데 결과: 테두리·그림자 없는 흰 시트 한 장. 안쪽 회색 바탕과 카드 껍데기(결론 카드의 번호 원·톤 테두리, `Panel`의 테두리, 처리시간 카드, 노란 면책 상자)를 전부 제거하고 섹션은 여백(`pt-10`)으로만 구분. 섹션 사이 가로선도 없앰. 상단 고정 줄(담보 한 줄 + 탭)의 아래 하선 하나만 유지(스크롤 시 경계 역할).
- 하위 회색 상자(건물 요인 타일, 층별 리스크 상자, 차수판 전후 EAL 표, 권고 조치의 EAL 줄, 포트폴리오 "임계치 미만" 안내, 결론의 "알림 없음" 줄)를 배경 없는 평문·표로. 표 헤더 배경 제거. 배지 그림자 제거. 남긴 선은 표 행 구분선(`surface-alt`)뿐.
- 왼쪽 폼·오른쪽 진행상황은 카드 없이 바탕 위에 바로. 폼 헤더 아이콘 타일·하선 제거, 실행 버튼은 그림자·호버 이동 없는 평면(`title` 색). 진행상황은 작은 회색 제목 + 점 목록(연결선 제거). 900~1199px 레일 버튼도 테두리·그라데이션 제거, 펼침 패널은 떠 있는 요소라 흰 배경 + 그림자 유지.
- 열 간격 16→32px, 좌우 여백 20→32px, 오른쪽 열 260→240px. 본문 글자 13.5→14.5px, 행간 1.75~1.8, 섹션 제목 17→18px.
- 글꼴: `pretendard` npm 패키지 자체 호스팅(동적 서브셋), `--font-sans` 첫 순위 "Pretendard Variable". 별도 커밋(1b360ae).
- `Section`의 `n`·`tone` prop 제거(호출부 `ConclusionSection` 갱신). 새 계산·새 값 없음, 백엔드 변경 없음. 실측 1440×900 헤드리스: 빈 상태·진행 중·완료·근거 원문까지 확인. 900~1199px 레일 모드는 이번엔 미확인(스타일만 바뀜).

**영향**: 디자인 캔버스 11p·12p 캡처(카드형)와 어긋남 — 갱신 여부는 사용자 판단. 발표자료 캡처도 마찬가지.

## 2026-09-09(계속) — 상단을 토스증권식 얇은 줄로: 회사명 │ 제품명 · 화면 메뉴 · 데모 라벨, 출처는 하단 줄로

**계획(HANDOVER.md 기준)**: 해당 없음(위 미니멀 정리의 후속, 사용자 결정 — tossinvest.com 상단처럼 "회사명이 문패, 설명 문장은 없음").

**실제**: 헤더를 52px 한 줄로. 왼쪽 `iM뱅크`(글자 워드마크, 민트) │ `담보 기후리스크 심사`, 가운데 메뉴 2개(담보 심사 / 포트폴리오 지도 — 현재 화면에 밑줄, `location.pathname` 기준), 오른쪽 "공공데이터 실연동 데모" 회색 라벨. 부제("물건 단위 조기경보와 심사메모 자동화")는 결과 시트 빈 상태 안내에 같은 내용이 있어 제거, "데이터 출처: …" 줄은 페이지 하단 `<footer>` 한 줄(왼쪽 출처 · 오른쪽 "AI 기반 참고자료 · 여신 결정 아님")로 이동. 결과 상자 높이 계산에 하단 줄을 반영(`innerHeight − 헤더 − 80`). 실측 1440×900: 문서 scrollHeight = innerHeight(페이지 스크롤 0).

iM뱅크 실제 로고 파일은 쓰지 않았다 — 공모전 제출물이라도 로고 이미지 재사용은 저작권·공식 서비스 오인 문제가 있어 글자 워드마크만 브랜드 민트로. 표기(iM뱅크 vs iM금융그룹)는 심사 업무 소관을 따라 iM뱅크로 두었고 사용자 확인 대기.

**영향**: `webapp/portfolio_map.html`(별도 정적 페이지)은 이 헤더를 쓰지 않아 상단이 서로 다름 — 맞출지는 후속 판단. 디자인 캔버스·발표자료 캡처 갱신 여부는 사용자 판단.

