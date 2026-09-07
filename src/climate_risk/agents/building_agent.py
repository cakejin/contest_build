"""건물취약도 에이전트 — HANDOVER.md §4.2 2.3. 해석→조회→스코어링 오케스트레이션.

이 모듈 자체는 판정 로직을 갖지 않는다 — building/address_resolver.py(코드 해석),
building/brhub.py(원자료 조회), building/vulnerability.py(스코어링) 세 순수 모듈을
순서대로 호출하고, 실패 상태를 gis 에이전트와 동일한 관례로 번역할 뿐이다:

- 코드 해석 자체가 안 되면(resolve_admin_codes -> None) "예상된 부재" — 예외 아님.
- 건축HUB API가 비정상 응답(BrHubError)을 내면 여기서 캐치해 FAILED 상태로 변환한다
  (예외를 파이프라인까지 전파시켜 그래프 전체를 죽이지 않는다 — "데이터 없음≠위험
  없음"과 마찬가지로 "API 장애≠위험 없음"이어야 하며, 동시에 파이프라인이 그 때문에
  통째로 죽어서도 안 된다).
- 건축물대장 레코드 자체가 없으면(fetch_br_title_info -> None) compute_vulnerability가
  네 항목 전부 결측으로 처리해 이미 FAILED+"부분 스코어 불가" 결과를 반환한다 — 여기서
  별도 분기를 만들 필요가 없다(vulnerability.py가 이미 그 상태를 표현한다).
"""

from __future__ import annotations

import datetime
import logging
from dataclasses import dataclass

from climate_risk.agents.flood_agent import FloodAgentOutput
from climate_risk.building.address_resolver import AdminCodeMatch, resolve_admin_codes
from climate_risk.building.brhub import BrHubError, BrTitleInfo, fetch_br_title_info
from climate_risk.building.vulnerability import (
    STATUS_FAILED,
    BuildingVulnerabilityResult,
    VulnerabilityFactor,
    compute_vulnerability,
)
from climate_risk.geocoding.vworld import VWorldGeocodeError
from climate_risk.scenario.floor_exposure import FloorExposureResult, determine_floor_flood_exposure

_RESOLUTION_FAILED_NOTE = "주소/좌표에서 건축물대장 조회 코드를 해석하지 못했습니다"
_RESOLUTION_API_ERROR_NOTE = "주소/좌표 해석 중 외부 API 호출 실패 — 건물 정보 미확인"
_API_ERROR_NOTE = "건축HUB API 호출 실패 — 건물 정보 미확인"
_RESOLUTION_FAILED_SOURCE_ID = "building:resolution_failed"

# 2026-09-07 — 실패 사유가 화면·서버 로그 어디에도 안 남아 "건물취약도가 안 나온다"를 재현·구분할
# 수 없었다(사용자 리포트: COL-004 2022-09-06, 재현 3회는 전부 정상). 캐치한 예외를 note 뒤에
# 덧붙이고 warning 로그로도 남긴다 — FAILED 상태 자체의 의미·처리 흐름은 그대로다.
_log = logging.getLogger(__name__)


def _failure_note(base: str, exc: Exception) -> str:
    detail = f"{type(exc).__name__}: {exc}"
    _log.warning("building agent FAILED — %s (%s)", base, detail)
    return f"{base} ({detail})"

# resolve_admin_codes()·fetch_br_title_info()가 "예상된 부재"(None)가 아니라
# 예외로 실패하는 경우 — V-World/건축HUB 상태 오류(VWorldGeocodeError/BrHubError),
# 네트워크 장애(URLError·timeout, 둘 다 OSError 하위), 응답 파싱 실패(JSONDecodeError는
# ValueError 하위, 예상 키 누락은 KeyError), 입력 형식 오류(resolve_from_pnu의 ValueError).
# 이 전부를 캐치해 FAILED로 변환한다 — 모듈 docstring의 "API 장애≠위험 없음, 파이프라인이
# 그 때문에 통째로 죽어서도 안 된다" 원칙 그대로.
_EXPECTED_API_FAILURES: tuple[type[Exception], ...] = (
    BrHubError,
    VWorldGeocodeError,
    OSError,
    ValueError,
    KeyError,
)


