"""포트폴리오 배치 재계산 오케스트레이션 — HANDOVER.md §4.1 "혼합형 구조"의
지역필터링 즉시재계산 경로. `advisory.trigger_event`가 False여도 함수 자체는 안전하게
호출 가능하다(호출 여부 판단은 caller 책임 — graph/week3_demo.py 참조).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from climate_risk.agents.advisory_agent import AdvisoryAgentOutput
from climate_risk.config import (
    ALERT_QUEUE_LOG_PATH,
    DEFAULT_EAL_ITERATIONS,
    DEFAULT_EAL_SEED,
    EAL_ALERT_THRESHOLD_PCT,
    PORTFOLIO_DATA_PATH,
    SEVERITY_ALERT_QUEUE_LOG_PATH,
)
from climate_risk.policy.disclosures import HITL_WATERMARK_TEXT
from climate_risk.portfolio.alerts import AlertQueueEntry, append_to_alert_queue_log, build_alert_queue
from climate_risk.portfolio.filter import filter_by_region
from climate_risk.portfolio.loader import load_portfolio
from climate_risk.portfolio.recalc import PortfolioRecalcResult, recalc_subset
from climate_risk.portfolio.severity_alerts import (
    SeverityAlertQueueEntry,
    append_to_severity_alert_queue_log,
    build_severity_alert_queue,
)


@dataclass(frozen=True)
class PortfolioBatchResult:
    region_code: str
    total_records: int
    matched_count: int
    skipped_ungeocoded_count: int
    other_region_count: int
    recalculated: list[PortfolioRecalcResult]
    alerts: list[AlertQueueEntry]
    # 2026-08-31 추가(DEV_LOG.md 참조) — EAL 임계치 알림(위 alerts)과 완전히 독립된
    # 심각도 기반 알림. EAL 재계산 결과를 전혀 참조하지 않으므로 alerts가 빈 리스트여도
    # 채워질 수 있다(거제 2026-08 실호우 재현에서 확인된 공백을 메움).
    severity_alerts: list[SeverityAlertQueueEntry]
    disclosure: str


def run_portfolio_agent(
    advisory: AdvisoryAgentOutput,
    portfolio_path: Path = PORTFOLIO_DATA_PATH,
    threshold_pct: float = EAL_ALERT_THRESHOLD_PCT,
    seed: int = DEFAULT_EAL_SEED,
    n_iterations: int = DEFAULT_EAL_ITERATIONS,
    alert_log_path: Path = ALERT_QUEUE_LOG_PATH,
    severity_alert_log_path: Path = SEVERITY_ALERT_QUEUE_LOG_PATH,
) -> PortfolioBatchResult:
    portfolio = load_portfolio(portfolio_path)
    filter_result = filter_by_region(portfolio, advisory.region_code)

    recalculated = recalc_subset(filter_result.matched, seed=seed, n_iterations=n_iterations)
    alerts = build_alert_queue(filter_result.matched, recalculated, threshold_pct=threshold_pct)
    append_to_alert_queue_log(alerts, alert_log_path)

    severity_alerts = build_severity_alert_queue(filter_result.matched, advisory.timeline)
    append_to_severity_alert_queue_log(severity_alerts, severity_alert_log_path)

    return PortfolioBatchResult(
        region_code=advisory.region_code,
        total_records=len(portfolio),
        matched_count=len(filter_result.matched),
        skipped_ungeocoded_count=filter_result.skipped_ungeocoded_count,
        other_region_count=filter_result.other_region_count,
        recalculated=recalculated,
        alerts=alerts,
        severity_alerts=severity_alerts,
        disclosure=HITL_WATERMARK_TEXT,
    )
