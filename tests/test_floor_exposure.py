"""scenario/floor_exposure.py — HANDOVER.md §⑧ 판정 로직 회귀 테스트.

판정 함수는 순수 결정론적 함수라 네트워크 mock 없이 직접 테스트한다.
"""

from climate_risk.scenario.floor_exposure import (
    FLOOR_TYPE_GROUND,
    FLOOR_TYPE_UNDERGROUND,
    TIER_HIGH,
    TIER_LOW,
    TIER_MEDIUM,
    apply_floor_adjustment,
    determine_floor_flood_exposure,
)


def test_out_of_scope_falls_back_to_building_score():
    result = determine_floor_flood_exposure(
        floor_type=FLOOR_TYPE_GROUND, floor_no=1, depth_class="N331",
        building_tier="내부", coverage="OUT_OF_SCOPE",
    )
    assert result.floor_unassessed is True
    assert result.fallback_to_building_score is True
    assert result.floor_risk_tier is None


def test_missing_floor_input_falls_back_to_building_score():
    result = determine_floor_flood_exposure(
        floor_type=None, floor_no=None, depth_class="N331",
        building_tier="내부", coverage="IN_SCOPE",
    )
    assert result.fallback_to_building_score is True


def test_underground_is_always_high_regardless_of_depth():
    result = determine_floor_flood_exposure(
        floor_type=FLOOR_TYPE_UNDERGROUND, floor_no=1, depth_class=None,
        building_tier="원거리", coverage="IN_SCOPE",
    )
    assert result.floor_risk_tier == TIER_HIGH
    assert result.fallback_to_building_score is False
    assert result.floor_unassessed is False


def test_ground_floor_outside_flood_polygon_is_confirmed_low_not_fallback():
    """5개 등급 폴리곤에 안 걸리면 '데이터 없음'이 아니라 '이 빈도에서 비침수'라는
    확정 신호 — fallback이 아니라 LOW로 확정 판정돼야 한다."""
    result = determine_floor_flood_exposure(
        floor_type=FLOOR_TYPE_GROUND, floor_no=1, depth_class=None,
        building_tier="근접", coverage="IN_SCOPE",
    )
    assert result.floor_risk_tier == TIER_LOW
    assert result.fallback_to_building_score is False


def test_ground_floor_deep_water_shallow_floor_is_high():
    # N334 상한 8.0m, 1층(elevation=0m) -> exposure_ratio = min(1, 8/3) = 1.0 >= 0.5 -> HIGH
    result = determine_floor_flood_exposure(
        floor_type=FLOOR_TYPE_GROUND, floor_no=1, depth_class="N334",
        building_tier="내부", coverage="IN_SCOPE",
    )
    assert result.floor_risk_tier == TIER_HIGH
    assert result.exposure_ratio == 1.0


def test_ground_floor_shallow_water_low_floor_is_medium():
    # N331 상한 1.0m, 1층(elevation=0m) -> exposure_ratio = min(1, 1.0/3.0) = 0.333.. -> MEDIUM
    result = determine_floor_flood_exposure(
        floor_type=FLOOR_TYPE_GROUND, floor_no=1, depth_class="N331",
        building_tier="내부", coverage="IN_SCOPE",
    )
    assert result.floor_risk_tier == TIER_MEDIUM
    assert 0.0 < result.exposure_ratio < 0.5


def test_high_floor_above_depth_class_is_low():
    # N330 상한 0.5m, 3층(elevation=6.0m) -> 6.0m >= 0.5m -> LOW, exposure_ratio=0.0
    result = determine_floor_flood_exposure(
        floor_type=FLOOR_TYPE_GROUND, floor_no=3, depth_class="N330",
        building_tier="내부", coverage="IN_SCOPE",
    )
    assert result.floor_risk_tier == TIER_LOW
    assert result.exposure_ratio == 0.0
    assert result.floor_elevation_m == 6.0


def test_apply_floor_adjustment_passthrough_when_no_floor_exposure():
    assert apply_floor_adjustment(55.0, None) == 55.0


def test_apply_floor_adjustment_passthrough_when_fallback():
    fallback = determine_floor_flood_exposure(None, None, None, None, "IN_SCOPE")
    assert apply_floor_adjustment(55.0, fallback) == 55.0


def test_apply_floor_adjustment_passthrough_when_score_none():
    high = determine_floor_flood_exposure(FLOOR_TYPE_UNDERGROUND, 1, None, None, "IN_SCOPE")
    assert apply_floor_adjustment(None, high) is None


def test_apply_floor_adjustment_blends_toward_high_tier():
    high = determine_floor_flood_exposure(FLOOR_TYPE_UNDERGROUND, 1, None, None, "IN_SCOPE")
    # 0.5*20 + 0.5*100 = 60.0
    assert apply_floor_adjustment(20.0, high) == 60.0
