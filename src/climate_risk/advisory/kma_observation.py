"""기상청 API허브 지상관측(강수량) 조회 — DEV_LOG.md 2026-09-03(계속5) 실호출 확인 결과를 코드화.

세 API(전부 `KMA_API_HUB_KEY`, API별 개별 활용신청 필요, EUC-KR 텍스트 응답, `#` 주석 행):
1. ASOS 시간자료 기간조회 `kma_sfctm3.php?tm1&tm2&stn` — 시간 강수 `RN`(4~10월 1시간, 11~3월은
   3시간 값이며 3·6·…·24시 외 결측), 일누적 `RN_DAY`. 결측 `-9`. 1904년부터. 최대 31일/호출(문서).
   `tm1==tm2`면 단일 시각 — 그래서 시점조회 API(kma_sfctm2)는 따로 쓰지 않는다.
2. AWS 시간통계 `awsh.php?var=RN&tm&stn` — `RN_HR1`·`RN_DAY`·`RN_60M_MAX`·`RN_15M_MAX`.
   **`tm1/tm2`는 무시되고 최근 30일이 돌아온다(실측)** — 과거는 `tm` 단일 시각 반복 조회만 가능.
   결측 `-99`. 지점이 그 시점에 없으면 본문에 "입력하신 지점번호가 없습니다".
3. AWS 일통계 `sfc_aws_day.php?obs=rn_day&tm1&tm2&stn` — `TM STN LON LAT HT VAL [지점명]`.
   `stn=0`이면 전국 714지점 + 위경도 → 관측소↔지역 매핑의 진실의 원천.

설계원칙1과 같은 정신으로 실패·결측을 조용히 0으로 바꾸지 않는다: 결측은 None, API 실패는
status로 반환. 이 모듈은 평가 하네스(evaluation/)와 향후 특보 에이전트 보강에서만 쓰며,
EAL·LTV·금리 계산 경로에는 연결하지 않는다(설계원칙2).
"""

from __future__ import annotations

import math
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from climate_risk.config import KMA_API_HUB_KEY

_KST = timezone(timedelta(hours=9))
_BASE = "https://apihub.kma.go.kr/api/typ01/url/"
ASOS_HOURLY_URL = _BASE + "kma_sfctm3.php"
AWS_HOURLY_STAT_URL = _BASE + "awsh.php"
AWS_DAILY_URL = _BASE + "sfc_aws_day.php"
OBSERVATION_SOURCE_URL = "https://apihub.kma.go.kr/"

STATUS_OK = "OK"
STATUS_ACTIVATION_REQUIRED = "ACTIVATION_REQUIRED"
STATUS_UPSTREAM_ERROR = "UPSTREAM_ERROR"
STATUS_NO_SUCH_STATION = "NO_SUCH_STATION"  # 그 시점에 존재하지 않는 지점(AWS는 개시일이 지점마다 다름)

_ASOS_MAX_DAYS_PER_CALL = 31
_NO_STATION_MARKER = "입력하신 지점번호가 없습니다"

# 우리 region_code → ASOS 지점(zone group당 1곳). 2026-09-03 sfc_aws_day 위경도로 골든 좌표와
# 대조해 확정(포항 138 12.3km, 대구 143 6.5km, 거제 294 9.3km).
REGION_CODE_TO_ASOS_STN: dict[str, str] = {
    "47111": "138",  # 포항
    "48310": "294",  # 거제
    "27200": "143", "27110": "143", "27260": "143", "27140": "143", "27230": "143",  # 대구
}
# 가장 가까운 AWS 지점(같은 대조). 995 오천은 2019·2022년 조회 시 "지점번호가 없습니다" —
# 과거 사건엔 결측일 수 있다(개시일 미확인).
REGION_CODE_TO_NEAREST_AWS_STN: dict[str, tuple[str, str, float]] = {
    "47111": ("995", "오천", 1.0),
    "48310": ("313", "양지암", 3.6),
    "27200": ("860", "신암", 5.8), "27110": ("860", "신암", 5.8), "27260": ("860", "신암", 5.8),
    "27140": ("860", "신암", 5.8), "27230": ("860", "신암", 5.8),
}


@dataclass(frozen=True)
class AsosHourly:
    tm: datetime  # KST
    stn: str
    rn_1h_mm: float | None  # RN(-9 → None). 11~3월엔 3시간값(3·6·…·24시만)
    rn_day_mm: float | None  # RN_DAY(해당 시각까지 일누적)


@dataclass(frozen=True)
class AwsHourlyStat:
    tm: datetime
    stn: str
    rn_hr1_mm: float | None
    rn_day_mm: float | None
    rn_60m_max_mm: float | None
    rn_15m_max_mm: float | None


@dataclass(frozen=True)
class AwsDaily:
    day: datetime  # KST 자정
    stn: str
    lon: float
    lat: float
    rn_day_mm: float | None
    name: str


