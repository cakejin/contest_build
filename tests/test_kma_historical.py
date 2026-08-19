"""advisory/kma_historical.py — 기상청 API허브 특보 이력 조회 회귀 테스트.

고정문(fixture)은 2026-08-19 실호출로 캡처한 실제 응답의 발췌본이다(DEV_LOG.md 참조).
파싱 함수는 순수 함수라 네트워크 없이 직접 테스트하고, `_fetch_*_raw`만 monkeypatch해
오케스트레이션(query_historical_warnings)을 검증한다.
"""

from __future__ import annotations

import urllib.error
from datetime import datetime, timedelta, timezone

import pytest

from climate_risk.advisory import kma_historical as kh

_KST = timezone(timedelta(hours=9))

# 실측 캡처(2026-08-19, wrn_reg.php) 발췌 — 포항·대구(개편 전/후)·거제 항목만.
_REG_SAMPLE = """#START7777
# REG_ID TM_ST        TM_ED        REG_SP   REG_UP   REG_KO---------------------------------- REG_NAME
L1000000 200507010000 210012310000 00000001 00000000 전국                                     전국
L1070000 200507010000 210012310000 00000002 L1000000 경북                                     경상북도
L1072400 200507010000 210012310000 00000113 L1070000 포항                                     포항시
L1140000 200507010000 210012310000 00000002 L1000000 대구                                     대구광역시
L1070100 200507010000 202605311329 00000013 L1140000 대구                                     대구광역시
L1140100 202605311330 210012310000 00000013 L1140000 대구중부                                 대구중부
L1140200 202605311330 210012310000 00000003 L1140000 달성                                     달성군
L1080000 200507010000 210012310000 00000002 L1000000 경상남도                                 경상남도
L1082200 200507010000 210012310000 00000113 L1080000 거제                                     거제시
#7777END
"""

# 실측 캡처(2026-08-19, wrn_met_data.php, reg=L1082200, 힌남노 당일) 발췌.
_MET_DATA_GEOJE_SAMPLE = """#START7777
#      TM_FC,        TM_EF,        TM_IN, STN,   REG_ID, WRN, LVL, CMD, GRD, CNT,   RPT, =
202209060920, 202209061200, 202209060938, 159, L1082200,   T,   3,   7,  00,   4,   101, =
202209060920, 202209061200, 202209060924, 159, L1082200,   W,   2,   6,  00,   4,   101, =
202209061300, 202209061500, 202209061257, 159, L1082200,   W,   2,   3,  00,   4,   101, =
#7777END
"""

# 실측 캡처(2026-08-19, wrn_met_data.php, reg=L1072400, 힌남노 당일) 발췌.
_MET_DATA_POHANG_SAMPLE = """#START7777
#      TM_FC,        TM_EF,        TM_IN, STN,   REG_ID, WRN, LVL, CMD, GRD, CNT,   RPT, =
202209060920, 202209060920, 202209060924, 108, L1072400,   T,   2,   6,  00,   4,   101, =
202209061200, 202209061200, 202209061155, 143, L1072400,   T,   2,   7,  00,   4,   101, =
202209061800, 202209061800, 202209061659, 143, L1072400,   O,   2,   3,  00,   4,   101, =
#7777END
"""

# 실측 캡처(2026-08-19, wrn_met_data.php, reg=L1140100, 대구 수성구 2026-07 호우) 발췌.
_MET_DATA_DAEGU_SAMPLE = """#START7777
#      TM_FC,        TM_EF,        TM_IN, STN,   REG_ID, WRN, LVL, CMD, GRD, CNT,   RPT, =
202607171720, 202607171720, 202607171717, 143, L1140100,   R,   2,   1,  00,   4,   101, =
202607172150, 202607172150, 202607172147, 143, L1140100,   R,   3,   6,  00,   4,   101, =
202607180030, 202607180030, 202607180010, 143, L1140100,   R,   2,   3,  00,   4,   101, =
#7777END
"""


