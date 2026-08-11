import json

import pytest

from climate_risk.advisory.live import run_live_query
from climate_risk.agents.advisory_agent import (
    STATUS_NO_CURATED_DATA_FOR_REGION,
    STATUS_OK,
    run_advisory_agent,
)
from climate_risk.config import HINNAMNO_TIMELINE_PATH


def test_replay_mode_against_real_hinnamno_data():
    output = run_advisory_agent(region_code="47111", mode="replay", timeline_path=HINNAMNO_TIMELINE_PATH)

    assert output.status == STATUS_OK
    assert output.trigger_event is True  # 특보/재난문자 이벤트가 실제 데이터에 존재
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


def test_live_mode_raises_not_implemented_via_run_advisory_agent():
    with pytest.raises(NotImplementedError):
        run_advisory_agent(region_code="47111", mode="live")


def test_run_live_query_stub_raises_not_implemented():
    with pytest.raises(NotImplementedError):
        run_live_query()


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