@dataclass(frozen=True)
class BuildingAgentOutput:
    vulnerability_score: float | None
    contributing_factors: list[VulnerabilityFactor]
    source: str
    source_id: str
    missing_fields: list[str]
    status: str  # "OK" | "PARTIAL" | "FAILED"
    note: str | None
    # HANDOVER.md §⑧(층별 리스크 차등화, 2026-08-18 추가) — target_floor 미입력 시 None
    # (기존 건물 전체 스코어링 경로는 이 필드와 무관하게 그대로 동작한다).
    floor_exposure: FloorExposureResult | None = None


def _admin_source_id(admin: AdminCodeMatch) -> str:
    return f"building:{admin.sigungu_cd}{admin.bjdong_cd}{admin.plat_gb_cd}{admin.bun}{admin.ji}"


def _from_vulnerability_result(
    result: BuildingVulnerabilityResult, source_id: str, floor_exposure: FloorExposureResult | None
) -> BuildingAgentOutput:
    return BuildingAgentOutput(
        vulnerability_score=result.vulnerability_score,
        contributing_factors=result.contributing_factors,
        source=result.source,
        source_id=source_id,
        missing_fields=result.missing_fields,
        status=result.status,
        note=result.note,
        floor_exposure=floor_exposure,
    )


def _compute_floor_exposure(
    target_floor: dict | None, flood: FloodAgentOutput | None
) -> FloorExposureResult | None:
    """target_floor 미입력이면 이 기능 자체를 안 쓴다는 뜻이라 None(필드 생략과 동일
    의미) — flood_exposure.py를 호출조차 하지 않는다. flood가 없는데 target_floor만
    있는 경우는 호출자 실수이므로 coverage="OUT_OF_SCOPE"와 동일하게 안전축으로
    처리한다(건물 전체 스코어로 폴백)."""
    if target_floor is None:
        return None
    coverage = flood.flood.coverage if flood is not None else "OUT_OF_SCOPE"
    depth_class = flood.flood.seg_code if flood is not None else None
    building_tier = flood.flood.tier if flood is not None else None
    return determine_floor_flood_exposure(
        floor_type=target_floor.get("floor_type"),
        floor_no=target_floor.get("floor_no"),
        depth_class=depth_class,
        building_tier=building_tier,
        coverage=coverage,
    )


def run_building_agent(
    address: str | None = None,
    lat: float | None = None,
    lon: float | None = None,
    pnu: str | None = None,
    as_of_year: int | None = None,
    target_floor: dict | None = None,
    flood: FloodAgentOutput | None = None,
) -> BuildingAgentOutput:
    if as_of_year is None:
        as_of_year = datetime.date.today().year

    floor_exposure = _compute_floor_exposure(target_floor, flood)

    try:
        admin = resolve_admin_codes(lat=lat, lon=lon, address=address, pnu=pnu)
    except _EXPECTED_API_FAILURES as exc:
        return BuildingAgentOutput(
            vulnerability_score=None,
            contributing_factors=[],
            source="",
            source_id=_RESOLUTION_FAILED_SOURCE_ID,
            missing_fields=["전체"],
            status=STATUS_FAILED,
            note=_failure_note(_RESOLUTION_API_ERROR_NOTE, exc),
            floor_exposure=floor_exposure,
        )
    if admin is None:
        return BuildingAgentOutput(
            vulnerability_score=None,
            contributing_factors=[],
            source="",
            source_id=_RESOLUTION_FAILED_SOURCE_ID,
            missing_fields=["전체"],
            status=STATUS_FAILED,
            note=_RESOLUTION_FAILED_NOTE,
            floor_exposure=floor_exposure,
        )

    source_id = _admin_source_id(admin)

    try:
        info: BrTitleInfo | None = fetch_br_title_info(admin)
    except _EXPECTED_API_FAILURES as exc:
        return BuildingAgentOutput(
            vulnerability_score=None,
            contributing_factors=[],
            source="",
            source_id=source_id,
            missing_fields=["전체"],
            status=STATUS_FAILED,
            note=_failure_note(_API_ERROR_NOTE, exc),
            floor_exposure=floor_exposure,
        )

    vuln = compute_vulnerability(
        strct_cd_nm=info.strct_cd_nm if info else None,
        ugrnd_flr_cnt=info.ugrnd_flr_cnt if info else None,
        use_apr_day=info.use_apr_day if info else None,
        main_purps_cd_nm=info.main_purps_cd_nm if info else None,
        as_of_year=as_of_year,
    )
    return _from_vulnerability_result(vuln, source_id, floor_exposure)
