"""HITL 확인 클릭 감사로그 — HANDOVER.md §⑥ item5 "심사역 확인 클릭 이벤트를 감사로그에
타임스탬프로 기록"의 실체.

Week3 UI는 CLI/JSON 확장으로 한정하기로 했으므로(실제 클릭 가능한 화면 없음) 이 모듈은
"심사역이 스코어를 확인했다"는 이벤트를 기록하는 함수 자체를 제공해, 실제 UI가 붙었을 때
그 클릭 핸들러가 호출할 지점을 미리 만들어둔다 — 메커니즘의 시연이 목적이지 화면 자체가
목적이 아니다.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from climate_risk.policy.forbidden_phrases import contains_forbidden_phrase


class ForbiddenPhraseError(ValueError):
    """감사로그 note에 금지어가 포함되어 기록을 거부했을 때."""


@dataclass(frozen=True)
class AckRecord:
    collateral_id: str
    reviewer_id: str
    acknowledged_at: str  # ISO8601
    note: str | None


def record_reviewer_ack(
    collateral_id: str,
    reviewer_id: str,
    note: str | None = None,
    log_path: Path | None = None,
) -> AckRecord:
    """심사역 확인 이벤트 1건을 JSONL로 append한다. note가 금지어를 포함하면 기록 자체를
    거부한다 — 감사로그가 블루라이닝 표현의 우회 경로가 되지 않도록 막는다."""
    if note and contains_forbidden_phrase(note):
        raise ForbiddenPhraseError(f"금지어가 포함된 note는 감사로그에 기록할 수 없습니다: {note!r}")

    if log_path is None:
        from climate_risk.config import AUDIT_LOG_PATH

        log_path = AUDIT_LOG_PATH

    record = AckRecord(
        collateral_id=collateral_id,
        reviewer_id=reviewer_id,
        acknowledged_at=datetime.now(timezone.utc).isoformat(),
        note=note,
    )

    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(asdict(record), ensure_ascii=False) + "\n")

    return record


def read_audit_log(log_path: Path) -> list[AckRecord]:
    if not log_path.exists():
        return []
    records = []
    with log_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            records.append(AckRecord(**json.loads(line)))
    return records