def test_parse_wrn_reg_extracts_zones():
    zones = kh._parse_wrn_reg(_REG_SAMPLE)

    by_id = {z.reg_id: z for z in zones}
    assert by_id["L1072400"].reg_name == "포항시"
    assert by_id["L1072400"].parent_reg_id == "L1070000"
    assert by_id["L1070100"].reg_name == "대구광역시"
    assert by_id["L1140100"].reg_name == "대구중부"
    # 2100년 sentinel은 "만료 없음"으로 정규화된다.
    assert by_id["L1140100"].valid_to.year == 2100


def test_parse_wrn_met_data_decodes_codes():
    events = kh._parse_wrn_met_data(_MET_DATA_POHANG_SAMPLE)

    assert len(events) == 3
    first = events[0]
    assert first.reg_id == "L1072400"
    assert first.wrn_code == "T"
    assert first.wrn_label == "태풍"
    assert first.lvl_code == "2"
    assert first.lvl_label == "주의보"
    assert first.cmd_code == "6"
    assert first.cmd_label == "변경"
    assert first.tm_ef == datetime(2022, 9, 6, 9, 20, tzinfo=_KST)


def test_parse_wrn_met_data_unknown_code_falls_back_to_labeled_raw_value():
    text = _MET_DATA_POHANG_SAMPLE.replace("   T,   2,   6", "   Z,   2,   6")
    events = kh._parse_wrn_met_data(text)
    assert events[0].wrn_label == "미확인(Z)"


def test_resolve_region_zone_picks_pre_reorg_daegu_code_for_old_date():
    zones = kh._parse_wrn_reg(_REG_SAMPLE)
    # 2026-05-31 개편 이전 날짜 -> 옛 REG_ID(L1070100, "대구광역시")를 골라야 한다.
    as_of = datetime(2024, 1, 1, tzinfo=_KST)

    zone = kh.resolve_region_zone("27260", as_of, zones)

    assert zone.reg_id == "L1070100"
    assert zone.reg_name == "대구광역시"


def test_resolve_region_zone_picks_post_reorg_daegu_code_for_recent_date():
    zones = kh._parse_wrn_reg(_REG_SAMPLE)
    # 2026-07 대구 수성구 이벤트 -> 개편 후 REG_ID(L1140100, "대구중부")를 골라야 한다.
    as_of = datetime(2026, 7, 17, tzinfo=_KST)

    zone = kh.resolve_region_zone("27260", as_of, zones)

    assert zone.reg_id == "L1140100"
    assert zone.reg_name == "대구중부"


def test_resolve_region_zone_all_five_daegu_gu_codes_converge_to_same_zone():
    """대구 5개구는 개별 구분이 안 된다는 게 이 모듈의 알려진 한계(모듈 docstring) —
    5개 SGG 코드 전부 같은 특보구역으로 수렴하는지 회귀로 고정한다."""
    zones = kh._parse_wrn_reg(_REG_SAMPLE)
    as_of = datetime(2026, 7, 17, tzinfo=_KST)

    resolved = {
        code: kh.resolve_region_zone(code, as_of, zones).reg_id
        for code in ("27200", "27110", "27260", "27140", "27230")
    }

    assert len(set(resolved.values())) == 1


def test_resolve_region_zone_pohang_maps_to_pohang_si():
    zones = kh._parse_wrn_reg(_REG_SAMPLE)
    zone = kh.resolve_region_zone("47111", datetime(2022, 9, 6, tzinfo=_KST), zones)
    assert zone.reg_id == "L1072400"


def test_resolve_region_zone_geoje_maps_to_geoje_si():
    """2026-08-19 추가 — 거제(48310)는 "경상남도"(L1080000) 직계 자식 "거제시"(L1082200)로
    매핑돼야 한다."""
    zones = kh._parse_wrn_reg(_REG_SAMPLE)
    zone = kh.resolve_region_zone("48310", datetime(2022, 9, 6, tzinfo=_KST), zones)
    assert zone.reg_id == "L1082200"
    assert zone.reg_name == "거제시"


