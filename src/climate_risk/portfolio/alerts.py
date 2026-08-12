"""재심사 알림 큐 — HANDOVER.md §4.1 정확한 스키마
`{collateral_id, score_before, score_after, EAL_before, EAL_after, EAL_change_pct, threshold, geocode_confidence}`.

LTV·금리 필드는 절대 넣지 않는다(보호형 사용 규율 2항 — 소급 불리 적용 금지) —
이 큐는 "재심사가 필요할 수 있다"는 알림일 뿐, 조건 변경 자체가 아니다.
`score_before`/`score_after`는 `building.vulnerability_score`(EAL과 별도로 존재하는
유일한 스칼라)를 쓴다.
"""

from __future__ import annotations

import dataclasses
import json
import math
from dataclasses import dataclass
from pathlib import Path

from climate_risk.config import EAL_ALERT_THRESHOLD_PCT
from climate_risk.portfolio.recalc import PortfolioRecalcResult
from climate_risk.portfolio.schema import PortfolioRecord


@dataclass(frozen=True)
class AlertQueueEntry:
    collateral_id: str
    score_before: float | None
    score_after: float | None
    EAL_before: float
    EAL_after: float | None
    EAL_change_pct: float | None
    threshold: float
    geocode_confidence: str | None


def _eal_change_pct(before: float, after: float | None) -> float | None:
    if after is None:
        return None
    if before == 0:
        return None if after == 0 else float("inf")
    return (after - before) / before


def build_alert_queue(
    portfolio_records: list[PortfolioRecord],
    recalc_results: list[PortfolioRecalcResult],
    threshold_pct: float = EAL_ALERT_THRESHOLD_PCT,
) -> list[AlertQueueEntry]:
    records_by_id = {r.collateral_id: r for r in portfolio_records}

    entries: list[AlertQueueEntry] = []
    for result in recalc_results:
        record = records_by_id.get(result.collateral_id)
        if record is None:
            continue

        eal_after = result.scenario.eal.EAL_mean  # None이면 INSUFFICIENT_INPUT — 알림 대상 아님
        change_pct = _eal_change_pct(record.eal_before, eal_after)

        if change_pct is None:
            continue
        if abs(change_pct) < threshold_pct:
            continue

        entries.append(
            AlertQueueEntry(
                collateral_id=result.collateral_id,
                score_before=record.score_before,
                score_after=result.building.vulnerability_score,
                EAL_before=record.eal_before,
                EAL_after=eal_after,
                EAL_change_pct=change_pct,
                threshold=threshold_pct,
                geocode_confidence=result.geocode_confidence,
            )
        )
    return entries


def _json_safe_entry(entry: AlertQueueEntry) -> dict:
    """EAL_change_pct가 무한대(before=0 -> after>0)면 json.dumps가 표준이 아닌
    `Infinity` 토큰을 그대로 써버려 로그가 유효한 JSON이 아니게 된다 — 문자열로 치환한다."""
    data = dataclasses.asdict(entry)
    pct = data.get("EAL_change_pct")
    if isinstance(pct, float) and math.isinf(pct):
        data["EAL_change_pct"] = "inf" if pct > 0 else "-inf"
    return data


def append_to_alert_queue_log(entries: list[AlertQueueEntry], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        for entry in entries:
            f.write(json.dumps(_json_safe_entry(entry), ensure_ascii=False) + "\n")
