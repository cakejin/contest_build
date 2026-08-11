"""힌남노 리플레이 큐레이션 JSON 로더 — HANDOVER.md §4.2 2.2 "출처 URL 명시된 정적
JSON을 타임스탬프 기준 재생". `flood_history_events.source_url NOT NULL`(§4.3)과
동일한 정신을 DB 제약 없이 Python 레벨에서 강제한다: source_url이 없는 이벤트는
로딩 자체를 거부한다.
"""

from __future__ import annotations

import json
from pathlib import Path

from climate_risk.advisory.schema import TIME_PRECISION_VALUES, AdvisoryEvent, CuratedTimeline


class CuratedDataError(ValueError):
    """큐레이션 JSON이 형식·제약을 위반했을 때(source_url 누락 등)."""


def load_curated_timeline(path: Path) -> CuratedTimeline:
    raw = json.loads(path.read_text(encoding="utf-8"))

    events: list[AdvisoryEvent] = []
    for raw_event in raw["events"]:
        source_url = raw_event.get("source_url")
        if not source_url:
            raise CuratedDataError(
                f"event_id={raw_event.get('event_id')!r}에 source_url이 없습니다 — "
                "출처 없는 이벤트는 로딩을 거부합니다(HANDOVER §4.3 source_url NOT NULL 원칙)."
            )
        time_precision = raw_event.get("time_precision")
        if time_precision not in TIME_PRECISION_VALUES:
            raise CuratedDataError(
                f"event_id={raw_event.get('event_id')!r}의 time_precision={time_precision!r}이 "
                f"허용 목록({sorted(TIME_PRECISION_VALUES)})에 없습니다."
            )
        events.append(
            AdvisoryEvent(
                event_id=raw_event["event_id"],
                issued_at=raw_event["issued_at"],
                time_precision=time_precision,
                event_type=raw_event["event_type"],
                warning_type=raw_event.get("warning_type"),
                description=raw_event["description"],
                source_url=source_url,
                target_region_text=raw_event.get("target_region_text", ""),
            )
        )

    return CuratedTimeline(
        event_name=raw["event_name"],
        region_code=raw["region_code"],
        region_name=raw["region_name"],
        disclaimer=raw["disclaimer"],
        events=events,
    )
