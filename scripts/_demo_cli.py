"""Week3/Week4 데모 CLI 공통 로직 — argparse/배너/JSON 출력이 두 스크립트에서 완전히
동일해 복붙해두면 한쪽만 고치고 다른 쪽을 잊는 드리프트가 생긴다(플래그 추가·배너
문구 변경 등)."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from climate_risk.config import DEFAULT_EAL_ITERATIONS, DEFAULT_EAL_SEED, HINNAMNO_TIMELINE_PATH

_KST = timezone(timedelta(hours=9))


def _parse_kst_date(date_str: str, *, end_of_day: bool = False) -> datetime:
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    if end_of_day:
        dt = dt.replace(hour=23, minute=59, second=59)
    return dt.replace(tzinfo=_KST)

_LOADING_BANNER = (
    "침수위험 SHP 최초 로딩 중 — 프로세스 첫 호출에서 약 75초 소요됩니다. "
    "메모 에이전트는 claude -p를 호출하므로 추가로 5~10초가 걸립니다."
)


def run_demo_cli(run_fn: Callable[..., dict[str, Any]], description: str) -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--address", required=True, help="담보 도로명주소")
    parser.add_argument("--collateral-value", required=True, type=float, help="담보가액(원)")
    parser.add_argument("--region-code", default="47111", help="특보 대상 지역코드(기본: 포항시 남구)")
    parser.add_argument(
        "--mode", choices=["replay", "live", "historical"], default="replay",
        help=(
            "특보 조회 방식 — replay(큐레이션 JSON 재생, 기본)·live(기상청 실시간 API)·"
            "historical(기상청 API허브 과거 특보 이력, --historical-start/--historical-end 필요)"
        ),
    )
    parser.add_argument(
        "--timeline-path", type=Path, default=HINNAMNO_TIMELINE_PATH,
        help="mode=replay일 때 재생할 큐레이션 타임라인 JSON 경로(기본: 힌남노 2022 포항)",
    )
    parser.add_argument(
        "--historical-start", default=None,
        help="mode=historical일 때 조회 시작일(YYYY-MM-DD, KST 00:00 기준)",
    )
    parser.add_argument(
        "--historical-end", default=None,
        help="mode=historical일 때 조회 종료일(YYYY-MM-DD, KST 23:59:59 기준)",
    )
    parser.add_argument("--seed", type=int, default=DEFAULT_EAL_SEED, help="몬테카를로 EAL 시드")
    parser.add_argument(
        "--n-iterations", type=int, default=DEFAULT_EAL_ITERATIONS, help="몬테카를로 반복 횟수"
    )
    parser.add_argument(
        "--floor-type", choices=["지상", "지하"], default=None,
        help="HANDOVER §⑧ 층별 리스크 차등화(선택) — 미입력 시 건물 전체 스코어링으로 폴백",
    )
    parser.add_argument(
        "--floor-no", type=int, default=None,
        help="담보 층수(지상 1층=바닥 기준). --floor-type과 함께 지정해야 반영됨",
    )
    args = parser.parse_args()

    if args.mode == "historical" and (not args.historical_start or not args.historical_end):
        parser.error("--mode historical에는 --historical-start와 --historical-end가 모두 필요합니다")

    print(_LOADING_BANNER, file=sys.stderr)

    target_floor = None
    if args.floor_type is not None or args.floor_no is not None:
        target_floor = {"floor_type": args.floor_type, "floor_no": args.floor_no}

    historical_start = _parse_kst_date(args.historical_start) if args.historical_start else None
    historical_end = _parse_kst_date(args.historical_end, end_of_day=True) if args.historical_end else None

    result = run_fn(
        address=args.address,
        collateral_value=args.collateral_value,
        region_code=args.region_code,
        mode=args.mode,
        timeline_path=args.timeline_path,
        seed=args.seed,
        n_iterations=args.n_iterations,
        target_floor=target_floor,
        historical_start=historical_start,
        historical_end=historical_end,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
