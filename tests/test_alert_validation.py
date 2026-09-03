"""재심사 알림 트리거 후보 4분면 검증 하네스 — DEV_LOG.md 2026-09-03 참조.

`tests/test_flood_marks_validation.py`와 같은 규율: 여기 라벨 사건은 우리가 통제하는
'정답'이 아니라 외부 독립 근거(침수흔적·뉴스·특별재난지역)라서 **precision/recall 수치
자체는 assert하지 않는다**. 고정하는 건 (1) 라벨 파일 계약(출처 URL 필수 등)과 알려진
사실(양성 3건, 현행 EAL 알림 참고 열 값), (2) 사전 등록된 후보 목록의 동결, (3) 후보
함수·클러스터링의 순수 로직, (4) 오프라인 지표가 네트워크 없이 캐시만으로 돌고 산술
불변식을 지키는지 뿐이다.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta

import pytest

from climate_risk.advisory import disaster_msg, kma_historical
from climate_risk.advisory.kma_historical import (
    CMD_CODE_LABELS,
    LVL_CODE_LABELS,
    WRN_CODE_LABELS,
    HistoricalWarningEvent,
)
from climate_risk.advisory.schema import AdvisoryEvent
from climate_risk.agents.advisory_agent import is_high_severity_event
from climate_risk.evaluation.alert_validation import (
    KST,
    AlertValidationDataError,
    cluster_episodes,
    count_sentinel_rows,
    episode_timeline,
    load_alert_validation_set,
    load_cached_timeline,
    load_kma_history,
    parse_issued_at_kst,
    zone_group_for,
)
from climate_risk.evaluation.metrics import alert_trigger_precision_metric
from climate_risk.evaluation.trigger_candidates import (
    CANDIDATE_IDS,
    CANDIDATES,
    c0_any_advisory,
    c1_high_severity_any,
    c2_hydro_high_severity,
    c3_disaster_msg_damage_keyword,
    c4_disaster_msg_burst,
    c5_warning_level_physical,
    c6_hydro_high_severity_or_burst,
    candidate_by_id,
)

# ---------------------------------------------------------------------------
# 합성 이벤트 헬퍼
# ---------------------------------------------------------------------------


def _event(
    event_type: str,
    warning_type: str | None,
    severity_level: str | None,
    issued_at: str = "2026-07-17T21:50:00+09:00",
    description: str = "",
    event_id: str = "ev",
) -> AdvisoryEvent:
    return AdvisoryEvent(
        event_id=event_id,
        issued_at=issued_at,
        time_precision="exact",
        event_type=event_type,
        warning_type=warning_type,
        description=description,
        source_url="https://example.invalid/",
        target_region_text="",
        severity_level=severity_level,
    )


def _warning(warning_type: str, severity: str) -> AdvisoryEvent:
    return _event("특보", warning_type, severity)


def _dm(dst_se_nm: str, step: str, issued_at: str, text: str = "") -> AdvisoryEvent:
    return _event("재난문자", dst_se_nm, step, issued_at=issued_at, description=f"[{dst_se_nm}/{step}] {text}", event_id=issued_at)


def _row(hours: float, wrn: str = "R", lvl: str = "3", cmd: str = "1") -> HistoricalWarningEvent:
    t = datetime(2026, 7, 17, tzinfo=KST) + timedelta(hours=hours)
    return HistoricalWarningEvent(
        reg_id="L1140100", tm_fc=t, tm_ef=t,
        wrn_code=wrn, wrn_label=WRN_CODE_LABELS[wrn],
        lvl_code=lvl, lvl_label=LVL_CODE_LABELS[lvl],
        cmd_code=cmd, cmd_label=CMD_CODE_LABELS[cmd],
    )


# ---------------------------------------------------------------------------
# 1. 사전 등록 동결
# ---------------------------------------------------------------------------


def test_candidate_ids_are_frozen_as_preregistered():
    assert CANDIDATE_IDS == (
        "C0_any_advisory",
        "C1_high_severity_any",
        "C2_hydro_high_severity",
        "C3_disaster_msg_damage_keyword",
        "C4_disaster_msg_burst",
        "C5_warning_level_physical",
        "C6_hydro_high_severity_or_burst",
    )


def test_every_candidate_is_a_pure_function_of_the_timeline_only():
    """후보 시그니처가 `list[AdvisoryEvent]`뿐 — 라벨(damage_confirmed)·참고 열(eal_alert_fired)이
    판정에 섞일 통로가 없다는 구조적 증거."""
    for cand in CANDIDATES:
        assert cand.fn([]) is False
        assert candidate_by_id(cand.candidate_id) is cand


# ---------------------------------------------------------------------------
# 2. 후보 순수 로직
# ---------------------------------------------------------------------------


def test_c0_fires_on_curated_warning_without_severity():
    assert c0_any_advisory([_warning("태풍경보(제주)", None)]) is True
    assert c0_any_advisory([_event("현장상황", None, None)]) is False


def test_c1_is_frozen_to_2026_08_31_rule_and_production_now_equals_c2():
    """C1은 2026-08-31 최초 규칙(등급만, 종류 무관)을 검증표용으로 고정한 것 — 2026-09-03(계속10)에
    프로덕션 is_high_severity_event가 A2(=C2, 종류 조건)로 바뀌어도 C1 수치가 따라 바뀌면 안 된다."""
    heat = _warning("폭염 경보 변경", "경보")
    rain_adv = _warning("호우 주의보 발표", "주의보")
    assert c1_high_severity_any([heat, rain_adv]) is True  # 옛 규칙: 폭염경보도 켜짐
    assert is_high_severity_event(heat) is False  # 새 프로덕션 규칙: 폭염은 꺼짐
    assert c1_high_severity_any([rain_adv]) is False
    for e in (heat, rain_adv, _warning("호우 경보 발표", "경보"), _dm("호우", "긴급재난", "2026-07-17T22:10:00+09:00"), _dm("산불", "긴급재난", "2025-03-25T18:42:05+09:00")):
        assert is_high_severity_event(e) is c2_hydro_high_severity([e])


def test_c2_hydro_warning_level_rules():
    assert c2_hydro_high_severity([_warning("호우 경보 발표", "경보")]) is True
    assert c2_hydro_high_severity([_warning("태풍 중대경보 발표", "중대경보")]) is True
    assert c2_hydro_high_severity([_warning("폭염 경보 발표", "경보")]) is False
    assert c2_hydro_high_severity([_warning("호우 주의보 발표", "주의보")]) is False
    assert c2_hydro_high_severity([_warning("강풍 경보 발표", "경보")]) is False


def test_c2_hydro_disaster_msg_rules():
    assert c2_hydro_high_severity([_dm("호우", "긴급재난", "2026-07-17T22:10:00+09:00")]) is True
    assert c2_hydro_high_severity([_dm("호우", "안전안내", "2026-07-17T22:10:00+09:00")]) is False
    assert c2_hydro_high_severity([_dm("산불", "긴급재난", "2025-03-25T18:42:05+09:00")]) is False


def test_c3_damage_keyword_only_on_disaster_msg():
    assert c3_disaster_msg_damage_keyword([_dm("호우", "안전안내", "2026-07-17T22:10:00+09:00", "저지대 침수 우려")]) is True
    assert c3_disaster_msg_damage_keyword([_dm("호우", "안전안내", "2026-07-17T22:10:00+09:00", "외출 자제")]) is False
    assert c3_disaster_msg_damage_keyword([_event("현장상황", None, None, description="냉천 범람")]) is False


def test_c4_burst_boundaries():
    base = datetime(2026, 8, 17, 0, 0, tzinfo=KST)

    def msgs(hours: list[float], dst: str = "호우") -> list[AdvisoryEvent]:
        return [_dm(dst, "안전안내", (base + timedelta(hours=h)).isoformat()) for h in hours]

    assert c4_disaster_msg_burst(msgs([0, 10, 23])) is True
    assert c4_disaster_msg_burst(msgs([0, 10, 25])) is False
    assert c4_disaster_msg_burst(msgs([0, 23])) is False
    assert c4_disaster_msg_burst(msgs([0, 30, 40, 50])) is True  # 30~50h 창
    assert c4_disaster_msg_burst(msgs([0, 10, 23], dst="폭염")) is False  # RELEVANT_DST_SE_NM 밖


def test_c5_excludes_non_physical_warnings():
    assert c5_warning_level_physical([_warning("강풍 경보 발표", "경보")]) is True
    assert c5_warning_level_physical([_warning("폭염 경보 변경", "경보")]) is False
    assert c5_warning_level_physical([_warning("한파 경보 발표", "경보")]) is False
    assert c5_warning_level_physical([_warning("강풍 주의보 발표", "주의보")]) is False


def test_c6_is_c2_or_c4():
    base = datetime(2026, 8, 17, 0, 0, tzinfo=KST)
    burst = [_dm("호우", "안전안내", (base + timedelta(hours=h)).isoformat()) for h in (0, 5, 10)]
    assert c6_hydro_high_severity_or_burst(burst) is True
    assert c6_hydro_high_severity_or_burst([_warning("호우 경보 발표", "경보")]) is True
    assert c6_hydro_high_severity_or_burst([_warning("폭염 경보 발표", "경보")]) is False


# ---------------------------------------------------------------------------
# 3. 시각 파싱·클러스터링
# ---------------------------------------------------------------------------


def test_parse_issued_at_kst_handles_date_only_and_naive():
    assert parse_issued_at_kst("2022-09-06") == datetime(2022, 9, 6, tzinfo=KST)
    assert parse_issued_at_kst("2026-07-17T22:10:00") == datetime(2026, 7, 17, 22, 10, tzinfo=KST)
    assert parse_issued_at_kst("2026-07-17T13:10:00+00:00") == datetime(2026, 7, 17, 22, 10, tzinfo=KST)


def test_cluster_episodes_gap_rule_and_window_pad():
    rows = [_row(0), _row(47), _row(47 + 49, wrn="W", lvl="2", cmd="3")]
    episodes = cluster_episodes(rows, "daegu")
    assert [len(e.rows) for e in episodes] == [2, 1]
    first = episodes[0]
    assert first.window_start == date(2026, 7, 16)
    assert first.window_end == date(2026, 7, 19)  # 마지막 발효 07-18 23:00 + 1일
    assert first.peak_lvl_code == "3"
    assert first.warning_codes == ("R",)
    # 두 번째 에피소드는 해제(cmd=3) 행뿐이라 peak 산정 대상이 없다
    assert episodes[1].peak_lvl_code == "0"


def test_cluster_episodes_peak_ignores_release_commands():
    rows = [_row(0, lvl="2", cmd="1"), _row(5, lvl="3", cmd="3")]
    (episode,) = cluster_episodes(rows, "47111")
    assert episode.peak_lvl_code == "2"


def test_cluster_episodes_drops_sentinel_rows():
    sentinel = HistoricalWarningEvent(
        reg_id="L1", tm_fc=datetime(2100, 12, 31, 23, 59, tzinfo=KST), tm_ef=datetime(2100, 12, 31, 23, 59, tzinfo=KST),
        wrn_code="R", wrn_label="호우", lvl_code="3", lvl_label="경보", cmd_code="1", cmd_label="발표",
    )
    rows = [_row(0), sentinel]
    assert count_sentinel_rows(rows) == 1
    (episode,) = cluster_episodes(rows, "47111")
    assert len(episode.rows) == 1


def test_episode_timeline_uses_production_conversion():
    (episode,) = cluster_episodes([_row(0, wrn="R", lvl="3", cmd="6")], "daegu")
    (event,) = episode_timeline(episode)
    assert event.event_type == "특보"
    assert event.severity_level == "경보"
    assert event.warning_type == "호우 경보 변경"


def test_zone_group_for_daegu_collapses_five_gu():
    assert {zone_group_for(c) for c in ("27200", "27110", "27260", "27140", "27230")} == {"daegu"}
    assert zone_group_for("47111") == "47111"
    with pytest.raises(AlertValidationDataError):
        zone_group_for("00000")


# ---------------------------------------------------------------------------
# 4. 라벨 파일 계약
# ---------------------------------------------------------------------------


def test_labeled_events_known_positives_and_eal_reference_column():
    vs = load_alert_validation_set()
    by_id = {e.event_id: e for e in vs.events}
    assert len(by_id) == len(vs.events)
    expected = {
        "pohang-2022-09-hinnamno": True,
        "daegu-suseong-2026-07": False,
        "geoje-2026-08": False,
    }
    for event_id, eal_fired in expected.items():
        assert by_id[event_id].damage_confirmed is True
        assert by_id[event_id].eal_alert_fired is eal_fired


def test_labeled_events_evidence_contract():
    vs = load_alert_validation_set()
    for e in vs.events:
        if e.damage_confirmed is None:
            assert e.label_note.strip()
        else:
            assert e.evidence
            assert all(ev.source_url.startswith("http") for ev in e.evidence)
        if e.eal_alert_fired is not None:
            assert e.eal_alert_source.strip()


def _write_labels(tmp_path, events: list[dict]):
    path = tmp_path / "labeled_events.json"
    path.write_text(json.dumps({"dataset": "t", "events": events}, ensure_ascii=False), encoding="utf-8")
    return path


def test_loader_rejects_true_label_without_source_url(tmp_path):
    path = _write_labels(
        tmp_path,
        [{
            "event_id": "x", "region_code": "47111", "window_start": "2022-09-04", "window_end": "2022-09-08",
            "episode_source": "curated", "damage_confirmed": True,
            "evidence": [{"type": "news", "detail": "…", "source_url": ""}],
        }],
    )
    with pytest.raises(AlertValidationDataError):
        load_alert_validation_set(path)


def test_loader_rejects_unknown_label_without_note(tmp_path):
    path = _write_labels(
        tmp_path,
        [{
            "event_id": "x", "region_code": "47111", "window_start": "2022-09-04", "window_end": "2022-09-08",
            "episode_source": "kma_mined", "damage_confirmed": "unknown", "evidence": [], "label_note": "",
        }],
    )
    with pytest.raises(AlertValidationDataError):
        load_alert_validation_set(path)


def test_loader_rejects_missing_file(tmp_path):
    with pytest.raises(AlertValidationDataError):
        load_alert_validation_set(tmp_path / "nope.json")
    with pytest.raises(AlertValidationDataError):
        load_cached_timeline("nope", tmp_path)
    with pytest.raises(AlertValidationDataError):
        load_kma_history("47111", tmp_path)


# ---------------------------------------------------------------------------
# 5. 오프라인 지표 — 네트워크 없이 캐시만으로, 산술 불변식만
# ---------------------------------------------------------------------------


def _raise_network(*_args, **_kwargs):
    raise AssertionError("지표는 네트워크를 호출하면 안 된다")


def test_alert_trigger_precision_metric_runs_offline_with_invariants(monkeypatch):
    monkeypatch.setattr(kma_historical, "_fetch_wrn_reg_raw", _raise_network)
    monkeypatch.setattr(kma_historical, "_fetch_wrn_met_data_raw", _raise_network)
    monkeypatch.setattr(disaster_msg, "_fetch_disaster_msg_raw", _raise_network)

    metric = alert_trigger_precision_metric()

    vs = load_alert_validation_set()
    event_ids = {e.event_id for e in vs.events}
    total = metric["labeled_events"]["total"]
    assert total == len(event_ids)
    assert metric["preregistration"]["candidate_ids"] == list(CANDIDATE_IDS)
    assert metric["fatigue_window"]["episodes_total"] >= 0

    for cid, r in metric["candidates"].items():
        assert r["tp"] + r["fn"] + r["tn"] + r["fp"] + r["unknown_fired"] + r["unknown_silent"] == total
        assert set(r["per_event"]) == event_ids
        for key in ("precision", "recall"):
            assert r[key] is None or 0.0 <= r[key] <= 1.0
        assert r["alerts_per_region_year"] is None or r["alerts_per_region_year"] >= 0.0
        assert r["fatigue_is_lower_bound"] is candidate_by_id(cid).requires_disaster_msg

    ref = metric["eal_alert_reference"]
    assert ref["role"] == "reference_only_not_a_candidate"
    assert ref["tp"] + ref["fn"] + ref["tn"] + ref["fp"] + ref["not_recorded"] == total


# ---------------------------------------------------------------------------
# 6. atom 피쳐·2개 조합·3단계 분리(DEV_LOG 2026-09-03(계속3)) — 수치는 assert하지 않음
# ---------------------------------------------------------------------------

from climate_risk.evaluation.metrics import staged_alert_validation_metric  # noqa: E402
from climate_risk.evaluation.trigger_features import (  # noqa: E402
    ATOM_IDS,
    ATOMS,
    HYDRO_LEVEL_MIN_DURATION_HOURS,
    RAIN_ATOM_IDS,
    a4_storm_surge,
    a7_hydro_level_duration,
    a8_hydro_types_ge2,
    a12_asos_1h_ge_30,
    a13_asos_1h_ge_50,
    a14_asos_day_ge_100,
    a15_asos_day_ge_150,
    a16_aws_60m_max_ge_30,
    a17_aws_day_ge_100,
    all_feature_candidates,
    build_pair_combos,
    hydro_level_durations_hours,
    parse_observation_values,
)


def test_atoms_and_pair_combos_are_frozen_and_unique():
    # A1~A11: 2026-09-03(계속3) 사전 등록, A12~A17: (계속6) 강수 관측 atom append
    assert ATOM_IDS == (
        "A1", "A2", "A3", "A4", "A5", "A6", "A7", "A8", "A9", "A10", "A11",
        "A12", "A13", "A14", "A15", "A16", "A17",
    )
    assert RAIN_ATOM_IDS == ("A12", "A13", "A14", "A15", "A16", "A17")
    combos = build_pair_combos()
    assert len(combos) == 272  # C(17,2) × {AND, OR}
    ids = [c.candidate_id for c in all_feature_candidates()]
    assert len(ids) == len(set(ids)) == 289
    for c in all_feature_candidates():
        assert c.fn([]) is False
    by_id = {c.candidate_id: c for c in all_feature_candidates()}
    assert by_id["A12"].requires_rainfall is True
    assert by_id["A2&A12"].requires_rainfall is True
    assert by_id["A2|A5"].requires_rainfall is False


def _obs(kind: str, stn: str, desc: str, issued_at: str = "2022-09-06T05:00:00+09:00") -> AdvisoryEvent:
    return AdvisoryEvent(
        event_id=f"obs-{kind}-{stn}-{issued_at}", issued_at=issued_at, time_precision="exact",
        event_type="강수관측", warning_type=f"{kind} {stn}", description=desc,
        source_url="https://apihub.kma.go.kr/", target_region_text="", severity_level=None,
    )


def test_rainfall_atoms_parse_observation_events_and_ignore_missing():
    assert parse_observation_values("RN_1H=77.0;RN_DAY=NA") == {"RN_1H": 77.0, "RN_DAY": None}
    hinnamno = [_obs("ASOS", "138", "RN_1H=77.0;RN_DAY=342.4"), _obs("ASOS", "138", "RN_1H=NA;RN_DAY=NA")]
    nanmadol = [_obs("ASOS", "138", "RN_1H=6.0;RN_DAY=36.7")]
    assert a12_asos_1h_ge_30(hinnamno) is True and a13_asos_1h_ge_50(hinnamno) is True
    assert a14_asos_day_ge_100(hinnamno) is True and a15_asos_day_ge_150(hinnamno) is True
    assert all(f(nanmadol) is False for f in (a12_asos_1h_ge_30, a13_asos_1h_ge_50, a14_asos_day_ge_100, a15_asos_day_ge_150))
    # 결측만 있으면 False(0으로 취급하지 않지만 임계값도 못 넘음), 특보 이벤트는 무시
    assert a12_asos_1h_ge_30([_obs("ASOS", "138", "RN_1H=NA;RN_DAY=NA"), _warning("호우 경보 발표", "경보")]) is False
    aws = [_obs("AWS", "313", "RN_HR1=10.5;RN_DAY=361.5;RN_60M_MAX=69.0;RN_15M_MAX=9.0")]
    assert a16_aws_60m_max_ge_30(aws) is True and a17_aws_day_ge_100(aws) is True
    assert a17_aws_day_ge_100([_obs("AWS일", "313", "RN_DAY=468.5", issued_at="2026-08-17")]) is True
    # AWS 관측은 ASOS atom에 영향 없음(지점 종류로 분리)
    assert a12_asos_1h_ge_30(aws) is False
    # 기존 특보 후보는 관측 이벤트를 무시
    assert c0_any_advisory(aws) is False and c2_hydro_high_severity(hinnamno) is False


def test_pair_combo_semantics():
    by_id = {c.candidate_id: c for c in all_feature_candidates()}
    surge_only = [_warning("폭풍해일 주의보 발표", "주의보")]
    rain_level = [_warning("호우 경보 발표", "경보")]
    assert by_id["A4|A6"].fn(surge_only) is True
    assert by_id["A4&A6"].fn(surge_only) is False
    assert by_id["A4&A6"].fn(surge_only + rain_level) is True
    assert by_id["A2&A9"].requires_disaster_msg is True
    assert by_id["A2&A5"].requires_disaster_msg is False


def test_a4_storm_surge_and_a8_hydro_types():
    assert a4_storm_surge([_warning("폭풍해일 주의보 변경", "주의보")]) is True
    assert a4_storm_surge([_warning("폭풍해일 예비 발표", "예비")]) is False
    assert a8_hydro_types_ge2([_warning("태풍 경보 변경", "경보"), _warning("폭풍해일 주의보 변경", "주의보")]) is True
    assert a8_hydro_types_ge2([_warning("태풍 경보 변경", "경보"), _warning("강풍 주의보 발표", "주의보")]) is False


def test_a7_duration_measures_level_state_until_downgrade():
    def w(ts: str, wt: str, sev: str) -> AdvisoryEvent:
        return _event("특보", wt, sev, issued_at=ts, event_id=ts + wt)

    events = [
        w("2022-09-05T21:00:00+09:00", "태풍 주의보 발표", "주의보"),
        w("2022-09-06T00:00:00+09:00", "태풍 경보 변경", "경보"),
        w("2022-09-06T12:00:00+09:00", "태풍 주의보 변경", "주의보"),
        w("2022-09-06T13:00:00+09:00", "태풍 주의보 변경해제", "주의보"),
    ]
    assert hydro_level_durations_hours(events) == {"태풍": 12.0}
    assert a7_hydro_level_duration(events) is (12.0 >= HYDRO_LEVEL_MIN_DURATION_HOURS)
    short = [
        w("2026-07-17T21:50:00+09:00", "호우 경보 변경", "경보"),
        w("2026-07-17T23:30:00+09:00", "호우 주의보 변경", "주의보"),
    ]
    assert a7_hydro_level_duration(short) is False


def test_staged_metric_partitions_events_and_keeps_invariants(monkeypatch):
    monkeypatch.setattr(kma_historical, "_fetch_wrn_reg_raw", _raise_network)
    monkeypatch.setattr(kma_historical, "_fetch_wrn_met_data_raw", _raise_network)
    monkeypatch.setattr(disaster_msg, "_fetch_disaster_msg_raw", _raise_network)

    metric = staged_alert_validation_metric(candidates=tuple(CANDIDATES) + ATOMS)
    vs = load_alert_validation_set()
    all_ids = {e.event_id for e in vs.events}
    p = metric["protocol"]
    stage_ids = {p["anchor_event_id"], *p["stage1_event_ids"], *p["stage2_event_ids"], *p["stage3_event_ids"]}
    assert stage_ids == all_ids  # 단계가 사건 집합을 정확히 분할
    assert set(p["stage1_event_ids"]).isdisjoint(p["stage2_event_ids"])
    assert metric["n_candidates"] == len(CANDIDATES) + len(ATOMS)
    assert set(metric["ranked"]) == set(metric["candidates"])
    for cid, r in metric["candidates"].items():
        s1, s2 = r["stage1"], r["stage2"]
        assert s1["fp"] + s1["tn"] + s1["unknown_fired"] + s1["unknown_silent"] == len(p["stage1_event_ids"])
        assert s2["tp"] + s2["fn"] + s2["tn"] + s2["fp"] + s2["unknown_fired"] + s2["unknown_silent"] == len(p["stage2_event_ids"])
        assert 0 <= s1["unlabeled_fires"] <= s1["unlabeled_episodes"]
        assert r["pass_all"] == (s1["passed"] and s2["passed"] and r["stage3"]["passed"])
        assert set(r["per_event"]) == all_ids
    assert set(metric["passing"]) <= set(metric["candidates"])



# ---------------------------------------------------------------------------
# 7. 담보별 알림 건수(DEV_LOG 2026-09-03(계속8)) — 순수 로직 + 오프라인 불변식
# ---------------------------------------------------------------------------

from climate_risk.evaluation.collateral_counts import (  # noqa: E402
    THRESHOLD_ADVISORY_MM,
    THRESHOLD_WARNING_MM,
    CollateralAssessment,
    StationRainfall,
    collateral_alert_count_metric,
    count_alerts,
    nearest_station,
)


def test_thresholds_are_kma_heavy_rain_criteria():
    assert (THRESHOLD_ADVISORY_MM, THRESHOLD_WARNING_MM) == (110.0, 180.0)


def test_nearest_station_skips_missing_values():
    near_missing = StationRainfall("1", "near-missing", 35.9216, 129.3745, None, 0)
    far_ok = StationRainfall("2", "far-ok", 36.03, 129.38, 342.4, 1)
    picked, km = nearest_station(35.9216, 129.3745, [near_missing, far_ok])
    assert picked.stn == "2" and km > 5
    assert nearest_station(35.9, 129.3, [near_missing]) is None


def test_count_alerts_rain_and_tier_variants():
    a = [
        CollateralAssessment("c1", "내부", "1", "s", 1.0, 342.4),
        CollateralAssessment("c2", "원거리", "1", "s", 1.0, 342.4),
        CollateralAssessment("c3", "근접", "1", "s", 1.0, 48.0),
        CollateralAssessment("c4", None, None, None, None, None),
    ]
    assert count_alerts(a, 110.0, require_tier=False) == 2
    assert count_alerts(a, 110.0, require_tier=True) == 1
    assert count_alerts(a, 180.0, require_tier=False) == 2
    assert count_alerts(a, 400.0, require_tier=False) == 0


def test_collateral_alert_count_metric_offline_invariants(monkeypatch):
    monkeypatch.setattr(kma_historical, "_fetch_wrn_reg_raw", _raise_network)
    monkeypatch.setattr(kma_historical, "_fetch_wrn_met_data_raw", _raise_network)
    monkeypatch.setattr(disaster_msg, "_fetch_disaster_msg_raw", _raise_network)
    from climate_risk.advisory import kma_observation
    monkeypatch.setattr(kma_observation, "_fetch_raw", _raise_network)

    metric = collateral_alert_count_metric()
    vs = load_alert_validation_set()
    assert set(metric["events"]) == {e.event_id for e in vs.events}
    for eid, r in metric["events"].items():
        if r.get("station_rainfall") == "MISSING":
            continue
        assert r["assessed"] <= r["matched"]
        for t, c in r["alerts"].items():
            assert 0 <= c["rain_and_tier"] <= c["rain_only"] <= r["assessed"]
            assert c["rain_only"] <= c["rain_only_ignoring_trigger"]
            if not r["region_triggered"]:
                assert c["rain_only"] == 0 and c["rain_and_tier"] == 0
        # 임계값이 높을수록 알림이 줄어든다(단조)
        a110, a180 = r["alerts"]["110mm"]["rain_only"], r["alerts"]["180mm"]["rain_only"]
        assert a180 <= a110
