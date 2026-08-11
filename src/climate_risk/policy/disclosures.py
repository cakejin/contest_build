"""고정 문구 상수 — HANDOVER.md §⑥ 규제 항목의 "코드 상수로 고정" 요구를 그대로 구현.

이 모듈의 문자열은 자유 텍스트 편집 대상이 아니다(AI기본법 이용자 고지 요건, HANDOVER
§⑥ item5) — 화면·CLI·심사메모 어디서든 이 상수를 그대로 참조해야 하고, 호출부가 자체
문구를 새로 만들면 안 된다.
"""

from __future__ import annotations

# HITL 워터마크 — 스코어 화면·심사메모 어디에나 상시 표기(HANDOVER §⑥ item5).
# "결정 아님, 참고자료" 문구는 스코어 시스템과 여신결정 시스템의 기능적 분리를 코드 레벨에서
# 재확인하는 안전장치다 — 이 문구를 지우거나 완화하는 변경은 규율 위반으로 간주한다.
HITL_WATERMARK_TEXT = (
    "이 산출물은 AI 기반 참고자료이며 여신 결정이 아닙니다. "
    "최종 LTV·금리·승인 여부는 담당 심사역이 별도 여신 승인 절차에서 결정합니다."
)

# AI기본법 고영향 AI 이용자 고지(HANDOVER §⑥ item5) — HITL_WATERMARK_TEXT와 목적이
# 겹치되 문구는 법령 문구에 더 가깝게 유지한다(용도가 다름: 이건 "AI기본법 고지",
# 워터마크는 "화면 상시 표기").
AI_HIGH_IMPACT_NOTICE = "AI 기반 산출물이며 최종 판단은 담당 심사역이 수행함."

# 신천 4개 지점처럼 "SHP 커버리지 안이지만 판정이 불확실"한 경우 — HANDOVER.md:419 원문 그대로.
UNCERTAIN_COVERAGE_LABEL = "판정보류(데이터 공백 — 위험 낮음 아님)"

# 좌표가 아예 로딩된 SHP 범위 밖(OUT_OF_SCOPE)인 경우 — UNCERTAIN_COVERAGE_LABEL과 원칙은
# 같으나("데이터 없음≠위험 없음") 상황이 다르므로(불확실 vs 아예 미커버) 별도 문구로 구분한다.
OUT_OF_SCOPE_LABEL = "커버리지 밖(데이터 없음 — 위험 낮음 아님)"

# 재심사 알림·ESG 추천 문구 — 보호형 사용 규율 2항("LTV 하향·금리 인상·회수 트리거로 쓰지
# 않음")·3항("인센티브는 인하 방향만")을 코드 상수 템플릿으로 고정한다. 자유 텍스트로 대체
# 불가 — policy/forbidden_phrases.py가 별도로 이 규율 위반 표현을 감지하는 이중 방어를 편다.
ACTION_PHRASE_TEMPLATES: dict[str, str] = {
    "INSURANCE_CHECK": "보험 가입 여부 확인 권장",
    "SITE_INSPECTION": "현장 피해 점검 권장",
    "DISASTER_SUPPORT_REFERRAL": "재해 지원 제도 연결 안내",
    "ADAPTATION_INCENTIVE": "차수판·방수 설비 등 적응 투자 시 우대 조건 안내(인하 방향만)",
}