@dataclass(frozen=True)
class ObservationResult:
    status: str
    rows: list  # AsosHourly | AwsHourlyStat | AwsDaily
    note: str


def _tm(dt: datetime) -> str:
    return dt.astimezone(_KST).strftime("%Y%m%d%H%M")


def _parse_tm(raw: str) -> datetime:
    return datetime.strptime(raw, "%Y%m%d%H%M").replace(tzinfo=_KST)


def _decode(raw: bytes) -> str:
    for enc in ("euc-kr", "utf-8"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1")


def _data_lines(text: str) -> list[str]:
    return [l for l in text.splitlines() if l.strip() and not l.lstrip().startswith("#")]


def _num(token: str, missing: tuple[str, ...]) -> float | None:
    try:
        v = float(token)
    except ValueError:
        return None
    return None if token in missing or v <= -9 else v


def _fetch_raw(url: str) -> bytes:
    """유일한 HTTP seam — 테스트는 이 함수만 monkeypatch한다(kma_historical과 같은 관례)."""
    with urllib.request.urlopen(url, timeout=60) as resp:
        return resp.read()


def _call(url: str) -> tuple[str, str]:
    try:
        return STATUS_OK, _decode(_fetch_raw(url))
    except urllib.error.HTTPError as exc:
        if exc.code == 403:
            return STATUS_ACTIVATION_REQUIRED, "활용신청이 승인되지 않았습니다 — apihub.kma.go.kr에서 해당 API 활용신청 후 재시도"
        return STATUS_UPSTREAM_ERROR, f"HTTP {exc.code}"
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return STATUS_UPSTREAM_ERROR, str(exc)


# --- 1. ASOS 시간자료 -------------------------------------------------------------


def parse_asos_hourly(text: str, stn: str) -> list[AsosHourly]:
    """`help=1` 문서 순서: 1 TM, 2 STN, …, 16 RN, 17 RN_DAY (공백 구분, 1-based)."""
    rows: list[AsosHourly] = []
    for line in _data_lines(text):
        p = line.split()
        if len(p) < 17 or not p[0].isdigit():
            continue
        rows.append(AsosHourly(tm=_parse_tm(p[0]), stn=p[1], rn_1h_mm=_num(p[15], ("-9", "-9.0")), rn_day_mm=_num(p[16], ("-9", "-9.0"))))
    return rows


def fetch_asos_hourly(stn: str, start: datetime, end: datetime) -> ObservationResult:
    """[start, end]를 31일 chunk로 나눠 순차 조회(문서상 호출당 최대 31일)."""
    rows: list[AsosHourly] = []
    cur = start
    while cur <= end:
        chunk_end = min(end, cur + timedelta(days=_ASOS_MAX_DAYS_PER_CALL - 1))
        url = f"{ASOS_HOURLY_URL}?tm1={_tm(cur)}&tm2={_tm(chunk_end)}&stn={stn}&help=0&authKey={KMA_API_HUB_KEY}"
        status, text = _call(url)
        if status != STATUS_OK:
            return ObservationResult(status=status, rows=rows, note=text)
        rows.extend(parse_asos_hourly(text, stn))
        cur = chunk_end + timedelta(hours=1)
    return ObservationResult(status=STATUS_OK, rows=rows, note="")


# --- 2. AWS 시간통계(단일 시각) -------------------------------------------------------


def parse_aws_hourly_stat(text: str) -> list[AwsHourlyStat]:
    """`YYMMDDHHMI STN RE_SUM RE_QCM RN_DAY RN_DAY_MI RN_HR1 RN_HR1_MI RN_60M_MAX MI QCM RN_15M_MAX MI QCM`."""
    rows: list[AwsHourlyStat] = []
    for line in _data_lines(text):
        p = line.split()
        if len(p) < 14 or not p[0].isdigit():
            continue
        rows.append(
            AwsHourlyStat(
                tm=_parse_tm(p[0]), stn=p[1],
                rn_day_mm=_num(p[4], ("-99", "-99.0")), rn_hr1_mm=_num(p[6], ("-99", "-99.0")),
                rn_60m_max_mm=_num(p[8], ("-99", "-99.0")), rn_15m_max_mm=_num(p[11], ("-99", "-99.0")),
            )
        )
    return rows


def fetch_aws_hourly_stat(stn: str, tm: datetime) -> ObservationResult:
    url = f"{AWS_HOURLY_STAT_URL}?var=RN&tm={_tm(tm)}&stn={stn}&help=0&authKey={KMA_API_HUB_KEY}"
    status, text = _call(url)
    if status != STATUS_OK:
        return ObservationResult(status=status, rows=[], note=text)
    if _NO_STATION_MARKER in text:
        return ObservationResult(status=STATUS_NO_SUCH_STATION, rows=[], note=f"stn={stn}은 {_tm(tm)} 시점에 존재하지 않는 지점")
    return ObservationResult(status=STATUS_OK, rows=parse_aws_hourly_stat(text), note="")


# --- 3. AWS 일통계 ----------------------------------------------------------------


def parse_aws_daily(text: str) -> list[AwsDaily]:
    """`YYMMDD STN LON LAT HT VAL [지점명]` — 지점명은 문서에 없지만 실응답 7번째 토큰."""
    rows: list[AwsDaily] = []
    for line in _data_lines(text):
        p = line.split()
        if len(p) < 6 or not p[0].isdigit():
            continue
        rows.append(
            AwsDaily(
                day=datetime.strptime(p[0], "%Y%m%d").replace(tzinfo=_KST), stn=p[1],
                lon=float(p[2]), lat=float(p[3]), rn_day_mm=_num(p[5], ("-99", "-99.0")),
                name=" ".join(p[6:]),
            )
        )
    return rows


def fetch_aws_daily(stn: str, start: datetime, end: datetime, obs: str = "rn_day") -> ObservationResult:
    url = (
        f"{AWS_DAILY_URL}?tm1={start.astimezone(_KST):%Y%m%d}&tm2={end.astimezone(_KST):%Y%m%d}"
        f"&obs={obs}&stn={stn}&disp=0&help=0&authKey={KMA_API_HUB_KEY}"
    )
    status, text = _call(url)
    if status != STATUS_OK:
        return ObservationResult(status=status, rows=[], note=text)
    if _NO_STATION_MARKER in text:
        return ObservationResult(status=STATUS_NO_SUCH_STATION, rows=[], note=f"stn={stn} 없음")
    return ObservationResult(status=STATUS_OK, rows=parse_aws_daily(text), note="")


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    a = (
        math.sin(math.radians(lat2 - lat1) / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    )
    return 2 * r * math.asin(math.sqrt(a))


# ---------------------------------------------------------------------------
# 담보별 강수 판정용(2026-09-03(계속10), 프로덕션 경로) — 조회 창의 날짜마다 전국 관측소
# 일강수를 받아 지점별 최대값으로 합치고, 담보 좌표에서 가장 가까운(값이 있는) 지점을 고른다.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class StationRainfall:
    stn: str
    name: str
    lat: float
    lon: float
    max_rn_day_mm: float | None  # 창 내 최대 일강수(전 날짜 결측이면 None)
    n_days: int  # 값이 있었던 날 수


@dataclass(frozen=True)
class StationRainfallWindow:
    status: str  # OK | ACTIVATION_REQUIRED | UPSTREAM_ERROR
    stations: list[StationRainfall]
    day_status: dict  # {YYYY-MM-DD: status}
    note: str


def nearest_station(lat: float, lon: float, stations: list[StationRainfall]) -> tuple[StationRainfall, float] | None:
    """값이 있는 관측소 중 가장 가까운 것과 거리(km). 결측만 있는 지점은 제외(0으로 취급하지 않음)."""
    candidates = [(haversine_km(lat, lon, s.lat, s.lon), s) for s in stations if s.max_rn_day_mm is not None]
    if not candidates:
        return None
    km, s = min(candidates, key=lambda x: x[0])
    return s, km


def fetch_station_rainfall_window(start: datetime, end: datetime) -> StationRainfallWindow:
    """[start, end] 각 날짜의 전국 관측소 일강수(sfc_aws_day stn=0)를 지점별 최대값으로 합친다.
    하루라도 실패하면 status에 그 상태를 남기되 받은 날짜의 값은 유지한다."""
    acc: dict[str, dict] = {}
    day_status: dict[str, str] = {}
    worst = STATUS_OK
    notes: list[str] = []
    cur = start.astimezone(_KST).replace(hour=0, minute=0, second=0, microsecond=0)
    last = end.astimezone(_KST)
    while cur.date() <= last.date():
        r = fetch_aws_daily("0", cur, cur)
        day_status[cur.date().isoformat()] = r.status
        if r.status != STATUS_OK:
            worst = r.status
            notes.append(f"{cur.date().isoformat()}: {r.note}")
        for row in r.rows:
            a = acc.setdefault(row.stn, {"stn": row.stn, "name": row.name, "lat": row.lat, "lon": row.lon, "max": None, "n": 0})
            if row.rn_day_mm is not None:
                a["n"] += 1
                a["max"] = row.rn_day_mm if a["max"] is None else max(a["max"], row.rn_day_mm)
        cur += timedelta(days=1)
    stations = [
        StationRainfall(stn=a["stn"], name=a["name"], lat=a["lat"], lon=a["lon"], max_rn_day_mm=a["max"], n_days=a["n"])
        for a in acc.values()
    ]
    return StationRainfallWindow(status=worst, stations=stations, day_status=day_status, note="; ".join(notes))
