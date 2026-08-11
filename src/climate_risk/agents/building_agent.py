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
from dataclasses import dataclass

from climate_risk.building.address_resolver import AdminCodeMatch, resolve_admin_codes
from climate_risk.building.brhub import BrHubError, BrTitleInfo, fetch_br_title_info
from climate_risk.building.vulnerability import (
    STATUS_FAILED,
    BuildingVulnerabilityResult,
    VulnerabilityFactor,
    compute_vulnerability,
)
from climate_risk.geocoding.vworld import VWorldGeocodeError

_RESOLUTION_FAILED_NOTE = "주소/좌표에서 건축물대장 조회 코드를 해석하지 못했습니다"
_RESOLUTION_API_ERROR_NOTE = "주소/좌표 해석 중 외부 API 호출 실패 — 건물 정보 미확인"
_API_ERROR_NOTE = "건축HUB API 호출 실패 — 건물 정보 미확인"
_RESOLUTION_FAILED_SOURCE_ID = "building:resolution_failed"

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


def _admin_source_id(admin: AdminCodeMatch) -> str:
    return f"building:{admin.sigungu_cd}{admin.bjdong_cd}{admin.plat_gb_cd}{admin.bun}{admin.ji}"


def _from_vulnerability_result(
    result: BuildingVulnerabilityResult, source_id: str
) -> BuildingAgentOutput:
    return BuildingAgentOutput(
        vulnerability_score=result.vulnerability_score,
        contributing_factors=result.contributing_factors,
        source=result.source,
        source_id=source_id,
        missing_fields=result.missing_fields,
        status=result.status,
        note=result.note,
    )


def run_building_agent(
    address: str | None = None,
    lat: float | None = None,
    lon: float | None = None,
    pnu: str | None = None,
    as_of_year: int | None = None,
) -> BuildingAgentOutput:
    if as_of_year is None:
        as_of_year = datetime.date.today().year

    try:
        admin = resolve_admin_codes(lat=lat, lon=lon, address=address, pnu=pnu)
    except _EXPECTED_API_FAILURES:
        return BuildingAgentOutput(
            vulnerability_score=None,
            contributing_factors=[],
            source="",
            source_id=_RESOLUTION_FAILED_SOURCE_ID,
            missing_fields=["전체"],
            status=STATUS_FAILED,
            note=_RESOLUTION_API_ERROR_NOTE,
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
        )

    source_id = _admin_source_id(admin)

    try:
        info: BrTitleInfo | None = fetch_br_title_info(admin)
    except _EXPECTED_API_FAILURES:
        return BuildingAgentOutput(
            vulnerability_score=None,
            contributing_factors=[],
            source="",
            source_id=source_id,
            missing_fields=["전체"],
            status=STATUS_FAILED,
            note=_API_ERROR_NOTE,
        )

    vuln = compute_vulnerability(
        strct_cd_nm=info.strct_cd_nm if info else None,
        ugrnd_flr_cnt=info.ugrnd_flr_cnt if info else None,
        use_apr_day=info.use_apr_day if info else None,
        main_purps_cd_nm=info.main_purps_cd_nm if info else None,
        as_of_year=as_of_year,
    )
    return _from_vulnerability_result(vuln, source_id)
