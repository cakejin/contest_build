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
