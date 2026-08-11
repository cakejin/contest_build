import json

import pytest

from climate_risk.advisory.curated_loader import CuratedDataError, load_curated_timeline

_VALID_EVENT = {
    "event_id": "e1",
    "issued_at": "2022-09-06T06:00:00+09:00",
    "time_precision": "approximate",
    "event_type": "특보",
    "warning_type": "태풍경보",
    "description": "테스트 이벤트",
    "source_url": "https://example.com/e1",
    "target_region_text": "테스트지역",
}


def _write(tmp_path, events):
    path = tmp_path / "timeline.json"
    path.write_text(
        json.dumps(
            {
                "event_name": "테스트 타임라인",
                "region_code": "47111",
                "region_name": "테스트지역",
                "disclaimer": "테스트",
                "events": events,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return path


def test_valid_timeline_loads(tmp_path):
    path = _write(tmp_path, [_VALID_EVENT])
    timeline = load_curated_timeline(path)

    assert timeline.region_code == "47111"
    assert len(timeline.events) == 1
    assert timeline.events[0].source_id == "advisory:event:e1"


def test_missing_source_url_is_rejected(tmp_path):
    bad_event = {**_VALID_EVENT, "source_url": ""}
    path = _write(tmp_path, [bad_event])

    with pytest.raises(CuratedDataError):
        load_curated_timeline(path)


def test_missing_source_url_key_is_rejected(tmp_path):
    bad_event = dict(_VALID_EVENT)
    del bad_event["source_url"]
    path = _write(tmp_path, [bad_event])

    with pytest.raises(CuratedDataError):
        load_curated_timeline(path)


def test_invalid_time_precision_is_rejected(tmp_path):
    bad_event = {**_VALID_EVENT, "time_precision": "매우정확함"}
    path = _write(tmp_path, [bad_event])

    with pytest.raises(CuratedDataError):
        load_curated_timeline(path)
