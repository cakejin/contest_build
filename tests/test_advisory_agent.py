import json
import urllib.error
from datetime import datetime, timedelta, timezone

import pytest

from climate_risk.advisory import kma_historical, live
from climate_risk.agents.advisory_agent import (
    STATUS_HISTORICAL_ACTIVATION_REQUIRED,
    STATUS_HISTORICAL_NO_ZONE_MATCH,
    STATUS_HISTORICAL_UPSTREAM_ERROR,
    STATUS_LIVE_UPSTREAM_ERROR,
    STATUS_NO_CURATED_DATA_FOR_REGION,
    STATUS_OK,
    run_advisory_agent,
)
from climate_risk.config import DAEGU_SUSEONG_2026_TIMELINE_PATH, HINNAMNO_TIMELINE_PATH

_KST = timezone(timedelta(hours=9))

# test_kma_historical.py의 실측 캡처 발췌본과 동일한 최소 fixture(대구 수성구 2026-07
# 호우, 개편 후 REG_ID) — 그 파일의 파싱 회귀와는 별개로, advisory_agent가 이 데이터를
# AdvisoryEvent로 올바르게 번역하는지만 검증한다.
_HIST_REG_SAMPLE = """#START7777
# REG_ID TM_ST        TM_ED        REG_SP   REG_UP   REG_KO---------------------------------- REG_NAME
L1140000 200507010000 210012310000 00000002 00000000 대구                                     대구광역시
L1140100 202605311330 210012310000 00000013 L1140000 대구중부                                 대구중부
"""

_HIST_MET_DATA_SAMPLE = """#START7777
#      TM_FC,        TM_EF,        TM_IN, STN,   REG_ID, WRN, LVL, CMD, GRD, CNT,   RPT, =
202607171720, 202607171720, 202607171717, 143, L1140100,   R,   2,   1,  00,   4,   101, =
202607172150, 202607172150, 202607172147, 143, L1140100,   R,   3,   6,  00,   4,   101, =
202607180030, 202607180030, 202607180010, 143, L1140100,   R,   2,   3,  00,   4,   101, =
"""


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


def test_historical_mode_requires_start_and_end():
    with pytest.raises(ValueError):
        run_advisory_agent(region_code="27260", mode="historical")


def test_historical_mode_wires_real_events_into_trigger_event(monkeypatch):
    monkeypatch.setattr(kma_historical, "_fetch_wrn_reg_raw", lambda: _HIST_REG_SAMPLE.encode("euc-kr"))
    monkeypatch.setattr(
        kma_historical,
        "_fetch_wrn_met_data_raw",
        lambda reg_id, start, end: _HIST_MET_DATA_SAMPLE.encode("euc-kr"),
    )

    # 큐레이션 겹침 병합(_overlapping_curated_events) 테스트는 별도 케이스로 분리했으니
    # 여기선 일부러 큐레이션 윈도우(2026-07-16~20) 밖 날짜를 써서 KMA 단독 결과만 검증한다.
    # (fixture의 L1140100 구역은 2026-05-31 개편 이후부터만 유효하므로 그 이후 날짜여야 함.)
    output = run_advisory_agent(
        region_code="27260",
        mode="historical",
        historical_start=datetime(2026, 6, 1, tzinfo=_KST),
        historical_end=datetime(2026, 6, 3, tzinfo=_KST),
    )

    assert output.status == STATUS_OK
    assert output.trigger_event is True  # 3건 전부 event_type="특보"로 변환됨
    assert output.mode == "historical"
    assert len(output.active_warnings) == 3
    assert output.source_id == "advisory:historical:kma:reg_id=L1140100"
    assert all(w["source_url"].startswith("http") for w in output.active_warnings)


