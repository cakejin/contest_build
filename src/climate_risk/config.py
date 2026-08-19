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

RAW_DATA_DIR = REPO_ROOT / "data" / "climate-collateral-underwriting-ai" / "raw"

FLOOD_MAP_SOURCE_CRS = "EPSG:5186"  # KGD2002 중부원점 2010 — 원본 SHP 좌표계 그대로 보관
LICENSE_LABEL = "환경부 홍수위험지도, 공공누리 4유형(출처표시·상업이용 금지·변경금지)"


@dataclass(frozen=True)
class FloodShpSource:
    path: Path
    region_code: str  # dbf SGG_CD와 일치 (로더에서 교차검증)
    region_name: str
    river_name: str
    freq_label: str  # dbf FLDLV_FREQ와 일치


# 6개 SHP 전량 — 냉천(포항시 남구, 기왕최대) + 신천(대구 5개구, 500년)
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
REGION_CODE_TO_KMA_STN_ID: dict[str, tuple[str, bool]] = {
    "47111": ("138", False),  # 포항 남구 — 미검증(best-effort)
    "27200": ("143", True),  # 대구 남구
    "27110": ("143", True),  # 대구 중구
    "27260": ("143", True),  # 대구 수성구
    "27140": ("143", True),  # 대구 동구
    "27230": ("143", True),  # 대구 북구
}
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
