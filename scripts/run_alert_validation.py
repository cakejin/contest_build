"""재심사 알림 트리거 후보 4분면 검증 — **오프라인** 실행 CLI(DEV_LOG.md 2026-09-03 참조).

`scripts/fetch_alert_validation_cache.py`가 만든 캐시만 읽는다(네트워크 없음). 사전 등록된
후보 전부(evaluation/trigger_candidates.py)를 라벨 사건에 한 번에 대입해 4분면 표를 찍고,
같은 내용을 JSON으로 출력한다. 마지막 행 `EAL(참고)`는 현행 EAL 변화율 알림이 같은 사건에서
어땠는지의 참고 열이며 후보가 아니다.

사용 예:
    python scripts/run_alert_validation.py                  # 표 + JSON
    python scripts/run_alert_validation.py --json-only
    python scripts/run_alert_validation.py --emit-episode-skeleton --min-level 3 --wrn R,T,O --since 2015-01-01
        # → 라벨링할 KMA 경보 에피소드 스텁(labeled_events.json에 붙여넣고 사람이 라벨링)
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from climate_risk.advisory.kma_historical import LVL_CODE_LABELS, WRN_CODE_LABELS  # noqa: E402
from climate_risk.evaluation.alert_validation import (  # noqa: E402
    ISSUE_CMD_CODES,
    REPRESENTATIVE_REGION_CODE,
    ZONE_GROUPS,
    cluster_episodes,
    load_alert_validation_set,
    load_kma_history,
)
from climate_risk.evaluation.metrics import (  # noqa: E402
    alert_trigger_precision_metric,
    staged_alert_validation_metric,
)
from climate_risk.evaluation.collateral_counts import collateral_alert_count_metric  # noqa: E402
from climate_risk.evaluation.trigger_candidates import CANDIDATES  # noqa: E402
from climate_risk.evaluation.trigger_features import all_feature_candidates  # noqa: E402


def _fmt(v: float | None) -> str:
    return "-" if v is None else f"{v:.2f}"


def render_table(metric: dict) -> str:
    header = f"{'candidate':34} {'TP':>3} {'FN':>3} {'TN':>3} {'FP':>3} {'unkF':>5} {'unkS':>5} {'prec':>5} {'rec':>5} {'alerts/rg-yr':>12}  note"
    lines = [header, "-" * len(header)]
    for cid, r in metric["candidates"].items():
        note = "재난문자 의존(피로 지표는 하한)" if r["fatigue_is_lower_bound"] else ""
        lines.append(
            f"{cid:34} {r['tp']:>3} {r['fn']:>3} {r['tn']:>3} {r['fp']:>3} {r['unknown_fired']:>5} {r['unknown_silent']:>5} "
            f"{_fmt(r['precision']):>5} {_fmt(r['recall']):>5} {_fmt(r['alerts_per_region_year']):>12}  {note}"
        )
    e = metric["eal_alert_reference"]
    lines.append("-" * len(header))
    lines.append(
        f"{'EAL(참고, 후보 아님)':34} {e['tp']:>3} {e['fn']:>3} {e['tn']:>3} {e['fp']:>3} {e['unknown_fired']:>5} {e['unknown_silent']:>5} "
        f"{_fmt(e['precision']):>5} {_fmt(e['recall']):>5} {'-':>12}  미기록 {e['not_recorded']}건"
    )
    le, fw = metric["labeled_events"], metric["fatigue_window"]
    lines.append("")
    lines.append(
        f"라벨 사건 {le['total']}건(양성 {le['positive']}·음성 {le['negative']}·unknown {le['unknown']}) | "
        f"알림 피로 창 {fw['start']}~{fw['end']} zone group {len(fw['zone_groups'])}개 = {fw['region_years']:.1f} region-year, "
        f"KMA 에피소드 {fw['episodes_total']}개"
    )
    if le["disaster_msg_missing"]:
        lines.append(f"재난문자 미확보 사건: {', '.join(le['disaster_msg_missing'])}")
    if fw["cache_warnings"]:
        lines.append(f"캐시 경고 {len(fw['cache_warnings'])}건(JSON cache_warnings 참조)")
    lines.append(metric["caveat"])
    return "\n".join(lines)


def render_staged_table(metric: dict, top: int) -> str:
    p = metric["protocol"]
    header = (
        f"{'candidate':34} {'S1앵커':>6} {'S1FP':>4} {'S1unk':>5} {'S1미라벨':>7} | "
        f"{'S2TP':>4} {'S2FN':>4} {'S2TN':>4} {'S2FP':>4} {'S2unk':>5} | {'S3':>4} | {'pass':>4} {'alerts/rg-yr':>12}"
    )
    lines = [
        f"앵커 {p['anchor_event_id']} | 1단계 범위 {p['stage1_scope']}: 라벨 {p['stage1_event_ids']}, 미라벨 에피소드 {p['stage1_unlabeled_episodes']}개 | "
        f"2단계 {len(p['stage2_event_ids'])}건 | 3단계 {p['stage3_event_ids']}",
        f"후보 {metric['n_candidates']}개, 3단계 전부 통과 {len(metric['passing'])}개 (상위 {top}개 표시)",
        header,
        "-" * len(header),
    ]
    shown = metric["ranked"][:top]
    base_ids = [c.candidate_id for c in CANDIDATES]
    for cid in base_ids:
        if cid not in shown and cid in metric["candidates"]:
            shown.append(cid)
    for cid in shown:
        r = metric["candidates"][cid]
        s1, s2, s3 = r["stage1"], r["stage2"], r["stage3"]
        s3_txt = "/".join("X" if v else "." for v in s3["fired"].values())
        lines.append(
            f"{cid:34} {('X' if s1['anchor_fired'] else '.'):>6} {s1['fp']:>4} {s1['unknown_fired']:>5} "
            f"{s1['unlabeled_fires']:>3}/{s1['unlabeled_episodes']:<3} | "
            f"{s2['tp']:>4} {s2['fn']:>4} {s2['tn']:>4} {s2['fp']:>4} {s2['unknown_fired']:>5} | {s3_txt:>4} | "
            f"{(str(r['stages_passed']) + '/3'):>4} {_fmt(r['alerts_per_region_year']):>12}{'(하한)' if r['fatigue_is_lower_bound'] else ''}"
        )
    lines.append(p["pass_rule"])
    return "\n".join(lines)


def render_collateral_counts(metric: dict) -> str:
    ths = [f"{t:.0f}mm" for t in metric["rule"]["thresholds_mm"]]
    header = f"{'event':28} {'label':8} {'matched':>7} {'A2':>3} " + " ".join(f"{t + '강수':>9} {t + '∧tier':>10}" for t in ths) + f" {'rain min/med/max':>20} {'stn km med':>10}"
    lines = [f"규칙: {metric['rule']['collateral_rule']} | 임계값 근거: {metric['rule']['threshold_basis']}", header, "-" * len(header)]
    for eid, r in metric["events"].items():
        lab = {True: "양성", False: "음성", None: "unknown"}[r["damage_confirmed"]]
        if r.get("station_rainfall") == "MISSING":
            lines.append(f"{eid:28} {lab:8} {r['matched']:>7} {'X' if r['region_triggered'] else '.':>3}  (관측소 캐시 없음)")
            continue
        cells = " ".join(f"{r['alerts'][t]['rain_only']:>9} {r['alerts'][t]['rain_and_tier']:>10}" for t in ths)
        rm = r["rain_mm"]
        rain = "-" if rm["max"] is None else f"{rm['min']:.0f}/{rm['median']:.0f}/{rm['max']:.0f}"
        km = "-" if r["station_km"]["median"] is None else f"{r['station_km']['median']:.1f}"
        lines.append(f"{eid:28} {lab:8} {r['matched']:>7} {'X' if r['region_triggered'] else '.':>3} {cells} {rain:>20} {km:>10}")
    if metric["station_rainfall_missing"]:
        lines.append(f"관측소 캐시 없음: {metric['station_rainfall_missing']}")
    return "\n".join(lines)


def _peak_by_type(ep) -> dict[str, str]:
    """특보 종류별 최고 등급(발표/대치/연장/변경 행 기준) — 라벨링 우선순위 판단용."""
    peaks: dict[str, str] = {}
    for r in ep.rows:
        if r.cmd_code not in ISSUE_CMD_CODES or not r.lvl_code.isdigit():
            continue
        label = WRN_CODE_LABELS.get(r.wrn_code, r.wrn_code)
        if int(r.lvl_code) > int(peaks.get(label, "0")):
            peaks[label] = r.lvl_code
    return {k: LVL_CODE_LABELS.get(v, v) for k, v in peaks.items()}


def emit_episode_skeleton(min_level: str, wrn_codes: set[str] | None, since: date) -> list[dict]:
    validation_set = load_alert_validation_set()
    labeled = [(e.zone_group, e.window_start, e.window_end) for e in validation_set.events]
    stubs: list[dict] = []
    for zg in ZONE_GROUPS:
        history = load_kma_history(zg)
        for ep in cluster_episodes(history.rows, zg):
            if ep.window_start < since:
                continue
            if not ep.peak_lvl_code.isdigit() or int(ep.peak_lvl_code) < int(min_level):
                continue
            if wrn_codes is not None and not (set(ep.warning_codes) & wrn_codes):
                continue
            overlaps = any(
                g == zg and ep.window_start <= we and ep.window_end >= ws for g, ws, we in labeled
            )
            stubs.append(
                {
                    "event_id": f"{zg}-{ep.window_start.isoformat()}-{'-'.join(ep.warning_codes)}",
                    "region_code": REPRESENTATIVE_REGION_CODE[zg],
                    "window_start": ep.window_start.isoformat(),
                    "window_end": ep.window_end.isoformat(),
                    "episode_source": "kma_mined",
                    "damage_confirmed": "unknown",
                    "evidence": [],
                    "label_note": "",
                    "eal_alert_fired": None,
                    "eal_alert_source": "",
                    "_peak": LVL_CODE_LABELS.get(ep.peak_lvl_code, ep.peak_lvl_code),
                    "_peak_by_type": _peak_by_type(ep),
                    "_warning_types": [WRN_CODE_LABELS.get(c, c) for c in ep.warning_codes],
                    "_n_rows": len(ep.rows),
                    "_overlaps_labeled_event": overlaps,
                }
            )
    return stubs


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="트리거 후보 4분면 검증(오프라인)")
    parser.add_argument("--json-only", action="store_true")
    parser.add_argument("--fatigue-start-year", type=int, default=2005)
    parser.add_argument("--emit-episode-skeleton", action="store_true", help="라벨링용 KMA 에피소드 스텁 출력")
    parser.add_argument("--min-level", default="3", help="스텁 최소 peak 등급 코드(1예비 2주의보 3경보 4중대경보)")
    parser.add_argument("--wrn", default="", help="스텁 특보 종류 코드 콤마구분(예: R,T,O). 비우면 전부")
    parser.add_argument("--since", type=date.fromisoformat, default=date(2015, 1, 1))
    parser.add_argument("--collateral-counts", action="store_true", help="사건별 매칭 담보 중 알림 담보 수(담보별 최근접 관측소 일강수 규칙, DEV_LOG (계속8))")
    parser.add_argument("--staged", action="store_true", help="3단계 분리 검증(앵커 힌남노 → 다른 사건 → 거제 2026-08 홀드아웃)")
    parser.add_argument("--combos", action="store_true", help="--staged에 atom 11개 + 2개 조합 110개 추가")
    parser.add_argument("--top", type=int, default=25, help="--staged 표에 표시할 상위 후보 수")
    parser.add_argument("--anchor", default="pohang-2022-09-hinnamno")
    parser.add_argument("--holdout", default="geoje-2026-08", help="콤마구분 홀드아웃 event_id")
    args = parser.parse_args()

    if args.collateral_counts:
        metric = collateral_alert_count_metric()
        if not args.json_only:
            print(render_collateral_counts(metric))
            print()
        print(json.dumps(metric, ensure_ascii=False, indent=2, default=str))
        return

    if args.staged:
        cands = tuple(CANDIDATES) + (all_feature_candidates() if args.combos else ())
        metric = staged_alert_validation_metric(
            candidates=cands,
            anchor_event_id=args.anchor,
            holdout_event_ids=tuple(h.strip() for h in args.holdout.split(",") if h.strip()),
            fatigue_start_year=args.fatigue_start_year,
        )
        if not args.json_only:
            print(render_staged_table(metric, args.top))
            print()
        print(json.dumps(metric, ensure_ascii=False, indent=2, default=str))
        return

    if args.emit_episode_skeleton:
        wrn = {c.strip() for c in args.wrn.split(",") if c.strip()} or None
        print(json.dumps(emit_episode_skeleton(args.min_level, wrn, args.since), ensure_ascii=False, indent=2))
        return

    metric = alert_trigger_precision_metric(fatigue_start_year=args.fatigue_start_year)
    if not args.json_only:
        print(render_table(metric))
        print()
    print(json.dumps(metric, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
