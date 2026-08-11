"""실제 큐레이션 파일(data/.../hinnamno_2022/events.json) 회귀 테스트 — test_coverage_gate.py와
같은 스타일로 "이 파일이 지금 이 형태를 유지하는가"를 고정한다. 조사로 확보한 7건 실사건
데이터가 실수로 손상되거나 출처 없는 이벤트가 섞여 들어가는 것을 방지한다."""

from climate_risk.advisory.curated_loader import load_curated_timeline
from climate_risk.config import HINNAMNO_TIMELINE_PATH


def test_real_hinnamno_file_loads_without_error():
    timeline = load_curated_timeline(HINNAMNO_TIMELINE_PATH)

    assert timeline.region_code == "47111"
    assert len(timeline.events) == 7


def test_every_real_event_has_a_source_url():
    timeline = load_curated_timeline(HINNAMNO_TIMELINE_PATH)

    for event in timeline.events:
        assert event.source_url.startswith("http"), event.event_id


def test_real_timeline_includes_a_trigger_type_event():
    """최소 1건은 특보/재난문자 이벤트여야 advisory_agent의 trigger_event=True 경로가
    실제로 시연된다 — Done 기준("힌남노리플레이" 클라이맥스)의 전제 조건."""
    timeline = load_curated_timeline(HINNAMNO_TIMELINE_PATH)

    assert any(event.event_type in {"특보", "재난문자"} for event in timeline.events)
