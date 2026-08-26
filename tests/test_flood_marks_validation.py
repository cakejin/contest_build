"""safemap 실측 침수흔적(A2SM_FLUDMARKS_WI) 골든셋 파이프라인 검증 — DEV_LOG.md
2026-08-26 참조.

`tests/test_coverage_gate.py`(사람이 정답을 직접 확인한 12개 골든셋, 정답과 정확히
일치해야 통과)와 성격이 다르다 — 여기 80건은 우리가 통제하는 '정답'이 아니라 외부
실측 데이터라서, recall 수치 자체를 assert하지 않는다(evaluation/metrics.py::
flood_marks_recall_metric 참조). 여기서 고정하는 건 데이터 무결성·파이프라인이 예외
없이 도는지·스키마 형태뿐이다.

실측 확인(2026-08-26): 80건 중 75건 IN_SCOPE·5건 OUT_OF_SCOPE(전부 거제시 — 해안범람
3건 + 저지대침수 2건, 거제 SHP가 "지방하천 17개소"만 커버해 전체 해안선은 원래
커버리지 밖이라 정상). overall recall 34.7%(26/75) — 특히 "혼합"(하천+내수배제 동시,
힌남노 기록 대부분) 카테고리가 26.6%(17/64)로 낮게 나왔다. 이 자체가 시스템 결함
증거가 아니라 정직한 1차 측정치이며, 낮게 나온 이유(SHP가 커버하는 물리적 범위 자체가
좁아서 힌남노 때 도심 전역에 번진 실제 침수 범위를 다 못 담는 것으로 추정)는 아직
분석하지 않았다 — 별도 후속 조사 과제.
"""

from climate_risk.evaluation.flood_marks import (
    CAUSE_COASTAL,
    CAUSE_MIXED,
    CAUSE_RIVER,
    CAUSE_UNCLASSIFIED,
    CAUSE_URBAN_DRAINAGE,
    classify_flud_cause,
    load_flood_marks_validation_set,
)
from climate_risk.evaluation.metrics import flood_marks_recall_metric


def test_load_flood_marks_validation_set_has_80_records():
    validation_set = load_flood_marks_validation_set()
    assert len(validation_set.records) == 80


def test_load_flood_marks_validation_set_region_counts():
    validation_set = load_flood_marks_validation_set()
    by_region: dict[str, int] = {}
    for rec in validation_set.records:
        by_region[rec.region_name] = by_region.get(rec.region_name, 0) + 1
    assert by_region == {
        "포항시 남구": 63,
        "거제시": 11,
        "대구광역시 수성구": 6,
    }


def test_classify_flud_cause_mixed_when_both_river_and_urban_keywords():
    assert classify_flud_cause("하천 수위 상승으로 인한 역류 및 내수배제 불량") == CAUSE_MIXED


def test_classify_flud_cause_river_only():
    assert classify_flud_cause("하천 유량 증가로 인한 월류") == CAUSE_RIVER


def test_classify_flud_cause_urban_only():
    assert classify_flud_cause("내수_방재시설 용량부족") == CAUSE_URBAN_DRAINAGE


def test_classify_flud_cause_coastal_when_no_river_or_urban_keyword():
    assert classify_flud_cause("태풍으로 인한 월파") == CAUSE_COASTAL


def test_classify_flud_cause_unclassified_when_no_keyword_matches():
    """원인을 지어내지 않는다는 원칙 확인 — "집중호우"만으로는 메커니즘을 알 수 없다."""
    assert classify_flud_cause("국지성 집중호우") == CAUSE_UNCLASSIFIED
    assert classify_flud_cause("저지대 침수") == CAUSE_UNCLASSIFIED


def test_flood_marks_recall_metric_runs_and_reports_well_formed_structure():
    metric = flood_marks_recall_metric()

    assert metric["overall"]["total"] == 80
    assert metric["overall"]["in_scope"] + metric["overall"]["out_of_scope"] == 80
    assert 0.0 <= metric["overall"]["recall"] <= 1.0

    for region_metric in metric["by_region"].values():
        assert region_metric["hit"] <= region_metric["in_scope"] <= region_metric["total"]
    for cause_metric in metric["by_cause_category"].values():
        assert cause_metric["hit"] <= cause_metric["in_scope"] <= cause_metric["total"]


def test_flood_marks_recall_metric_out_of_scope_is_confined_to_geoje():
    """실측 확인(2026-08-26): OUT_OF_SCOPE 5건 전부 거제시(해안범람·저지대침수) —
    포항 남구·대구 수성구는 74건 전부 IN_SCOPE. 이 지역 분포가 흔들리면(예: 포항 남구에서
    OUT_OF_SCOPE가 새로 나타나면) SHP 로딩·커버리지 게이트 쪽 회귀일 가능성이 높다."""
    metric = flood_marks_recall_metric()
    ooc_regions = {r["region"] for r in metric["out_of_scope_records"]}
    assert ooc_regions == {"거제시"}
    assert metric["by_region"]["포항시 남구"]["out_of_scope"] == 0
    assert metric["by_region"]["대구광역시 수성구"]["out_of_scope"] == 0
