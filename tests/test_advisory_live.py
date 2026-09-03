"""라이브 기상청 특보 API(advisory/live.py) — 2026-08-12 실호출로 확정된 스펙(DEV_LOG.md
참조)대로 응답을 파싱하는지 네트워크 없이 검증한다. `_fetch_kma_json`이 유일한 HTTP 호출
지점(seam)이라 이 함수만 monkeypatch하면 실제 API를 부르지 않고도 파싱·상태 판정 로직을
검증할 수 있다."""

from climate_risk.advisory import live


def _fake_response(items):
    return {
        "response": {
            "header": {"resultCode": "00", "resultMsg": "NORMAL_SERVICE"},
            "body": {"dataType": "JSON", "items": {"item": items}, "pageNo": 1, "numOfRows": 50, "totalCount": len(items)},
        }
    }


def test_unknown_region_returns_unknown_region_status_without_calling_api(monkeypatch):
    def _boom(stn_id):
        raise AssertionError("매핑 없는 지역은 API를 호출하면 안 됨")

    monkeypatch.setattr(live, "_fetch_kma_json", _boom)

    result = live.run_live_query(region_code="00000")

    assert result.status == live.STATUS_UNKNOWN_REGION
    assert result.events == []
    assert result.stn_id is None


def test_no_data_result_code_returns_ok_with_empty_events(monkeypatch):
    """resultCode 03(NO_DATA)은 "특보 없음"의 정상 상태 — 에러로 취급하지 않는다."""
    monkeypatch.setattr(
        live, "_fetch_kma_json", lambda stn_id: {"response": {"header": {"resultCode": "03", "resultMsg": "NO_DATA"}}}
    )

    result = live.run_live_query(region_code="27260")

    assert result.status == live.STATUS_OK
    assert result.events == []
    assert result.stn_id == "143"
    assert result.stn_id_verified is True


def test_real_daegu_suseong_title_shape_parses_into_advisory_event(monkeypatch):
    """2026-08-12 실호출로 확인한 실제 title 형식 — DEV_LOG.md 참조."""
    items = [
        {"stnId": "143", "title": "[특보] 제08-43호 : 2026.08.12.06:00 / 풍랑주의보 발표 (*)", "tmFc": 202608120600, "tmSeq": 43},
        {"stnId": "143", "title": "[특보] 제08-42호 : 2026.08.12.04:00 / 강풍주의보·풍랑주의보 발표 (*)", "tmFc": 202608120400, "tmSeq": 42},
    ]
    monkeypatch.setattr(live, "_fetch_kma_json", lambda stn_id: _fake_response(items))

    result = live.run_live_query(region_code="27260")

    assert result.status == live.STATUS_OK
    assert len(result.events) == 2
    first = result.events[0]
    assert first.event_type == "특보"
    assert first.warning_type == "풍랑주의보 발표"
    assert first.issued_at == "2026-08-12T06:00:00+09:00"
    assert first.time_precision == "exact"
    assert first.source_url.startswith("http")
    assert first.event_id == "kma-live-143-43"
    # 2026-09-03(계속10): 실시간 모드도 등급을 채워 재심사 지역 트리거가 동작한다
    assert first.severity_level == "주의보"


def test_unparseable_title_falls_back_to_raw_text(monkeypatch):
    items = [{"stnId": "143", "title": "형식이 다른 임의의 특보 문자열", "tmFc": 202608120600, "tmSeq": 1}]
    monkeypatch.setattr(live, "_fetch_kma_json", lambda stn_id: _fake_response(items))

    result = live.run_live_query(region_code="27260")

    assert result.events[0].warning_type == "형식이 다른 임의의 특보 문자열"


def test_upstream_network_error_returns_upstream_error_not_silently_empty(monkeypatch):
    import urllib.error

    def _raise(stn_id):
        raise urllib.error.URLError("연결 실패")

    monkeypatch.setattr(live, "_fetch_kma_json", _raise)

    result = live.run_live_query(region_code="27260")

    assert result.status == live.STATUS_UPSTREAM_ERROR
    assert result.events == []


def test_non_ok_non_no_data_result_code_returns_upstream_error(monkeypatch):
    """6일 초과 과거 조회 등 resultCode 99 같은 비정상 응답 — 조용히 빈 결과로 두지 않는다."""
    monkeypatch.setattr(
        live, "_fetch_kma_json", lambda stn_id: {"response": {"header": {"resultCode": "99", "resultMsg": "APPLICATION_ERROR"}}}
    )

    result = live.run_live_query(region_code="27260")

    assert result.status == live.STATUS_UPSTREAM_ERROR


def test_unverified_region_mapping_surfaces_in_note(monkeypatch):
    monkeypatch.setattr(live, "_fetch_kma_json", lambda stn_id: _fake_response([]))

    result = live.run_live_query(region_code="47111")  # 포항 — stn_id_verified=False

    assert result.stn_id == "138"


def test_geoje_region_maps_to_busan_regional_office_verified(monkeypatch):
    """2026-08-19 추가 — 거제(48310)는 wrn_met_data.php의 실제 과거 발효 기록(힌남노
    2022-09-06, REG_ID=L1082200)에서 STN=159로 확인돼 verified=True(포항과 달리
    추정치가 아님, DEV_LOG.md 참조)."""
    monkeypatch.setattr(live, "_fetch_kma_json", lambda stn_id: _fake_response([]))

    result = live.run_live_query(region_code="48310")

    assert result.stn_id == "159"
    assert result.stn_id_verified is True


def test_live_severity_level_parsed_from_title_detail(monkeypatch):
    items = [
        {"stnId": "143", "title": "[특보] 제08-50호 : 2026.07.17.21:50 / 호우경보 변경 (*)", "tmFc": 202607172150, "tmSeq": 50},
        {"stnId": "143", "title": "[특보] 제08-51호 : 2026.08.25.10:00 / 폭염경보 변경·폭염주의보·열대야주의보 발표 (*)", "tmFc": 202608251000, "tmSeq": 51},
        {"stnId": "143", "title": "제목 형식이 다른 항목", "tmFc": 202608251100, "tmSeq": 52},
    ]
    monkeypatch.setattr(live, "_fetch_kma_json", lambda stn_id: _fake_response(items))
    result = live.run_live_query(region_code="27260")
    levels = [e.severity_level for e in result.events]
    assert levels == ["경보", "경보", None]
    from climate_risk.agents.advisory_agent import is_high_severity_event
    assert [is_high_severity_event(e) for e in result.events] == [True, False, False]  # 호우경보만 트리거
