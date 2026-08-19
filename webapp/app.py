"""데모용 웹 프론트엔드 백엔드 — HANDOVER.md·PROGRESS.md의 CLI 데모(`scripts/run_week4_demo.py`)를
그대로 감싸는 얇은 계층이다. 새 판정 로직은 만들지 않는다 — `graph/week4_demo.py::run_week4_demo`가
이미 하는 계산을 그대로 호출하고, `on_stage` 콜백으로 실제 진행 단계를 SSE로 중계할 뿐이다.

진행상황 메시지는 타이머로 흉내낸 가짜 시퀀스가 아니라 백엔드가 실제로 그 단계를 처리
중일 때만 전송된다(`graph/week3_demo.py::_notify` 참조) — 이 프로젝트의 "정직하게 실측
근거만 쓴다"는 정체성을 데모 UI에도 그대로 반영한다.
"""

from __future__ import annotations

import json
import queue
import sys
import threading
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fastapi import FastAPI, Query  # noqa: E402
from fastapi.responses import StreamingResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402

from climate_risk.agents.flood_agent import run_flood_agent  # noqa: E402
from climate_risk.config import (  # noqa: E402
    DAEGU_SUSEONG_2026_TIMELINE_PATH,
    DEFAULT_EAL_ITERATIONS,
    DEFAULT_EAL_SEED,
    HINNAMNO_TIMELINE_PATH,
    PORTFOLIO_DATA_PATH,
    REGION_CODE_TO_KMA_STN_ID,
    SHP_FILENAME_TO_REGION_CODE,
)
from climate_risk.geocoding.juso import JusoSearchError, search_road_addresses  # noqa: E402
from climate_risk.geocoding.vworld import geocode_road_address  # noqa: E402
from climate_risk.graph.week4_demo import run_week4_demo  # noqa: E402

app = FastAPI(title="담보 기후리스크 여신심사 AI — 데모")

_STATIC_DIR = Path(__file__).resolve().parent / "static"


@app.middleware("http")
async def _no_cache_static(request, call_next):
    """정적 파일(index.html/app.js/style.css)에 브라우저 캐시를 걸지 않는다 — 데모 화면을
    반복 수정하며 확인하는 로컬 개발 서버라, 캐시 때문에 "고쳤는데 그대로다"가 나오면 안 된다."""
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    return response

# 프론트 드롭다운용 프리셋 — 전부 이미 실측 검증된 조합(PROGRESS.md "Week4 이후 보강" 참조).
_REGION_PRESETS: list[dict[str, Any]] = [
    {
        "id": "pohang-hinnamno",
        "label": "포항 남구 — 태풍 힌남노(2022) 리플레이",
        "region_code": "47111",
        "mode": "replay",
        "timeline_path": str(HINNAMNO_TIMELINE_PATH),
        "sample_address": "경상북도 포항시 남구 인덕로 27",
    },
    {
        "id": "daegu-suseong-replay",
        "label": "대구 수성구 — 2026-07 집중호우 리플레이",
        "region_code": "27260",
        "mode": "replay",
        "timeline_path": str(DAEGU_SUSEONG_2026_TIMELINE_PATH),
        "sample_address": "대구광역시 수성구 지산동",
    },
    {
        "id": "daegu-suseong-live",
        "label": "대구 수성구 — 기상청 라이브 특보",
        "region_code": "27260",
        "mode": "live",
        "timeline_path": None,
        "sample_address": "대구광역시 수성구 지산동",
    },
]


@app.get("/api/regions")
def get_regions() -> list[dict[str, Any]]:
    return _REGION_PRESETS


# region_code -> 큐레이션된 리플레이 프리셋(있으면). "지역 프리셋" 드롭다운이 미리 정해준
# region_code를 프론트가 신뢰하던 것을, 2026-08-18 설계 논의(DEV_LOG.md 참조) 이후로는
# 입력 주소를 지오코딩해 실제로 감지한 region_code 기준으로 뒤집었다 — _REGION_PRESETS를
# 새 진실의 원천으로 다시 만들지 않고 그대로 재사용(단일 소스 유지).
_CURATED_REPLAY_BY_REGION: dict[str, dict[str, Any]] = {
    p["region_code"]: {"mode": p["mode"], "timeline_path": p["timeline_path"], "label": p["label"]}
    for p in _REGION_PRESETS
    if p["mode"] == "replay"
}


