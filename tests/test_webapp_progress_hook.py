"""graph/week3_demo.py·week4_demo.py의 on_stage 진행상황 훅 — webapp/app.py가 SSE로
실제 단계 진행상황을 중계하는 데 쓰는 콜백이 실제로 올바른 순서로 불리는지 검증한다.

test_week3_demo_smoke.py와 동일한 monkeypatch 체인을 재사용해 네트워크·SHP 호출 없이
검증한다 — 이 테스트가 검증하는 건 "훅이 불리는 순서"이지 각 에이전트의 계산 로직
자체가 아니다(그건 각 에이전트별 테스트가 이미 커버).
"""

import json
from pathlib import Path

from climate_risk.agents import memo_agent
from climate_risk.graph import week3_demo, week4_demo
from tests.test_week3_demo_smoke import _fake_portfolio_agent, _patch_common

_FAKE_MEMO_RESPONSE = {"sections": [{"text": "정상 문장입니다.", "citations": ["flood:test.shp"]}]}


def _patch_memo_llm(monkeypatch):
    monkeypatch.setattr(
        memo_agent, "call_claude_structured", lambda prompt, schema_path, model="sonnet": _FAKE_MEMO_RESPONSE
    )


def test_on_stage_omitted_leaves_behavior_unchanged(monkeypatch):
    """기본값 None이면 훅을 아예 안 부른다 — 기존 CLI/테스트 동작 100% 그대로."""
    _patch_common(monkeypatch)
    _patch_memo_llm(monkeypatch)
    _fake_portfolio_agent.calls.clear()

    result = week3_demo.run_week3_demo("테스트주소", collateral_value=5.0e8)

    assert "error" not in result
    assert result["portfolio_batch"] is not None


def test_on_stage_called_in_pipeline_order_when_trigger_fires(monkeypatch):
    _patch_common(monkeypatch)
    _patch_memo_llm(monkeypatch)
    _fake_portfolio_agent.calls.clear()
    seen: list[str] = []

    def spy(stage: str, message: str) -> None:
        assert message, f"{stage} 단계에 빈 메시지가 전달됨"
        seen.append(stage)

    result = week3_demo.run_week3_demo("테스트주소", collateral_value=5.0e8, on_stage=spy)

    assert "error" not in result
    assert result["advisory"]["trigger_event"] is True  # 힌남노 실데이터라 포트폴리오 단계까지 실행됨
    assert seen == ["advisory", "geocode", "flood", "building", "scenario", "portfolio", "memo", "done"]


def test_on_stage_skips_portfolio_stage_when_no_trigger(monkeypatch, tmp_path: Path):
    """trigger_event=False인 지역(큐레이션 없음)에서는 portfolio 단계 자체가 안 불려야 한다."""
    _patch_common(monkeypatch)
    _patch_memo_llm(monkeypatch)
    seen: list[str] = []

    timeline_path = tmp_path / "timeline.json"
    timeline_path.write_text(
        json.dumps(
            {"event_name": "x", "region_code": "99999", "region_name": "x", "disclaimer": "x", "events": []}
        ),
        encoding="utf-8",
    )

    result = week3_demo.run_week3_demo(
        "테스트주소",
        collateral_value=5.0e8,
        region_code="47111",
        timeline_path=timeline_path,
        on_stage=lambda stage, message: seen.append(stage),
    )

    assert "error" not in result
    assert result["advisory"]["trigger_event"] is False
    assert "portfolio" not in seen
    assert seen == ["advisory", "geocode", "flood", "building", "scenario", "memo", "done"]


def test_week4_demo_forwards_on_stage_to_week3(monkeypatch):
    """week4_demo는 week3_demo를 감싸기만 하므로 on_stage가 그대로 통과돼야 한다."""
    _patch_common(monkeypatch)
    _patch_memo_llm(monkeypatch)
    _fake_portfolio_agent.calls.clear()
    seen: list[str] = []

    result = week4_demo.run_week4_demo(
        "테스트주소", collateral_value=5.0e8, on_stage=lambda stage, message: seen.append(stage)
    )

    assert "error" not in result
    assert seen == ["advisory", "geocode", "flood", "building", "scenario", "portfolio", "memo", "done"]


# 2026-09-07(멘토 피드백 1) — on_partial 부분 결과 훅. 각 단계 산출물이 완료 즉시 넘어오고,
# 최종 반환 dict의 같은 키와 값이 완전히 동일해야 한다(새 계산 없이 먼저 흘려보내기만 함).
def test_on_partial_omitted_leaves_behavior_unchanged(monkeypatch):
    _patch_common(monkeypatch)
    _patch_memo_llm(monkeypatch)
    _fake_portfolio_agent.calls.clear()

    result = week3_demo.run_week3_demo("테스트주소", collateral_value=5.0e8)

    assert "error" not in result


def test_on_partial_emits_each_stage_payload_identical_to_final_result(monkeypatch):
    _patch_common(monkeypatch)
    _patch_memo_llm(monkeypatch)
    _fake_portfolio_agent.calls.clear()
    partials: list[tuple[str, object]] = []

    result = week4_demo.run_week4_demo(
        "테스트주소", collateral_value=5.0e8, on_partial=lambda stage, payload: partials.append((stage, payload))
    )

    assert "error" not in result
    stages = [s for s, _ in partials]
    assert stages == ["advisory", "geocode", "flood", "building", "scenario", "portfolio", "memo"]
    by_stage = dict(partials)
    assert by_stage["advisory"] == result["advisory"]
    assert by_stage["geocode"] == result["geocoded"]
    assert by_stage["flood"] == {"flood": result["flood"], "coverage_label": result["coverage_label"]}
    assert by_stage["building"] == result["building"]
    assert by_stage["scenario"] == result["scenario"]
    assert by_stage["memo"] == result["memo"]
    assert by_stage["portfolio"] == result["portfolio_batch"]


def test_on_partial_stage_arrives_before_next_stage_starts(monkeypatch):
    """부분 결과가 '다음 단계 시작 알림(on_stage)'보다 먼저 와야 화면이 즉시 갱신된다."""
    _patch_common(monkeypatch)
    _patch_memo_llm(monkeypatch)
    _fake_portfolio_agent.calls.clear()
    timeline: list[str] = []

    week3_demo.run_week3_demo(
        "테스트주소",
        collateral_value=5.0e8,
        on_stage=lambda stage, message: timeline.append(f"start:{stage}"),
        on_partial=lambda stage, payload: timeline.append(f"done:{stage}"),
    )

    assert timeline.index("done:flood") < timeline.index("start:building")
    assert timeline.index("done:scenario") < timeline.index("start:portfolio")
    assert timeline.index("done:portfolio") < timeline.index("start:memo")
