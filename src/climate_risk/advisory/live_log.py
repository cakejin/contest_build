"""라이브 특보 조회 결과 적재 — 실시간 기상청 API 호출 결과를 append-only로 쌓아
나중에 "이 날짜에 이 지역에 실제로 무슨 특보가 있었는지"를 조회할 수 있게 한다
(2026-08-18 사용자와의 설계 논의, DEV_LOG.md 참조).

기상청 API 자체가 "지금 시점" 조회 전용이라(advisory/live.py — 6일 초과 과거 조회는
resultCode 99로 실패함이 실측 확인됨) 과거를 재구성할 방법이 이 로그밖에 없다. 조회에
실패했거나(UPSTREAM_ERROR) 매핑이 없어도(UNKNOWN_REGION) 그 자체가 사실이라 정직하게
남긴다(설계원칙1 "데이터 없음≠위험 없음"과 같은 정신 — 특보가 없었다는 사실도 기록할
가치가 있다).

지금 당장은 이 로그를 읽어 "날짜 기반 리플레이" 화면을 만드는 건 다음 단계다 —
로그가 어느 정도 쌓인 뒤에나 의미가 있어서, 이 모듈은 적재(append)와 원시 조회(read)만
제공한다.
"""

from __future__ import annotations

import dataclasses
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from climate_risk.advisory.live import LiveQueryResult


@dataclass(frozen=True)
class LiveAdvisoryLogEntry:
    queried_at: str  # ISO8601 UTC — 실제 조회 시각(사건 발효 시각이 아니다)
    region_code: str
    stn_id: str | None
    stn_id_verified: bool
    status: str
    trigger_event: bool
    events: list[dict]  # AdvisoryEvent를 dataclasses.asdict()한 형태 그대로 — 나중에
    # 날짜 기반 재생 시 그대로 재구성 가능하도록 요약(개수)이 아니라 원본을 남긴다.
    note: str


def append_live_query_log(
    region_code: str,
    result: LiveQueryResult,
    trigger_event: bool,
    log_path: Path,
) -> LiveAdvisoryLogEntry:
    entry = LiveAdvisoryLogEntry(
        queried_at=datetime.now(timezone.utc).isoformat(),
        region_code=region_code,
        stn_id=result.stn_id,
        stn_id_verified=result.stn_id_verified,
        status=result.status,
        trigger_event=trigger_event,
        events=[dataclasses.asdict(e) for e in result.events],
        note=result.note,
    )
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(dataclasses.asdict(entry), ensure_ascii=False) + "\n")
    return entry


def read_live_advisory_log(log_path: Path) -> list[LiveAdvisoryLogEntry]:
    if not log_path.exists():
        return []
    entries: list[LiveAdvisoryLogEntry] = []
    with log_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            entries.append(LiveAdvisoryLogEntry(**json.loads(line)))
    return entries
