"""커버리지 게이트 UI 표기 — HANDOVER.md §⑦ "Week3 UI 단계" 항목의 실체.

flood_agent/gis.query가 반환하는 FloodRiskResult를 그대로 두고(원자료 무결성 보존,
config.py LICENSE_LABEL 원칙과 동일), 화면·CLI 표시용 라벨만 이 모듈에서 파생한다 —
FloodRiskResult 자체를 변형하지 않는다.
"""

from __future__ import annotations

from climate_risk.gis.query import FloodRiskResult
from climate_risk.policy.disclosures import OUT_OF_SCOPE_LABEL, UNCERTAIN_COVERAGE_LABEL


def label_for_flood_result(flood: FloodRiskResult) -> str | None:
    """UI에 표기할 커버리지 경고 라벨. 정상 판정(IN_SCOPE, 판정보류 아님)이면 None —
    호출부는 None이면 별도 경고 배지를 그리지 않으면 된다."""
    if flood.uncertain is not None:
        return UNCERTAIN_COVERAGE_LABEL
    if flood.coverage == "OUT_OF_SCOPE":
        return OUT_OF_SCOPE_LABEL
    return None
