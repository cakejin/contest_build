"""담보 포트폴리오 확장 — 3단계(최종): 후보 실주소 -> 담보유형별 40건(부족분은 정직하게 보고).

기존 COL-001~040(4종)은 그대로 보존하고, discover_collateral_addresses.py(POI)와
grid_scan_residential.py(격자 스캔)가 모은 실주소 후보 중에서 유형별 부족분만 뽑아
COL-041부터 이어 붙인다. 각 신규 레코드는 실제 flood_agent+building_agent+scenario_agent를
라이브로 1회 실행해 score_before/eal_before를 산출한다(임의 숫자 아님) — 커버리지 밖이면
eal_before=None으로 정직하게 남긴다(schema.py 2026-08-18 변경 참조).

대출잔액/담보가액/LTV는 contest_research/plans/data-security_...md §4와 동일한 방법론
(로그정규분포 담보가액 + 절단정규분포 LTV)을 유형별로 확장 적용한 것 — 문헌 근거 없는
초기 가정임을 동일하게 명시한다.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np  # noqa: E402

from climate_risk.agents.building_agent import run_building_agent  # noqa: E402
from climate_risk.agents.flood_agent import run_flood_agent  # noqa: E402
from climate_risk.agents.scenario_agent import run_scenario_agent  # noqa: E402
from climate_risk.config import (  # noqa: E402
    DEFAULT_EAL_ITERATIONS,
    DEFAULT_EAL_SEED,
    PORTFOLIO_DATA_PATH,
    SHP_FILENAME_TO_REGION_CODE,
)
from climate_risk.portfolio.loader import load_portfolio, save_portfolio  # noqa: E402
from climate_risk.portfolio.schema import PortfolioRecord  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
CURATED = REPO_ROOT / "data" / "climate-collateral-underwriting-ai" / "curated" / "portfolio"
POI_CANDIDATES_PATH = CURATED / "_address_candidates.json"
GRID_CANDIDATES_PATH = CURATED / "_grid_scan_candidates.json"
REPORT_PATH = CURATED / "_generation_report.json"

TARGET_PER_TYPE = 40

# collateral_type -> (담보가액 중앙값, 변동계수) — 근거문헌 없는 초기 가정
# (data-security_climate-collateral-underwriting-ai.md §4의 대출잔액 방법론을
# 담보가액 축으로 옮기고 8종으로 확장한 것, 동일하게 "그럴듯한 데모용 분포"일 뿐임을 명시)
VALUE_PARAMS: dict[str, tuple[float, float]] = {
    "아파트": (500_000_000, 0.4),
    "공동주택": (300_000_000, 0.4),
    "단독주택": (350_000_000, 0.4),
    "다가구주택": (450_000_000, 0.4),
    "근린생활시설": (600_000_000, 0.4),
    "업무시설": (800_000_000, 0.4),
    "창고": (700_000_000, 0.4),
    "공장": (1_200_000_000, 0.4),
}

LTV_MEAN, LTV_SD, LTV_MIN, LTV_MAX = 0.65, 0.10, 0.30, 0.90
FIN_SEED = 2026  # 담보가액/LTV 합성 난수 시드(EAL 몬테카를로 시드와 별개, 재현성용 고정)
# 보험가입여부(2026-08-18 추가, scripts/backfill_insurance_coverage.py와 동일 정신) — 근거문헌 없는 잠정치.
INSURANCE_COVERED_PROB = 0.70


def _load_poi_candidates() -> dict[str, list[dict]]:
    return json.loads(POI_CANDIDATES_PATH.read_text(encoding="utf-8"))


def _load_grid_candidates() -> list[dict]:
    if not GRID_CANDIDATES_PATH.exists():
        return []
    return json.loads(GRID_CANDIDATES_PATH.read_text(encoding="utf-8"))


def _classify_grid_hit(hit: dict) -> str | None:
    purps = hit["main_purps_cd_nm"]
    floors = hit.get("grnd_flr_cnt") or 0
    if "다가구주택" in purps or "다중주택" in purps:
        return "다가구주택"
    if "단독주택" in purps:
        return "단독주택"
    if "공동주택" in purps:
        return "아파트" if floors >= 10 else "공동주택"
    return None


def build_candidate_pool() -> dict[str, list[dict]]:
    pool: dict[str, list[dict]] = {t: [] for t in VALUE_PARAMS}

    poi = _load_poi_candidates()
    for t, items in poi.items():
        for it in items:
            if not it.get("road_address"):
                continue
            pool.setdefault(t, []).append(
                {
                    "road_address": it["road_address"],
                    "lat": it["lat"],
                    "lon": it["lon"],
                    "label": it.get("title") or it.get("label") or it["road_address"],
                }
            )

    for hit in _load_grid_candidates():
        t = _classify_grid_hit(hit)
        if t is None or not hit.get("road_address"):
            continue
        pool[t].append(
            {"road_address": hit["road_address"], "lat": hit["lat"], "lon": hit["lon"], "label": hit["road_address"]}
        )

    for t in pool:
        seen: set[str] = set()
        deduped = []
        for c in pool[t]:
            if c["road_address"] in seen:
                continue
            seen.add(c["road_address"])
            deduped.append(c)
        pool[t] = deduped

    return pool


def _sample_value_ltv_balance(rng: np.random.Generator, ctype: str) -> tuple[float, float, float]:
    median, cv = VALUE_PARAMS[ctype]
    sigma = float(np.sqrt(np.log(1 + cv**2)))
    mu = float(np.log(median))
    value = round(float(rng.lognormal(mu, sigma)), -5)
    ltv = round(float(np.clip(rng.normal(LTV_MEAN, LTV_SD), LTV_MIN, LTV_MAX)), 2)
    balance = round(value * ltv, -5)
    return value, ltv, balance


def _now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

    existing = load_portfolio(PORTFOLIO_DATA_PATH)
    existing_by_type: dict[str, list[PortfolioRecord]] = {}
    for r in existing:
        existing_by_type.setdefault(r.collateral_type, []).append(r)
    used_addresses = {r.address for r in existing}

    pool = build_candidate_pool()
    for t in pool:
        pool[t] = [c for c in pool[t] if c["road_address"] not in used_addresses]
    rng = np.random.default_rng(FIN_SEED)

    next_id_num = max((int(r.collateral_id.split("-")[1]) for r in existing), default=0) + 1
    new_records: list[PortfolioRecord] = []
    shortfall_report: dict[str, dict] = {}
    scope_counts: dict[str, dict] = {}

    for ctype in VALUE_PARAMS:
        have = len(existing_by_type.get(ctype, []))
        need = max(0, TARGET_PER_TYPE - have)
        candidates = pool.get(ctype, [])
        take = candidates[:need]
        if len(take) < need:
            shortfall_report[ctype] = {"target": TARGET_PER_TYPE, "already_had": have, "needed": need, "found": len(take)}

        in_scope_n = 0
        out_scope_n = 0
        for cand in take:
            collateral_id = f"COL-{next_id_num:03d}"
            next_id_num += 1
            lat, lon = cand["lat"], cand["lon"]

            value, ltv, balance = _sample_value_ltv_balance(rng, ctype)

            for attempt in range(2):
                try:
                    flood = run_flood_agent(lat, lon)
                    building = run_building_agent(lat=lat, lon=lon)
                    break
                except OSError:
                    time.sleep(1.0)
            else:
                flood = run_flood_agent(lat, lon)
                building = run_building_agent(lat=lat, lon=lon)

            scenario = run_scenario_agent(
                flood, building, collateral_value=value, seed=DEFAULT_EAL_SEED, n_iterations=DEFAULT_EAL_ITERATIONS
            )

            region_code = SHP_FILENAME_TO_REGION_CODE.get(flood.flood.source_shp_file or "")
            if flood.flood.coverage == "IN_SCOPE":
                in_scope_n += 1
            else:
                out_scope_n += 1

            new_records.append(
                PortfolioRecord(
                    collateral_id=collateral_id,
                    address=cand["road_address"],
                    collateral_type=ctype,
                    balance=balance,
                    collateral_value=value,
                    ltv=ltv,
                    score_before=building.vulnerability_score,
                    eal_before=scenario.eal.EAL_mean,
                    lat=lat,
                    lon=lon,
                    region_code=region_code,
                    geocode_confidence="OK",
                    geocoded_at=_now_iso(),
                    insurance_covered=bool(rng.random() < INSURANCE_COVERED_PROB),
                )
            )
            time.sleep(0.1)

        scope_counts[ctype] = {"generated": len(take), "in_scope": in_scope_n, "out_of_scope": out_scope_n}
        print(f"{ctype}: {len(take)}건 생성(IN_SCOPE {in_scope_n} / OUT_OF_SCOPE {out_scope_n})", file=sys.stderr)

    all_records = existing + new_records
    save_portfolio(all_records, PORTFOLIO_DATA_PATH)

    report = {
        "total_records": len(all_records),
        "new_records": len(new_records),
        "by_type_final_count": {
            t: len(existing_by_type.get(t, [])) + sum(1 for r in new_records if r.collateral_type == t)
            for t in VALUE_PARAMS
        },
        "shortfalls": shortfall_report,
        "scope_counts": scope_counts,
    }
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2), file=sys.stderr)


if __name__ == "__main__":
    main()
