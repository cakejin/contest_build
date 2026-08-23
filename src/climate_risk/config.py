"""환경설정 및 SHP 파일 레지스트리.

HANDOVER.md ④ 확장성 원칙: "하천/지역 수를 하드코딩하지 않는다"는 원칙은
point-in-polygon 질의 로직(gis/query.py, gis/loader.py)에 적용된다 — 그 코드는
이 리스트의 길이·내용에 의존하지 않고 순회만 한다. 이 파일 자체는 "현재 다운로드된
SHP가 어떤 것인지"의 데이터 목록이므로, 새 SHP를 추가할 때는 이 리스트에 항목만
추가하면 된다(코드 변경 불요).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[2]

load_dotenv(REPO_ROOT / ".env")

VWORLD_API_KEY = os.environ.get("VWORLD_API_KEY", "")
DATA_GO_KR_API_KEY = os.environ.get("DATA_GO_KR_API_KEY", "")
KMA_API_HUB_KEY = os.environ.get("KMA_API_HUB_KEY", "")
SAFEMAP_API_KEY_A = os.environ.get("SAFEMAP_API_KEY_A", "")
# business.juso.go.kr 도로명주소 검색API(jstRoadNmAddrApiSearch) — 담보 포트폴리오 확장(2026-08-18)의
# 미달 유형(공동주택·다가구주택 등) 실주소 발굴용. 개발 승인키(본인인증 없이 발급)라 유효기간 제한 있음.
# 주의: scripts/discover_via_juso.py 등 배치 생성 스크립트 전용이다. 라이브 단건 조회(webapp/app.py)의
# 주소 입력은 이 키와 무관하게 geocoding/vworld.py로 처리된다 — 혼동 시 DEV_LOG.md 2026-08-18 참조.
JUSO_API_KEY = os.environ.get("JUSO_API_KEY", "")

# safetydata.go.kr 행정안전부 재난문자 발송내역 조회(DSSP-IF-00247), 2026-08-20 승인.
# IP 화이트리스트 1개만 등록 가능(등록 IP 아니면 거부) — DEV_LOG.md 2026-08-19 IP 화이트리스트
# 이슈 참조. 구 단위 세분화 가능성 보완 소스로 도입(대구 5개구가 기상청 특보 API로는 개별
# 구분이 안 되는 한계, advisory/kma_historical.py·advisory/live.py 참조) — 실제로 그런지는
# 미검증, 실호출로 응답 스키마부터 확인 필요.
SAFETYDATA_DISASTER_MSG_API_KEY = os.environ.get("SAFETYDATA_DISASTER_MSG_API_KEY", "")
SAFETYDATA_DISASTER_MSG_URL = "https://www.safetydata.go.kr/V2/api/DSSP-IF-00247"

RAW_DATA_DIR = REPO_ROOT / "data" / "climate-collateral-underwriting-ai" / "raw"

# 2026-08-19 추가(DEV_LOG.md 참조) — SHP 콜드 로딩(gis/loader.py, 파일 수·복잡도에
# 따라 수 분) 결과를 디스크에 캐시해 프로세스가 새로 시작될 때마다(pytest 재실행,
# 서버 재시작 등) 매번 콜드 로딩하던 것을 없앤다. data/ 자체가 .gitignore 대상이라
# 이 캐시 파일도 git 이력에 안 남는다.
GIS_LOAD_CACHE_PATH = REPO_ROOT / "data" / "climate-collateral-underwriting-ai" / ".cache" / "gis_load_cache.pkl"

FLOOD_MAP_SOURCE_CRS = "EPSG:5186"  # KGD2002 중부원점 2010 — 원본 SHP 좌표계 그대로 보관
LICENSE_LABEL = "환경부 홍수위험지도, 공공누리 4유형(출처표시·상업이용 금지·변경금지)"


@dataclass(frozen=True)
class FloodShpSource:
    path: Path
    region_code: str  # dbf SGG_CD와 일치 (로더에서 교차검증)
    region_name: str
    river_name: str
    freq_label: str  # dbf FLDLV_FREQ와 일치


# 7개 SHP 전량 — 냉천(포항시 남구, 기왕최대) + 신천(대구 5개구, 500년) + 거제시(2026-08-19 추가, 500년)
FLOOD_SHP_SOURCES: list[FloodShpSource] = [
    FloodShpSource(
        path=RAW_DATA_DIR
        / "행정구역 경상북도 포항시 남구 기왕최대 지방하천 하천범람지도"
        / "RFM_SGG_RGN_47111_MAX.shp",
        region_code="47111",
        region_name="포항시 남구",
        river_name="냉천",
        freq_label="MAX",
    ),
    # 거제시는 냉천/신천과 달리 대표 하천 하나로 특정할 수 없다 — 지방하천 17개소
    # (연초천·산양천·둔덕천·고현천 등)가 시 전역에 분포하고, 이 SHP 1개가 SGG 전체의
    # 다중 하천 침수구역을 함께 담고 있다(세그먼트 bbox가 시 전역 21km를 가로지름,
    # 특정 하천 하나의 범위가 아님을 실측 확인). "고현천" 등 단일 하천명으로 라벨링하면
    # 부정확하므로 일반화된 표기를 쓴다. 6개 빈도(50/80/100/200/500/기왕최대)가 전부
    # 다운로드돼 있으나 500년만 등록 — query_flood_risk()가 좌표당 폴리곤 1개만
    # 선택하는 구조라 동일 region_code에 여러 빈도를 동시 등록하면 겹치는 좌표에서
    # 선택이 비결정적이 된다(EAL의 발생확률 입력이 흔들림). 신천과 동일 기준(500년)으로
    # 맞춰 AEP_BY_FREQ_LABEL 기존 매핑을 그대로 재사용(사용자 확인, 2026-08-19).
    FloodShpSource(
        path=RAW_DATA_DIR
        / "행정구역 경상남도 거제시 500년 빈도 지방하천 하천범람지도"
        / "RFM_SGG_RGN_48310_500.shp",
        region_code="48310",
        region_name="거제시",
        river_name="거제시 관내 지방하천(다수)",
        freq_label="500",
    ),
    FloodShpSource(
        path=RAW_DATA_DIR
        / "행정구역 대구광역시 남구 500년 빈도 지방하천 하천범람지도"
        / "RFM_SGG_RGN_27200_500.shp",
        region_code="27200",
        region_name="대구광역시 남구",
        river_name="신천",
        freq_label="500",
    ),
    FloodShpSource(
        path=RAW_DATA_DIR
        / "행정구역 대구광역시 중구 500년 빈도 지방하천 하천범람지도"
        / "RFM_SGG_RGN_27110_500.shp",
        region_code="27110",
        region_name="대구광역시 중구",
        river_name="신천",
        freq_label="500",
    ),
    FloodShpSource(
        path=RAW_DATA_DIR
        / "행정구역 대구광역시 수성구 500년 빈도 지방하천 하천범람지도"
        / "RFM_SGG_RGN_27260_500.shp",
        region_code="27260",
        region_name="대구광역시 수성구",
        river_name="신천",
        freq_label="500",
    ),
    FloodShpSource(
        path=RAW_DATA_DIR
        / "행정구역 대구광역시 동구 500년 빈도 지방하천 하천범람지도"
        / "RFM_SGG_RGN_27140_500.shp",
        region_code="27140",
        region_name="대구광역시 동구",
        river_name="신천",
        freq_label="500",
    ),
    FloodShpSource(
        path=RAW_DATA_DIR
        / "행정구역 대구광역시 북구 500년 빈도 지방하천 하천범람지도"
        / "RFM_SGG_RGN_27230_500.shp",
        region_code="27230",
        region_name="대구광역시 북구",
        river_name="신천",
        freq_label="500",
    ),
]

# 좌표 커버리지 1단 게이트(gis/coverage.py)에서 "로딩 범위 밖" bbox 판정 시 붙이는 여유폭.
# SHP 자체 bbox만 쓰면 폴리곤 바로 바깥 좌표조차 OUT_OF_SCOPE가 되어 tier="원거리" 분류
# 기회를 잃으므로, 행정구역 전체를 대략 감싸는 여유값을 둔다. 값은 잠정치 — Week1 스파이크
# 결과에 따라 조정.
COVERAGE_BBOX_BUFFER_M = 3000.0

DEFAULT_SEARCH_RADIUS_M = 500.0

# Week2 추가 — 건물취약도 에이전트(building/brhub.py)가 호출하는 건축HUB 서비스 경로.
# 라이브 체크포인트로 실호출 확정됨(DEV_LOG.md 2026-08-11 참조) — 더는 TODO 아님.
BR_HUB_BASE_URL = "https://apis.data.go.kr/1613000/BldRgstHubService"

# Week2 추가 — 시나리오 에이전트(scenario/eal.py) 몬테카를로 EAL 기본값.
# HANDOVER.md §4.2 2.4 스펙: 기본 10,000회, 시드 고정 재현성 절대 축소 금지 항목.
DEFAULT_EAL_SEED = 42
DEFAULT_EAL_ITERATIONS = 10000

# Week3 추가 — 큐레이션·합성 데이터·감사로그 경로.
CURATED_DATA_DIR = REPO_ROOT / "data" / "climate-collateral-underwriting-ai" / "curated"
HINNAMNO_TIMELINE_PATH = CURATED_DATA_DIR / "hinnamno_2022" / "events.json"

# Week4 이후 보강 — 포항(냉천) 외 지역(대구 신천) 실측 특보 리플레이 예시.
# region_code=27260(대구 수성구), HANDOVER.md §⑦ PM 항목 B6 해결(DEV_LOG.md 참조).
DAEGU_SUSEONG_2026_TIMELINE_PATH = CURATED_DATA_DIR / "daegu_suseong_2026" / "events.json"

# Week4 이후 보강 — 기상청 라이브 특보 API(advisory/live.py). 2026-08-12 실호출로 엔드포인트·
# 파라미터 확정(DEV_LOG.md 참조): data.go.kr 호스팅, DATA_GO_KR_API_KEY 사용(KMA_API_HUB_KEY
# 아님 — 별도 포털/키), serviceKey는 이미 percent-encoding된 값이므로 재인코딩 금지
# (building/brhub.py의 이중 인코딩 함정과 동일 주의). 과거 6일 초과 조회는 구조적으로 불가능
# (resultCode 99, contest_research 실측 확인) — 라이브 모드는 "지금 시점" 조회 전용이다.
KMA_WTHR_WRN_BASE_URL = "https://apis.data.go.kr/1360000/WthrWrnInfoService/getWthrWrnList"

# region_code(SGG 5자리) -> (기상청 특보구역/관서 stnId, 실경보로 검증됐는지).
# stnId=143(대구)은 2026-08-12 실호출로 전국(108) 피드와 다른 목록을 반환함을 확인해
# "대구 지역 필터로 실제 작동한다"까지 검증됨 — 단 대구 5개구(남구·중구·수성구·동구·북구)를
# API 자체가 더 세분화하지 못해 전부 같은 stnId로 묶인다(신천이 여러 구 경계를 흐르므로 이미
# 예견된 제약, DEV_LOG.md 2026-08-12 참조). 포항(47111)의 stnId=138은 표준 기상청 관측지점
# 번호(포항)를 따른 추정값 — 확인 시점에 활성 특보가 없어 "매핑이 맞다"를 실측으로 증명하지
# 못했다(resultCode 03=NO_DATA는 "특보 없음"과 "잘못된 stnId"를 구분해주지 않는다).
# 2026-08-19 추가 — 거제(48310)의 stnId=159(부산지방기상청). 다른 지역들과 달리 실경보
# 텍스트만으로 검증한 게 아니라, `wrn_met_data.php`(kma_historical.py)에서 거제
# REG_ID(L1082200)의 실제 과거 발효 기록(힌남노 2022-09-06) 자체가 STN=159로 발표된
# 것을 교차 확인했다 — 그래서 verified=True. 같은 날 라이브 조회에서도 stnId=159가
# 실제 활성 폭염주의보(2026-08-19)를 정상 반환함을 재확인.
REGION_CODE_TO_KMA_STN_ID: dict[str, tuple[str, bool]] = {
    "47111": ("138", False),  # 포항 남구 — 미검증(best-effort)
    "48310": ("159", True),  # 거제시
    "27200": ("143", True),  # 대구 남구
    "27110": ("143", True),  # 대구 중구
    "27260": ("143", True),  # 대구 수성구
    "27140": ("143", True),  # 대구 동구
    "27230": ("143", True),  # 대구 북구
}

# 2026-08-19 추가(DEV_LOG.md 참조) — 기상청 API허브(apihub.kma.go.kr)의 "특보자료 API"/
# "특보구역 API". data.go.kr의 WthrWrnInfoService(위 KMA_WTHR_WRN_BASE_URL)와 완전히
# 다른 포털·인증키 체계이며, API마다 개별 "활용신청" 승인이 필요함을 사용자와의 실측
# 조사로 확인했다(계정 키가 있어도 API별로 따로 신청해야 함). 2004-06-30~현재까지의
# 정형 특보 발효/해제 이력을 조회할 수 있어, advisory/live.py의 "6일 초과 과거 조회
# 불가" 한계를 이 API로 우회한다.
KMA_WRN_MET_DATA_URL = "https://apihub.kma.go.kr/api/typ01/url/wrn_met_data.php"
KMA_WRN_REG_URL = "https://apihub.kma.go.kr/api/typ01/url/wrn_reg.php"
PORTFOLIO_DATA_PATH = CURATED_DATA_DIR / "portfolio" / "synthetic_portfolio.json"
AUDIT_LOG_PATH = REPO_ROOT / "data" / "climate-collateral-underwriting-ai" / "audit" / "reviewer_ack_log.jsonl"
ALERT_QUEUE_LOG_PATH = REPO_ROOT / "data" / "climate-collateral-underwriting-ai" / "audit" / "alert_queue_log.jsonl"
# 2026-08-18 추가(DEV_LOG.md 참조) — 라이브 모드 기상청 API 조회 결과를 append-only로
# 적재한다. 기상청 API 자체가 "지금 시점"만 조회 가능(과거 조회 불가, advisory/live.py
# 참조)해서, 이 로그가 쌓여야만 나중에 "이 날짜에 이 지역에 실제로 무슨 특보가 있었는지"를
# 재구성할 수 있다 — 지금 당장 이 로그를 조회하는 UI는 없다(축적만 시작).
ADVISORY_LIVE_LOG_PATH = REPO_ROOT / "data" / "climate-collateral-underwriting-ai" / "audit" / "advisory_live_log.jsonl"

# region_code 역조회(SHP 절대경로 문자열 -> region_code) — portfolio/geocode_cache.py가 홍수
# 에이전트 결과(source_shp_file)에서 포트폴리오 필터링용 region_code를 유도할 때 쓴다. 하드코딩
# 목록을 새로 만들지 않고 FLOOD_SHP_SOURCES 하나만 진실의 원천으로 유지 — gis/loader.py가
# source_file=str(source.path)(절대경로 전체)로 태깅하므로 키도 동일하게 str(path)를 쓴다.
SHP_FILENAME_TO_REGION_CODE: dict[str, str] = {
    str(src.path): src.region_code for src in FLOOD_SHP_SOURCES
}

# Week3 추가 — 재심사 알림 임계치·인용실패율 폴백 컷.
# HANDOVER.md §4.6 항목7·§4.2 2.5: 둘 다 "구체 수치 잠정 미정, 실측 데이터로 캘리브레이션 필요"라고
# 명시된 잠정치다. Week2의 w1~w4·AEP_BY_FREQ_LABEL과 동일한 패턴 — 이름 붙은 상수로 노출해
# 나중에 실측 골든셋으로 캘리브레이션할 자리를 코드에 선점해둔다.
EAL_ALERT_THRESHOLD_PCT = 0.20  # 잠정치 — EAL 변화율이 이 값 이상이면 재심사 알림 큐에 등재
CITATION_FAILURE_FALLBACK_THRESHOLD = 0.30  # 잠정치 — HANDOVER §4.2 2.5 "예 30%"

MEMO_SCHEMA_PATH = (
    Path(__file__).resolve().parent / "llm" / "schemas" / "memo_sections.schema.json"
)
