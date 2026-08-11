"""scenario/eal.py — 입력 불충분 시 허수 EAL을 만들지 않는다는 계약 검증.

HANDOVER.md §4.2 2.4 실패 시 폴백: "입력 3종 중 하나라도 결측·판정 불가면 시뮬레이션
자체를 실행하지 않고 EAL: null 반환" — 이 테스트는 그 계약이 실제로 지켜지는지 확인한다.
"""

from climate_risk.scenario.eal import STATUS_INSUFFICIENT_INPUT, STATUS_OK, run_monte_carlo_eal


def test_out_of_scope_flood_returns_insufficient_input(out_of_scope_flood):
    result = run_monte_carlo_eal(
        flood=out_of_scope_flood, vulnerability_score=55.0, collateral_value=5.0e8
    )
    assert result.status == STATUS_INSUFFICIENT_INPUT
    assert result.reason == "입력 데이터 불충분"
    assert result.EAL_mean is None
    assert result.EAL_p50 is None
    assert result.EAL_p95 is None
    assert result.EAL_p99 is None
    assert result.distribution_histogram_bins is None


def test_missing_vulnerability_score_returns_insufficient_input(in_scope_flood):
    result = run_monte_carlo_eal(
        flood=in_scope_flood, vulnerability_score=None, collateral_value=5.0e8
    )
    assert result.status == STATUS_INSUFFICIENT_INPUT
    assert result.EAL_mean is None


def test_both_present_returns_ok_with_numeric_output(in_scope_flood):
    result = run_monte_carlo_eal(
        flood=in_scope_flood, vulnerability_score=55.0, collateral_value=5.0e8
    )
    assert result.status == STATUS_OK
    assert result.reason is None
    assert result.EAL_mean is not None
    assert result.EAL_mean >= 0.0
    assert result.EAL_p50 <= result.EAL_p95 <= result.EAL_p99
