"""advisory/disaster_msg.py — safetydata.go.kr 재난문자 API 회귀 테스트.

fixture는 전부 2026-08-20 실호출로 캡처한 실제 응답의 발췌본이다(DEV_LOG.md 참조) —
IP 미등록 에러, 대구 수성구 2026-07-17 집중호우(지산동 세분화 포함), 포항 남구
2025년 봄 동해안 산불(신규 산불/화재 카테고리 검증용).
"""

from __future__ import annotations

import json
import urllib.error
from datetime import datetime, timedelta, timezone

from climate_risk.advisory import disaster_msg as dm

_KST = timezone(timedelta(hours=9))

# 2026-08-20 실측 캡처(공용 와이파이 IP로 호출, safetydata.go.kr 화이트리스트에 미등록).
_UNREGISTERED_IP_SAMPLE = (
    '{"header":{"resultMsg":"UNREGISTERED IP ERROR","resultCode":"32",'
    '"errorMsg":"등록되지 않은 IP"},"body":null}'
).encode("utf-8")

# 2026-08-20 실측 캡처(rgnNm="대구광역시 수성구", crtDt=20260717) 발췌 — 지산동 집중호우
# 사건(DEV_LOG.md 2026-08-12 큐레이션 데이터와 동일 사건). 관련 없는 카테고리(폭염·정전)
# 섞임과 빈 DST_SE_NM 레코드도 실제 응답 그대로 포함해 필터링 로직을 검증한다.
_SUSEONG_JULY_SAMPLE = {
    "header": {"resultMsg": "NORMAL SERVICE", "resultCode": "00", "errorMsg": None},
    "numOfRows": 100, "pageNo": 1, "totalCount": 15,
    "body": [
        {
            "SN": 261835, "CRT_DT": "2026/07/20 10:04:21",
            "MSG_CN": "폭염 안내", "RCPTN_RGN_NM": "대구광역시 남구 ,대구광역시 수성구 ",
            "EMRG_STEP_NM": "안전안내", "DST_SE_NM": "폭염",
        },
        {
            "SN": 261350, "CRT_DT": "2026/07/17 17:30:06",
            "MSG_CN": "호우 안내", "RCPTN_RGN_NM": (
                "대구광역시 남구 ,대구광역시 달서구 ,대구광역시 동구 ,대구광역시 북구 ,"
                "대구광역시 서구 ,대구광역시 수성구 ,대구광역시 중구 "
            ),
            "EMRG_STEP_NM": "안전안내", "DST_SE_NM": "호우",
        },
        {
            "SN": 261453, "CRT_DT": "2026/07/17 22:55:47",
            "MSG_CN": "수성구 지산동 호우 안내", "RCPTN_RGN_NM": "대구광역시 수성구 지산동",
            "EMRG_STEP_NM": "안전안내", "DST_SE_NM": "호우",
        },
        {
            "SN": 261436, "CRT_DT": "2026/07/17 22:03:19",
            "MSG_CN": "기타 안내", "RCPTN_RGN_NM": "대구광역시 수성구 지산동",
            "EMRG_STEP_NM": "안전안내", "DST_SE_NM": "",
        },
        {
            "SN": 265707, "CRT_DT": "2026/08/08 00:07:37",
            "MSG_CN": "정전 안내", "RCPTN_RGN_NM": "대구광역시 수성구 매호동",
            "EMRG_STEP_NM": "안전안내", "DST_SE_NM": "정전",
        },
    ],
}

# 2026-08-20 실측 캡처(rgnNm="경상북도 포항시 남구", 2025년 봄 동해안 산불) 발췌.
_POHANG_WILDFIRE_SAMPLE = {
    "header": {"resultMsg": "NORMAL SERVICE", "resultCode": "00", "errorMsg": None},
    "numOfRows": 100, "pageNo": 1, "totalCount": 3,
    "body": [
        {
            "SN": 999001, "CRT_DT": "2025/03/25 18:42:05",
            "MSG_CN": "산불 확산 중 — 대피 안내", "RCPTN_RGN_NM": "경상북도 포항시 남구 ,경상북도 포항시 북구 ",
            "EMRG_STEP_NM": "긴급재난", "DST_SE_NM": "산불",
        },
        {
            "SN": 999002, "CRT_DT": "2025/03/18 13:05:36",
            "MSG_CN": "풍랑주의보 안내", "RCPTN_RGN_NM": "경상북도 포항시 남구 ,경상북도 포항시 북구 ",
            "EMRG_STEP_NM": "안전안내", "DST_SE_NM": "풍랑",
        },
        {
            "SN": 999003, "CRT_DT": "2025/04/13 10:59:51",
            "MSG_CN": "강풍 안내", "RCPTN_RGN_NM": "경상북도 포항시 남구 ,경상북도 포항시 북구 ",
            "EMRG_STEP_NM": "안전안내", "DST_SE_NM": "강풍",
        },
    ],
}


def _ok_bytes(payload: dict) -> bytes:
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")


def test_unregistered_ip_translates_to_clear_guidance_not_raw_code(monkeypatch):
    monkeypatch.setattr(dm, "_fetch_disaster_msg_raw", lambda params: _UNREGISTERED_IP_SAMPLE)

    result = dm.query_disaster_messages({"pageNo": "1", "numOfRows": "5"})

    assert result.status == dm.STATUS_UNREGISTERED_IP
    assert result.raw_body is None
    assert "등록" in result.note  # 원시 코드(32)나 영문 메시지를 그대로 노출하지 않고 안내문으로 번역됨
    assert "핫스팟" not in result.note  # 특정 네트워크를 전제하지 않는다(사용자 명시 요청)


