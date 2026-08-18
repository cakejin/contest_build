"""파이프라인 엔트리포인트 — 주소 1건 → EAL 분포+tier+vulnerability_score JSON.

HANDOVER.md Week2 Done 기준의 실물: "주소 1건 → EAL 분포(mean/p50/p95/p99) + tier +
vulnerability_score가 JSON으로 출력"을 실제로 호출 가능한 함수 하나로 노출한다.
"""

from __future__ import annotations

import dataclasses
from typing import Any

from climate_risk.config import DEFAULT_EAL_ITERATIONS, DEFAULT_EAL_SEED
from climate_risk.geocoding.vworld import geocode_road_address
from climate_risk.graph.pipeline import build_graph


def run_pipeline(
    address: str,
    collateral_value: float,
    seed: int = DEFAULT_EAL_SEED,
    n_iterations: int = DEFAULT_EAL_ITERATIONS,
    target_floor: dict | None = None,
) -> dict[str, Any]:
    geocoded = geocode_road_address(address)
    if geocoded is None:
        # "좌표 없이는 어떤 에이전트도 실행하지 않음" — 그래프 자체를 실행하지 않는다.
        return {"error": "주소 인식 실패 — 주소 수정 요청", "address": address}

    graph = build_graph()
    final_state = graph.invoke(
        {
            "address": address,
            "collateral_value": collateral_value,
            "seed": seed,
            "n_iterations": n_iterations,
            "target_floor": target_floor,
            "geocoded": geocoded,
        }
    )

    return {
        "address": address,
        "geocoded": dataclasses.asdict(geocoded),
        "flood": dataclasses.asdict(final_state["flood"]),
        "building": dataclasses.asdict(final_state["building"]),
        "scenario": dataclasses.asdict(final_state["scenario"]),
    }
