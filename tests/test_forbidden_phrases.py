from climate_risk.policy.disclosures import ACTION_PHRASE_TEMPLATES
from climate_risk.policy.forbidden_phrases import (
    FORBIDDEN_PHRASES,
    contains_forbidden_phrase,
    scan_forbidden_phrases,
)


def test_each_forbidden_phrase_is_detected_in_context():
    for phrase in FORBIDDEN_PHRASES:
        sample = f"이번 재심사로 {phrase}이 필요합니다."
        assert contains_forbidden_phrase(sample), phrase


def test_clean_text_has_no_match():
    assert not contains_forbidden_phrase("보험 가입 여부 확인을 권장합니다.")


def test_scan_returns_position_and_matched_text():
    matches = scan_forbidden_phrases("이 담보는 금리 인상 대상입니다.")
    assert len(matches) == 1
    assert matches[0].matched_text == "금리 인상"
    assert matches[0].phrase == "금리 인상"


def test_action_phrase_templates_never_trip_the_filter():
    """정책상 승인된 인하 방향 문구 자체가 금지어 오탐을 내면 안 된다 — 자기모순 회귀 방지."""
    for template in ACTION_PHRASE_TEMPLATES.values():
        assert not contains_forbidden_phrase(template), template
