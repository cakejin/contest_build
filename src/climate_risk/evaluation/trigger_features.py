"""트리거 기본 피쳐(atom) 11개 + 2개 조합(AND/OR) 생성기 — 3단계 분리 검증용
(DEV_LOG.md 2026-09-03(계속3) 참조).

`trigger_candidates.py`의 C0~C6은 "규칙 하나 = 후보 하나"였다. 사용자 요청(2026-09-03)으로
피쳐를 더 잘게 쪼갠 atom을 정의하고, atom 2개의 AND/OR 조합을 전부 후보로 만들어 같은
하네스에 넣는다. 조합이 단일 피쳐보다 오탐을 줄이는지 보기 위한 것이다.

**사전 등록 주의**: 이 atom 목록은 C0~C6의 전체 결과표(2026-09-03 첫 실행)를 본 뒤에
정의됐다. 즉 "완전히 결과를 모르는 상태"는 아니다 — 특히 A4(폭풍해일)는 힌남노·난마돌
타임라인을 직접 본 뒤 추가됐다(둘 다 태풍경보이고 폭풍해일 주의보만 힌남노에 있음).
그래서 3단계 검증에서 1단계(힌남노 선정)는 사실상 사후 정의이고, 2단계(다른 사건)와
3단계(거제 2026-08)만이 이 atom들에 대한 실질적 검증이다 — DEV_LOG에 같은 문구를 남긴다.

atom은 전부 `list[AdvisoryEvent] -> bool` 순수 함수(trigger_candidates와 같은 계약).
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from itertools import combinations

from climate_risk.advisory.disaster_msg import RELEVANT_DST_SE_NM
from climate_risk.advisory.schema import AdvisoryEvent
from climate_risk.evaluation.alert_validation import (
    OBS_KIND_ASOS_HOURLY,
    OBS_KIND_AWS_DAILY,
    OBS_KIND_AWS_HOURLY,
    OBSERVATION_EVENT_TYPE,
    parse_issued_at_kst,
)
from climate_risk.evaluation.trigger_candidates import (
    C4_MIN_MESSAGES,
    C4_WINDOW_HOURS,
    DAMAGE_KEYWORDS,
    EMERGENCY_STEPS,
    EVENT_TYPE_DISASTER_MSG,
    EVENT_TYPE_WARNING,
    HYDRO_DST_SE_NM,
    HYDRO_WARNING_TOKENS,
    WARNING_LEVELS,
    TriggerCandidate,
    c3_disaster_msg_damage_keyword,
    c4_disaster_msg_burst,
)

FEATURES_REGISTERED_AT = "2026-09-03"

ADVISORY_OR_ABOVE = frozenset({"주의보", "경보", "중대경보"})
STORM_SURGE_TOKEN = "폭풍해일"
TYPHOON_TOKEN = "태풍"
RAIN_TOKEN = "호우"
# A7 — 수문 경보 지속시간 임계값(사전 등록). 힌남노 12h·난마돌 15h·수성구 1h40m·거제 2026 20h대.
HYDRO_LEVEL_MIN_DURATION_HOURS = 12
# 발표/대치/연장/변경 = 상태 시작, 해제/대치해제/변경해제 = 상태 종료(kma_historical CMD 코드).
_ISSUE_CMD_LABELS = ("발표", "대치", "연장", "변경")
_RELEASE_CMD_LABELS = ("해제", "대치해제", "변경해제")


def _is_warning(e: AdvisoryEvent) -> bool:
    return e.event_type == EVENT_TYPE_WARNING


def _is_dm(e: AdvisoryEvent) -> bool:
    return e.event_type == EVENT_TYPE_DISASTER_MSG


def _wt(e: AdvisoryEvent) -> str:
    return e.warning_type or ""


def _hydro_type_of(e: AdvisoryEvent) -> str | None:
    for tok in HYDRO_WARNING_TOKENS:
        if tok in _wt(e):
            return tok
    return None


def _cmd_of(e: AdvisoryEvent) -> str:
    """historical 모드 warning_type = f"{종류} {등급} {명령}" — 마지막 토큰이 명령."""
    parts = _wt(e).split()
    return parts[-1] if len(parts) >= 3 else ""


# --- atoms -----------------------------------------------------------------------


def a1_any_warning_level(events: list[AdvisoryEvent]) -> bool:
    return any(_is_warning(e) and e.severity_level in WARNING_LEVELS for e in events)


def a2_hydro_warning_level(events: list[AdvisoryEvent]) -> bool:
    return any(_is_warning(e) and e.severity_level in WARNING_LEVELS and _hydro_type_of(e) for e in events)


def a3_hydro_warning_advisory(events: list[AdvisoryEvent]) -> bool:
    return any(_is_warning(e) and e.severity_level in ADVISORY_OR_ABOVE and _hydro_type_of(e) for e in events)


def a4_storm_surge(events: list[AdvisoryEvent]) -> bool:
    return any(_is_warning(e) and e.severity_level in ADVISORY_OR_ABOVE and STORM_SURGE_TOKEN in _wt(e) for e in events)


def a5_typhoon_level(events: list[AdvisoryEvent]) -> bool:
    return any(_is_warning(e) and e.severity_level in WARNING_LEVELS and TYPHOON_TOKEN in _wt(e) for e in events)


def a6_rain_level(events: list[AdvisoryEvent]) -> bool:
    return any(_is_warning(e) and e.severity_level in WARNING_LEVELS and RAIN_TOKEN in _wt(e) for e in events)


def hydro_level_durations_hours(events: list[AdvisoryEvent]) -> dict[str, float]:
    """수문 종류별 '경보 이상' 상태의 총 지속시간(시간). 경보 등급 발표/변경 행에서 시작해
    같은 종류의 다음 행이 해제 계열이거나 등급이 경보 미만이면 종료. 타임라인 끝까지
    종료 행이 없으면 마지막 이벤트 시각까지로 잡는다(과소가 아니라 관측 한계)."""
    # "예비특보" 행은 상태 변화가 아니라 예고라 지속시간 계산에서 제외(난마돌·카눈에서 경보
    # 중간에 예비 발표 행이 끼어 지속시간이 잘못 끊기던 것 — 2026-09-03 실측 확인).
    warnings = sorted(
        (e for e in events if _is_warning(e) and _hydro_type_of(e) and e.severity_level != "예비"),
        key=lambda e: parse_issued_at_kst(e.issued_at),
    )
    if not warnings:
        return {}
    last_time = parse_issued_at_kst(warnings[-1].issued_at)
    open_since: dict[str, datetime] = {}
    total: dict[str, float] = {}
    for e in warnings:
        typ = _hydro_type_of(e) or ""
        t = parse_issued_at_kst(e.issued_at)
        is_level = e.severity_level in WARNING_LEVELS
        cmd = _cmd_of(e)
        if typ in open_since and (not is_level or cmd in _RELEASE_CMD_LABELS):
            total[typ] = total.get(typ, 0.0) + (t - open_since.pop(typ)).total_seconds() / 3600
        if is_level and cmd in _ISSUE_CMD_LABELS and typ not in open_since:
            open_since[typ] = t
    for typ, since in open_since.items():
        total[typ] = total.get(typ, 0.0) + (last_time - since).total_seconds() / 3600
    return total


def a7_hydro_level_duration(events: list[AdvisoryEvent]) -> bool:
    return any(h >= HYDRO_LEVEL_MIN_DURATION_HOURS for h in hydro_level_durations_hours(events).values())


def a8_hydro_types_ge2(events: list[AdvisoryEvent]) -> bool:
    types = {_hydro_type_of(e) for e in events if _is_warning(e) and e.severity_level in ADVISORY_OR_ABOVE and _hydro_type_of(e)}
    return len(types) >= 2


def a9_dm_hydro_emergency(events: list[AdvisoryEvent]) -> bool:
    return any(_is_dm(e) and e.warning_type in HYDRO_DST_SE_NM and e.severity_level in EMERGENCY_STEPS for e in events)


def a10_dm_damage_keyword(events: list[AdvisoryEvent]) -> bool:
    return c3_disaster_msg_damage_keyword(events)


def a11_dm_burst(events: list[AdvisoryEvent]) -> bool:
    return c4_disaster_msg_burst(events)


# --- 강수 관측 atom(2026-09-03(계속6) 사전 등록) ------------------------------------------
# 임계값 근거: 기상청 극한호우 재난문자 기준(1시간 50mm ∧ 3시간 90mm) 및 호우경보 기준(12시간
# 180mm)을 참고하되, 실측 표(DEV_LOG (계속5))를 보기 전에 물리적으로 정한 값이 아니라는 점을
# 정직하게 남긴다 — 힌남노 77/난마돌 6/마이삭 41/카눈 39/힌남노 대구 16(mm/h)을 이미 본 상태.
ASOS_1H_THRESHOLDS_MM = (30.0, 50.0)
ASOS_DAY_THRESHOLDS_MM = (100.0, 150.0)
AWS_60M_MAX_THRESHOLD_MM = 30.0
AWS_DAY_THRESHOLD_MM = 100.0


def parse_observation_values(description: str) -> dict[str, float | None]:
    """'KEY=값;KEY=값' 고정 포맷(alert_validation.rainfall_to_advisory_events) 파서. NA → None."""
    out: dict[str, float | None] = {}
    for part in description.split(";"):
        if "=" not in part:
            continue
        k, v = part.split("=", 1)
        out[k.strip()] = None if v.strip() == "NA" else float(v)
    return out


def _obs_max(events: list[AdvisoryEvent], kind: str, key: str) -> float | None:
    vals = [
        parse_observation_values(e.description).get(key)
        for e in events
        if e.event_type == OBSERVATION_EVENT_TYPE and (e.warning_type or "").startswith(kind + " ")
    ]
    vals = [v for v in vals if v is not None]
    return max(vals) if vals else None


def _ge(v: float | None, threshold: float) -> bool:
    return v is not None and v >= threshold


def a12_asos_1h_ge_30(events: list[AdvisoryEvent]) -> bool:
    return _ge(_obs_max(events, OBS_KIND_ASOS_HOURLY, "RN_1H"), ASOS_1H_THRESHOLDS_MM[0])


def a13_asos_1h_ge_50(events: list[AdvisoryEvent]) -> bool:
    return _ge(_obs_max(events, OBS_KIND_ASOS_HOURLY, "RN_1H"), ASOS_1H_THRESHOLDS_MM[1])


def a14_asos_day_ge_100(events: list[AdvisoryEvent]) -> bool:
    return _ge(_obs_max(events, OBS_KIND_ASOS_HOURLY, "RN_DAY"), ASOS_DAY_THRESHOLDS_MM[0])


def a15_asos_day_ge_150(events: list[AdvisoryEvent]) -> bool:
    return _ge(_obs_max(events, OBS_KIND_ASOS_HOURLY, "RN_DAY"), ASOS_DAY_THRESHOLDS_MM[1])


def a16_aws_60m_max_ge_30(events: list[AdvisoryEvent]) -> bool:
    return _ge(_obs_max(events, OBS_KIND_AWS_HOURLY, "RN_60M_MAX"), AWS_60M_MAX_THRESHOLD_MM)


def a17_aws_day_ge_100(events: list[AdvisoryEvent]) -> bool:
    day_hourly = _obs_max(events, OBS_KIND_AWS_HOURLY, "RN_DAY")
    day_daily = _obs_max(events, OBS_KIND_AWS_DAILY, "RN_DAY")
    best = max((v for v in (day_hourly, day_daily) if v is not None), default=None)
    return _ge(best, AWS_DAY_THRESHOLD_MM)


_ATOM_DEFS: tuple[tuple[str, str, Callable[[list[AdvisoryEvent]], bool], bool], ...] = (
    ("A1", "특보 경보 이상(종류 무관)", a1_any_warning_level, False),
    ("A2", "수문 특보 경보 이상", a2_hydro_warning_level, False),
    ("A3", "수문 특보 주의보 이상", a3_hydro_warning_advisory, False),
    ("A4", "폭풍해일 특보(주의보 이상)", a4_storm_surge, False),
    ("A5", "태풍 경보 이상", a5_typhoon_level, False),
    ("A6", "호우 경보 이상", a6_rain_level, False),
    ("A7", f"수문 경보 지속 ≥{HYDRO_LEVEL_MIN_DURATION_HOURS}h", a7_hydro_level_duration, False),
    ("A8", "수문 특보 종류 ≥2(주의보 이상)", a8_hydro_types_ge2, False),
    ("A9", "수문 재난문자 긴급재난 이상", a9_dm_hydro_emergency, True),
    ("A10", f"재난문자 본문 {DAMAGE_KEYWORDS}", a10_dm_damage_keyword, True),
    ("A11", f"담보 관련 재난문자 {C4_WINDOW_HOURS}h 내 ≥{C4_MIN_MESSAGES}건({sorted(RELEVANT_DST_SE_NM)[:3]}…)", a11_dm_burst, True),
)

_RAIN_ATOM_DEFS: tuple[tuple[str, str, Callable[[list[AdvisoryEvent]], bool]], ...] = (
    ("A12", f"ASOS 1시간 강수 ≥{ASOS_1H_THRESHOLDS_MM[0]:.0f}mm", a12_asos_1h_ge_30),
    ("A13", f"ASOS 1시간 강수 ≥{ASOS_1H_THRESHOLDS_MM[1]:.0f}mm", a13_asos_1h_ge_50),
    ("A14", f"ASOS 일강수 ≥{ASOS_DAY_THRESHOLDS_MM[0]:.0f}mm", a14_asos_day_ge_100),
    ("A15", f"ASOS 일강수 ≥{ASOS_DAY_THRESHOLDS_MM[1]:.0f}mm", a15_asos_day_ge_150),
    ("A16", f"최근접 AWS 60분 최대강수 ≥{AWS_60M_MAX_THRESHOLD_MM:.0f}mm", a16_aws_60m_max_ge_30),
    ("A17", f"최근접 AWS 일강수 ≥{AWS_DAY_THRESHOLD_MM:.0f}mm", a17_aws_day_ge_100),
)

ATOMS: tuple[TriggerCandidate, ...] = tuple(
    TriggerCandidate(candidate_id=cid, title=title, rule_text=title, fn=fn, requires_disaster_msg=dm)
    for cid, title, fn, dm in _ATOM_DEFS
) + tuple(
    TriggerCandidate(candidate_id=cid, title=title, rule_text=title, fn=fn, requires_disaster_msg=False, requires_rainfall=True)
    for cid, title, fn in _RAIN_ATOM_DEFS
)
RAIN_ATOM_IDS: tuple[str, ...] = tuple(cid for cid, _, _ in _RAIN_ATOM_DEFS)
ATOM_IDS: tuple[str, ...] = tuple(a.candidate_id for a in ATOMS)


def _and(a: TriggerCandidate, b: TriggerCandidate) -> TriggerCandidate:
    return TriggerCandidate(
        candidate_id=f"{a.candidate_id}&{b.candidate_id}",
        title=f"({a.title}) AND ({b.title})",
        rule_text=f"{a.candidate_id} and {b.candidate_id}",
        fn=lambda events, fa=a.fn, fb=b.fn: fa(events) and fb(events),
        requires_disaster_msg=a.requires_disaster_msg or b.requires_disaster_msg,
        requires_rainfall=a.requires_rainfall or b.requires_rainfall,
    )


def _or(a: TriggerCandidate, b: TriggerCandidate) -> TriggerCandidate:
    return TriggerCandidate(
        candidate_id=f"{a.candidate_id}|{b.candidate_id}",
        title=f"({a.title}) OR ({b.title})",
        rule_text=f"{a.candidate_id} or {b.candidate_id}",
        fn=lambda events, fa=a.fn, fb=b.fn: fa(events) or fb(events),
        # OR는 한쪽만으로도 켜지므로, 재난문자 없는 에피소드에서도 특보 쪽으로 켜질 수 있다 —
        # 그래도 재난문자 쪽 기여분은 하한이라 보수적으로 True 유지.
        requires_disaster_msg=a.requires_disaster_msg or b.requires_disaster_msg,
        requires_rainfall=a.requires_rainfall or b.requires_rainfall,
    )


def build_pair_combos(atoms: Sequence[TriggerCandidate] = ATOMS) -> tuple[TriggerCandidate, ...]:
    """atom 2개의 AND/OR 전부(17개 → 136쌍 × 2 = 272개). 3개 이상 조합은 만들지 않는다 —
    양성 표본이 한 자리 수라 조합이 늘수록 우연히 맞는 후보가 반드시 생긴다."""
    out: list[TriggerCandidate] = []
    for a, b in combinations(atoms, 2):
        out.append(_and(a, b))
        out.append(_or(a, b))
    return tuple(out)


def all_feature_candidates() -> tuple[TriggerCandidate, ...]:
    return ATOMS + build_pair_combos()
