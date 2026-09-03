"""포트폴리오 배치 재계산 오케스트레이션 — HANDOVER.md §4.1 "혼합형 구조"의
지역필터링 즉시재계산 경로. `advisory.trigger_event`가 False여도 함수 자체는 안전하게
호출 가능하다(호출 여부 판단은 caller 책임 — graph/week3_demo.py 참조).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from climate_risk.advisory.kma_observation import StationRainfallWindow, fetch_station_rainfall_window
from climate_risk.agents.advisory_agent import AdvisoryAgentOutput, is_high_severity_event
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
    RAIN_STATUS_NOT_QUERIED,
    SeverityAlertQueueEntry,
    SeverityAlertSummary,
    append_to_severity_alert_queue_log,
    build_severity_alert_queue,
    summarize_severity_alerts,
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
    # 2026-09-03(계속10) — 지역별 최종 알림 1건(매칭 N건 중 주의 a·심각 s, 임계값·근거 포함).
    severity_summary: SeverityAlertSummary
    disclosure: str


def run_portfolio_agent(
    advisory: AdvisoryAgentOutput,
    portfolio_path: Path = PORTFOLIO_DATA_PATH,
    threshold_pct: float = EAL_ALERT_THRESHOLD_PCT,
    seed: int = DEFAULT_EAL_SEED,
    n_iterations: int = DEFAULT_EAL_ITERATIONS,
    alert_log_path: Path = ALERT_QUEUE_LOG_PATH,
    severity_alert_log_path: Path = SEVERITY_ALERT_QUEUE_LOG_PATH,
    # 2026-09-03(계속10) — 담보별 강수 등급용 관측 창. None이면 강수 조회를 생략하고 매칭 담보
    # 전원을 "강수미확인"으로 유지한다(네트워크 호출 없음 — 기존 호출부·테스트와 동작 호환).
    observation_window: tuple[datetime, datetime] | None = None,
    station_rainfall_fetcher: Callable[[datetime, datetime], StationRainfallWindow] = fetch_station_rainfall_window,
) -> PortfolioBatchResult:
    portfolio = load_portfolio(portfolio_path)
    filter_result = filter_by_region(portfolio, advisory.region_code)

    recalculated = recalc_subset(filter_result.matched, seed=seed, n_iterations=n_iterations)
    alerts = build_alert_queue(filter_result.matched, recalculated, threshold_pct=threshold_pct)
    append_to_alert_queue_log(alerts, alert_log_path)

    # 지역 트리거가 켜졌고 관측 창이 주어진 경우에만 강수를 조회한다(불필요한 API 호출 방지).
    station_rainfall = None
    rain_status, rain_note = RAIN_STATUS_NOT_QUERIED, ""
    region_triggered = any(is_high_severity_event(e) for e in advisory.timeline)
    if observation_window is not None and region_triggered and filter_result.matched:
        window = station_rainfall_fetcher(*observation_window)
        rain_status, rain_note = window.status, window.note
        station_rainfall = window.stations if window.stations else None
    severity_alerts = build_severity_alert_queue(filter_result.matched, advisory.timeline, station_rainfall)
    append_to_severity_alert_queue_log(severity_alerts, severity_alert_log_path)
    severity_summary = summarize_severity_alerts(
        filter_result.matched, advisory.timeline, severity_alerts, rain_status=rain_status, rain_note=rain_note
    )

    return PortfolioBatchResult(
        region_code=advisory.region_code,
        total_records=len(portfolio),
        matched_count=len(filter_result.matched),
        skipped_ungeocoded_count=filter_result.skipped_ungeocoded_count,
        other_region_count=filter_result.other_region_count,
        recalculated=recalculated,
        alerts=alerts,
        severity_alerts=severity_alerts,
        severity_summary=severity_summary,
        disclosure=HITL_WATERMARK_TEXT,
    )
