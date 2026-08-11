"""지역필터링 재계산 — HANDOVER.md §4.1 "포트폴리오에서 해당 지역 코드에 매칭되는
담보만 추출(전체가 아니라 대상 지역 서브셋)"의 실체. 미지오코딩 레코드는 조용히
누락시키지 않고 별도 카운트로 가시화한다."""

from __future__ import annotations

from dataclasses import dataclass

from climate_risk.portfolio.schema import PortfolioRecord


@dataclass(frozen=True)
class FilterResult:
    matched: list[PortfolioRecord]
    # 지오코딩 실패(FAILED)와 "지오코딩은 성공했으나 6개 SHP 커버리지 밖"인 레코드를
    # 함께 센다 — 둘 다 region_code=None으로 귀결되고, 둘 다 "이 지역필터 대상이 아님"을
    # 조용히 넘기지 않고 가시화해야 한다는 점에서 동일하게 취급한다.
    skipped_ungeocoded_count: int
    # region_code는 있으나 이번 특보 대상 지역과 다른 레코드 — 포트폴리오가 여러 지역에
    # 걸쳐 있으므로(냉천 1개+신천 5개 구) 이 버킷이 없으면 matched+skipped가 total과
    # 어긋난다. matched+skipped_ungeocoded+other_region == len(records)가 항상 성립한다.
    other_region_count: int


def filter_by_region(records: list[PortfolioRecord], region_code: str) -> FilterResult:
    matched: list[PortfolioRecord] = []
    skipped = 0
    other_region = 0
    for record in records:
        if record.region_code is None:
            skipped += 1
        elif record.region_code == region_code:
            matched.append(record)
        else:
            other_region += 1
    return FilterResult(
        matched=matched, skipped_ungeocoded_count=skipped, other_region_count=other_region
    )
