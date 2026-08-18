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
