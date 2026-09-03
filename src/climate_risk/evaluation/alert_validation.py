"""재심사 알림 트리거 후보 4분면 검증 — 라벨셋·캐시 로더 + 에피소드 클러스터링
(DEV_LOG.md 2026-09-03 논의 항목 참조).

이 모듈은 **평가 전용**이다. 프로덕션 트리거 경로(portfolio/alerts.py·
portfolio/severity_alerts.py·agents/portfolio_agent.py)는 이 모듈을 import하지 않는다.

세 종류의 데이터를 다룬다(전부 `config.ALERT_VALIDATION_DIR` 아래, data/는 gitignore):
1. `labeled_events.json` — 사람이 라벨링한 과거 사건(지역×기간). `damage_confirmed`는
   **독립 근거**(실측 침수흔적·뉴스·특별재난지역 선포)로만 정하고 source_url이 필수다.
   `eal_alert_fired`(현행 EAL 변화율 알림이 켜졌는지)는 **참고 열**이다 — 후보 선정에
   쓰지 않는다(2026-09-03 사용자 결정, 이유는 DEV_LOG 참조).
2. `kma_history/{zone_group}.json` — 기상청 API허브 특보 이력을 한 번 조회해 저장한
   원시 행. 코드(wrn/lvl/cmd)만 저장하고 라벨은 로드 시 kma_historical의 사전으로
   재유도한다(진실의 원천을 하나로 유지).
3. `timelines/{event_id}.json` — 라벨 사건별로 KMA 이력+큐레이션+재난문자를 병합한
   `AdvisoryEvent` 타임라인. 소스별 조회 상태(`sources`)를 그대로 보존한다 — 재난문자
   조회가 IP 미등록으로 실패했으면 그 사실이 파일에 남는다(설계원칙1 "데이터 없음≠
   위험 없음"과 같은 정신: 실패를 빈 결과로 위장하지 않는다).

캐시 파일이 없으면 조용히 빈 결과를 내지 않고 `AlertValidationDataError`를 던진다.

`_historical_event_to_advisory_event`는 agents/advisory_agent.py의 private 헬퍼지만
일부러 그대로 import한다 — 프로덕션 historical 모드가 만드는 `AdvisoryEvent`와 여기서
만드는 에피소드 타임라인이 조용히 달라지면(warning_type 포맷·severity_level 채움 등)
후보 함수의 판정이 프로덕션과 어긋나므로, 변환 로직을 복제하지 않는다.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from climate_risk.advisory.kma_historical import (
    CMD_CODE_LABELS,
    LVL_CODE_LABELS,
    REGION_CODE_TO_KMA_ZONE,
    WRN_CODE_LABELS,
    HistoricalWarningEvent,
)
from climate_risk.advisory.schema import TIME_PRECISION_VALUES, AdvisoryEvent
from climate_risk.agents.advisory_agent import _historical_event_to_advisory_event
from climate_risk.config import ALERT_VALIDATION_DIR

KST = timezone(timedelta(hours=9))

LABELED_EVENTS_PATH = ALERT_VALIDATION_DIR / "labeled_events.json"
KMA_HISTORY_DIR = ALERT_VALIDATION_DIR / "kma_history"
TIMELINES_DIR = ALERT_VALIDATION_DIR / "timelines"
RAINFALL_DIR = ALERT_VALIDATION_DIR / "rainfall"  # 2026-09-03(계속6) 강수 관측 캐시(사건별)

# kma_historical.REGION_CODE_TO_KMA_ZONE이 대구 5개구를 특보구역 하나로 묶으므로
# (kma_historical.py 모듈 docstring), 같은 특보 에피소드가 5번 집계되지 않도록 zone
# group 단위로 이력을 마이닝한다. 대표 region_code는 27260(수성구) — 큐레이션 타임라인·
# 침수흔적·심각도 로그가 전부 이 코드를 참조한다.
ZONE_GROUPS: dict[str, tuple[str, ...]] = {
    "47111": ("47111",),
    "48310": ("48310",),
    "daegu": ("27200", "27110", "27260", "27140", "27230"),
}
REPRESENTATIVE_REGION_CODE: dict[str, str] = {"47111": "47111", "48310": "48310", "daegu": "27260"}

EPISODE_SOURCES = frozenset({"curated", "kma_mined", "live_log"})
DAMAGE_UNKNOWN = "unknown"

# 에피소드 클러스터링 규칙(사전 등록, DEV_LOG.md 2026-09-03 참조 — 결과를 보고 바꾸지 않는다).
EPISODE_GAP_HOURS = 48
EPISODE_WINDOW_PAD_DAYS = 1
# 발표/대치/연장/변경 — 해제 계열(3 해제, 4 대치해제, 7 변경해제)은 peak 등급 산정에서 제외.
ISSUE_CMD_CODES = frozenset({"1", "2", "5", "6"})

_SENTINEL_YEAR = 2100  # kma_historical._SENTINEL_NEVER_EXPIRES와 같은 기준(연도≥2100)


class AlertValidationDataError(ValueError):
    """라벨 파일·캐시 파일이 없거나 계약을 위반할 때 — 조용히 빈 결과로 대체하지 않는다."""


def zone_group_for(region_code: str) -> str:
    for group, codes in ZONE_GROUPS.items():
        if region_code in codes:
            return group
    raise AlertValidationDataError(f"region_code={region_code!r}는 어떤 zone group에도 속하지 않습니다.")


# ---------------------------------------------------------------------------
# 1. 라벨셋
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LabelEvidence:
    type: str  # "flood_marks" | "news" | "special_disaster_area" | 기타 자유 문자열
    detail: str
    source_url: str


@dataclass(frozen=True)
class LabeledAlertEvent:
    event_id: str
    region_code: str
    zone_group: str
    window_start: date  # KST 달력 날짜, 양끝 포함
    window_end: date
    episode_source: str  # "curated" | "kma_mined" | "live_log"
    damage_confirmed: bool | None  # None == "unknown"
    evidence: tuple[LabelEvidence, ...]
    label_note: str
    eal_alert_fired: bool | None  # 참고 열 — 후보 선정에 쓰지 않음
    eal_alert_source: str


@dataclass(frozen=True)
class AlertValidationSet:
    dataset: str
    created_at: str
    preregistration_note: str
    label_policy: str
    events: list[LabeledAlertEvent]


def _parse_damage_label(raw: object, event_id: str) -> bool | None:
    if raw is True or raw is False:
        return raw
    if raw == DAMAGE_UNKNOWN:
        return None
    raise AlertValidationDataError(
        f"{event_id}: damage_confirmed는 true/false/\"unknown\" 중 하나여야 합니다(현재 {raw!r})."
    )


def _parse_labeled_event(raw: dict) -> LabeledAlertEvent:
    event_id = raw.get("event_id")
    if not event_id:
        raise AlertValidationDataError("event_id가 비어있는 라벨 사건이 있습니다.")
    region_code = raw.get("region_code")
    if region_code not in REGION_CODE_TO_KMA_ZONE:
        raise AlertValidationDataError(f"{event_id}: region_code={region_code!r}는 특보구역 매핑에 없습니다.")
    episode_source = raw.get("episode_source")
    if episode_source not in EPISODE_SOURCES:
        raise AlertValidationDataError(f"{event_id}: episode_source={episode_source!r} (허용: {sorted(EPISODE_SOURCES)})")

    window_start = date.fromisoformat(raw["window_start"])
    window_end = date.fromisoformat(raw["window_end"])
    if window_start > window_end:
        raise AlertValidationDataError(f"{event_id}: window_start가 window_end보다 늦습니다.")

    damage_confirmed = _parse_damage_label(raw.get("damage_confirmed"), event_id)
    evidence = tuple(
        LabelEvidence(type=e.get("type", ""), detail=e.get("detail", ""), source_url=e.get("source_url", ""))
        for e in raw.get("evidence", [])
    )
    label_note = raw.get("label_note", "") or ""

    if damage_confirmed is None:
        if not label_note.strip():
            raise AlertValidationDataError(f"{event_id}: damage_confirmed=\"unknown\"이면 label_note(왜 미확인인지)가 필수입니다.")
    else:
        if not evidence:
            raise AlertValidationDataError(f"{event_id}: damage_confirmed={damage_confirmed}이면 evidence가 1건 이상 필요합니다.")
        for e in evidence:
            if not e.source_url.startswith("http"):
                raise AlertValidationDataError(f"{event_id}: evidence source_url이 http로 시작하지 않습니다({e.source_url!r}).")

    eal_alert_fired = raw.get("eal_alert_fired")
    if eal_alert_fired not in (True, False, None):
        raise AlertValidationDataError(f"{event_id}: eal_alert_fired는 true/false/null이어야 합니다.")
    eal_alert_source = raw.get("eal_alert_source", "") or ""
    if eal_alert_fired is not None and not eal_alert_source.strip():
        raise AlertValidationDataError(f"{event_id}: eal_alert_fired를 기록했으면 eal_alert_source(근거)가 필수입니다.")

    return LabeledAlertEvent(
        event_id=event_id,
        region_code=region_code,
        zone_group=zone_group_for(region_code),
        window_start=window_start,
        window_end=window_end,
        episode_source=episode_source,
        damage_confirmed=damage_confirmed,
        evidence=evidence,
        label_note=label_note,
        eal_alert_fired=eal_alert_fired,
        eal_alert_source=eal_alert_source,
    )


def load_alert_validation_set(path: Path = LABELED_EVENTS_PATH) -> AlertValidationSet:
    if not path.exists():
        raise AlertValidationDataError(f"라벨 파일이 없습니다: {path}")
    raw = json.loads(path.read_text(encoding="utf-8"))
    events = [_parse_labeled_event(r) for r in raw.get("events", [])]
    ids = [e.event_id for e in events]
    duplicates = sorted({i for i in ids if ids.count(i) > 1})
    if duplicates:
        raise AlertValidationDataError(f"event_id 중복: {duplicates}")
    return AlertValidationSet(
        dataset=raw.get("dataset", ""),
        created_at=raw.get("created_at", ""),
        preregistration_note=raw.get("preregistration_note", ""),
        label_policy=raw.get("label_policy", ""),
        events=events,
    )


# ---------------------------------------------------------------------------
# 2. 시각 파싱 / AdvisoryEvent 직렬화
# ---------------------------------------------------------------------------


def parse_issued_at_kst(value: str) -> datetime:
    """`AdvisoryEvent.issued_at`(ISO8601, 날짜만 있을 수도 있음)을 KST-aware datetime으로.
    tz 정보가 없으면 KST로 간주하고, 날짜만 있으면 그날 00:00 KST로 본다(큐레이션의
    `time_precision="date_only"` 이벤트)."""
    text = value.strip()
    if len(text) == 10:  # "YYYY-MM-DD"
        return datetime.combine(date.fromisoformat(text), datetime.min.time(), tzinfo=KST)
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=KST)
    return dt.astimezone(KST)


def advisory_event_to_dict(event: AdvisoryEvent) -> dict:
    return {
        "event_id": event.event_id,
        "issued_at": event.issued_at,
        "time_precision": event.time_precision,
        "event_type": event.event_type,
        "warning_type": event.warning_type,
        "description": event.description,
        "source_url": event.source_url,
        "target_region_text": event.target_region_text,
        "severity_level": event.severity_level,
    }


def advisory_event_from_dict(raw: dict) -> AdvisoryEvent:
    if not raw.get("source_url"):
        raise AlertValidationDataError(f"타임라인 이벤트 {raw.get('event_id')!r}에 source_url이 없습니다.")
    if raw.get("time_precision") not in TIME_PRECISION_VALUES:
        raise AlertValidationDataError(f"타임라인 이벤트 {raw.get('event_id')!r}의 time_precision이 유효하지 않습니다.")
    return AdvisoryEvent(
        event_id=raw["event_id"],
        issued_at=raw["issued_at"],
        time_precision=raw["time_precision"],
        event_type=raw["event_type"],
        warning_type=raw.get("warning_type"),
        description=raw.get("description", ""),
        source_url=raw["source_url"],
        target_region_text=raw.get("target_region_text", ""),
        severity_level=raw.get("severity_level"),
    )


# ---------------------------------------------------------------------------
# 3. 사건별 타임라인 캐시
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CachedTimeline:
    event_id: str
    region_code: str
    window_start: date
    window_end: date
    fetched_at: str
    sources: dict  # {"kma_historical": {...}, "curated": {...}, "disaster_msg": {...}}
    events: list[AdvisoryEvent]


def timeline_cache_path(event_id: str, directory: Path = TIMELINES_DIR) -> Path:
    return directory / f"{event_id}.json"


def load_cached_timeline(event_id: str, directory: Path = TIMELINES_DIR) -> CachedTimeline:
    path = timeline_cache_path(event_id, directory)
    if not path.exists():
        raise AlertValidationDataError(
            f"타임라인 캐시가 없습니다: {path} — scripts/fetch_alert_validation_cache.py --events-only 로 먼저 생성하세요."
        )
    raw = json.loads(path.read_text(encoding="utf-8"))
    events = [advisory_event_from_dict(e) for e in raw.get("events", [])]
    events.sort(key=lambda e: parse_issued_at_kst(e.issued_at))
    return CachedTimeline(
        event_id=raw["event_id"],
        region_code=raw["region_code"],
        window_start=date.fromisoformat(raw["window_start"]),
        window_end=date.fromisoformat(raw["window_end"]),
        fetched_at=raw.get("fetched_at", ""),
        sources=raw.get("sources", {}),
        events=events,
    )


def cached_timeline_to_dict(timeline: CachedTimeline) -> dict:
    return {
        "event_id": timeline.event_id,
        "region_code": timeline.region_code,
        "window_start": timeline.window_start.isoformat(),
        "window_end": timeline.window_end.isoformat(),
        "fetched_at": timeline.fetched_at,
        "sources": timeline.sources,
        "events": [advisory_event_to_dict(e) for e in timeline.events],
    }


def events_in_window(events: list[AdvisoryEvent], window_start: date, window_end: date) -> list[AdvisoryEvent]:
    """issued_at(KST 날짜)이 [window_start, window_end] 안인 이벤트만."""
    return [e for e in events if window_start <= parse_issued_at_kst(e.issued_at).date() <= window_end]


# ---------------------------------------------------------------------------
# 4. KMA 이력 캐시 + 에피소드 클러스터링
# ---------------------------------------------------------------------------


def historical_event_to_dict(row: HistoricalWarningEvent) -> dict:
    return {
        "reg_id": row.reg_id,
        "tm_fc": row.tm_fc.isoformat(),
        "tm_ef": row.tm_ef.isoformat(),
        "wrn_code": row.wrn_code,
        "lvl_code": row.lvl_code,
        "cmd_code": row.cmd_code,
    }


def historical_event_from_dict(raw: dict) -> HistoricalWarningEvent:
    wrn, lvl, cmd = raw["wrn_code"], raw["lvl_code"], raw["cmd_code"]
    return HistoricalWarningEvent(
        reg_id=raw["reg_id"],
        tm_fc=datetime.fromisoformat(raw["tm_fc"]),
        tm_ef=datetime.fromisoformat(raw["tm_ef"]),
        wrn_code=wrn,
        wrn_label=WRN_CODE_LABELS.get(wrn, f"미확인({wrn})"),
        lvl_code=lvl,
        lvl_label=LVL_CODE_LABELS.get(lvl, f"미확인({lvl})"),
        cmd_code=cmd,
        cmd_label=CMD_CODE_LABELS.get(cmd, f"미확인({cmd})"),
    )


@dataclass(frozen=True)
class KmaHistoryCache:
    zone_group: str
    representative_region_code: str
    fetched_at: str
    range_start: date
    range_end: date
    chunks: list[dict]  # [{tmfc1, tmfc2, reg_id, status, n_rows, note}]
    rows: list[HistoricalWarningEvent]


def kma_history_cache_path(zone_group: str, directory: Path = KMA_HISTORY_DIR) -> Path:
    return directory / f"{zone_group}.json"


def load_kma_history(zone_group: str, directory: Path = KMA_HISTORY_DIR) -> KmaHistoryCache:
    path = kma_history_cache_path(zone_group, directory)
    if not path.exists():
        raise AlertValidationDataError(
            f"KMA 이력 캐시가 없습니다: {path} — scripts/fetch_alert_validation_cache.py 로 먼저 생성하세요."
        )
    raw = json.loads(path.read_text(encoding="utf-8"))
    rows = [historical_event_from_dict(r) for r in raw.get("rows", [])]
    rows.sort(key=lambda r: r.tm_ef)
    return KmaHistoryCache(
        zone_group=raw["zone_group"],
        representative_region_code=raw["representative_region_code"],
        fetched_at=raw.get("fetched_at", ""),
        range_start=date.fromisoformat(raw["range_start"]),
        range_end=date.fromisoformat(raw["range_end"]),
        chunks=raw.get("chunks", []),
        rows=rows,
    )


def kma_history_cache_to_dict(cache: KmaHistoryCache) -> dict:
    return {
        "zone_group": cache.zone_group,
        "representative_region_code": cache.representative_region_code,
        "fetched_at": cache.fetched_at,
        "range_start": cache.range_start.isoformat(),
        "range_end": cache.range_end.isoformat(),
        "chunks": cache.chunks,
        "rows": [historical_event_to_dict(r) for r in cache.rows],
    }


@dataclass(frozen=True)
class WarningEpisode:
    episode_id: str
    zone_group: str
    window_start: date  # 첫 tm_ef 날짜 − pad
    window_end: date  # 마지막 tm_ef 날짜 + pad
    peak_lvl_code: str  # 발표/대치/연장/변경 행 중 최고 등급("0"이면 해당 행 없음)
    warning_codes: tuple[str, ...]  # 에피소드 안 wrn_code 종류(정렬)
    rows: tuple[HistoricalWarningEvent, ...]


def is_sentinel_row(row: HistoricalWarningEvent) -> bool:
    return row.tm_ef.year >= _SENTINEL_YEAR or row.tm_fc.year >= _SENTINEL_YEAR


def cluster_episodes(
    rows: list[HistoricalWarningEvent],
    zone_group: str,
    gap_hours: int = EPISODE_GAP_HOURS,
    pad_days: int = EPISODE_WINDOW_PAD_DAYS,
) -> list[WarningEpisode]:
    """tm_ef 순으로 정렬한 뒤 인접 행 간격이 gap_hours를 넘으면 새 에피소드로 자른다.
    만료 sentinel(연도≥2100) 행은 제외한다(count_sentinel_rows로 따로 센다)."""
    valid = sorted((r for r in rows if not is_sentinel_row(r)), key=lambda r: r.tm_ef)
    episodes: list[WarningEpisode] = []
    bucket: list[HistoricalWarningEvent] = []
    gap = timedelta(hours=gap_hours)

    def _flush() -> None:
        if not bucket:
            return
        first, last = bucket[0].tm_ef, bucket[-1].tm_ef
        issue_levels = [r.lvl_code for r in bucket if r.cmd_code in ISSUE_CMD_CODES and r.lvl_code.isdigit()]
        peak = max(issue_levels, key=int) if issue_levels else "0"
        episodes.append(
            WarningEpisode(
                episode_id=f"{zone_group}-{first.astimezone(KST):%Y%m%d-%H%M}",
                zone_group=zone_group,
                window_start=first.astimezone(KST).date() - timedelta(days=pad_days),
                window_end=last.astimezone(KST).date() + timedelta(days=pad_days),
                peak_lvl_code=peak,
                warning_codes=tuple(sorted({r.wrn_code for r in bucket})),
                rows=tuple(bucket),
            )
        )

    for row in valid:
        if bucket and row.tm_ef - bucket[-1].tm_ef > gap:
            _flush()
            bucket = []
        bucket.append(row)
    _flush()
    return episodes


def count_sentinel_rows(rows: list[HistoricalWarningEvent]) -> int:
    return sum(1 for r in rows if is_sentinel_row(r))


def episode_timeline(episode: WarningEpisode) -> list[AdvisoryEvent]:
    """에피소드의 KMA 행을 프로덕션 historical 모드와 동일한 변환으로 AdvisoryEvent화.
    재난문자·큐레이션은 포함되지 않는다 — 재난문자 의존 후보에겐 하한(lower bound)."""
    return [_historical_event_to_advisory_event(r) for r in episode.rows]


# ---------------------------------------------------------------------------
# 5. 강수 관측 캐시(2026-09-03(계속6)) — 기상청 API허브 지상관측 값을 사건별로 저장하고,
#    후보 함수 계약(`list[AdvisoryEvent] -> bool`)을 유지하기 위해 관측값을 AdvisoryEvent로 인코딩한다.
#    event_type="강수관측", event_id 접두어 "obs-", description은 "KEY=값;KEY=값" 고정 포맷
#    (trigger_features.parse_observation_values가 파싱). 특보·재난문자 후보는 event_type으로
#    걸러내므로 관측 이벤트가 섞여도 기존 판정에 영향이 없다.
# ---------------------------------------------------------------------------

OBSERVATION_EVENT_TYPE = "강수관측"
OBSERVATION_EVENT_ID_PREFIX = "obs-"
OBS_KIND_ASOS_HOURLY = "ASOS"
OBS_KIND_AWS_HOURLY = "AWS"
OBS_KIND_AWS_DAILY = "AWS일"


@dataclass(frozen=True)
class RainfallCache:
    event_id: str
    region_code: str
    fetched_at: str
    asos_stn: str | None
    aws_stn: str | None
    sources: dict  # {"asos_hourly": {status,n}, "aws_hourly": {status,n}, "aws_daily": {status,n}}
    asos_hourly: list[dict]  # {tm, rn_1h_mm, rn_day_mm}
    aws_hourly: list[dict]  # {tm, rn_hr1_mm, rn_day_mm, rn_60m_max_mm, rn_15m_max_mm}
    aws_daily: list[dict]  # {day, rn_day_mm, name}


def rainfall_cache_path(event_id: str, directory: Path = RAINFALL_DIR) -> Path:
    return directory / f"{event_id}.json"


def load_cached_rainfall(event_id: str, directory: Path = RAINFALL_DIR) -> RainfallCache:
    path = rainfall_cache_path(event_id, directory)
    if not path.exists():
        raise AlertValidationDataError(
            f"강수 캐시가 없습니다: {path} — scripts/fetch_alert_validation_cache.py --rainfall 로 먼저 생성하세요."
        )
    raw = json.loads(path.read_text(encoding="utf-8"))
    return RainfallCache(
        event_id=raw["event_id"], region_code=raw["region_code"], fetched_at=raw.get("fetched_at", ""),
        asos_stn=raw.get("asos_stn"), aws_stn=raw.get("aws_stn"), sources=raw.get("sources", {}),
        asos_hourly=raw.get("asos_hourly", []), aws_hourly=raw.get("aws_hourly", []), aws_daily=raw.get("aws_daily", []),
    )


def rainfall_cache_to_dict(cache: RainfallCache) -> dict:
    return {
        "event_id": cache.event_id, "region_code": cache.region_code, "fetched_at": cache.fetched_at,
        "asos_stn": cache.asos_stn, "aws_stn": cache.aws_stn, "sources": cache.sources,
        "asos_hourly": cache.asos_hourly, "aws_hourly": cache.aws_hourly, "aws_daily": cache.aws_daily,
    }


def _fmt_val(v: float | None) -> str:
    return "NA" if v is None else f"{v:.1f}"


def rainfall_to_advisory_events(cache: RainfallCache) -> list[AdvisoryEvent]:
    """관측 행 → AdvisoryEvent(event_type=강수관측). 결측은 'NA'로 남긴다(0으로 바꾸지 않음)."""
    src = "https://apihub.kma.go.kr/"
    out: list[AdvisoryEvent] = []
    for r in cache.asos_hourly:
        out.append(AdvisoryEvent(
            event_id=f"{OBSERVATION_EVENT_ID_PREFIX}asos-{cache.asos_stn}-{r['tm'][:16]}",
            issued_at=r["tm"], time_precision="exact", event_type=OBSERVATION_EVENT_TYPE,
            warning_type=f"{OBS_KIND_ASOS_HOURLY} {cache.asos_stn}",
            description=f"RN_1H={_fmt_val(r.get('rn_1h_mm'))};RN_DAY={_fmt_val(r.get('rn_day_mm'))}",
            source_url=src, target_region_text=f"ASOS stn={cache.asos_stn}", severity_level=None,
        ))
    for r in cache.aws_hourly:
        out.append(AdvisoryEvent(
            event_id=f"{OBSERVATION_EVENT_ID_PREFIX}aws-{cache.aws_stn}-{r['tm'][:16]}",
            issued_at=r["tm"], time_precision="exact", event_type=OBSERVATION_EVENT_TYPE,
            warning_type=f"{OBS_KIND_AWS_HOURLY} {cache.aws_stn}",
            description=(
                f"RN_HR1={_fmt_val(r.get('rn_hr1_mm'))};RN_DAY={_fmt_val(r.get('rn_day_mm'))};"
                f"RN_60M_MAX={_fmt_val(r.get('rn_60m_max_mm'))};RN_15M_MAX={_fmt_val(r.get('rn_15m_max_mm'))}"
            ),
            source_url=src, target_region_text=f"AWS stn={cache.aws_stn}", severity_level=None,
        ))
    for r in cache.aws_daily:
        out.append(AdvisoryEvent(
            event_id=f"{OBSERVATION_EVENT_ID_PREFIX}awsday-{cache.aws_stn}-{r['day'][:10]}",
            issued_at=r["day"], time_precision="date_only", event_type=OBSERVATION_EVENT_TYPE,
            warning_type=f"{OBS_KIND_AWS_DAILY} {cache.aws_stn}",
            description=f"RN_DAY={_fmt_val(r.get('rn_day_mm'))}",
            source_url=src, target_region_text=f"AWS stn={cache.aws_stn} {r.get('name', '')}", severity_level=None,
        ))
    return out
