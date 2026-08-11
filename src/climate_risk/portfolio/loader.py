"""합성 포트폴리오 JSON 로드/저장 — scripts/geocode_portfolio.py의 warm-up write-back과
portfolio_agent.py의 read 양쪽에서 공용으로 쓴다."""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

from climate_risk.portfolio.schema import PortfolioRecord


def load_portfolio(path: Path) -> list[PortfolioRecord]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return [PortfolioRecord(**r) for r in raw["records"]]


def save_portfolio(records: list[PortfolioRecord], path: Path) -> None:
    payload = {"records": [dataclasses.asdict(r) for r in records]}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
