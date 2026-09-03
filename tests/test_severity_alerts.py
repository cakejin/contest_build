from climate_risk.advisory.schema import AdvisoryEvent
from climate_risk.portfolio.schema import PortfolioRecord
from climate_risk.portfolio.severity_alerts import (
    SEVERITY_SOURCE_DISASTER_MSG,
    SEVERITY_SOURCE_HISTORICAL_WARNING,
    SeverityAlertQueueEntry,
    build_severity_alert_queue,
)


def _record(collateral_id="COL-001", region_code="48310"):
    return PortfolioRecord(
        collateral_id=collateral_id,
        address="테스트",
        collateral_type="아파트",
        balance=100.0,
        collateral_value=200.0,
        ltv=0.5,
        score_before=50.0,
        eal_before=1000.0,
        region_code=region_code,
        geocode_confidence="OK",
    )


def _event(event_type, severity_level, issued_at="2026-08-17T10:00:00+09:00", event_id="e1"):
    return AdvisoryEvent(
        event_id=event_id,
        issued_at=issued_at,
        time_precision="exact",
        event_type=event_type,
        warning_type="호우",
        description=f"테스트 {event_type} {severity_level}",
        source_url="https://example.com",
        target_region_text="거제시",
        severity_level=severity_level,
    )


def test_warning_level_경보_generates_alert():
    records = [_record()]
    events = [_event("특보", "경보")]

    alerts = build_severity_alert_queue(records, events)

    assert len(alerts) == 1
    assert alerts[0].collateral_id == "COL-001"
    assert alerts[0].severity_level == "경보"
    assert alerts[0].severity_source == SEVERITY_SOURCE_HISTORICAL_WARNING


def test_warning_level_주의보_no_alert():
    records = [_record()]
    events = [_event("특보", "주의보")]

    alerts = build_severity_alert_queue(records, events)

    assert alerts == []


def test_disaster_msg_긴급재난_generates_alert():
    records = [_record()]
    events = [_event("재난문자", "긴급재난")]

    alerts = build_severity_alert_queue(records, events)

    assert len(alerts) == 1
    assert alerts[0].severity_source == SEVERITY_SOURCE_DISASTER_MSG


def test_disaster_msg_안전안내_no_alert():
    records = [_record()]
    events = [_event("재난문자", "안전안내")]

    alerts = build_severity_alert_queue(records, events)

    assert alerts == []


def test_no_events_no_alert():
    records = [_record()]

    alerts = build_severity_alert_queue(records, [])

    assert alerts == []


def test_no_matched_records_no_alert():
    events = [_event("특보", "경보")]

    alerts = build_severity_alert_queue([], events)

    assert alerts == []


def test_all_matched_records_get_alerted_once_per_call():
    """55건짜리 조회 구간이어도 담보당 알림 1건만 생성된다(가장 최근 고심각도 이벤트가
    대표값) — 이벤트마다 중복 생성하지 않음을 확인."""
    records = [_record("COL-001"), _record("COL-002")]
    events = [
        _event("특보", "주의보", issued_at="2026-08-17T09:00:00+09:00", event_id="e1"),
        _event("특보", "경보", issued_at="2026-08-17T10:00:00+09:00", event_id="e2"),
        _event("재난문자", "긴급재난", issued_at="2026-08-18T03:00:00+09:00", event_id="e3"),
    ]

    alerts = build_severity_alert_queue(records, events)

    assert len(alerts) == 2
    assert {a.collateral_id for a in alerts} == {"COL-001", "COL-002"}
    # 가장 최근 고심각도 이벤트(e3, 재난문자/긴급재난)가 대표값으로 쓰였는지 확인
    for alert in alerts:
        assert alert.severity_level == "긴급재난"
        assert alert.severity_source == SEVERITY_SOURCE_DISASTER_MSG


def test_severity_alert_entry_has_no_money_fields():
    """CLAUDE.md 설계원칙2(특보는 알림 트리거로만, EAL·LTV·금리 계산에 직접 연결 금지)의
    회귀 방지 — 심각도 알림 스키마에 EAL/LTV/금리/score 관련 필드가 구조적으로 존재하지
    않는지 고정한다. tests/test_portfolio_alerts.py의
    test_alert_entry_has_no_ltv_or_rate_fields와 동일 정신."""
    field_names = {f.name for f in SeverityAlertQueueEntry.__dataclass_fields__.values()}

    forbidden_keywords = {"ltv", "rate", "recall", "interest", "eal", "score"}
    for field_name in field_names:
        assert not any(kw in field_name.lower() for kw in forbidden_keywords), field_name

    expected = {
        "collateral_id",
        "region_code",
        "severity_level",
        "severity_source",
        "event_description",
        "issued_at",
        "source_url",
        "geocode_confidence",
        # 2026-09-03(계속10) — 담보별 강수 등급·근거(금전 필드 아님)
        "alert_tier",
        "rain_mm",
        "rain_station",
        "rain_station_km",
    }
    assert field_names == expected