def test_query_historical_warnings_geoje_happy_path(monkeypatch):
    monkeypatch.setattr(kh, "_fetch_wrn_reg_raw", lambda: _REG_SAMPLE.encode("euc-kr"))
    monkeypatch.setattr(
        kh, "_fetch_wrn_met_data_raw", lambda reg_id, start, end: _MET_DATA_GEOJE_SAMPLE.encode("euc-kr")
    )

    result = kh.query_historical_warnings(
        "48310", datetime(2022, 9, 5, tzinfo=_KST), datetime(2022, 9, 7, tzinfo=_KST)
    )

    assert result.status == kh.STATUS_OK
    assert result.reg_id == "L1082200"
    assert len(result.events) == 3
    assert result.events[0].wrn_label == "태풍"
    assert result.events[0].lvl_label == "경보"


def test_resolve_region_zone_unknown_region_code_returns_none():
    zones = kh._parse_wrn_reg(_REG_SAMPLE)
    assert kh.resolve_region_zone("99999", datetime(2024, 1, 1, tzinfo=_KST), zones) is None


def test_query_historical_warnings_happy_path(monkeypatch):
    monkeypatch.setattr(kh, "_fetch_wrn_reg_raw", lambda: _REG_SAMPLE.encode("euc-kr"))
    monkeypatch.setattr(
        kh, "_fetch_wrn_met_data_raw", lambda reg_id, start, end: _MET_DATA_DAEGU_SAMPLE.encode("euc-kr")
    )

    result = kh.query_historical_warnings(
        "27260", datetime(2026, 7, 17, tzinfo=_KST), datetime(2026, 7, 19, tzinfo=_KST)
    )

    assert result.status == kh.STATUS_OK
    assert result.reg_id == "L1140100"
    assert len(result.events) == 3
    assert result.events[1].lvl_label == "경보"  # 21:50 호우경보로 격상


def test_query_historical_warnings_no_zone_match(monkeypatch):
    monkeypatch.setattr(kh, "_fetch_wrn_reg_raw", lambda: _REG_SAMPLE.encode("euc-kr"))

    result = kh.query_historical_warnings(
        "99999", datetime(2024, 1, 1, tzinfo=_KST), datetime(2024, 1, 2, tzinfo=_KST)
    )

    assert result.status == kh.STATUS_NO_ZONE_MATCH
    assert result.events == []


def test_query_historical_warnings_activation_required_on_reg_zone_call(monkeypatch):
    def _raise(*args, **kwargs):
        raise urllib.error.HTTPError("url", 403, "Forbidden", {}, None)

    monkeypatch.setattr(kh, "_fetch_wrn_reg_raw", _raise)

    result = kh.query_historical_warnings(
        "27260", datetime(2026, 7, 17, tzinfo=_KST), datetime(2026, 7, 19, tzinfo=_KST)
    )

    assert result.status == kh.STATUS_ACTIVATION_REQUIRED
    assert "활용신청" in result.note


def test_query_historical_warnings_activation_required_on_met_data_call(monkeypatch):
    monkeypatch.setattr(kh, "_fetch_wrn_reg_raw", lambda: _REG_SAMPLE.encode("euc-kr"))

    def _raise(reg_id, start, end):
        raise urllib.error.HTTPError("url", 403, "Forbidden", {}, None)

    monkeypatch.setattr(kh, "_fetch_wrn_met_data_raw", _raise)

    result = kh.query_historical_warnings(
        "27260", datetime(2026, 7, 17, tzinfo=_KST), datetime(2026, 7, 19, tzinfo=_KST)
    )

    assert result.status == kh.STATUS_ACTIVATION_REQUIRED
    assert result.reg_id == "L1140100"  # 구역 조회는 이미 성공했었다는 게 남아있어야 함


def test_query_historical_warnings_upstream_network_error_not_silently_empty(monkeypatch):
    def _raise():
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr(kh, "_fetch_wrn_reg_raw", _raise)

    result = kh.query_historical_warnings(
        "27260", datetime(2026, 7, 17, tzinfo=_KST), datetime(2026, 7, 19, tzinfo=_KST)
    )

    assert result.status == kh.STATUS_UPSTREAM_ERROR
