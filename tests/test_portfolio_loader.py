from climate_risk.portfolio.loader import load_portfolio, save_portfolio
from climate_risk.portfolio.schema import PortfolioRecord


def test_round_trip_preserves_all_fields(tmp_path):
    path = tmp_path / "portfolio.json"
    records = [
        PortfolioRecord(
            collateral_id="COL-001",
            address="경상북도 포항시 남구 인덕로 27",
            collateral_type="아파트",
            balance=300_000_000,
            collateral_value=500_000_000,
            ltv=0.6,
            score_before=55.0,
            eal_before=10_000_000,
            lat=35.98768,
            lon=129.39979,
            region_code="47111",
            geocode_confidence="OK",
            geocoded_at="2026-08-11T00:00:00+00:00",
        )
    ]

    save_portfolio(records, path)
    loaded = load_portfolio(path)

    assert loaded == records


def test_real_synthetic_portfolio_file_loads():
    from climate_risk.config import PORTFOLIO_DATA_PATH

    records = load_portfolio(PORTFOLIO_DATA_PATH)

    # 316(8종 담보유형 확대, 2026-08-18) + 154(거제 확장, 2026-08-19, DEV_LOG.md 참조
    # — 유형당 목표 20건, 창고 15/공장 19만 후보 부족으로 미달) = 470.
    assert len(records) == 470
    assert all(r.collateral_id for r in records)
    assert all(r.collateral_value > 0 for r in records)
