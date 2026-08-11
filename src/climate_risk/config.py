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
