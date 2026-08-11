"""특보 리플레이 데이터 형태 — HANDOVER.md §4.2 2.2 replay 모드 스펙.

`{active_warnings: [{type, issued_at, source_url}], trigger_event: bool, mode}` 출력
형태를 만드는 `AdvisoryEvent`/`CuratedTimeline`. 실제 힌남노 데이터의 issued_at은
분단위 공식 발효시각이 아니라 뉴스 보도시각이라(events.json disclaimer 참조)
time_precision으로 정밀도를 정직하게 남긴다 — 허위로 분단위 정밀도를 주장하지 않는다.
"""

from __future__ import annotations

from dataclasses import dataclass

TIME_PRECISION_VALUES = {
    "exact",
    "approximate",
    "approximate_range",
    "approximate_shortly_after",
    "date_only",
    "article_timestamp",
    "unspecified",
}


@dataclass(frozen=True)
class AdvisoryEvent:
    event_id: str
    issued_at: str
    time_precision: str
    event_type: str
    warning_type: str | None
    description: str
    source_url: str
    target_region_text: str

    @property
    def source_id(self) -> str:
        return f"advisory:event:{self.event_id}"


@dataclass(frozen=True)
class CuratedTimeline:
    event_name: str
    region_code: str
    region_name: str
    disclaimer: str
    events: list[AdvisoryEvent]
