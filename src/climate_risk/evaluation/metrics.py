"""평가 대시보드 최소셋 — HANDOVER.md §4.4 9개 지표 중 최소셋(인용률·커버리지게이트
통과)에 EAL 재현성·금지어 부재를 더한 4개. 전부 기존 파이프라인 산출값을 그대로 읽거나
기존 순수 함수를 재호출할 뿐, 새 판정 로직을 만들지 않는다(memo/citation_gate.py,
gis/query.py, gis/coverage.py, scenario/eal.py가 이미 진실의 원천).

이 모듈은 pytest 밖(라이브 CLI, Week4 통합 리허설)에서도 그대로 호출 가능한 런타임
함수로 설계했다 — 회귀 테스트(tests/test_coverage_gate.py 등)와 이 모듈이 같은
gis/golden_points.py 골든셋을 공유해 두 곳이 조용히 어긋나지 않게 한다.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date

from climate_risk.agents.building_agent import BuildingAgentOutput
from climate_risk.agents.flood_agent import FloodAgentOutput
from climate_risk.agents.scenario_agent import run_scenario_agent
from climate_risk.config import DEFAULT_EAL_ITERATIONS, DEFAULT_EAL_SEED
from climate_risk.evaluation.flood_marks import FloodMarksValidationSet, load_flood_marks_validation_set
from climate_risk.evaluation.alert_validation import (
    ZONE_GROUPS,
    AlertValidationDataError,
    AlertValidationSet,
    CachedTimeline,
    KmaHistoryCache,
    LabeledAlertEvent,
    WarningEpisode,
    cluster_episodes,
    count_sentinel_rows,
    episode_timeline,
    load_alert_validation_set,
    load_cached_rainfall,
    load_cached_timeline,
    load_kma_history,
    rainfall_to_advisory_events,
)
from climate_risk.evaluation.trigger_candidates import CANDIDATES, PREREGISTERED_AT, TriggerCandidate
from climate_risk.gis.coverage import match_known_uncertain_point
from climate_risk.gis.golden_points import GEOJE_POINTS, NAECHEON_POINTS, SINCHEON_POINTS
from climate_risk.gis.query import TIER_INNER, TIER_NEAR, query_flood_risk
from climate_risk.memo.schema import MemoAgentOutput
from climate_risk.policy.forbidden_phrases import scan_forbidden_phrases


def citation_metric(memo: MemoAgentOutput) -> dict:
    accepted = len(memo.sections)
    rejected = len(memo.rejected_sentences)
    return {
        "accepted": accepted,
        "rejected": rejected,
        "rate": 1.0 - memo.citation_failure_rate,
    }


def coverage_gate_metric() -> dict:
    """골든 좌표셋(gis/golden_points.py) 전체를 실제로 질의해 기대값과 대조한다 —
    tests/test_coverage_gate.py의 회귀 assertion을 pytest 밖에서도 재실행 가능한
    형태로 노출한 것(레드팀 시나리오4 체크가 이 함수를 그대로 위임 호출한다)."""
    failures: list[dict] = []
    all_points = NAECHEON_POINTS + SINCHEON_POINTS + GEOJE_POINTS
    for label, lat, lon, expected_in_polygon, expected_tier in all_points:
        result = query_flood_risk(lat, lon)
        ok = (
            result.coverage == "IN_SCOPE"
            and result.in_polygon is expected_in_polygon
            and result.tier == expected_tier
        )
        if not ok:
            failures.append(
                {
                    "label": label,
                    "expected": {"in_polygon": expected_in_polygon, "tier": expected_tier},
                    "actual": {"coverage": result.coverage, "in_polygon": result.in_polygon, "tier": result.tier},
                }
            )

    total = len(all_points)
    passed = total - len(failures)
    return {
        "total": total,
        "passed": passed,
        "failed": len(failures),
        "pass_rate": passed / total if total else 0.0,
        "failures": failures,
    }


def eal_reproducibility_metric(
    flood: FloodAgentOutput,
    building: BuildingAgentOutput,
    collateral_value: float,
    seed: int = DEFAULT_EAL_SEED,
    n_iterations: int = DEFAULT_EAL_ITERATIONS,
) -> dict:
    """동일 seed로 시나리오 에이전트를 2회 재실행해 EAL 분포가 바이트 단위로
    재현되는지 확인한다 — HANDOVER "절대 축소 금지" 항목을 런타임에서도 실측."""
    run1 = run_scenario_agent(flood, building, collateral_value, seed=seed, n_iterations=n_iterations)
    run2 = run_scenario_agent(flood, building, collateral_value, seed=seed, n_iterations=n_iterations)
    reproducible = run1.eal == run2.eal
    return {
        "reproducible": reproducible,
        "seed": seed,
        "EAL_mean": run1.eal.EAL_mean,
    }


def forbidden_phrase_absence_metric(memo: MemoAgentOutput) -> dict:
    """인용검증·금지어 게이트를 이미 통과한 memo.sections에 다시 한번 금지어 스캔을
    돌린다 — 게이트 통과 후에도 실제로 깨끗한지 이중검증 결과를 증거로 남긴다."""
    matches: list[dict] = []
    for section in memo.sections:
        for m in scan_forbidden_phrases(section.text):
            matches.append({"text": section.text, "phrase": m.phrase})
    return {"clean": len(matches) == 0, "matches": matches}


def flood_marks_recall_metric(
    validation_set: FloodMarksValidationSet | None = None,
) -> dict:
    """실측 침수흔적(safemap A2SM_FLUDMARKS_WI, DEV_LOG.md 2026-08-26) 대비 우리
    SHP tier 판정의 recall — coverage_gate_metric()의 골든셋(12개, 사람이 정답을 직접
    확인)과 달리 여기엔 우리가 통제하는 '정답'이 없다. 실제로 침수됐던 지점을 우리
    화이트박스 판정이 위험(내부/근접)으로 잡아내는 비율을 있는 그대로 보고할 뿐,
    특정 수치를 목표로 만들지 않는다(설계 원칙 4 "정직성"과 같은 정신) — 그래서 이
    함수를 호출하는 회귀 테스트도 recall 값 자체를 assert하지 않는다."""
    if validation_set is None:
        validation_set = load_flood_marks_validation_set()

    evaluated = [
        {"record": rec, "result": query_flood_risk(rec.lat, rec.lon)}
        for rec in validation_set.records
    ]

    def _recall(subset: list[dict]) -> dict:
        in_scope = [x for x in subset if x["result"].coverage == "IN_SCOPE"]
        hit = [x for x in in_scope if x["result"].tier in (TIER_INNER, TIER_NEAR)]
        return {
            "total": len(subset),
            "in_scope": len(in_scope),
            "out_of_scope": len(subset) - len(in_scope),
            "hit": len(hit),
            "recall": (len(hit) / len(in_scope)) if in_scope else None,
        }

    by_region = {
        region: _recall([x for x in evaluated if x["record"].region_name == region])
        for region in sorted({x["record"].region_name for x in evaluated})
    }
    by_cause = {
        cause: _recall([x for x in evaluated if x["record"].cause_category == cause])
        for cause in sorted({x["record"].cause_category for x in evaluated})
    }

    return {
        "overall": _recall(evaluated),
        "by_region": by_region,
        "by_cause_category": by_cause,
        "out_of_scope_records": [
            {
                "region": x["record"].region_name,
                "lat": x["record"].lat,
                "lon": x["record"].lon,
            }
            for x in evaluated
            if x["result"].coverage != "IN_SCOPE"
        ],
    }


def coverage_uncertain_point_metric() -> dict:
    """신천 4개 판정보류 지점이 실제로 match_known_uncertain_point에 걸리는지,
    남구 확정 지점·냉천 3지점은 걸리지 않는지 런타임 확인(coverage_gate_metric과
    별도 축 — '위험 없음'과 '판정보류'를 혼동하지 않는지가 검증 대상)."""
    mismatches: list[dict] = []
    for label, lat, lon, _, _ in NAECHEON_POINTS:
        if match_known_uncertain_point(lat, lon) is not None:
            mismatches.append({"label": label, "expected_uncertain": False})
    for label, lat, lon, _, _ in SINCHEON_POINTS[:1]:
        if match_known_uncertain_point(lat, lon) is not None:
            mismatches.append({"label": label, "expected_uncertain": False})
    for label, lat, lon, _, _ in SINCHEON_POINTS[1:]:
        if match_known_uncertain_point(lat, lon) is None:
            mismatches.append({"label": label, "expected_uncertain": True})
    for label, lat, lon, _, _ in GEOJE_POINTS:
        if match_known_uncertain_point(lat, lon) is not None:
            mismatches.append({"label": label, "expected_uncertain": False})
    return {"clean": len(mismatches) == 0, "mismatches": mismatches}


def _quadrants(fired_by_event: dict[str, bool], labels: dict[str, bool | None]) -> dict:
    tp = fn = tn = fp = unknown_fired = unknown_silent = 0
    for event_id, fired in fired_by_event.items():
        label = labels[event_id]
        if label is None:
            if fired:
                unknown_fired += 1
            else:
                unknown_silent += 1
        elif label:
            if fired:
                tp += 1
            else:
                fn += 1
        else:
            if fired:
                fp += 1
            else:
                tn += 1
    return {
        "tp": tp,
        "fn": fn,
        "tn": tn,
        "fp": fp,
        "unknown_fired": unknown_fired,
        "unknown_silent": unknown_silent,
        "precision": (tp / (tp + fp)) if (tp + fp) else None,
        "recall": (tp / (tp + fn)) if (tp + fn) else None,
    }


ALERT_VALIDATION_CAVEAT = (
    "양성(damage_confirmed=true) 사건이 소수라 precision/recall은 일화 수준이다 — 후보 간 차이는 "
    "전체 KMA 에피소드 대상 alerts_per_region_year(알림 피로 프록시)로 비교할 것. "
    "eal_alert_reference는 참고 열이며 후보 선정에 쓰지 않는다(DEV_LOG.md 2026-09-03)."
)


def alert_trigger_precision_metric(
    validation_set: AlertValidationSet | None = None,
    candidates: Sequence[TriggerCandidate] = CANDIDATES,
    timelines: Mapping[str, CachedTimeline] | None = None,
    kma_histories: Mapping[str, KmaHistoryCache] | None = None,
    fatigue_start_year: int = 2005,
    fatigue_end: date | None = None,
) -> dict:
    """재심사 알림 트리거 후보 4분면 검증 — HANDOVER §4.4 "알림 정밀도(트리거 오탐 방지
    검증)"의 구현(DEV_LOG.md 2026-09-03 참조). flood_marks_recall_metric과 같은 성격:
    우리가 통제하는 '정답'이 아니라 출처 명시 독립 근거로 라벨링한 과거 사건(지역×기간)에
    사전 등록된 후보(evaluation/trigger_candidates.py)를 대입해 TP/FN/TN/FP를 있는 그대로
    보고한다 — 회귀 테스트는 수치를 assert하지 않는다.

    입력은 전부 오프라인 캐시(evaluation/alert_validation.py)다. 인자로 넘기지 않으면
    `config.ALERT_VALIDATION_DIR`에서 로드하며, 캐시가 없으면 조용히 빈 결과를 내지 않고
    AlertValidationDataError를 던진다.
    """
    if validation_set is None:
        validation_set = load_alert_validation_set()
    if timelines is None:
        timelines = {e.event_id: load_cached_timeline(e.event_id) for e in validation_set.events}
    if kma_histories is None:
        kma_histories = {zg: load_kma_history(zg) for zg in ZONE_GROUPS}

    labels = {e.event_id: e.damage_confirmed for e in validation_set.events}
    event_ids = [e.event_id for e in validation_set.events]

    # --- 알림 피로 프록시: 전체 KMA 에피소드 ---------------------------------------
    if fatigue_end is None:
        fatigue_end = max(h.range_end for h in kma_histories.values()) if kma_histories else date.today()
    fatigue_start = date(fatigue_start_year, 1, 1)
    years = max((fatigue_end - fatigue_start).days, 0) / 365.25
    region_years = years * len(kma_histories)
    episodes_by_group = {}
    cache_warnings: list[dict] = []
    for zg, history in kma_histories.items():
        eps = [
            ep
            for ep in cluster_episodes(history.rows, zg)
            if ep.window_start >= fatigue_start and ep.window_end <= fatigue_end
        ]
        episodes_by_group[zg] = eps
        for chunk in history.chunks:
            if chunk.get("status") != "OK":
                cache_warnings.append({"zone_group": zg, **chunk})
        sentinel = count_sentinel_rows(history.rows)
        if sentinel:
            cache_warnings.append({"zone_group": zg, "sentinel_rows_dropped": sentinel})
    episode_timelines = {
        zg: [episode_timeline(ep) for ep in eps] for zg, eps in episodes_by_group.items()
    }
    episodes_total = sum(len(v) for v in episodes_by_group.values())

    # --- 후보별 4분면 -----------------------------------------------------------------
    candidate_results: dict[str, dict] = {}
    for cand in candidates:
        fired_by_event = {eid: bool(cand.fn(timelines[eid].events)) for eid in event_ids}
        quad = _quadrants(fired_by_event, labels)
        fires_by_group = {zg: sum(1 for tl in tls if cand.fn(tl)) for zg, tls in episode_timelines.items()}
        total_fires = sum(fires_by_group.values())
        candidate_results[cand.candidate_id] = {
            "title": cand.title,
            "rule_text": cand.rule_text,
            "requires_disaster_msg": cand.requires_disaster_msg,
            **quad,
            "episode_fires_by_zone_group": fires_by_group,
            "alerts_per_region_year": (total_fires / region_years) if region_years else None,
            "fatigue_is_lower_bound": cand.requires_disaster_msg,
            "per_event": fired_by_event,
        }

    # --- 참고 열: 현행 EAL 알림 --------------------------------------------------------
    eal_fired = {e.event_id: e.eal_alert_fired for e in validation_set.events if e.eal_alert_fired is not None}
    eal_ref = _quadrants(eal_fired, {k: labels[k] for k in eal_fired})
    eal_ref["not_recorded"] = len(event_ids) - len(eal_fired)
    eal_ref["role"] = "reference_only_not_a_candidate"

    by_zone_group: dict[str, dict] = {}
    for e in validation_set.events:
        bucket = by_zone_group.setdefault(e.zone_group, {"positive": 0, "negative": 0, "unknown": 0})
        key = "unknown" if e.damage_confirmed is None else ("positive" if e.damage_confirmed else "negative")
        bucket[key] += 1

    return {
        "caveat": ALERT_VALIDATION_CAVEAT,
        "preregistration": {"candidates_fixed_at": PREREGISTERED_AT, "candidate_ids": [c.candidate_id for c in candidates]},
        "labeled_events": {
            "total": len(event_ids),
            "positive": sum(1 for v in labels.values() if v is True),
            "negative": sum(1 for v in labels.values() if v is False),
            "unknown": sum(1 for v in labels.values() if v is None),
            "by_zone_group": by_zone_group,
            "disaster_msg_missing": [
                eid for eid in event_ids if timelines[eid].sources.get("disaster_msg", {}).get("status") != "OK"
            ],
        },
        "fatigue_window": {
            "start": fatigue_start.isoformat(),
            "end": fatigue_end.isoformat(),
            "zone_groups": sorted(kma_histories),
            "region_years": region_years,
            "episodes_total": episodes_total,
            "episodes_by_zone_group": {zg: len(eps) for zg, eps in episodes_by_group.items()},
            "cache_warnings": cache_warnings,
        },
        "candidates": candidate_results,
        "eal_alert_reference": eal_ref,
    }


# ---------------------------------------------------------------------------
# 3단계 분리 검증(사용자 요청 2026-09-03): 1단계 앵커 사건(힌남노)으로 선정 → 2단계 다른
# 사건으로 검증 → 3단계 홀드아웃(거제 2026-08)으로 최종 테스트.
# ---------------------------------------------------------------------------

DEFAULT_ANCHOR_EVENT_ID = "pohang-2022-09-hinnamno"
# 정형 API 원자료 이벤트 id 접두어(advisory_agent가 붙임) — 큐레이션(뉴스) 이벤트는 여기 없음.
STRUCTURED_EVENT_ID_PREFIXES = ("kma-historical-", "disaster-msg-", "obs-")


def _merge_rainfall(timelines: Mapping[str, CachedTimeline]) -> tuple[dict[str, CachedTimeline], list[str]]:
    """사건별 강수 캐시(rainfall/{event_id}.json)가 있으면 관측 이벤트를 타임라인에 병합. 없으면
    그 사건 id를 `missing`에 남기고 타임라인은 그대로 둔다(강수 의존 후보는 그 사건에서 False)."""
    merged: dict[str, CachedTimeline] = {}
    missing: list[str] = []
    for eid, tl in timelines.items():
        try:
            cache = load_cached_rainfall(eid)
        except AlertValidationDataError:
            missing.append(eid)
            merged[eid] = tl
            continue
        obs = rainfall_to_advisory_events(cache)
        merged[eid] = CachedTimeline(
            event_id=tl.event_id, region_code=tl.region_code, window_start=tl.window_start,
            window_end=tl.window_end, fetched_at=tl.fetched_at,
            sources={**tl.sources, "rainfall": cache.sources},
            events=sorted(tl.events + obs, key=lambda e: e.issued_at),
        )
    return merged, missing
DEFAULT_HOLDOUT_EVENT_IDS: tuple[str, ...] = ("geoje-2026-08",)


def _episodes_overlapping(ep: WarningEpisode, events: Sequence[LabeledAlertEvent]) -> bool:
    return any(
        e.zone_group == ep.zone_group and ep.window_start <= e.window_end and ep.window_end >= e.window_start
        for e in events
    )


def staged_alert_validation_metric(
    validation_set: AlertValidationSet | None = None,
    candidates: Sequence[TriggerCandidate] = CANDIDATES,
    timelines: Mapping[str, CachedTimeline] | None = None,
    kma_histories: Mapping[str, KmaHistoryCache] | None = None,
    anchor_event_id: str = DEFAULT_ANCHOR_EVENT_ID,
    holdout_event_ids: Sequence[str] = DEFAULT_HOLDOUT_EVENT_IDS,
    fatigue_start_year: int = 2005,
    exclude_news_derived: bool = True,
) -> dict:
    """사건 단위 3단계 분리 검증(DEV_LOG.md 2026-09-03(계속3)).

    `exclude_news_derived=True`(기본)면 타임라인에서 큐레이션(뉴스 기반) 이벤트를 빼고
    정형 API 원자료(기상청 특보 이력 `kma-historical-*`, 재난문자 `disaster-msg-*`)만 피쳐에
    쓴다 — 사용자 요구 "피쳐는 뉴스 제외 데이터로"(2026-09-03). 뉴스는 라벨에만 쓴다.

    - 1단계(선정): 앵커 사건(기본 힌남노)이 반드시 켜져야 하고, **같은 zone group·같은
      연도**의 다른 라벨 사건에서 FP가 0이어야 통과. 같은 해의 라벨 없는 KMA 에피소드에서
      몇 번 켜지는지(`unlabeled_fires`)도 같이 센다(그 해의 알림 피로).
    - 2단계(검증): 앵커·1단계·홀드아웃을 뺀 나머지 라벨 사건 전부. FN=0이어야 통과, FP는 기록.
    - 3단계(테스트): 홀드아웃 사건(기본 거제 2026-08). 양성이면 켜져야 통과.
    - pass_all = 세 단계 모두 통과. 정렬은 pass_all → 2단계 FP 오름차순 → 알림 피로 오름차순.

    flood_marks_recall_metric·alert_trigger_precision_metric과 같은 성격 — 수치는 있는 그대로,
    테스트는 불변식만 확인한다. 후보 채택은 사용자 결정.
    """
    if validation_set is None:
        validation_set = load_alert_validation_set()
    if timelines is None:
        timelines = {e.event_id: load_cached_timeline(e.event_id) for e in validation_set.events}
    if kma_histories is None:
        kma_histories = {zg: load_kma_history(zg) for zg in ZONE_GROUPS}
    timelines, rainfall_missing = _merge_rainfall(timelines)

    if exclude_news_derived:
        timelines = {
            eid: CachedTimeline(
                event_id=tl.event_id, region_code=tl.region_code, window_start=tl.window_start,
                window_end=tl.window_end, fetched_at=tl.fetched_at, sources=tl.sources,
                events=[e for e in tl.events if e.event_id.startswith(STRUCTURED_EVENT_ID_PREFIXES)],
            )
            for eid, tl in timelines.items()
        }

    by_id = {e.event_id: e for e in validation_set.events}
    if anchor_event_id not in by_id:
        raise ValueError(f"앵커 사건 {anchor_event_id!r}가 라벨 파일에 없습니다.")
    anchor = by_id[anchor_event_id]
    holdout = [by_id[h] for h in holdout_event_ids if h in by_id]
    missing_holdout = [h for h in holdout_event_ids if h not in by_id]
    holdout_ids = {e.event_id for e in holdout}

    stage1_peers = [
        e for e in validation_set.events
        if e.event_id != anchor_event_id
        and e.event_id not in holdout_ids
        and e.zone_group == anchor.zone_group
        and e.window_start.year == anchor.window_start.year
    ]
    stage1_ids = {e.event_id for e in stage1_peers}
    stage2_events = [
        e for e in validation_set.events
        if e.event_id != anchor_event_id and e.event_id not in holdout_ids and e.event_id not in stage1_ids
    ]

    # 1단계의 라벨 없는 같은 해 에피소드(앵커·라벨 사건과 겹치지 않는 것만)
    anchor_history = kma_histories[anchor.zone_group]
    same_year_unlabeled = [
        ep
        for ep in cluster_episodes(anchor_history.rows, anchor.zone_group)
        if ep.window_start.year == anchor.window_start.year
        and not _episodes_overlapping(ep, [anchor, *stage1_peers, *holdout])
    ]
    same_year_timelines = [episode_timeline(ep) for ep in same_year_unlabeled]

    # 알림 피로(전체 이력) — alert_trigger_precision_metric과 동일 산식
    fatigue_end = max(h.range_end for h in kma_histories.values())
    fatigue_start = date(fatigue_start_year, 1, 1)
    region_years = max((fatigue_end - fatigue_start).days, 0) / 365.25 * len(kma_histories)
    all_episode_timelines = [
        episode_timeline(ep)
        for zg, h in kma_histories.items()
        for ep in cluster_episodes(h.rows, zg)
        if ep.window_start >= fatigue_start and ep.window_end <= fatigue_end
    ]

    results: dict[str, dict] = {}
    for cand in candidates:
        fired = {e.event_id: bool(cand.fn(timelines[e.event_id].events)) for e in validation_set.events}
        s1 = _quadrants({e.event_id: fired[e.event_id] for e in stage1_peers}, {e.event_id: e.damage_confirmed for e in stage1_peers})
        s1_unlabeled_fires = sum(1 for tl in same_year_timelines if cand.fn(tl))
        s2 = _quadrants({e.event_id: fired[e.event_id] for e in stage2_events}, {e.event_id: e.damage_confirmed for e in stage2_events})
        s3 = {e.event_id: fired[e.event_id] for e in holdout}
        s3_pass = all(fired[e.event_id] == bool(e.damage_confirmed) for e in holdout if e.damage_confirmed is not None)
        anchor_fired = fired[anchor_event_id]
        pass1 = anchor_fired and s1["fp"] == 0
        pass2 = s2["fn"] == 0
        rain_dep = getattr(cand, "requires_rainfall", False)
        total_fires = None if rain_dep else sum(1 for tl in all_episode_timelines if cand.fn(tl))
        results[cand.candidate_id] = {
            "title": cand.title,
            "rule_text": cand.rule_text,
            "requires_disaster_msg": cand.requires_disaster_msg,
            "requires_rainfall": rain_dep,
            "stage1": {"anchor_fired": anchor_fired, **{k: s1[k] for k in ("fp", "tn", "unknown_fired", "unknown_silent")},
                       "unlabeled_fires": s1_unlabeled_fires, "unlabeled_episodes": len(same_year_unlabeled), "passed": pass1},
            "stage2": {**s2, "passed": pass2},
            "stage3": {"fired": s3, "passed": s3_pass},
            "pass_all": pass1 and pass2 and s3_pass,
            "stages_passed": int(pass1) + int(pass2) + int(s3_pass),
            "alerts_per_region_year": (total_fires / region_years) if (region_years and total_fires is not None) else None,
            "fatigue_is_lower_bound": cand.requires_disaster_msg,
            "fatigue_not_computed": rain_dep,  # 전체 KMA 에피소드엔 강수 캐시가 없음
            "per_event": fired,
        }

    def _stages_passed(r: dict) -> int:
        return int(r["stage1"]["passed"]) + int(r["stage2"]["passed"]) + int(r["stage3"]["passed"])

    # 통과 단계 수 → 2단계 FN(놓친 양성) → 2단계 FP → unknown 발화 → 알림 피로 순.
    ranked = sorted(
        results,
        key=lambda cid: (
            -_stages_passed(results[cid]),
            results[cid]["stage2"]["fn"],
            results[cid]["stage2"]["fp"],
            results[cid]["stage2"]["unknown_fired"],
            results[cid]["alerts_per_region_year"] or 0.0,
            cid,
        ),
    )
    return {
        "caveat": ALERT_VALIDATION_CAVEAT,
        "protocol": {
            "anchor_event_id": anchor_event_id,
            "exclude_news_derived": exclude_news_derived,
            "stage1_scope": f"zone_group={anchor.zone_group}, year={anchor.window_start.year}",
            "stage1_event_ids": [e.event_id for e in stage1_peers],
            "stage1_unlabeled_episodes": len(same_year_unlabeled),
            "stage2_event_ids": [e.event_id for e in stage2_events],
            "stage3_event_ids": [e.event_id for e in holdout],
            "stage3_missing": missing_holdout,
            "rainfall_missing": rainfall_missing,
            "pass_rule": "1단계: 앵커 켜짐 ∧ 같은 해 라벨 음성에서 FP 0 / 2단계: FN 0 / 3단계: 홀드아웃 라벨과 일치",
        },
        "n_candidates": len(results),
        "passing": [cid for cid in ranked if results[cid]["pass_all"]],
        "ranked": ranked,
        "candidates": results,
    }
