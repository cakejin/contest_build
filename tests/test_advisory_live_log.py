"""advisory/live_log.py — 라이브 특보 조회 결과 append-only 로그 회귀 테스트.

DEV_LOG.md 2026-08-18 참조 — 기상청 API가 과거 조회를 지원하지 않아, 이 로그가
축적돼야만 나중에 날짜 기반 리플레이의 원자료가 된다.
"""

from climate_risk.advisory.live import LiveQueryResult
from climate_risk.advisory.live_log import append_live_query_log, read_live_advisory_log
from climate_risk.advisory.schema import AdvisoryEvent


def _event(event_id="e1") -> AdvisoryEvent:
    return AdvisoryEvent(
        event_id=event_id,
        issued_at="2026-08-12T06:00:00+09:00",
        time_precision="exact",
        event_type="특보",
        warning_type="풍랑주의보 발표",
        description="[특보] 풍랑주의보 발표",
        source_url="https://www.weather.go.kr/w/special-report/overall.do",
        target_region_text="기상청 특보구역 stnId=143",
    )


def test_append_and_read_round_trip(tmp_path):
    log_path = tmp_path / "live_log.jsonl"
    result = LiveQueryResult(
        status="OK", events=[_event()], stn_id="143", stn_id_verified=True, note=""
    )

    append_live_query_log("27260", result, trigger_event=True, log_path=log_path)

    entries = read_live_advisory_log(log_path)
    assert len(entries) == 1
    entry = entries[0]
    assert entry.region_code == "27260"
    assert entry.stn_id == "143"
    assert entry.stn_id_verified is True
    assert entry.status == "OK"
    assert entry.trigger_event is True
    assert entry.events[0]["event_id"] == "e1"
    assert entry.queried_at  # ISO8601 타임스탬프가 채워짐


def test_multiple_appends_accumulate_in_order(tmp_path):
    log_path = tmp_path / "live_log.jsonl"
    empty = LiveQueryResult(status="OK", events=[], stn_id="143", stn_id_verified=True, note="특보 없음")

    append_live_query_log("27260", empty, trigger_event=False, log_path=log_path)
    append_live_query_log("47111", empty, trigger_event=False, log_path=log_path)

    entries = read_live_advisory_log(log_path)
    assert [e.region_code for e in entries] == ["27260", "47111"]


def test_read_missing_log_returns_empty_list(tmp_path):
    assert read_live_advisory_log(tmp_path / "does_not_exist.jsonl") == []
