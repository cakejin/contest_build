"""담보 포트폴리오 거제 확장 — 3단계(최종): 후보 실주소 -> 담보유형별 20건(부족분은 정직하게 보고).

`generate_portfolio.py`(대구·포항, 유형당 40건 목표)와 완전히 별도 스크립트다 — 기존
COL-001~316을 그대로 두고 그 뒤에 이어 붙이며, 거제 전용 후보 파일(`_geoje_address_
candidates.json`)만 소비한다. 유형당 목표를 20건으로 낮춘 이유: 사용자가 "가상 데이터를
만들어두고 싶다"고만 요청했지 대구·포항 수준(유형당 40건)의 전면 확장을 요청한 게
아니라 — 데모용으로 거제 지역이 실제로 동작함을 보여주기에 충분한 규모로 판단(2026-08-19).

각 신규 레코드는 실제 flood_agent+building_agent+scenario_agent를 라이브로 1회 실행해
score_before/eal_before를 산출한다(임의 숫자 아님) — 커버리지 밖이면 eal_before=None으로
정직하게 남긴다(schema.py 2026-08-18 변경 참조). 담보가액/LTV 방법론은 generate_portfolio.py와
동일(로그정규분포 담보가액 + 절단정규분포 LTV, 근거문헌 없는 초기 가정임을 동일하게 명시).
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
GEOJE_CANDIDATES_PATH = CURATED / "_geoje_address_candidates.json"
REPORT_PATH = CURATED / "_geoje_generation_report.json"

TARGET_PER_TYPE = 20

# generate_portfolio.py의 VALUE_PARAMS와 동일 — 근거문헌 없는 초기 가정을 그대로 재사용.
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
FIN_SEED = 2026  # generate_portfolio.py와 동일 시드(재현성) — 새 레코드 순번이 달라 실제 뽑히는 값은 다름
INSURANCE_COVERED_PROB = 0.70


def _load_geoje_candidates() -> dict[str, list[dict]]:
    return json.loads(GEOJE_CANDIDATES_PATH.read_text(encoding="utf-8"))


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
    used_addresses = {r.address for r in existing}

    pool = _load_geoje_candidates()
    for t in pool:
        seen: set[str] = set()
        deduped = []
        for c in pool[t]:
            road = c.get("road_address")
            if not road or road in used_addresses or road in seen:
                continue
            seen.add(road)
            deduped.append(c)
        pool[t] = deduped

    rng = np.random.default_rng(FIN_SEED)
    next_id_num = max((int(r.collateral_id.split("-")[1]) for r in existing), default=0) + 1
    new_records: list[PortfolioRecord] = []
    shortfall_report: dict[str, dict] = {}
    scope_counts: dict[str, dict] = {}

    for ctype in VALUE_PARAMS:
        candidates = pool.get(ctype, [])
        take = candidates[:TARGET_PER_TYPE]
        if len(take) < TARGET_PER_TYPE:
            shortfall_report[ctype] = {
                "target": TARGET_PER_TYPE, "found_candidates": len(candidates), "taken": len(take),
            }

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
        "shortfalls": shortfall_report,
        "scope_counts": scope_counts,
    }
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2), file=sys.stderr)


if __name__ == "__main__":
    main()
