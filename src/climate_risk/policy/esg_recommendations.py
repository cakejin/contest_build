"""ESG 추천(전환금융) 화면 — HANDOVER.md ③ 시나리오4 "고위험 담보 목록 → 재해예방
설비 개선자금(전환금융) 추천 리스트"의 실체. 보호형 사용 규율 3항("인센티브는 인하
방향만")을 코드 레벨에서 위반 불가능하게 만든다 — 이 모듈은 `disclosures.py
ACTION_PHRASE_TEMPLATES`(전부 인하/지원 방향 문구)에서만 값을 가져오고, 자유 텍스트나
조건부 인상 방향 로직 자체를 만들지 않는다.

포트폴리오 재심사 알림 큐(`portfolio/alerts.py`)에 이미 등재된 담보는 정의상 EAL
변화율이 임계치를 넘긴 "재심사가 필요할 수 있는" 담보다 — 별도의 위험도 재판정 없이
알림 큐에 오른 담보 전원에게 동일한 액션 템플릿(현장 점검·재해지원 연결·적응투자
우대 3개는 항상)을 추천한다.

`INSURANCE_CHECK`(보험 가입 여부 확인 권장)만 예외다 — `insurance_covered is True`
(이미 가입 확인된 담보)면 이 액션을 뺀다. 이미 가입된 담보에 "가입 여부 확인"을
반복 추천하는 게 부자연스럽기도 하고, HANDOVER §③이 약속한 "보험 커버리지 미확인
N건"이라는 데모 문구가 실제로 셀 수 있는 숫자를 갖게 하기 위함이다(2026-08-18 추가,
DEV_LOG.md 참조) — `count_insurance_unconfirmed()`가 그 N을 계산한다.
"""

from __future__ import annotations

from dataclasses import dataclass

from climate_risk.policy.disclosures import ACTION_PHRASE_TEMPLATES

_BASE_ACTION_PHRASES: list[str] = [
    v for k, v in ACTION_PHRASE_TEMPLATES.items() if k != "INSURANCE_CHECK"
]
_INSURANCE_CHECK_PHRASE = ACTION_PHRASE_TEMPLATES["INSURANCE_CHECK"]


@dataclass(frozen=True)
class ESGRecommendation:
    collateral_id: str
    actions: list[str]


def recommend_actions_for_alert(
    collateral_id: str, insurance_covered: bool | None = None
) -> ESGRecommendation:
    actions = list(_BASE_ACTION_PHRASES)
    if insurance_covered is not True:  # None(미확인)도 False(미가입 확인됨)도 둘 다 확인 필요
        actions.insert(0, _INSURANCE_CHECK_PHRASE)
    return ESGRecommendation(collateral_id=collateral_id, actions=actions)


def build_esg_recommendations(alerts: list[dict]) -> list[ESGRecommendation]:
    """`run_week3_demo()`가 반환하는 `portfolio_batch["alerts"]`(dict 리스트,
    `AlertQueueEntry`를 `dataclasses.asdict`한 형태)를 그대로 소비한다. 옛 알림 로그처럼
    `insurance_covered` 키 자체가 없는 입력도 `.get()`으로 안전하게 "미확인"(None) 취급한다."""
    return [
        recommend_actions_for_alert(alert["collateral_id"], alert.get("insurance_covered"))
        for alert in alerts
    ]


def count_insurance_unconfirmed(alerts: list[dict]) -> int:
    """HANDOVER §③ "보험 커버리지 미확인 N건" 문구의 N — 알림 큐 중 가입이 확인되지
    않은(True가 아닌) 담보 수."""
    return sum(1 for alert in alerts if alert.get("insurance_covered") is not True)
