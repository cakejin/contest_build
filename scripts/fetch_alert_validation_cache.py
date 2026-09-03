"""재심사 알림 트리거 후보 4분면 검증 — **라이브 API를 호출해 오프라인 캐시를 만드는
유일한 스크립트**(DEV_LOG.md 2026-09-03 참조). 지표(`metrics.py::alert_trigger_precision_metric`)와
테스트는 이 스크립트가 만든 JSON만 읽는다(flood_marks_validation과 같은 관례).

두 가지를 만든다(둘 다 `config.ALERT_VALIDATION_DIR` 아래, data/는 gitignore):
1. `kma_history/{zone_group}.json` — 기상청 API허브 특보 이력을 `--since`(기본 2004-07-01,
   API 제공 시작일)부터 오늘까지 **연 단위 chunk**로 조회해 원시 행을 저장. chunk 양끝에서
   특보구역(REG_ID)이 다르면(대구 2026-05-31 개편) 구역 유효기간 경계에서 chunk를 쪼갠다 —
   `query_historical_warnings`가 구역을 `as_of=start`로만 해석하므로, 개편을 가로지르는
   chunk는 개편 이후 행을 조용히 놓치기 때문. chunk별 상태·행 수를 `chunks[]`에 남긴다.
2. `timelines/{event_id}.json` — `labeled_events.json`의 사건별로 (a) 위 캐시의 KMA 행
   (창 안) + (b) 큐레이션 타임라인(겹치면) + (c) 재난문자(safetydata) 를 병합한
   AdvisoryEvent 타임라인. 재난문자 조회 실패(IP 미등록 등)는 `sources.disaster_msg.status`에
   그대로 기록한다 — OK로 위장하지 않는다.

사용 예:
    python scripts/fetch_alert_validation_cache.py                      # KMA 전체 + 사건 타임라인
    python scripts/fetch_alert_validation_cache.py --skip-disaster-msg  # 화이트리스트 IP 아닐 때
    python scripts/fetch_alert_validation_cache.py --events-only        # 라벨 파일에 사건 추가 후
    python scripts/fetch_alert_validation_cache.py --events-only --refresh-disaster-msg  # 등록 IP에서 재난문자만 보강
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from climate_risk.advisory import kma_historical  # noqa: E402
from climate_risk.advisory.disaster_msg import (  # noqa: E402
    STATUS_OK as DM_STATUS_OK,
    query_disaster_messages_for_region,
)
from climate_risk.advisory.kma_historical import (  # noqa: E402
    STATUS_ACTIVATION_REQUIRED,
    STATUS_OK as KMA_STATUS_OK,
    HistoricalWarningEvent,
    fetch_region_zones,
    query_historical_warnings,
    resolve_region_zone,
)
from climate_risk.agents.advisory_agent import (  # noqa: E402
    _disaster_message_to_advisory_event,
    _historical_event_to_advisory_event,
    _overlapping_curated_events,
)
from climate_risk.advisory.kma_observation import (  # noqa: E402
    REGION_CODE_TO_ASOS_STN,
    REGION_CODE_TO_NEAREST_AWS_STN,
    fetch_asos_hourly,
    fetch_aws_daily,
    fetch_aws_hourly_stat,
)
from climate_risk.evaluation.collateral_counts import (  # noqa: E402
    STATION_RAINFALL_DIR,
    StationRainfall,
    StationRainfallCache,
    station_rainfall_cache_path,
    station_rainfall_cache_to_dict,
)
from climate_risk.evaluation.alert_validation import (  # noqa: E402
    KMA_HISTORY_DIR,
    KST,
    RAINFALL_DIR,
    REPRESENTATIVE_REGION_CODE,
    TIMELINES_DIR,
    ZONE_GROUPS,
    AlertValidationDataError,
    CachedTimeline,
    KmaHistoryCache,
    LabeledAlertEvent,
    RainfallCache,
    cached_timeline_to_dict,
    kma_history_cache_path,
    kma_history_cache_to_dict,
    load_alert_validation_set,
    load_cached_timeline,
    load_kma_history,
    parse_issued_at_kst,
    rainfall_cache_path,
    rainfall_cache_to_dict,
    timeline_cache_path,
)

_DEFAULT_SINCE = date(2004, 7, 1)


def _log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def _memoize_region_zones() -> None:
    """`query_historical_warnings`가 chunk마다 특보구역 API를 다시 호출하므로(2 HTTP/chunk),
    이 스크립트 프로세스 안에서만 첫 결과를 재사용한다 — 모듈 동작 자체는 바꾸지 않는다."""
    cache: dict[str, list] = {}

    def _cached():  # type: ignore[no-untyped-def]
        if "zones" not in cache:
            cache["zones"] = fetch_region_zones()
        return cache["zones"]

    kma_historical.fetch_region_zones = _cached  # type: ignore[assignment]


def _year_chunks(since: date, until: date) -> list[tuple[datetime, datetime]]:
    chunks: list[tuple[datetime, datetime]] = []
    start = datetime(since.year, since.month, since.day, tzinfo=KST)
    end_all = datetime(until.year, until.month, until.day, 23, 59, tzinfo=KST)
    while start <= end_all:
        year_end = datetime(start.year, 12, 31, 23, 59, tzinfo=KST)
        end = min(year_end, end_all)
        chunks.append((start, end))
        start = datetime(start.year + 1, 1, 1, tzinfo=KST)
    return chunks


def _split_at_zone_boundary(
    region_code: str, start: datetime, end: datetime, zones: list
) -> list[tuple[datetime, datetime]]:
    """chunk 양끝의 특보구역이 다르면 앞 구역의 valid_to에서 쪼갠다(재귀로 여러 경계 대응)."""
    zone_a = resolve_region_zone(region_code, start, zones)
    zone_b = resolve_region_zone(region_code, end, zones)
    if zone_a is None or zone_b is None or zone_a.reg_id == zone_b.reg_id:
        return [(start, end)]
    boundary = zone_a.valid_to
    if not (start < boundary < end):
        return [(start, end)]
    return [(start, boundary)] + _split_at_zone_boundary(region_code, boundary + timedelta(minutes=1), end, zones)


def mine_kma_history(zone_group: str, since: date, until: date, sleep_s: float) -> KmaHistoryCache:
    rep_code = REPRESENTATIVE_REGION_CODE[zone_group]
    zones = kma_historical.fetch_region_zones()
    chunk_records: list[dict] = []
    rows: list[HistoricalWarningEvent] = []
    seen: set[tuple] = set()

    for year_start, year_end in _year_chunks(since, until):
        for start, end in _split_at_zone_boundary(rep_code, year_start, year_end, zones):
            result = query_historical_warnings(rep_code, start, end)
            record = {
                "tmfc1": start.strftime("%Y%m%d%H%M"),
                "tmfc2": end.strftime("%Y%m%d%H%M"),
                "reg_id": result.reg_id,
                "status": result.status,
                "n_rows": len(result.events),
                "note": result.note,
            }
            chunk_records.append(record)
            _log(f"[{zone_group}] {record['tmfc1']}~{record['tmfc2']} reg={result.reg_id} {result.status} rows={len(result.events)}")
            if result.status == STATUS_ACTIVATION_REQUIRED:
                _log("특보자료 API 활용신청 미승인 — 중단합니다.")
                break
            for ev in result.events:
                key = (ev.reg_id, ev.tm_fc, ev.tm_ef, ev.wrn_code, ev.lvl_code, ev.cmd_code)
                if key in seen:
                    continue
                seen.add(key)
                rows.append(ev)
            time.sleep(sleep_s)

    rows.sort(key=lambda r: r.tm_ef)
    return KmaHistoryCache(
        zone_group=zone_group,
        representative_region_code=rep_code,
        fetched_at=datetime.now(tz=KST).isoformat(timespec="seconds"),
        range_start=since,
        range_end=until,
        chunks=chunk_records,
        rows=rows,
    )


def _window_bounds(event: LabeledAlertEvent) -> tuple[datetime, datetime]:
    start = datetime(event.window_start.year, event.window_start.month, event.window_start.day, tzinfo=KST)
    end = datetime(event.window_end.year, event.window_end.month, event.window_end.day, 23, 59, 59, tzinfo=KST)
    return start, end


def _kma_events_for_window(history: KmaHistoryCache, start: datetime, end: datetime) -> tuple[list, dict]:
    rows = [r for r in history.rows if start <= r.tm_ef <= end]
    reg_ids = sorted({r.reg_id for r in rows})
    covered = any(
        c["status"] == KMA_STATUS_OK
        and c["tmfc1"] <= end.strftime("%Y%m%d%H%M")
        and c["tmfc2"] >= start.strftime("%Y%m%d%H%M")
        for c in history.chunks
    )
    status = KMA_STATUS_OK if covered else "NOT_COVERED_BY_CACHE"
    return [_historical_event_to_advisory_event(r) for r in rows], {"status": status, "reg_ids": reg_ids, "n": len(rows)}


def _disaster_msg_events(event: LabeledAlertEvent, start: datetime, end: datetime) -> tuple[list, dict]:
    result = query_disaster_messages_for_region(event.region_code, start, end)
    if result.status != DM_STATUS_OK:
        return [], {"status": result.status, "n": 0, "note": result.note}
    return [_disaster_message_to_advisory_event(m) for m in result.messages], {"status": DM_STATUS_OK, "n": len(result.messages), "note": ""}


def build_timeline(
    event: LabeledAlertEvent,
    history: KmaHistoryCache,
    *,
    skip_disaster_msg: bool,
    existing: CachedTimeline | None,
    refresh_disaster_msg: bool,
) -> CachedTimeline:
    start, end = _window_bounds(event)
    kma_events, kma_source = _kma_events_for_window(history, start, end)
    curated_events = _overlapping_curated_events(event.region_code, start, end)
    curated_source = {"merged": bool(curated_events), "n": len(curated_events)}

    if existing is not None and not refresh_disaster_msg:
        dm_events = [e for e in existing.events if e.event_type == "재난문자" and e.event_id.startswith("disaster-msg-")]
        dm_source = existing.sources.get("disaster_msg", {"status": "SKIPPED", "n": 0})
    elif skip_disaster_msg:
        dm_events, dm_source = [], {"status": "SKIPPED", "n": 0, "note": "--skip-disaster-msg"}
    else:
        dm_events, dm_source = _disaster_msg_events(event, start, end)

    merged = {e.event_id: e for e in kma_events + curated_events + dm_events}
    events = sorted(merged.values(), key=lambda e: parse_issued_at_kst(e.issued_at))
    return CachedTimeline(
        event_id=event.event_id,
        region_code=event.region_code,
        window_start=event.window_start,
        window_end=event.window_end,
        fetched_at=datetime.now(tz=KST).isoformat(timespec="seconds"),
        sources={"kma_historical": kma_source, "curated": curated_source, "disaster_msg": dm_source},
        events=events,
    )


def build_rainfall(event: LabeledAlertEvent, aws_peak_pad_hours: int = 3, sleep_s: float = 0.3) -> RainfallCache:
    """사건 창의 강수 관측(2026-09-03(계속6)): ①지역 ASOS 시간자료 ②최근접 AWS 일통계
    ③최근접 AWS 시간통계(ASOS 최대 1시간 강수 시각 ±pad, 단일시각 반복 — awsh는 기간 파라미터를
    무시하므로). 실패·결측은 status로 남기고 값은 지어내지 않는다."""
    start, end = _window_bounds(event)
    asos_stn = REGION_CODE_TO_ASOS_STN.get(event.region_code)
    aws = REGION_CODE_TO_NEAREST_AWS_STN.get(event.region_code)
    aws_stn = aws[0] if aws else None
    sources: dict = {}
    asos_rows: list[dict] = []
    aws_hourly: list[dict] = []
    aws_daily: list[dict] = []

    if asos_stn:
        r = fetch_asos_hourly(asos_stn, start, end)
        sources["asos_hourly"] = {"status": r.status, "n": len(r.rows), "note": r.note, "stn": asos_stn}
        asos_rows = [{"tm": x.tm.isoformat(), "rn_1h_mm": x.rn_1h_mm, "rn_day_mm": x.rn_day_mm} for x in r.rows]
    else:
        sources["asos_hourly"] = {"status": "NO_STATION_MAPPING", "n": 0}
    time.sleep(sleep_s)

    if aws_stn:
        r = fetch_aws_daily(aws_stn, start, end)
        sources["aws_daily"] = {"status": r.status, "n": len(r.rows), "note": r.note, "stn": aws_stn, "name": aws[1], "km": aws[2]}
        aws_daily = [{"day": x.day.isoformat(), "rn_day_mm": x.rn_day_mm, "name": x.name} for x in r.rows]
        time.sleep(sleep_s)
        # ASOS 최대 1시간 강수 시각 ±pad(없으면 창 중앙) — 결측(-9)은 제외
        peaks = [x for x in asos_rows if x["rn_1h_mm"] is not None]
        if peaks:
            peak_tm = datetime.fromisoformat(max(peaks, key=lambda x: x["rn_1h_mm"])["tm"])
        else:
            peak_tm = start + (end - start) / 2
        statuses: list[str] = []
        for h in range(-aws_peak_pad_hours, aws_peak_pad_hours + 1):
            tm = (peak_tm + timedelta(hours=h)).replace(minute=0, second=0)
            r = fetch_aws_hourly_stat(aws_stn, tm)
            statuses.append(r.status)
            if r.status == "NO_SUCH_STATION":
                break  # 그 시점에 지점이 없으면 나머지도 없다
            for x in r.rows:
                aws_hourly.append({"tm": x.tm.isoformat(), "rn_hr1_mm": x.rn_hr1_mm, "rn_day_mm": x.rn_day_mm,
                                   "rn_60m_max_mm": x.rn_60m_max_mm, "rn_15m_max_mm": x.rn_15m_max_mm})
            time.sleep(sleep_s)
        sources["aws_hourly"] = {"status": "OK" if any(s == "OK" for s in statuses) else statuses[-1], "n": len(aws_hourly),
                                 "statuses": statuses, "peak_tm": peak_tm.isoformat(), "stn": aws_stn}
    else:
        sources["aws_daily"] = {"status": "NO_STATION_MAPPING", "n": 0}
        sources["aws_hourly"] = {"status": "NO_STATION_MAPPING", "n": 0}

    return RainfallCache(
        event_id=event.event_id, region_code=event.region_code,
        fetched_at=datetime.now(tz=KST).isoformat(timespec="seconds"),
        asos_stn=asos_stn, aws_stn=aws_stn, sources=sources,
        asos_hourly=asos_rows, aws_hourly=aws_hourly, aws_daily=aws_daily,
    )


def build_station_rainfall(event: LabeledAlertEvent, sleep_s: float = 0.3) -> StationRainfallCache:
    """사건 창의 날짜마다 전국 관측소 일강수(sfc_aws_day stn=0)를 조회해 지점별 최대값으로 합친다
    (DEV_LOG 2026-09-03(계속8)). 결측은 None 유지, 날짜별 API 상태를 day_status에 남긴다."""
    start, end = _window_bounds(event)
    days: list[str] = []
    day_status: dict[str, str] = {}
    acc: dict[str, dict] = {}
    cur = start
    while cur.date() <= end.date():
        day = cur.date().isoformat()
        days.append(day)
        r = fetch_aws_daily("0", cur, cur)
        day_status[day] = r.status
        for row in r.rows:
            a = acc.setdefault(row.stn, {"stn": row.stn, "name": row.name, "lat": row.lat, "lon": row.lon, "max": None, "n": 0})
            if row.rn_day_mm is not None:
                a["n"] += 1
                a["max"] = row.rn_day_mm if a["max"] is None else max(a["max"], row.rn_day_mm)
        cur += timedelta(days=1)
        time.sleep(sleep_s)
    stations = [StationRainfall(stn=a["stn"], name=a["name"], lat=a["lat"], lon=a["lon"], max_rn_day_mm=a["max"], n_days=a["n"]) for a in acc.values()]
    return StationRainfallCache(
        event_id=event.event_id, region_code=event.region_code,
        fetched_at=datetime.now(tz=KST).isoformat(timespec="seconds"),
        days=days, day_status=day_status, stations=stations,
    )


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="트리거 후보 4분면 검증용 오프라인 캐시 생성(라이브 API 호출)")
    parser.add_argument("--station-rainfall", action="store_true", help="사건별 전국 관측소 일강수 캐시만 생성(station_rainfall/{event_id}.json)")
    parser.add_argument("--rainfall", action="store_true", help="사건별 강수 관측 캐시만 생성(rainfall/{event_id}.json, 기존 파일은 --force 없이는 유지)")
    parser.add_argument("--zone-group", choices=["all", *ZONE_GROUPS], default="all")
    parser.add_argument("--since", type=date.fromisoformat, default=_DEFAULT_SINCE)
    parser.add_argument("--until", type=date.fromisoformat, default=datetime.now(tz=KST).date())
    parser.add_argument("--skip-kma", action="store_true", help="KMA 이력 마이닝 생략(기존 캐시 사용)")
    parser.add_argument("--skip-disaster-msg", action="store_true", help="재난문자 조회 생략(SKIPPED로 기록)")
    parser.add_argument("--events-only", action="store_true", help="사건 타임라인만 갱신(=--skip-kma)")
    parser.add_argument("--refresh-disaster-msg", action="store_true", help="기존 타임라인의 재난문자 부분만 재조회")
    parser.add_argument("--force", action="store_true", help="기존 타임라인을 무조건 재생성")
    parser.add_argument("--sleep", type=float, default=0.5, help="KMA chunk 호출 간 대기(초)")
    args = parser.parse_args()

    groups = list(ZONE_GROUPS) if args.zone_group == "all" else [args.zone_group]

    if args.station_rainfall:
        validation_set = load_alert_validation_set()
        STATION_RAINFALL_DIR.mkdir(parents=True, exist_ok=True)
        st_summary: dict = {}
        for event in validation_set.events:
            if event.zone_group not in groups:
                continue
            path = station_rainfall_cache_path(event.event_id)
            if path.exists() and not args.force:
                st_summary[event.event_id] = {"status": "kept"}
                continue
            cache = build_station_rainfall(event)
            path.write_text(json.dumps(station_rainfall_cache_to_dict(cache), ensure_ascii=False, indent=1), encoding="utf-8")
            st_summary[event.event_id] = {"status": "written", "days": cache.day_status, "n_stations": len(cache.stations)}
            _log(f"[stations {event.event_id}] {cache.day_status} stations={len(cache.stations)}")
        print(json.dumps({"station_rainfall": st_summary}, ensure_ascii=False, indent=2, default=str))
        return

    if args.rainfall:
        validation_set = load_alert_validation_set()
        RAINFALL_DIR.mkdir(parents=True, exist_ok=True)
        rain_summary: dict = {}
        for event in validation_set.events:
            if event.zone_group not in groups:
                continue
            path = rainfall_cache_path(event.event_id)
            if path.exists() and not args.force:
                rain_summary[event.event_id] = {"status": "kept"}
                continue
            cache = build_rainfall(event)
            path.write_text(json.dumps(rainfall_cache_to_dict(cache), ensure_ascii=False, indent=1), encoding="utf-8")
            rain_summary[event.event_id] = {"status": "written", "sources": cache.sources,
                                            "n_asos": len(cache.asos_hourly), "n_aws_hourly": len(cache.aws_hourly), "n_aws_daily": len(cache.aws_daily)}
            _log(f"[rain {event.event_id}] {cache.sources}")
        print(json.dumps({"rainfall": rain_summary}, ensure_ascii=False, indent=2, default=str))
        return

    _memoize_region_zones()
    summary: dict = {"kma_history": {}, "timelines": {}}

    if not (args.skip_kma or args.events_only):
        KMA_HISTORY_DIR.mkdir(parents=True, exist_ok=True)
        for zg in groups:
            cache = mine_kma_history(zg, args.since, args.until, args.sleep)
            path = kma_history_cache_path(zg)
            path.write_text(json.dumps(kma_history_cache_to_dict(cache), ensure_ascii=False, indent=1), encoding="utf-8")
            by_year: dict[int, int] = {}
            for r in cache.rows:
                by_year[r.tm_ef.year] = by_year.get(r.tm_ef.year, 0) + 1
            summary["kma_history"][zg] = {
                "rows": len(cache.rows),
                "chunks": len(cache.chunks),
                "non_ok_chunks": [c for c in cache.chunks if c["status"] != KMA_STATUS_OK],
                "rows_by_year": dict(sorted(by_year.items())),
                "path": str(path),
            }

    validation_set = load_alert_validation_set()
    TIMELINES_DIR.mkdir(parents=True, exist_ok=True)
    histories: dict[str, KmaHistoryCache] = {}
    for event in validation_set.events:
        if event.zone_group not in groups:
            continue
        if event.zone_group not in histories:
            histories[event.zone_group] = load_kma_history(event.zone_group)
        path = timeline_cache_path(event.event_id)
        existing: CachedTimeline | None = None
        if path.exists() and not args.force:
            try:
                existing = load_cached_timeline(event.event_id)
            except AlertValidationDataError:
                existing = None
        if existing is not None and not args.refresh_disaster_msg:
            summary["timelines"][event.event_id] = {"status": "kept", "n_events": len(existing.events), "sources": existing.sources}
            continue
        timeline = build_timeline(
            event,
            histories[event.zone_group],
            skip_disaster_msg=args.skip_disaster_msg,
            existing=existing,
            refresh_disaster_msg=args.refresh_disaster_msg,
        )
        path.write_text(json.dumps(cached_timeline_to_dict(timeline), ensure_ascii=False, indent=1), encoding="utf-8")
        summary["timelines"][event.event_id] = {"status": "written", "n_events": len(timeline.events), "sources": timeline.sources}
        _log(f"[{event.event_id}] events={len(timeline.events)} sources={timeline.sources}")

    print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