@app.get("/api/resolve-region")
def resolve_region(address: str) -> dict[str, Any]:
    """주소 입력창에 실제로 입력된 주소를 지오코딩→홍수 에이전트로 region_code를
    감지한다 — "지역 프리셋"에 종속됐던 region_code를 실제 주소 기준으로 뒤집어,
    담보 평가 결과와 포트폴리오 알림 섹션이 항상 같은 지역을 가리키게 한다
    (DEV_LOG.md 2026-08-18 "불일치 버그" 참조). run_flood_agent는 이미 로딩된 SHP
    캐시를 재사용하므로(query_caching) 이 호출이 추가로 콜드로딩을 유발하지 않는다."""
    geocoded = geocode_road_address(address)
    if geocoded is None:
        return {"resolved": False, "reason": "주소 인식 실패 — 주소를 다시 확인해 주세요"}

    flood = run_flood_agent(geocoded.lat, geocoded.lon)
    region_code = SHP_FILENAME_TO_REGION_CODE.get(flood.flood.source_shp_file or "")

    return {
        "resolved": True,
        "matched_address": geocoded.refined_text,
        "lat": geocoded.lat,
        "lon": geocoded.lon,
        "coverage": flood.flood.coverage,
        "region_code": region_code,
        "region_name": flood.flood.region_name,
        # 라이브 모드는 6개 커버리지 구 전부 가능(REGION_CODE_TO_KMA_STN_ID가 이미
        # 6개 다 매핑돼 있음, DEV_LOG.md 2026-08-18 참조) — 리플레이만 2곳으로 제한적.
        "live_supported": region_code in REGION_CODE_TO_KMA_STN_ID,
        "curated_replay": _CURATED_REPLAY_BY_REGION.get(region_code or ""),
    }


@app.get("/api/address-search")
def address_search(keyword: str) -> list[dict[str, Any]]:
    """도로명주소 자동완성 — JUSO API 프록시(대구·포항 커버리지 지역만 필터링).
    JUSO 키 만료 등으로 실패해도 자동완성은 부가기능이라 페이지 자체를 죽이지 않고
    빈 목록으로 조용히 degrade한다."""
    try:
        suggestions = search_road_addresses(keyword)
    except JusoSearchError:
        return []
    return [{"road_address": s.road_address, "building_name": s.building_name} for s in suggestions]


def _sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"


def _run_in_background(
    address: str,
    collateral_value: float,
    region_code: str,
    mode: str,
    timeline_path: Path | None,
    seed: int,
    n_iterations: int,
    target_floor: dict[str, Any] | None,
    events: "queue.Queue[str]",
) -> None:
    def on_stage(stage: str, message: str) -> None:
        events.put(_sse("progress", {"stage": stage, "message": message}))

    kwargs: dict[str, Any] = {
        "address": address,
        "collateral_value": collateral_value,
        "region_code": region_code,
        "portfolio_path": PORTFOLIO_DATA_PATH,
        "mode": mode,
        "seed": seed,
        "n_iterations": n_iterations,
        "on_stage": on_stage,
        "target_floor": target_floor,
    }
    if timeline_path is not None:
        kwargs["timeline_path"] = timeline_path

    try:
        result = run_week4_demo(**kwargs)
    except Exception as exc:  # noqa: BLE001 — 데모 화면에 원인을 그대로 보여주기 위해 넓게 잡는다
        result = {"error": f"평가 중 오류가 발생했어요: {exc}"}

    events.put(_sse("result", result))
    events.put("__STREAM_DONE__")


@app.get("/api/assess")
def assess(
    address: str,
    collateral_value: float,
    region_code: str = "47111",
    mode: str = "replay",
    timeline_path: str | None = Query(default=None),
    seed: int = DEFAULT_EAL_SEED,
    n_iterations: int = DEFAULT_EAL_ITERATIONS,
    # HANDOVER §⑧ 층별 리스크 차등화(선택 입력) — 둘 다 미지정이면 target_floor=None으로
    # 기존 건물 전체 스코어링 경로와 100% 동일하게 동작한다.
    floor_type: str | None = Query(default=None),
    floor_no: int | None = Query(default=None),
) -> StreamingResponse:
    events: "queue.Queue[str]" = queue.Queue()
    resolved_timeline = Path(timeline_path) if timeline_path else None
    target_floor = {"floor_type": floor_type, "floor_no": floor_no} if floor_type or floor_no is not None else None

    thread = threading.Thread(
        target=_run_in_background,
        args=(
            address,
            collateral_value,
            region_code,
            mode,
            resolved_timeline,
            seed,
            n_iterations,
            target_floor,
            events,
        ),
        daemon=True,
    )
    thread.start()

    def stream():
        while True:
            chunk = events.get()
            if chunk == "__STREAM_DONE__":
                break
            yield chunk

    return StreamingResponse(stream(), media_type="text/event-stream")


# API 라우트를 전부 등록한 뒤 마지막에 정적 파일을 "/"에 마운트한다 — 등록 순서상
# "/api/..."가 이 catch-all보다 먼저 매치되므로 충돌하지 않는다.
app.mount("/", StaticFiles(directory=str(_STATIC_DIR), html=True), name="static")
