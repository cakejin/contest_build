"""scenario/eal.py 시드 재현성 회귀 테스트 — PROGRESS.md Week2 "절대 축소 금지" 항목.

동일 seed·동일 입력으로 2회 실행 시 히스토그램 bin까지 완전히 동일해야 한다. 이것이
"화이트박스, 블랙박스 ML 아님" 포지셔닝의 기술적 증거이므로 이 테스트는 절대 삭제/완화
금지(CLAUDE.md "EAL은 시드 고정 재현성 테스트 필수"). 홍수 판정 fixture는 conftest.py의
in_scope_flood — 실제 SHP 조회 없이 최소 구성으로 EAL 계산 로직만 검증한다.
"""

from climate_risk.scenario.eal import run_monte_carlo_eal


def test_same_seed_reproduces_identical_result(in_scope_flood):
    kwargs = dict(flood=in_scope_flood, vulnerability_score=55.0, collateral_value=5.0e8, seed=42)
    first = run_monte_carlo_eal(**kwargs)
    second = run_monte_carlo_eal(**kwargs)

    assert first == second  # frozen dataclass — 필드 전부(히스토그램 bin 포함) 동일해야 함
    assert first.status == "OK"
    assert first.EAL_mean is not None


def test_different_seed_changes_result(in_scope_flood):
    base = run_monte_carlo_eal(
        flood=in_scope_flood, vulnerability_score=55.0, collateral_value=5.0e8, seed=42
    )
    other = run_monte_carlo_eal(
        flood=in_scope_flood, vulnerability_score=55.0, collateral_value=5.0e8, seed=7
    )
    assert base.EAL_mean != other.EAL_mean


def test_default_seed_and_iterations_are_used_when_unspecified(in_scope_flood):
    from climate_risk.config import DEFAULT_EAL_ITERATIONS, DEFAULT_EAL_SEED

    result = run_monte_carlo_eal(
        flood=in_scope_flood, vulnerability_score=55.0, collateral_value=5.0e8
    )
    assert result.seed == DEFAULT_EAL_SEED
    assert result.n_iterations == DEFAULT_EAL_ITERATIONS
