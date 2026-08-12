"""ESG 추천 모듈 회귀 테스트 — 보호형 사용 규율 3항("인센티브는 인하 방향만")이
코드 레벨에서 실제로 지켜지는지 확인한다."""

from climate_risk.policy.disclosures import ACTION_PHRASE_TEMPLATES
from climate_risk.policy.esg_recommendations import (
    build_esg_recommendations,
    recommend_actions_for_alert,
)
from climate_risk.policy.forbidden_phrases import scan_forbidden_phrases

_TEMPLATE_PHRASES = set(ACTION_PHRASE_TEMPLATES.values())


def test_actions_are_subset_of_whitelisted_templates():
    rec = recommend_actions_for_alert("C-001")
    assert rec.actions
    assert set(rec.actions).issubset(_TEMPLATE_PHRASES)


def test_no_action_phrase_trips_forbidden_phrase_filter():
    for phrase in _TEMPLATE_PHRASES:
        assert scan_forbidden_phrases(phrase) == [], phrase


def test_alert_queue_maps_one_to_one_to_recommendations():
    alerts = [{"collateral_id": "C-001"}, {"collateral_id": "C-002"}, {"collateral_id": "C-003"}]
    recs = build_esg_recommendations(alerts)
    assert [r.collateral_id for r in recs] == ["C-001", "C-002", "C-003"]


def test_empty_alert_queue_produces_no_recommendations():
    assert build_esg_recommendations([]) == []


def test_adaptation_incentive_always_present():
    rec = recommend_actions_for_alert("C-001")
    assert ACTION_PHRASE_TEMPLATES["ADAPTATION_INCENTIVE"] in rec.actions
