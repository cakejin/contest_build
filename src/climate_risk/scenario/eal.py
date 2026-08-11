"""시나리오 에이전트 코어 — HANDOVER.md §4.2 2.4 몬테카를로 EAL.

**알려진 데이터 공백(구현 착수 전 확인, PROGRESS.md Week1 "발견한 이슈"와 같은 성격)**:
HANDOVER는 "기상청 30년 확률강우량 통계 기반" 강우빈도-침수심 분포를 전제했으나,
실제로 그 통계 원자료는 이 리포지토리에도 contest_research 문서 어디에도 다운로드된 적이
없다(수치 자체가 존재하지 않음). 이 모듈은 그 자리를 freq_label/tier 기반 파라메트릭
근사로 메운다 — 문헌 근거 없는 잠정치임을 methodology_note로 항상 명시한다
(gis/query.py의 METHODOLOGY_DISCLAIMER와 동일한 정직성 패턴).

재현성 규칙(절대 축소 금지 항목 — PROGRESS.md Week2 "절대 축소 금지"): 이 모듈은
전역 np.random.* 를 절대 호출하지 않는다. 오직 호출자가 넘긴 seed로 만든 단일
np.random.default_rng(seed) 인스턴스에서, 고정된 순서로만 난수를 뽑는다. 이 순서가
바뀌면 과거 seed의 재현값이 깨지므로 이 함수 내부 rng 호출 순서를 바꿀 때는 주의할 것.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from climate_risk.config import DEFAULT_EAL_ITERATIONS, DEFAULT_EAL_SEED
from climate_risk.gis.query import FloodRiskResult

# freq_label -> 연간초과확률(AEP) 근사. "500"=500년빈도 지도이므로 1/500.
# "MAX"(기왕최대)는 특정 재현주기가 아니라 실측 최대 이력 기반이라, 500년빈도보다
# 보수적으로(더 자주 발생 가능하다고) 가정해 1/200을 부여 — 근거 문헌 없는 잠정치.
AEP_BY_FREQ_LABEL: dict[str, float] = {"500": 1.0 / 500.0, "MAX": 1.0 / 200.0}
AEP_DEFAULT = 1.0 / 500.0

# tier -> (사상 발생 시 이 지점이 실제로 침수될 조건부 확률배율, 조건부 침수심 삼각분포[m]).
# "내부"는 폴리곤 안이므로 배율 1.0. "근접"/"원거리"는 거리가 멀수록 실제 침수 확률·심도가
# 낮아진다고 가정 — 문헌 근거 없는 잠정치(구조는 화이트박스로 100% 역추적 가능).
TIER_PARAMS: dict[str, tuple[float, tuple[float, float, float]]] = {
    "내부": (1.00, (0.10, 0.50, 2.00)),
    "근접": (0.30, (0.05, 0.20, 0.80)),
    "원거리": (0.05, (0.02, 0.10, 0.40)),
}

# 손상함수: loss_ratio = 1 - exp(-K * depth_m) — 포화형(깊이 증가할수록 한계손상 체감).
# 0.3m→30%, 1.0m→70%, 2.0m→91%. 표준 depth-damage curve의 일반형 근사, 잠정치.
DEPTH_DAMAGE_K = 1.2

# vulnerability_score(0~100)를 손상률 배율로 변환. 0점이어도 침수 시 손상 0은 비현실적이라
# 최소 40%는 적용하고, 100점이면 손상함수 그대로(1.0배) 적용.
VULN_SCALE_FLOOR = 0.4
VULN_SCALE_CEIL = 1.0

METHODOLOGY_NOTE = (
    "강우빈도-침수심 분포는 기상청 30년 확률강우량 통계를 미확보한 상태의 초기 "
    "파라메트릭 가정입니다(freq_label→연간초과확률, tier→조건부 침수심 분포). "
    "실측 통계 확보 시 캘리브레이션이 필요한 잠정치입니다."
)

STATUS_OK = "OK"
STATUS_INSUFFICIENT_INPUT = "INSUFFICIENT_INPUT"

INSUFFICIENT_INPUT_REASON = "입력 데이터 불충분"


@dataclass(frozen=True)
class HistogramBin:
    bin_start: float
    bin_end: float
    count: int


@dataclass(frozen=True)
class EALResult:
    EAL_mean: float | None
    EAL_p50: float | None
    EAL_p95: float | None
    EAL_p99: float | None
    n_iterations: int
    seed: int
    distribution_histogram_bins: list[HistogramBin] | None
    methodology_note: str
    status: str  # "OK" | "INSUFFICIENT_INPUT"
    reason: str | None


def _insufficient(n_iterations: int, seed: int) -> EALResult:
    return EALResult(
        EAL_mean=None,
        EAL_p50=None,
        EAL_p95=None,
        EAL_p99=None,
        n_iterations=n_iterations,
        seed=seed,
        distribution_histogram_bins=None,
        methodology_note=METHODOLOGY_NOTE,
        status=STATUS_INSUFFICIENT_INPUT,
        reason=INSUFFICIENT_INPUT_REASON,
    )


def run_monte_carlo_eal(
    flood: FloodRiskResult,
    vulnerability_score: float | None,
    collateral_value: float,
    seed: int = DEFAULT_EAL_SEED,
    n_iterations: int = DEFAULT_EAL_ITERATIONS,
) -> EALResult:
    """입력 3종(침수 판정·취약도·담보가액) 중 하나라도 불충분하면 시뮬레이션 자체를
    실행하지 않고 EAL=None+사유를 명시 반환한다 — 허수 EAL 원천 차단
    (HANDOVER.md §4.2 2.4 "실패 시 폴백" 그대로).
    """
    if flood.coverage != "IN_SCOPE" or vulnerability_score is None:
        return _insufficient(n_iterations, seed)

    aep = AEP_BY_FREQ_LABEL.get(flood.freq_label, AEP_DEFAULT)
    multiplier, (depth_min, depth_mode, depth_max) = TIER_PARAMS[flood.tier]
    p_event = aep * multiplier

    rng = np.random.default_rng(seed)
    event_occurs = rng.random(n_iterations) < p_event
    depths = np.where(
        event_occurs,
        rng.triangular(depth_min, depth_mode, depth_max, n_iterations),
        0.0,
    )
    loss_ratio = 1.0 - np.exp(-DEPTH_DAMAGE_K * depths)
    vuln_scale = VULN_SCALE_FLOOR + (VULN_SCALE_CEIL - VULN_SCALE_FLOOR) * (vulnerability_score / 100.0)
    financial_loss = loss_ratio * vuln_scale * collateral_value

    counts, edges = np.histogram(financial_loss, bins=20)
    bins = [
        HistogramBin(bin_start=float(edges[i]), bin_end=float(edges[i + 1]), count=int(counts[i]))
        for i in range(len(counts))
    ]

    return EALResult(
        EAL_mean=float(financial_loss.mean()),
        EAL_p50=float(np.percentile(financial_loss, 50)),
        EAL_p95=float(np.percentile(financial_loss, 95)),
        EAL_p99=float(np.percentile(financial_loss, 99)),
        n_iterations=n_iterations,
        seed=seed,
        distribution_histogram_bins=bins,
        methodology_note=METHODOLOGY_NOTE,
        status=STATUS_OK,
        reason=None,
    )
