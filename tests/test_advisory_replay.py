from datetime import datetime

from climate_risk.advisory.replay import replay_timeline
from climate_risk.advisory.schema import AdvisoryEvent, CuratedTimeline


def _event(event_id, issued_at, event_type="현장상황"):
    return AdvisoryEvent(
        event_id=event_id,
        issued_at=issued_at,
        time_precision="approximate",
        event_type=event_type,
        warning_type=None,
        description="테스트",
        source_url="https://example.com",
        target_region_text="테스트",
    )


def _timeline(events):
    return CuratedTimeline(
        event_name="테스트", region_code="47111", region_name="테스트", disclaimer="테스트", events=events
    )


def test_replay_sorts_by_issued_at_regardless_of_input_order():
    timeline = _timeline(
        [
            _event("e3", "2022-09-06T09:00:00+09:00"),
            _event("e1", "2022-09-05T06:00:00+09:00"),
            _event("e2", "2022-09-06T05:00:00+09:00"),
        ]
    )

    result = replay_timeline(timeline)

    assert [e.event_id for e in result] == ["e1", "e2", "e3"]


def test_replay_handles_date_only_event_in_sort_order():
    timeline = _timeline(
        [
            _event("e1", "2022-09-05T06:00:00+09:00"),
            _event("e2", "2022-09-06"),  # date_only
        ]
    )

    result = replay_timeline(timeline)

    assert [e.event_id for e in result] == ["e1", "e2"]


def test_replay_as_of_filters_future_events():
    timeline = _timeline(
        [
            _event("e1", "2022-09-05T06:00:00+09:00"),
            _event("e2", "2022-09-06T09:00:00+09:00"),
        ]
    )

    result = replay_timeline(timeline, as_of=datetime(2022, 9, 5, 12, 0, 0))

    assert [e.event_id for e in result] == ["e1"]


def test_replay_none_as_of_returns_full_timeline():
    timeline = _timeline([_event("e1", "2022-09-05T06:00:00+09:00")])

    result = replay_timeline(timeline, as_of=None)

    assert [e.event_id for e in result] == ["e1"]
