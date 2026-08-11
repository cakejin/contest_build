"""큐레이션 타임라인 재생 — HANDOVER.md §4.2 2.2 "타임스탬프 기준 재생, API 호출 없음".

issued_at은 전체 ISO8601(타임존 포함)일 수도, 날짜만(date_only 이벤트)일 수도 있다 —
날짜만인 이벤트는 그 날 00:00을 정렬 키로 취급한다(비교만을 위한 것이지 "정확한
시각이 00:00"이라는 주장이 아니다 — time_precision="date_only"가 그 정직성을 담보).
"""

from __future__ import annotations

from datetime import datetime

from climate_risk.advisory.schema import AdvisoryEvent, CuratedTimeline


def _sort_key(event: AdvisoryEvent) -> datetime:
    """정렬·비교 전용 naive datetime. date_only 이벤트(타임존 없음)와 그 외 이벤트
    (+09:00 타임존)가 섞여 있어, 그대로 비교하면 aware/naive 혼재로 TypeError가 난다 —
    타임존 정보를 버리고 비교하되 이건 순서 판단용일 뿐, 필드 자체(issued_at)는
    원본 정밀도 그대로 보존한다(time_precision이 그 사실을 담보)."""
    dt = datetime.fromisoformat(event.issued_at)
    return dt.replace(tzinfo=None) if dt.tzinfo is not None else dt


def replay_timeline(
    timeline: CuratedTimeline, as_of: datetime | None = None
) -> list[AdvisoryEvent]:
    """issued_at 기준 정렬된 이벤트 목록. as_of가 주어지면 그 시점까지 발생한 이벤트만
    반환한다(as_of=None이면 전체 타임라인 — 데모 기본값)."""
    events = sorted(timeline.events, key=_sort_key)

    if as_of is None:
        return events

    as_of_naive = as_of.replace(tzinfo=None) if as_of.tzinfo is not None else as_of
    return [event for event in events if _sort_key(event) <= as_of_naive]
