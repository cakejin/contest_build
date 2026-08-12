"""ESG 추천(전환금융) 화면 — HANDOVER.md ③ 시나리오4 "고위험 담보 목록 → 재해예방
설비 개선자금(전환금융) 추천 리스트"의 실체. 보호형 사용 규율 3항("인센티브는 인하
방향만")을 코드 레벨에서 위반 불가능하게 만든다 — 이 모듈은 `disclosures.py
ACTION_PHRASE_TEMPLATES`(전부 인하/지원 방향 문구)에서만 값을 가져오고, 자유 텍스트나
조건부 인상 방향 로직 자체를 만들지 않는다.

포트폴리오 재심사 알림 큐(`portfolio/alerts.py`)에 이미 등재된 담보는 정의상 EAL
변화율이 임계치를 넘긴 "재심사가 필요할 수 있는" 담보다 — 별도의 위험도 재판정 없이
알림 큐에 오른 담보 전원에게 동일한 4개 액션 템플릿(보험 확인·현장 점검·재해지원
연결·적응투자 우대)을 추천한다.
"""

from __future__ import annotations

from dataclasses import dataclass

from climate_risk.policy.disclosures import ACTION_PHRASE_TEMPLATES

_ALL_ACTION_PHRASES: list[str] = list(ACTION_PHRASE_TEMPLATES.values())


@dataclass(frozen=True)
class ESGRecommendation:
    collateral_id: str
    actions: list[str]


def recommend_actions_for_alert(collateral_id: str) -> ESGRecommendation:
    return ESGRecommendation(collateral_id=collateral_id, actions=list(_ALL_ACTION_PHRASES))


def build_esg_recommendations(alerts: list[dict]) -> list[ESGRecommendation]:
    """`run_week3_demo()`가 반환하는 `portfolio_batch["alerts"]`(dict 리스트,
    `AlertQueueEntry`를 `dataclasses.asdict`한 형태)를 그대로 소비한다."""
    return [recommend_actions_for_alert(alert["collateral_id"]) for alert in alerts]
