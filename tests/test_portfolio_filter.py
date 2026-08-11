from climate_risk.portfolio.filter import filter_by_region
from climate_risk.portfolio.schema import PortfolioRecord


def _record(collateral_id, region_code):
    return PortfolioRecord(
        collateral_id=collateral_id,
        address="테스트",
        collateral_type="아파트",
        balance=100.0,
        collateral_value=200.0,
        ltv=0.5,
        score_before=50.0,
        eal_before=1000.0,
        region_code=region_code,
    )


def test_exact_region_match_only():
    records = [
        _record("A", "47111"),
        _record("B", "27200"),
        _record("C", "47111"),
    ]

    result = filter_by_region(records, "47111")

    assert [r.collateral_id for r in result.matched] == ["A", "C"]
    assert result.other_region_count == 1
    assert result.skipped_ungeocoded_count == 0


def test_ungeocoded_records_are_counted_not_dropped_silently():
    records = [
        _record("A", "47111"),
        _record("B", None),
        _record("C", None),
    ]

    result = filter_by_region(records, "47111")

    assert [r.collateral_id for r in result.matched] == ["A"]
    assert result.skipped_ungeocoded_count == 2
    assert result.other_region_count == 0


def test_matched_plus_skipped_plus_other_region_equals_total():
    records = [
        _record("A", "47111"),
        _record("B", "27200"),
        _record("C", None),
        _record("D", "27110"),
        _record("E", "47111"),
    ]

    result = filter_by_region(records, "47111")

    total = len(result.matched) + result.skipped_ungeocoded_count + result.other_region_count
    assert total == len(records)