def test_historical_mode_merges_overlapping_curated_timeline(monkeypatch):
    """2026-08-19(계속) — 사용자 피드백: 공식 특보(광역 단위)와 뉴스 기반 큐레이션(국지
    피해 서술)은 서로 다른 사실이라 하나가 다른 하나를 대체하지 않는다. 조회 구간이
    대구 수성구 2026-07 큐레이션 사건 날짜와 겹치면 그 7건이 KMA 이력에 병합돼야 한다."""
    monkeypatch.setattr(kma_historical, "_fetch_wrn_reg_raw", lambda: _HIST_REG_SAMPLE.encode("euc-kr"))
    monkeypatch.setattr(
        kma_historical,
        "_fetch_wrn_met_data_raw",
        lambda reg_id, start, end: _HIST_MET_DATA_SAMPLE.encode("euc-kr"),
    )

    output = run_advisory_agent(
        region_code="27260",
        mode="historical",
        historical_start=datetime(2026, 7, 17, tzinfo=_KST),
        historical_end=datetime(2026, 7, 19, tzinfo=_KST),
    )

    assert output.status == STATUS_OK
    # KMA 3건 + 큐레이션(대구 수성구 2026-07) 7건 = 10건.
    assert len(output.active_warnings) == 10
    curated_source_urls = {
        w["source_url"] for w in output.active_warnings if "weather.go.kr" not in w["source_url"] and w["source_url"] != "https://apihub.kma.go.kr/"
    }
    assert len(curated_source_urls) > 0  # 큐레이션 이벤트는 뉴스 기사 URL을 갖는다


def test_historical_mode_no_curated_overlap_when_dates_dont_match(monkeypatch):
    """대구 수성구 큐레이션 윈도우(2026-07-16~20)와 안 겹치는 날짜 -> 병합 없이 KMA만."""
    monkeypatch.setattr(kma_historical, "_fetch_wrn_reg_raw", lambda: _HIST_REG_SAMPLE.encode("euc-kr"))
    monkeypatch.setattr(
        kma_historical,
        "_fetch_wrn_met_data_raw",
        lambda reg_id, start, end: _HIST_MET_DATA_SAMPLE.encode("euc-kr"),
    )

    output = run_advisory_agent(
        region_code="27260",
        mode="historical",
        historical_start=datetime(2026, 6, 10, tzinfo=_KST),
        historical_end=datetime(2026, 6, 12, tzinfo=_KST),
    )

    assert len(output.active_warnings) == 3  # KMA 3건만, 큐레이션 병합 없음


def test_historical_mode_activation_required_is_explicit_not_silent(monkeypatch):
    def _raise():
        raise urllib.error.HTTPError("url", 403, "Forbidden", {}, None)

    monkeypatch.setattr(kma_historical, "_fetch_wrn_reg_raw", _raise)

    output = run_advisory_agent(
        region_code="27260",
        mode="historical",
        historical_start=datetime(2026, 7, 17, tzinfo=_KST),
        historical_end=datetime(2026, 7, 19, tzinfo=_KST),
    )

    assert output.status == STATUS_HISTORICAL_ACTIVATION_REQUIRED
    assert output.trigger_event is False
    assert output.active_warnings == []


def test_historical_mode_no_zone_match_is_explicit(monkeypatch):
    monkeypatch.setattr(kma_historical, "_fetch_wrn_reg_raw", lambda: _HIST_REG_SAMPLE.encode("euc-kr"))

    output = run_advisory_agent(
        region_code="99999",
        mode="historical",
        historical_start=datetime(2024, 1, 1, tzinfo=_KST),
        historical_end=datetime(2024, 1, 2, tzinfo=_KST),
    )

    assert output.status == STATUS_HISTORICAL_NO_ZONE_MATCH
    assert output.trigger_event is False


def test_historical_mode_upstream_error_not_silently_empty(monkeypatch):
    def _raise():
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr(kma_historical, "_fetch_wrn_reg_raw", _raise)

    output = run_advisory_agent(
        region_code="27260",
        mode="historical",
        historical_start=datetime(2026, 7, 17, tzinfo=_KST),
        historical_end=datetime(2026, 7, 19, tzinfo=_KST),
    )

    assert output.status == STATUS_HISTORICAL_UPSTREAM_ERROR
    assert output.trigger_event is False
