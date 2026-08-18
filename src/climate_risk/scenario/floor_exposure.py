"""층별 리스크 차등화 — HANDOVER.md §⑧ 판정 로직 그대로의 화이트박스 구현.

담보의 층수(지상/지하)를 선택 입력하면, 건물 전체 단위 취약도 점수 대신 그 층의
침수 노출도로 리스크를 세분화한다. 입력하지 않으면(§2.3 기존 경로) 이 모듈은
호출되지 않는다 — 추가 옵션이지 기존 건물 전체 스코어링의 대체가 아니다.

결정론적 규칙함수만 사용한다(LLM/ML 없음, HANDOVER §4.1 설계원칙3과 동일 정신).
"""

from __future__ import annotations

from dataclasses import dataclass

# 지상 표준 층고 근사치 — 공식 출처 미확정, 안전측(보수적) 추정치로 사용(HANDOVER §⑧).
STANDARD_FLOOR_HEIGHT_M = 3.0

# SEG_CODE(홍수위험지도) → 보수적 침수심 상한(m). 출처: floodmap.go.kr WMS API 파라미터
# 문서(SegCode). N334("5.0m 이상")는 무한대가 아닌 보수적 상한(8m)으로 캡(HANDOVER §⑧).
DEPTH_CLASS_UPPER_BOUND_M: dict[str, float] = {
    "N330": 0.5,
    "N331": 1.0,
    "N332": 2.0,
    "N333": 5.0,
    "N334": 8.0,
}

FLOOR_TYPE_GROUND = "지상"
FLOOR_TYPE_UNDERGROUND = "지하"

TIER_HIGH = "HIGH"
TIER_MEDIUM = "MEDIUM"
TIER_LOW = "LOW"

_EXPOSURE_RATIO_HIGH_THRESHOLD = 0.5


@dataclass(frozen=True)
class FloorExposureResult:
    floor_risk_tier: str | None  # "HIGH" | "MEDIUM" | "LOW" | None
    floor_unassessed: bool
    fallback_to_building_score: bool
    basis: str | None = None
    reason: str | None = None
    floor_elevation_m: float | None = None
    depth_upper_m: float | None = None
    exposure_ratio: float | None = None


def determine_floor_flood_exposure(
    floor_type: str | None,
    floor_no: int | None,
    depth_class: str | None,
    building_tier: str | None,
    coverage: str,
) -> FloorExposureResult:
    """HANDOVER.md §⑧ 판정 로직 — 원본 pseudocode를 그대로 옮긴 것(로직 변경 없음).

    - coverage == "OUT_OF_SCOPE": 건물 전체가 커버리지 밖(데이터 없음) → 건물 전체
      스코어로 폴백. "위험 낮음"으로 조용히 대체하지 않는다(CLAUDE.md 원칙1).
    - floor_type/floor_no 미입력: 이 기능 자체를 안 쓰겠다는 뜻 → 폴백.
    - 지하: 무조건 HIGH(지하층은 침수 유입의 직접 경로 — 예외 없음).
    - 지상이지만 building_tier != "내부" 이거나 depth_class 없음: 5개 등급 폴리곤은
      상호 배타적 분할이므로 "데이터 없음"이 아니라 "이 빈도 시나리오에서 실제로
      비침수"라는 확정 신호 → LOW(폴백이 아니라 확정 판정).
    - 그 외: 표준 층고로 근사한 층 바닥 높이(1층=0m 기준)와 침수심 상한을 비교해
      노출비율(exposure_ratio)을 산출, 0.5 이상이면 HIGH, 미만이면 MEDIUM.
    """
    if coverage == "OUT_OF_SCOPE":
        return FloorExposureResult(
            floor_risk_tier=None,
            floor_unassessed=True,
            fallback_to_building_score=True,
            reason="건물 전체가 커버리지 밖(데이터 없음)",
        )
    if floor_type is None or floor_no is None:
        return FloorExposureResult(
            floor_risk_tier=None,
            floor_unassessed=True,
            fallback_to_building_score=True,
            reason="층 정보 미입력",
        )
    if floor_type == FLOOR_TYPE_UNDERGROUND:
        return FloorExposureResult(
            floor_risk_tier=TIER_HIGH,
            floor_unassessed=False,
            fallback_to_building_score=False,
            basis="지하층 무조건 고위험 원칙",
        )
    if building_tier != "내부" or depth_class is None:
        return FloorExposureResult(
            floor_risk_tier=TIER_LOW,
            floor_unassessed=False,
            fallback_to_building_score=False,
            basis="침수 폴리곤(5개 등급) 어디에도 속하지 않음 — 이 빈도 시나리오상 비침수 지역",
        )

    depth_upper_m = DEPTH_CLASS_UPPER_BOUND_M[depth_class]
    floor_elevation_m = (floor_no - 1) * STANDARD_FLOOR_HEIGHT_M  # 지상 1층 바닥 = 0m 기준

    if floor_elevation_m < depth_upper_m:
        exposure_ratio = min(1.0, (depth_upper_m - floor_elevation_m) / STANDARD_FLOOR_HEIGHT_M)
        tier = TIER_HIGH if exposure_ratio >= _EXPOSURE_RATIO_HIGH_THRESHOLD else TIER_MEDIUM
        return FloorExposureResult(
            floor_risk_tier=tier,
            floor_unassessed=False,
            fallback_to_building_score=False,
            floor_elevation_m=floor_elevation_m,
            depth_upper_m=depth_upper_m,
            exposure_ratio=exposure_ratio,
        )
    return FloorExposureResult(
        floor_risk_tier=TIER_LOW,
        floor_unassessed=False,
        fallback_to_building_score=False,
        floor_elevation_m=floor_elevation_m,
        depth_upper_m=depth_upper_m,
        exposure_ratio=0.0,
    )


# HANDOVER §⑧ "기존 파이프라인과의 통합점" 옵션A(권고, 먼저 구현) — 몬테카를로 반복마다
# 침수심에서 층고를 차감하는 옵션B(고도화)는 아직 미구현. 여기서는 층별 리스크 등급을
# 건물 전체 취약도 점수(0~100)와 같은 축의 대체 점수로 변환해 가중평균한다 — 근거문헌
# 없는 잠정 가중치(50:50)이며, 실손해 데이터 확보 시 캘리브레이션 대상(vulnerability.py의
# w1~w4와 동일한 성격).
FLOOR_TIER_SCORE: dict[str, float] = {TIER_HIGH: 100.0, TIER_MEDIUM: 60.0, TIER_LOW: 20.0}
FLOOR_ADJUSTMENT_WEIGHT = 0.5


def apply_floor_adjustment(
    vulnerability_score: float | None, floor_exposure: FloorExposureResult | None
) -> float | None:
    """floor_exposure가 없거나(§2.3 기존 경로) 판정 불가(fallback_to_building_score)면
    건물 전체 점수를 그대로 반환한다 — 층 정보를 입력하지 않은 기존 흐름은 이 함수
    호출 여부와 무관하게 동일한 값을 낸다(하위 호환)."""
    if vulnerability_score is None or floor_exposure is None or floor_exposure.fallback_to_building_score:
        return vulnerability_score
    tier_score = FLOOR_TIER_SCORE.get(floor_exposure.floor_risk_tier or "")
    if tier_score is None:
        return vulnerability_score
    blended = FLOOR_ADJUSTMENT_WEIGHT * vulnerability_score + (1 - FLOOR_ADJUSTMENT_WEIGHT) * tier_score
    return round(blended, 1)
