"""webapp/app.py의 신규 엔드포인트(/api/resolve-region, /api/address-search) 회귀
테스트 — DEV_LOG.md 2026-08-18 "주소-프리셋 디커플링" 논의의 실체.

이 파일들은 `webapp/`이 파이썬 패키지가 아니라 `python -m uvicorn webapp.app:app`으로만
실행되던 모듈이라, 테스트에서 직접 임포트하려면 그 디렉터리를 sys.path에 넣어야 한다
(webapp/app.py 자신도 src/를 같은 방식으로 넣는다 — 동일 패턴).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

_WEBAPP_DIR = Path(__file__).resolve().parents[1] / "webapp"
if str(_WEBAPP_DIR) not in sys.path:
    sys.path.insert(0, str(_WEBAPP_DIR))

import app as webapp_app  # noqa: E402
from climate_risk.agents.flood_agent import FloodAgentOutput  # noqa: E402
from climate_risk.config import FLOOD_SHP_SOURCES  # noqa: E402
from climate_risk.geocoding import juso as juso_module  # noqa: E402
from climate_risk.geocoding.vworld import GeocodedAddress  # noqa: E402
from climate_risk.gis.query import FloodRiskResult  # noqa: E402

client = TestClient(webapp_app.app)

_FAKE_GEOCODED = GeocodedAddress(
    lat=35.98768, lon=129.39979, refined_text="경상북도 포항시 남구 인덕로 27", input_address="포항 남구 인덕로 27"
)


def _flood_output(source_shp_file: str | None, coverage: str = "IN_SCOPE") -> FloodAgentOutput:
    return FloodAgentOutput(
        flood=FloodRiskResult(
            coverage=coverage,
            in_polygon=True,
            tier="내부",
            distance_to_polygon_m=0.0,
            freq_label="MAX",
            river_name="냉천",
            region_name="포항시 남구",
            source_shp_file=source_shp_file,
            license="공공누리4유형",
            methodology_disclaimer="test",
            uncertain=None,
        ),
        source_id="flood:test.shp",
        field_sources={},
    )


def test_resolve_region_returns_unresolved_on_geocode_failure(monkeypatch):
    monkeypatch.setattr(webapp_app, "geocode_road_address", lambda address: None)

    res = client.get("/api/resolve-region", params={"address": "존재하지않는주소"})

    assert res.status_code == 200
    body = res.json()
    assert body["resolved"] is False
    assert "reason" in body


def test_resolve_region_derives_region_code_and_curated_replay(monkeypatch):
    """HANDOVER §③ 힌남노 프리셋과 동일한 지역(포항 남구, 47111)이 실제 SHP 파일명 매핑을
    통해 자동 감지되는지 — 담보 평가↔포트폴리오 알림 불일치 버그 수정의 핵심 경로."""
    pohang_shp = str(next(src.path for src in FLOOD_SHP_SOURCES if src.region_code == "47111"))

    monkeypatch.setattr(webapp_app, "geocode_road_address", lambda address: _FAKE_GEOCODED)
    monkeypatch.setattr(webapp_app, "run_flood_agent", lambda lat, lon, **kwargs: _flood_output(pohang_shp))

    res = client.get("/api/resolve-region", params={"address": "경상북도 포항시 남구 인덕로 27"})

    assert res.status_code == 200
    body = res.json()
    assert body["resolved"] is True
    assert body["region_code"] == "47111"
    assert body["coverage"] == "IN_SCOPE"
    assert body["live_supported"] is True
    assert body["curated_replay"]["mode"] == "replay"
    assert "힌남노" in body["curated_replay"]["label"]


def test_resolve_region_region_without_curated_replay_still_reports_live_supported(monkeypatch):
    """대구 북구(27230)는 SHP 커버리지·라이브 매핑은 있지만 큐레이션 리플레이가 없다
    (DEV_LOG.md 2026-08-18) — curated_replay는 None, live_supported는 True여야 한다."""
    monkeypatch.setattr(webapp_app, "geocode_road_address", lambda address: _FAKE_GEOCODED)
    monkeypatch.setattr(
        webapp_app,
        "run_flood_agent",
        lambda lat, lon, **kwargs: _flood_output("dummy_bukgu.shp"),
    )
    monkeypatch.setitem(webapp_app.SHP_FILENAME_TO_REGION_CODE, "dummy_bukgu.shp", "27230")

    res = client.get("/api/resolve-region", params={"address": "대구광역시 북구 침산로 10"})

    body = res.json()
    assert body["region_code"] == "27230"
    assert body["live_supported"] is True
    assert body["curated_replay"] is None


def test_resolve_region_out_of_scope_coverage(monkeypatch):
    monkeypatch.setattr(webapp_app, "geocode_road_address", lambda address: _FAKE_GEOCODED)
    monkeypatch.setattr(
        webapp_app, "run_flood_agent", lambda lat, lon, **kwargs: _flood_output(None, coverage="OUT_OF_SCOPE")
    )

    res = client.get("/api/resolve-region", params={"address": "아무데나"})

    body = res.json()
    assert body["resolved"] is True
    assert body["coverage"] == "OUT_OF_SCOPE"
    assert body["region_code"] is None
    assert body["curated_replay"] is None


def test_address_search_proxies_and_filters(monkeypatch):
    def fake_search(keyword, count=20):
        from climate_risk.geocoding.juso import AddressSuggestion

        return [
            AddressSuggestion(road_address="대구광역시 북구 침산로 10", building_name="테스트빌라"),
        ]

    monkeypatch.setattr(webapp_app, "search_road_addresses", fake_search)

    res = client.get("/api/address-search", params={"keyword": "침산로"})

    assert res.status_code == 200
    body = res.json()
    assert body == [{"road_address": "대구광역시 북구 침산로 10", "building_name": "테스트빌라"}]


def test_address_search_degrades_to_empty_list_on_juso_error(monkeypatch):
    def _raise(keyword, count=20):
        raise juso_module.JusoSearchError("키 만료")

    monkeypatch.setattr(webapp_app, "search_road_addresses", _raise)

    res = client.get("/api/address-search", params={"keyword": "침산로"})

    assert res.status_code == 200
    assert res.json() == []


@pytest.mark.parametrize("path", ["/api/resolve-region", "/api/address-search"])
def test_missing_required_query_param_is_422(path):
    res = client.get(path)
    assert res.status_code == 422


def test_portfolio_list_exposes_fields_needed_by_picker_only(monkeypatch):
    """2026-08-19(계속, DEV_LOG.md 참조) — "기존 포트폴리오 조회" 탭용 목록. ltv·balance는
    고를 때 참고용으로 불필요해 일부러 안 내보낸다(HANDOVER §⑥ 블루라이닝 방지 설계와
    같은 결 — 화면에 굳이 흘려보낼 이유가 없는 값은 애초에 API 응답에 안 넣는다)."""
    from climate_risk.portfolio.schema import PortfolioRecord

    fake_records = [
        PortfolioRecord(
            collateral_id="COL-001",
            address="경상북도 포항시 남구 인덕로 27",
            collateral_type="아파트",
            balance=300000000.0,
            collateral_value=500000000.0,
            ltv=0.6,
            score_before=55.0,
            eal_before=1000.0,
            region_code="47111",
        )
    ]
    monkeypatch.setattr(webapp_app, "load_portfolio", lambda path: fake_records)

    res = client.get("/api/portfolio-list")

    assert res.status_code == 200
    body = res.json()
    assert body == [
        {
            "collateral_id": "COL-001",
            "address": "경상북도 포항시 남구 인덕로 27",
            "collateral_type": "아파트",
            "region_code": "47111",
            "collateral_value": 500000000.0,
        }
    ]
    assert "ltv" not in body[0]
    assert "balance" not in body[0]


def test_parse_kst_date_start_of_day():
    dt = webapp_app._parse_kst_date("2026-07-17")
    assert dt.isoformat() == "2026-07-17T00:00:00+09:00"


def test_assess_without_query_date_uses_live_mode(monkeypatch):
    """DEV_LOG.md 2026-08-19(계속) — "리플레이/라이브/특정날짜" 드롭다운을 걷어내고
    query_date 하나로 단순화했다: 날짜 미입력 -> mode="live", historical_start/end=None."""
    captured = {}

    def fake_run_week4_demo(**kwargs):
        captured.update(kwargs)
        return {"ok": True}

    monkeypatch.setattr(webapp_app, "run_week4_demo", fake_run_week4_demo)

    res = client.get(
        "/api/assess",
        params={"address": "테스트주소", "collateral_value": "500000000", "region_code": "47111"},
    )

    assert res.status_code == 200
    assert captured["mode"] == "live"
    assert captured["historical_start"] is None
    assert captured["historical_end"] is None


def test_assess_with_query_date_uses_historical_mode_and_24h_window(monkeypatch):
    """날짜 하나 입력 -> mode="historical", [그 날 00:00, 다음날 00:00) KST 구간으로
    자동 변환 — 사용자가 시작/종료를 따로 안 넣어도 되게(2026-08-19 사용자 피드백)."""
    captured = {}

    def fake_run_week4_demo(**kwargs):
        captured.update(kwargs)
        return {"ok": True}

    monkeypatch.setattr(webapp_app, "run_week4_demo", fake_run_week4_demo)

    res = client.get(
        "/api/assess",
        params={
            "address": "테스트주소",
            "collateral_value": "500000000",
            "region_code": "47111",
            "query_date": "2022-09-06",
        },
    )

    assert res.status_code == 200
    assert captured["mode"] == "historical"
    assert captured["historical_start"].isoformat() == "2022-09-06T00:00:00+09:00"
    assert captured["historical_end"].isoformat() == "2022-09-07T00:00:00+09:00"


def test_portfolio_map_exposes_ltv_insurance_eal_and_derives_city_from_address(monkeypatch):
    """2026-08-25 — /api/portfolio-list와 대구를 이루는 테스트. 이 엔드포인트는 내부
    리스크 개관용 포트폴리오 지도 화면 전용이라 ltv·eal_before·insurance_covered를
    일부러 노출한다(위 test_portfolio_list_...와 정반대). 'c'(지역 라벨)는 region_code가
    아니라 주소 문자열로 판정해야 한다 — region_code=None(SHP 커버리지 밖)이어도 주소가
    대구/포항/거제면 '기타'가 아니라 그 도시로 분류돼야 한다(DEV_LOG.md 2026-08-18 참조)."""
    from climate_risk.portfolio.schema import PortfolioRecord

    fake_records = [
        PortfolioRecord(
            collateral_id="COL-001",
            address="경상북도 포항시 남구 인덕로 27",
            collateral_type="아파트",
            balance=300000000.0,
            collateral_value=500000000.0,
            ltv=0.6,
            score_before=55.0,
            eal_before=1000.0,
            lat=35.98768,
            lon=129.39979,
            region_code="47111",
            insurance_covered=True,
        ),
        PortfolioRecord(
            collateral_id="COL-500",
            address="대구광역시 달서구 성서공단로 1",  # 커버리지 밖 공단지역 예시
            collateral_type="공장",
            balance=100000000.0,
            collateral_value=200000000.0,
            ltv=0.5,
            score_before=None,
            eal_before=None,
            lat=35.85,
            lon=128.45,
            region_code=None,  # SHP 커버리지 밖 — 그래도 주소는 명백히 대구
            insurance_covered=None,
        ),
    ]
    monkeypatch.setattr(webapp_app, "load_portfolio", lambda path: fake_records)

    res = client.get("/api/portfolio-map")

    assert res.status_code == 200
    body = res.json()
    assert body[0] == {
        "id": "COL-001",
        "a": "경상북도 포항시 남구 인덕로 27",
        "t": "아파트",
        "c": "포항",
        "lat": 35.98768,
        "lon": 129.39979,
        "ltv": 0.6,
        "sc": 55.0,
        "eal": 1000.0,
        "ins": True,
        "bal": 300000000.0,
        "val": 500000000.0,
    }
    assert body[1]["c"] == "대구"  # region_code=None이어도 주소 기반으로 정확히 분류됨
    assert body[1]["sc"] is None
    assert body[1]["eal"] is None


def test_portfolio_map_skips_records_without_lat_lon(monkeypatch):
    from climate_risk.portfolio.schema import PortfolioRecord

    fake_records = [
        PortfolioRecord(
            collateral_id="COL-999",
            address="대구광역시 남구 대봉로 1",
            collateral_type="아파트",
            balance=100000000.0,
            collateral_value=200000000.0,
            ltv=0.5,
            score_before=None,
            eal_before=None,
            lat=None,
            lon=None,
        )
    ]
    monkeypatch.setattr(webapp_app, "load_portfolio", lambda path: fake_records)

    res = client.get("/api/portfolio-map")

    assert res.status_code == 200
    assert res.json() == []


def test_portfolio_map_page_serves_html():
    res = client.get("/portfolio-map")

    assert res.status_code == 200
    assert res.headers["content-type"].startswith("text/html")
    assert "담보 포트폴리오 지도" in res.text
    assert "/api/portfolio-map" in res.text  # 라이브 데이터를 fetch하는지 확인
