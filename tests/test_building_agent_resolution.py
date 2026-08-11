"""agents/building_agent.py 오케스트레이션 검증 — 실네트워크 호출 없이 monkeypatch.

라이브 API 정합성 자체는 DEV_LOG.md 2026-08-11 체크포인트에서 실호출로 이미 확인됨
(building/address_resolver.py, building/brhub.py 참조). 여기서는 실패 상태 변환
규약(resolve_admin_codes 실패→FAILED, BrHubError→FAILED, 정상 응답→스코어링)만
검증한다.
"""

from climate_risk.agents import building_agent as building_agent_module
from climate_risk.agents.building_agent import run_building_agent
from climate_risk.building.address_resolver import AdminCodeMatch, resolve_from_pnu
from climate_risk.building.brhub import BrHubError, BrTitleInfo
from climate_risk.building.vulnerability import STATUS_FAILED, STATUS_OK
from climate_risk.geocoding.vworld import VWorldGeocodeError

VALID_PNU = "4711111200002220005"  # sigungu=47111 bjdong=11200 platGb=0 bun=0222 ji=0005

ADMIN = AdminCodeMatch(
    sigungu_cd="47111",
    bjdong_cd="11200",
    plat_gb_cd="0",
    bun="0222",
    ji="0005",
    resolution_path="TEST",
    source_id="test",
)


def test_pnu_shortcut_parses_without_network_calls():
    admin = resolve_from_pnu(VALID_PNU)
    assert admin.sigungu_cd == "47111"
    assert admin.bjdong_cd == "11200"
    assert admin.plat_gb_cd == "0"
    assert admin.bun == "0222"
    assert admin.ji == "0005"


def test_resolution_failure_returns_failed_status_not_exception(monkeypatch):
    monkeypatch.setattr(building_agent_module, "resolve_admin_codes", lambda **kwargs: None)

    result = run_building_agent(address="존재하지않는주소")

    assert result.status == STATUS_FAILED
    assert result.vulnerability_score is None
    assert result.source_id == "building:resolution_failed"


def test_brhub_error_is_caught_and_translated_to_failed(monkeypatch):
    monkeypatch.setattr(building_agent_module, "resolve_admin_codes", lambda **kwargs: ADMIN)

    def _raise(admin):
        raise BrHubError("resultCode=99 시뮬레이션")

    monkeypatch.setattr(building_agent_module, "fetch_br_title_info", _raise)

    result = run_building_agent(address="아무주소")

    assert result.status == STATUS_FAILED
    assert result.vulnerability_score is None
    assert result.source_id == "building:4711111200002220005"


def test_successful_resolution_and_fetch_produces_scored_output(monkeypatch):
    monkeypatch.setattr(building_agent_module, "resolve_admin_codes", lambda **kwargs: ADMIN)
    monkeypatch.setattr(
        building_agent_module,
        "fetch_br_title_info",
        lambda admin: BrTitleInfo(
            strct_cd_nm="철근콘크리트구조",
            main_purps_cd_nm="공동주택",
            ugrnd_flr_cnt=1,
            grnd_flr_cnt=5,
            use_apr_day="20160913",
            raw={},
        ),
    )

    result = run_building_agent(address="아무주소", as_of_year=2026)

    assert result.status == STATUS_OK
    assert result.vulnerability_score is not None
    assert result.source_id == "building:4711111200002220005"
    assert result.missing_fields == []


def test_resolution_api_error_returns_failed_status_not_exception(monkeypatch):
    """resolve_admin_codes()가 None이 아니라 예외(V-World 상태 오류 등)로 실패해도
    파이프라인이 죽지 않고 FAILED로 변환돼야 한다(리뷰 발견 항목 회귀 고정)."""

    def _raise(**kwargs):
        raise VWorldGeocodeError("status=ERROR 시뮬레이션")

    monkeypatch.setattr(building_agent_module, "resolve_admin_codes", _raise)

    result = run_building_agent(address="아무주소")

    assert result.status == STATUS_FAILED
    assert result.vulnerability_score is None
    assert result.source_id == "building:resolution_failed"


def test_fetch_network_error_returns_failed_status_not_exception(monkeypatch):
    """fetch_br_title_info()가 BrHubError가 아니라 네트워크 계열 예외(OSError — URLError·
    timeout의 상위 클래스)로 실패해도 FAILED로 변환돼야 한다(리뷰 발견 항목 회귀 고정)."""
    monkeypatch.setattr(building_agent_module, "resolve_admin_codes", lambda **kwargs: ADMIN)

    def _raise(admin):
        raise OSError("네트워크 타임아웃 시뮬레이션")

    monkeypatch.setattr(building_agent_module, "fetch_br_title_info", _raise)

    result = run_building_agent(address="아무주소")

    assert result.status == STATUS_FAILED
    assert result.vulnerability_score is None
    assert result.source_id == "building:4711111200002220005"


def test_no_building_record_produces_failed_not_midpoint(monkeypatch):
    """fetch_br_title_info가 None(레코드 없음)을 반환해도 조용히 중간값을 만들지
    않고 compute_vulnerability의 전항목결측 FAILED 상태를 그대로 물려받아야 한다."""
    monkeypatch.setattr(building_agent_module, "resolve_admin_codes", lambda **kwargs: ADMIN)
    monkeypatch.setattr(building_agent_module, "fetch_br_title_info", lambda admin: None)

    result = run_building_agent(address="건물없는지번", as_of_year=2026)

    assert result.status == STATUS_FAILED
    assert result.vulnerability_score is None
