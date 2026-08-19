import json

import pytest

from climate_risk.advisory import live
from climate_risk.agents.advisory_agent import (
    STATUS_LIVE_UPSTREAM_ERROR,
    STATUS_NO_CURATED_DATA_FOR_REGION,
    STATUS_OK,
    run_advisory_agent,
)
from climate_risk.config import DAEGU_SUSEONG_2026_TIMELINE_PATH, HINNAMNO_TIMELINE_PATH


def test_replay_mode_against_real_hinnamno_data():
    output = run_advisory_agent(region_code="47111", mode="replay", timeline_path=HINNAMNO_TIMELINE_PATH)

    assert output.status == STATUS_OK
    assert output.trigger_event is True  # 특보/재난문자 이벤트가 실제 데이터에 존재
    assert len(output.active_warnings) == 7
    assert all(w["source_url"].startswith("http") for w in output.active_warnings)


def test_replay_mode_against_real_daegu_suseong_data():
    """포항(냉천) 외 지역 리플레이 예시 — 2026-07 대구 수성구 집중호우.
    HANDOVER.md §⑦ PM 항목 B6 해결, DEV_LOG.md 참조."""
    output = run_advisory_agent(
        region_code="27260", mode="replay", timeline_path=DAEGU_SUSEONG_2026_TIMELINE_PATH
    )

    assert output.status == STATUS_OK
    assert output.trigger_event is True  # 산사태주의보·호우특보 해제·재난문자 이벤트가 실제 데이터에 존재
    assert len(output.active_warnings) == 7
    assert all(w["source_url"].startswith("http") for w in output.active_warnings)


def test_replay_mode_region_mismatch_returns_no_curated_data(tmp_path):
    path = tmp_path / "timeline.json"
    path.write_text(
        json.dumps(
            {
                "event_name": "테스트",
                "region_code": "99999",
                "region_name": "테스트",
                "disclaimer": "테스트",
                "events": [],
            }
        ),
        encoding="utf-8",
    )

    output = run_advisory_agent(region_code="47111", mode="replay", timeline_path=path)

    assert output.status == STATUS_NO_CURATED_DATA_FOR_REGION
    assert output.trigger_event is False
    assert output.active_warnings == []


def test_live_mode_unmapped_region_returns_no_curated_data_status(monkeypatch, tmp_path):
    def _boom(region_code):
        raise AssertionError("매핑 없는 지역은 fetch까지 가면 안 됨")

    monkeypatch.setattr(live, "_fetch_kma_json", _boom)

    output = run_advisory_agent(
        region_code="00000", mode="live", live_log_path=tmp_path / "live_log.jsonl"
    )

    assert output.status == STATUS_NO_CURATED_DATA_FOR_REGION
    assert output.trigger_event is False


def test_live_mode_upstream_error_returns_explicit_status_not_silent_false(monkeypatch, tmp_path):
    """API 호출 자체가 실패해도 조용히 '안전'으로 처리하지 않고 명시적 상태를 반환한다
    (설계원칙1 "데이터 없음≠위험 없음"과 같은 정신)."""

    def _raise(stn_id):
        raise TimeoutError("network down")

    monkeypatch.setattr(live, "_fetch_kma_json", _raise)

    output = run_advisory_agent(
        region_code="27260", mode="live", live_log_path=tmp_path / "live_log.jsonl"
    )

    assert output.status == STATUS_LIVE_UPSTREAM_ERROR
    assert output.trigger_event is False


def test_live_mode_wires_real_events_into_trigger_event(monkeypatch, tmp_path):
    monkeypatch.setattr(
        live,
        "_fetch_kma_json",
        lambda stn_id: {
            "response": {
                "header": {"resultCode": "00", "resultMsg": "NORMAL_SERVICE"},
                "body": {
                    "items": {
                        "item": [
                            {
                                "stnId": "143",
                                "title": "[특보] 제08-43호 : 2026.08.12.06:00 / 풍랑주의보 발표 (*)",
                                "tmFc": 202608120600,
                                "tmSeq": 43,
                            }
                        ]
                    }
                },
            }
        },
    )

    output = run_advisory_agent(
        region_code="27260", mode="live", live_log_path=tmp_path / "live_log.jsonl"
    )

    assert output.status == STATUS_OK
    assert output.trigger_event is True
    assert output.mode == "live"
    assert len(output.active_warnings) == 1
    assert output.source_id == "advisory:live:kma:stnId=143"


def test_live_mode_appends_query_to_live_log(monkeypatch, tmp_path):
    """HANDOVER §⑧ 이후 논의(DEV_LOG.md 2026-08-18) — 라이브 조회는 매번 로그에 남아야
    나중에 날짜 기반 리플레이를 만들 원자료가 쌓인다."""
    from climate_risk.advisory.live_log import read_live_advisory_log

    monkeypatch.setattr(
        live,
        "_fetch_kma_json",
        lambda stn_id: {
            "response": {
                "header": {"resultCode": "00", "resultMsg": "NORMAL_SERVICE"},
                "body": {
                    "items": {
                        "item": [
                            {
                                "stnId": "143",
                                "title": "[특보] 제08-43호 : 2026.08.12.06:00 / 풍랑주의보 발표 (*)",
                                "tmFc": 202608120600,
                                "tmSeq": 43,
                            }
                        ]
                    }
                },
            }
        },
    )
    log_path = tmp_path / "live_log.jsonl"

    run_advisory_agent(region_code="27260", mode="live", live_log_path=log_path)

    entries = read_live_advisory_log(log_path)
    assert len(entries) == 1
    assert entries[0].region_code == "27260"
    assert entries[0].trigger_event is True
    assert entries[0].status == STATUS_OK
    assert len(entries[0].events) == 1


def test_live_mode_upstream_error_is_also_logged(monkeypatch, tmp_path):
    """조회가 실패해도 "실패했다"는 사실 자체를 정직하게 로그에 남긴다(설계원칙1과 같은 정신)."""
    from climate_risk.advisory.live_log import read_live_advisory_log

    def _raise(stn_id):
        raise TimeoutError("network down")

    monkeypatch.setattr(live, "_fetch_kma_json", _raise)
    log_path = tmp_path / "live_log.jsonl"

    run_advisory_agent(region_code="27260", mode="live", live_log_path=log_path)

    entries = read_live_advisory_log(log_path)
    assert len(entries) == 1
    # 로그는 advisory_agent가 번역한 상태(STATUS_LIVE_UPSTREAM_ERROR)가 아니라
    # advisory/live.py의 원시 LiveQueryResult.status를 그대로 남긴다 — 원자료 보존.
    assert entries[0].status == live.STATUS_UPSTREAM_ERROR
    assert entries[0].trigger_event is False
    assert entries[0].events == []


def test_unknown_mode_raises_value_error(tmp_path):
    path = tmp_path / "timeline.json"
    path.write_text(
        json.dumps(
            {"event_name": "x", "region_code": "47111", "region_name": "x", "disclaimer": "x", "events": []}
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError):
        run_advisory_agent(region_code="47111", mode="bogus", timeline_path=path)