def test_unknown_result_code_is_explicit_upstream_error_not_silent_success(monkeypatch):
    monkeypatch.setattr(
        dm, "_fetch_disaster_msg_raw", lambda params: b'{"header":{"resultCode":"99","resultMsg":"UNKNOWN"},"body":null}'
    )

    result = dm.query_disaster_messages({"pageNo": "1", "numOfRows": "5"})

    assert result.status == dm.STATUS_UPSTREAM_ERROR
    assert result.raw_body is None


def test_network_error_not_silently_empty(monkeypatch):
    def _raise(params):
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr(dm, "_fetch_disaster_msg_raw", _raise)

    result = dm.query_disaster_messages({"pageNo": "1", "numOfRows": "5"})

    assert result.status == dm.STATUS_UPSTREAM_ERROR
    assert result.raw_body is None


def test_success_result_code_returns_raw_body_list_unparsed(monkeypatch):
    monkeypatch.setattr(dm, "_fetch_disaster_msg_raw", lambda params: _ok_bytes(_SUSEONG_JULY_SAMPLE))

    result = dm.query_disaster_messages({"pageNo": "1", "numOfRows": "100"})

    assert result.status == dm.STATUS_OK
    assert len(result.raw_body) == 5


def test_message_matches_region_exact_and_broader_and_narrower():
    target = "대구광역시 수성구"
    assert dm._message_matches_region("대구광역시 수성구 ", target)  # 후행 공백
    assert dm._message_matches_region("대구광역시 수성구 지산동", target)  # 하위(동) 세분화
    assert dm._message_matches_region("대구광역시", target)  # 상위지역(광역시 전체)
    assert dm._message_matches_region("대구광역시 남구 ,대구광역시 수성구 ,대구광역시 중구", target)  # 다중지역 중 포함
    assert not dm._message_matches_region("대구광역시 남구", target)  # 다른 구
    assert not dm._message_matches_region("대구광역시 동남구", target)  # 토큰 경계 오탐 방지


def test_query_disaster_messages_for_region_filters_relevant_categories_and_matches_dong_level(monkeypatch):
    monkeypatch.setattr(dm, "_fetch_disaster_msg_raw", lambda params: _ok_bytes(_SUSEONG_JULY_SAMPLE))

    result = dm.query_disaster_messages_for_region(
        "27260", datetime(2026, 7, 17, tzinfo=_KST), datetime(2026, 7, 19, tzinfo=_KST)
    )

    assert result.status == dm.STATUS_OK
    # 5건 중: 폭염(무관 카테고리 제외)·정전(무관·기간 밖)·빈 DST_SE_NM(제외)·07-20(기간 밖) 빠지고
    # 호우 2건(전체지역 리스트 1건 + 지산동 세분화 1건)만 남아야 한다.
    assert len(result.messages) == 2
    assert all(m.dst_se_nm == "호우" for m in result.messages)
    assert any("지산동" in m.rcptn_rgn_nm for m in result.messages)


def test_query_disaster_messages_for_region_includes_wildfire_category(monkeypatch):
    """2026-08-20 사용자 요청으로 신규 추가된 산불/화재 카테고리 — 2025년 봄 포항 인근
    동해안 산불 실측 데이터로 검증(DEV_LOG.md 참조)."""
    monkeypatch.setattr(dm, "_fetch_disaster_msg_raw", lambda params: _ok_bytes(_POHANG_WILDFIRE_SAMPLE))

    result = dm.query_disaster_messages_for_region(
        "47111", datetime(2025, 3, 1, tzinfo=_KST), datetime(2025, 4, 15, tzinfo=_KST)
    )

    assert result.status == dm.STATUS_OK
    dst_types = {m.dst_se_nm for m in result.messages}
    assert dst_types == {"산불", "풍랑", "강풍"}  # 3건 전부 관련 카테고리라 다 남아야 함


def test_query_disaster_messages_for_region_unmapped_region_is_explicit():
    result = dm.query_disaster_messages_for_region(
        "99999", datetime(2024, 1, 1, tzinfo=_KST), datetime(2024, 1, 2, tzinfo=_KST)
    )

    assert result.status == dm.STATUS_UNMAPPED_REGION
    assert result.messages == []


def test_query_disaster_messages_for_region_propagates_unregistered_ip(monkeypatch):
    monkeypatch.setattr(dm, "_fetch_disaster_msg_raw", lambda params: _UNREGISTERED_IP_SAMPLE)

    result = dm.query_disaster_messages_for_region(
        "27260", datetime(2026, 7, 17, tzinfo=_KST), datetime(2026, 7, 19, tzinfo=_KST)
    )

    assert result.status == dm.STATUS_UNREGISTERED_IP
    assert "핫스팟" not in result.note


def test_query_disaster_messages_for_region_page_limit_reached_is_explicit_not_silent_truncation(monkeypatch):
    """페이지 상한(_MAX_PAGES)에 도달하면 결과를 조용히 자르지 않고 명시 상태를 반환한다
    (설계원칙1과 같은 정신)."""
    full_page = dict(_SUSEONG_JULY_SAMPLE)
    full_page["body"] = [_SUSEONG_JULY_SAMPLE["body"][0]] * dm._PAGE_SIZE  # 매 페이지 꽉 채워서 종료 조건 안 걸리게

    monkeypatch.setattr(dm, "_fetch_disaster_msg_raw", lambda params: _ok_bytes(full_page))

    result = dm.query_disaster_messages_for_region(
        "27260", datetime(2026, 7, 17, tzinfo=_KST), datetime(2026, 7, 19, tzinfo=_KST)
    )

    assert result.status == dm.STATUS_PAGE_LIMIT_REACHED
    assert result.messages == []