# ---------------------------------------------------------------------------
# 2026-09-03(계속10) — 규칙 교체: 지역 트리거 종류 조건 + 담보별 강수 2단계(110/180mm)
# ---------------------------------------------------------------------------

from climate_risk.advisory.kma_observation import StationRainfall  # noqa: E402
from climate_risk.portfolio.severity_alerts import (  # noqa: E402
    ALERT_TIER_ADVISORY,
    ALERT_TIER_RAIN_UNKNOWN,
    ALERT_TIER_WARNING,
    RAIN_STATUS_NOT_QUERIED,
    classify_rain_tier,
    summarize_severity_alerts,
)


def _located(collateral_id, lat, lon, region_code="48310"):
    return PortfolioRecord(
        collateral_id=collateral_id, address="테스트", collateral_type="아파트", balance=100.0,
        collateral_value=200.0, ltv=0.5, score_before=50.0, eal_before=1000.0,
        lat=lat, lon=lon, region_code=region_code, geocode_confidence="OK",
    )


def _typed_event(event_type, warning_type, severity_level, event_id="e1"):
    return AdvisoryEvent(
        event_id=event_id, issued_at="2026-08-17T10:00:00+09:00", time_precision="exact",
        event_type=event_type, warning_type=warning_type, description=f"{warning_type} {severity_level}",
        source_url="https://example.com", target_region_text="거제시", severity_level=severity_level,
    )


def test_region_trigger_requires_hydro_type():
    """폭염·강풍 경보는 더 이상 재심사 알림을 켜지 않는다(검증 후보 A2)."""
    assert build_severity_alert_queue([_record()], [_typed_event("특보", "폭염 경보 변경", "경보")]) == []
    assert build_severity_alert_queue([_record()], [_typed_event("특보", "강풍 경보 발표", "경보")]) == []
    assert build_severity_alert_queue([_record()], [_typed_event("재난문자", "산불", "긴급재난")]) == []
    assert len(build_severity_alert_queue([_record()], [_typed_event("특보", "태풍 경보 변경", "경보")])) == 1
    assert len(build_severity_alert_queue([_record()], [_typed_event("재난문자", "호우", "긴급재난")])) == 1


def test_classify_rain_tier_thresholds_are_kma_criteria():
    assert classify_rain_tier(None) == ALERT_TIER_RAIN_UNKNOWN
    assert classify_rain_tier(109.9) is None
    assert classify_rain_tier(110.0) == ALERT_TIER_ADVISORY
    assert classify_rain_tier(179.9) == ALERT_TIER_ADVISORY
    assert classify_rain_tier(180.0) == ALERT_TIER_WARNING


def test_collateral_tiers_from_nearest_station_and_unknown_when_no_observation():
    events = [_typed_event("특보", "호우 경보 변경", "경보")]
    records = [_located("NEAR-WET", 34.870, 128.705), _located("NEAR-DRY", 34.700, 128.600), _located("NOGEO", None, None)]
    stations = [
        StationRainfall("313", "양지암", 34.882, 128.741, 654.3, 5),  # 고현 인근, 심각
        StationRainfall("999", "남쪽", 34.700, 128.600, 48.0, 5),  # 주의보 미만 → 알림 없음
        StationRainfall("000", "결측", 34.870, 128.705, None, 0),  # 결측 지점은 최근접 후보에서 제외
    ]
    entries = build_severity_alert_queue(records, events, stations)
    by_id = {e.collateral_id: e for e in entries}
    assert by_id["NEAR-WET"].alert_tier == ALERT_TIER_WARNING and by_id["NEAR-WET"].rain_mm == 654.3
    assert by_id["NEAR-WET"].rain_station == "313 양지암"
    assert "NEAR-DRY" not in by_id  # 48mm → 주의보 임계 미만
    assert by_id["NOGEO"].alert_tier == ALERT_TIER_RAIN_UNKNOWN  # 좌표 없음 → 판정 불가, 알림 유지

    # 관측 없음(None) → 전원 강수미확인 유지(데이터 없음 ≠ 위험 없음)
    no_obs = build_severity_alert_queue(records, events, None)
    assert {e.alert_tier for e in no_obs} == {ALERT_TIER_RAIN_UNKNOWN} and len(no_obs) == 3

    summary = summarize_severity_alerts(records, events, entries, rain_status="OK")
    assert (summary.matched_count, summary.alert_count, summary.warning_count, summary.advisory_count, summary.rain_unknown_count) == (3, 2, 1, 0, 1)
    assert summary.region_triggered is True and (summary.threshold_advisory_mm, summary.threshold_warning_mm) == (110.0, 180.0)
    empty = summarize_severity_alerts(records, [], [], rain_status=RAIN_STATUS_NOT_QUERIED)
    assert empty.region_triggered is False and empty.alert_count == 0
