"""2026-09-08 결과 화면 ③단계에서 추가한 결정론 계산·표시용 값의 회귀 테스트.

- 적응 투자(차수판) 전후 EAL: 높이 0은 기존 경로와 완전 동일, 높이가 커질수록 EAL 단조 감소,
  같은 시드면 재현.
- 침수심 등급 요약(depth_class_summary): SEG_CODE → 범위 라벨, tier가 '내부'가 아니면 reliable=False.
- 실측 침수흔적 근접 요약(summarize_flood_marks_near): 임시 큐레이션 파일로 건수·최근접 거리 검증,
  파일이 없으면 None.
- 단계별 소요시간(_stage_durations): 단계 간 차이·총합·특보→알림 지연.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from climate_risk.agents.building_agent import BuildingAgentOutput
from climate_risk.agents.flood_agent import FloodAgentOutput
from climate_risk.agents.scenario_agent import run_scenario_agent
from climate_risk.config import ADAPTATION_BARRIER_HEIGHTS_M
from climate_risk.evaluation.flood_marks import summarize_flood_marks_near
from climate_risk.gis.query import FloodRiskResult
from climate_risk.scenario.eal import run_monte_carlo_eal
from climate_risk.scenario.floor_exposure import depth_class_summary

_WEBAPP_DIR = Path(__file__).resolve().parents[1] / "webapp"
if str(_WEBAPP_DIR) not in sys.path:
    sys.path.insert(0, str(_WEBAPP_DIR))
from app import _stage_durations  # noqa: E402


def _inside_flood() -> FloodRiskResult:
    return FloodRiskResult(
        coverage="IN_SCOPE", in_polygon=True, tier="내부", distance_to_polygon_m=0.0, freq_label="MAX",
        river_name="냉천", region_name="포항시 남구", source_shp_file="x.shp", license="l",
        methodology_disclaimer="t", uncertain=None, seg_code="N332",
    )


def test_barrier_zero_is_byte_identical_to_baseline():
    f = _inside_flood()
    a = run_monte_carlo_eal(f, 55.0, 5e8, seed=42, n_iterations=5000)
    b = run_monte_carlo_eal(f, 55.0, 5e8, seed=42, n_iterations=5000, barrier_height_m=0.0)
    assert a == b


def test_barrier_reduces_eal_monotonically_and_is_reproducible():
    f = _inside_flood()
    base = run_monte_carlo_eal(f, 55.0, 5e8, seed=42, n_iterations=5000).EAL_mean
    prev = base
    for h in ADAPTATION_BARRIER_HEIGHTS_M:
        after = run_monte_carlo_eal(f, 55.0, 5e8, seed=42, n_iterations=5000, barrier_height_m=h).EAL_mean
        again = run_monte_carlo_eal(f, 55.0, 5e8, seed=42, n_iterations=5000, barrier_height_m=h).EAL_mean
        assert after == again
        assert after <= prev
        prev = after
    assert prev < base


def test_scenario_agent_attaches_adaptation_only_when_eal_exists():
    flood = FloodAgentOutput(flood=_inside_flood(), source_id="flood:x", field_sources={})
    building = BuildingAgentOutput(
        vulnerability_score=55.0, contributing_factors=[], source="t", source_id="building:t",
        missing_fields=[], status="OK", note=None,
    )
    out = run_scenario_agent(flood, building, 5e8, seed=42, n_iterations=3000)
    assert out.adaptation is not None
    assert [s.barrier_height_m for s in out.adaptation.scenarios] == list(ADAPTATION_BARRIER_HEIGHTS_M)
    assert all(s.change_pct <= 0.0 for s in out.adaptation.scenarios)
    assert out.adaptation.baseline_EAL_mean == out.eal.EAL_mean

    oos = FloodAgentOutput(
        flood=FloodRiskResult(
            coverage="OUT_OF_SCOPE", in_polygon=None, tier=None, distance_to_polygon_m=None, freq_label=None,
            river_name=None, region_name=None, source_shp_file=None, license=None,
            methodology_disclaimer="t", uncertain=None,
        ),
        source_id="flood:oos", field_sources={},
    )
    assert run_scenario_agent(oos, building, 5e8, seed=42, n_iterations=3000).adaptation is None


def test_depth_class_summary_labels_and_reliability():
    s = depth_class_summary("N332", "내부")
    assert s["label"] == "1.0~2.0m" and s["rank"] == 3 and s["reliable"] is True
    assert depth_class_summary("N330", "내부")["label"] == "0.5m 미만"
    assert depth_class_summary("N334", "근접")["reliable"] is False
    assert depth_class_summary(None, "내부") is None
    assert depth_class_summary("XXX", "내부") is None


def test_flood_marks_nearby_counts_and_missing_file(tmp_path: Path):
    path = tmp_path / "marks.json"
    lat, lon = 35.9876, 129.3972
    # 약 100m 동쪽(경도 +0.0011), 약 1.1km 북쪽(위도 +0.01), 약 5.5km 북쪽(위도 +0.05)
    path.write_text(
        json.dumps(
            {
                "dataset": "test", "fetched_at": "2026-09-08", "license_note": "재배포 금지",
                "cause_texts": ["하천범람", "내수배제"], "region_names": {"47111": "포항시 남구"},
                "records": [
                    {"sgg_cd": "47111", "flud_year": "2022", "cause_idx": 0, "avg_fldwtl_cm": 9, "lat": lat, "lon": lon + 0.0011},
                    {"sgg_cd": "47111", "flud_year": "2020", "cause_idx": 1, "avg_fldwtl_cm": 5, "lat": lat + 0.01, "lon": lon},
                    {"sgg_cd": "47111", "flud_year": "2019", "cause_idx": 0, "avg_fldwtl_cm": 3, "lat": lat + 0.05, "lon": lon},
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    s = summarize_flood_marks_near(lat, lon, path=path, radii_m=(500.0, 2000.0))
    assert s is not None
    assert 80 < s.nearest_m < 130 and s.nearest_year == "2022"
    assert s.counts_by_radius_m == {"500": 1, "2000": 2}
    assert s.total_in_dataset == 3 and s.license_note == "재배포 금지"
    assert summarize_flood_marks_near(lat, lon, path=tmp_path / "missing.json") is None


def test_stage_durations_shape():
    starts = [("advisory", 0.0), ("geocode", 0.8), ("flood", 1.0), ("building", 1.2), ("scenario", 6.8),
              ("portfolio", 6.8), ("memo", 15.2), ("done", 95.4)]
    t = _stage_durations(starts)
    assert [s["stage"] for s in t["stages"]] == [s for s, _ in starts]
    assert t["stages"][0]["seconds"] == 0.8 and t["stages"][-1]["seconds"] == 0.0
    assert t["total_seconds"] == 95.4
    assert t["alert_latency_seconds"] == 15.2
    assert _stage_durations([]) == {"stages": [], "total_seconds": 0.0, "alert_latency_seconds": None}
