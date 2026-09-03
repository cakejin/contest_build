"""재심사 알림 트리거 후보 레지스트리 — **사전 등록(pre-registration)** 목록
(DEV_LOG.md 2026-09-03 참조).

각 후보는 `list[AdvisoryEvent] -> bool` 순수 함수다. 입력이 특보 타임라인뿐이라
라벨 파일의 `eal_alert_fired`(현행 EAL 알림, 참고 열)나 `damage_confirmed`(정답)가
후보 판정에 섞여 들어갈 통로가 구조적으로 없다.

**이 목록과 상수는 검증 결과를 보기 전에 고정됐다**(PREREGISTERED_AT). 결과를 본 뒤
후보를 추가하고 싶으면 기존 항목을 고치지 말고 날짜를 붙여 뒤에 append한다 — 2026-08-12
항목(포항 외 리플레이 데이터셋)의 "임계치는 날짜를 보기 전에 확정" 방법론과 같은 규율.
tests/test_alert_validation.py가 CANDIDATE_IDS 튜플을 그대로 assert해 순서·구성을 동결한다.

후보 선정 기준은 "물리적으로 담보 침수와 연결되는 관측 원자료인가"이지 "3개 양성
사건을 맞히는가"가 아니다 — 양성이 3건뿐이라 후자로 고르면 과적합된다(DEV_LOG 참조).
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from climate_risk.advisory.disaster_msg import RELEVANT_DST_SE_NM
from climate_risk.advisory.schema import AdvisoryEvent
from climate_risk.agents.advisory_agent import HIGH_SEVERITY_LEVELS
from climate_risk.evaluation.alert_validation import parse_issued_at_kst

PREREGISTERED_AT = "2026-09-03"

EVENT_TYPE_WARNING = "특보"
EVENT_TYPE_DISASTER_MSG = "재난문자"
# advisory_agent._TRIGGER_EVENT_TYPES와 같은 값 — 현행 trigger_event 규칙을 그대로 복제(C0).
TRIGGER_EVENT_TYPES = frozenset({EVENT_TYPE_WARNING, EVENT_TYPE_DISASTER_MSG})

# 수문(水文) 특보 — 담보 건물의 침수와 물리적으로 직결되는 종류만. warning_type 문자열은
# historical 모드에서 f"{wrn_label} {lvl_label} {cmd_label}"(예: "호우 경보 변경")이라
# 토큰 포함 검사로 매칭한다. "폭풍해일"은 "폭풍"·"해일" 어느 쪽 토큰과도 겹치지 않게
# 전체 단어로 둔다.
HYDRO_WARNING_TOKENS: tuple[str, ...] = ("호우", "태풍", "홍수", "폭풍해일")
# 재난문자 DST_SE_NM(warning_type에 그대로 들어감) 중 수문 재해.
HYDRO_DST_SE_NM = frozenset({"호우", "홍수", "태풍"})
# 특보 등급(lvl_label) 중 "경보" 이상.
WARNING_LEVELS = frozenset({"경보", "중대경보"})
# 재난문자 긴급단계(emrg_step_nm) 중 "긴급재난" 이상.
EMERGENCY_STEPS = frozenset({"긴급재난", "위급재난"})
# 재난문자 본문에 실제 피해·대응을 뜻하는 단어 — 예보("우려")가 아니라 관측된 상황.
DAMAGE_KEYWORDS: tuple[str, ...] = ("침수", "범람", "대피", "역류")
# 경보 등급이어도 건물 침수와 무관한 기상현상 — C5에서 제외.
NON_PHYSICAL_WARNING_TOKENS: tuple[str, ...] = ("폭염", "한파", "황사", "건조", "열대야", "안개")
# C4 — 24시간 창 안에 담보 관련(RELEVANT_DST_SE_NM) 재난문자가 3건 이상.
C4_MIN_MESSAGES = 3
C4_WINDOW_HOURS = 24


@dataclass(frozen=True)
class TriggerCandidate:
    candidate_id: str
    title: str
    rule_text: str
    fn: Callable[[list[AdvisoryEvent]], bool]
    requires_disaster_msg: bool  # True면 재난문자 없는 KMA-only 에피소드에선 하한(lower bound)
    # 2026-09-03(계속6) — 강수 관측 의존 후보. 전체 KMA 에피소드엔 강수 캐시가 없어
    # 알림 피로 지표를 계산하지 않는다(None). 기본값 False라 기존 후보는 영향 없음.
    requires_rainfall: bool = False


def _is_warning(e: AdvisoryEvent) -> bool:
    return e.event_type == EVENT_TYPE_WARNING


def _is_disaster_msg(e: AdvisoryEvent) -> bool:
    return e.event_type == EVENT_TYPE_DISASTER_MSG


def _warning_text(e: AdvisoryEvent) -> str:
    return e.warning_type or ""


def _is_hydro_warning_high(e: AdvisoryEvent) -> bool:
    return (
        _is_warning(e)
        and e.severity_level in WARNING_LEVELS
        and any(tok in _warning_text(e) for tok in HYDRO_WARNING_TOKENS)
    )


def _is_hydro_disaster_msg_emergency(e: AdvisoryEvent) -> bool:
    return _is_disaster_msg(e) and e.warning_type in HYDRO_DST_SE_NM and e.severity_level in EMERGENCY_STEPS


def c0_any_advisory(events: list[AdvisoryEvent]) -> bool:
    """현행 `trigger_event` 규칙 — 특보·재난문자가 하나라도 있으면 True."""
    return any(e.event_type in TRIGGER_EVENT_TYPES for e in events)


def c1_high_severity_any(events: list[AdvisoryEvent]) -> bool:
    """2026-08-31 최초 심각도 채널 규칙(종류 무관, 등급만) — 2026-09-03(계속10)에 프로덕션
    `is_high_severity_event`가 A2(종류 조건 추가)로 바뀌었으므로, 검증표의 C1이 조용히 따라
    바뀌지 않도록 여기서 옛 규칙을 그대로 고정한다."""
    return any(e.severity_level in HIGH_SEVERITY_LEVELS for e in events)


def c2_hydro_high_severity(events: list[AdvisoryEvent]) -> bool:
    """수문 특보 경보 이상, 또는 수문 재난문자 긴급재난 이상."""
    return any(_is_hydro_warning_high(e) or _is_hydro_disaster_msg_emergency(e) for e in events)


def c3_disaster_msg_damage_keyword(events: list[AdvisoryEvent]) -> bool:
    """재난문자 본문(description)에 침수/범람/대피/역류 중 하나라도."""
    return any(_is_disaster_msg(e) and any(k in e.description for k in DAMAGE_KEYWORDS) for e in events)


def c4_disaster_msg_burst(events: list[AdvisoryEvent]) -> bool:
    """담보 관련 재난문자(RELEVANT_DST_SE_NM)가 어떤 24시간 창 안에 3건 이상(슬라이딩 창)."""
    times = sorted(
        parse_issued_at_kst(e.issued_at)
        for e in events
        if _is_disaster_msg(e) and (e.warning_type or "") in RELEVANT_DST_SE_NM
    )
    if len(times) < C4_MIN_MESSAGES:
        return False
    window = C4_WINDOW_HOURS * 3600
    left = 0
    for right in range(len(times)):
        while (times[right] - times[left]).total_seconds() > window:
            left += 1
        if right - left + 1 >= C4_MIN_MESSAGES:
            return True
    return False


def c5_warning_level_physical(events: list[AdvisoryEvent]) -> bool:
    """경보 이상 특보 중 비물리(폭염·한파·황사·건조·열대야·안개) 제외 — 강풍·풍랑·대설 포함."""
    return any(
        _is_warning(e)
        and e.severity_level in WARNING_LEVELS
        and not any(tok in _warning_text(e) for tok in NON_PHYSICAL_WARNING_TOKENS)
        for e in events
    )


def c6_hydro_high_severity_or_burst(events: list[AdvisoryEvent]) -> bool:
    """C2 ∨ C4 — 유일한 결합 후보. 두 소스(기상청 특보·재난문자)가 독립이라 합쳐볼 가치가 있다."""
    return c2_hydro_high_severity(events) or c4_disaster_msg_burst(events)


CANDIDATES: tuple[TriggerCandidate, ...] = (
    TriggerCandidate(
        candidate_id="C0_any_advisory",
        title="현행 트리거(특보·재난문자 아무거나)",
        rule_text="event_type ∈ {특보, 재난문자}인 이벤트가 1건 이상",
        fn=c0_any_advisory,
        requires_disaster_msg=False,
    ),
    TriggerCandidate(
        candidate_id="C1_high_severity_any",
        title="현행 심각도 채널(경보·중대경보·긴급재난·위급재난)",
        rule_text="severity_level ∈ HIGH_SEVERITY_LEVELS인 이벤트가 1건 이상(2026-08-31 규칙, 종류 무관)",
        fn=c1_high_severity_any,
        requires_disaster_msg=False,
    ),
    TriggerCandidate(
        candidate_id="C2_hydro_high_severity",
        title="수문 특보 경보 이상 ∨ 수문 재난문자 긴급재난 이상",
        rule_text=(
            f"특보: warning_type에 {HYDRO_WARNING_TOKENS} 중 하나 ∧ severity ∈ {sorted(WARNING_LEVELS)}; "
            f"또는 재난문자: warning_type ∈ {sorted(HYDRO_DST_SE_NM)} ∧ severity ∈ {sorted(EMERGENCY_STEPS)}"
        ),
        fn=c2_hydro_high_severity,
        requires_disaster_msg=False,
    ),
    TriggerCandidate(
        candidate_id="C3_disaster_msg_damage_keyword",
        title="재난문자 본문 피해 키워드",
        rule_text=f"재난문자 description에 {DAMAGE_KEYWORDS} 중 하나",
        fn=c3_disaster_msg_damage_keyword,
        requires_disaster_msg=True,
    ),
    TriggerCandidate(
        candidate_id="C4_disaster_msg_burst",
        title="재난문자 폭주(24h 내 3건 이상)",
        rule_text=f"RELEVANT_DST_SE_NM 재난문자 ≥{C4_MIN_MESSAGES}건이 어떤 {C4_WINDOW_HOURS}h 슬라이딩 창 안",
        fn=c4_disaster_msg_burst,
        requires_disaster_msg=True,
    ),
    TriggerCandidate(
        candidate_id="C5_warning_level_physical",
        title="경보 이상 특보(비물리 제외)",
        rule_text=f"특보 severity ∈ {sorted(WARNING_LEVELS)} ∧ warning_type에 {NON_PHYSICAL_WARNING_TOKENS} 없음",
        fn=c5_warning_level_physical,
        requires_disaster_msg=False,
    ),
    TriggerCandidate(
        candidate_id="C6_hydro_high_severity_or_burst",
        title="C2 ∨ C4",
        rule_text="c2_hydro_high_severity(events) or c4_disaster_msg_burst(events)",
        fn=c6_hydro_high_severity_or_burst,
        requires_disaster_msg=True,
    ),
)

CANDIDATE_IDS: tuple[str, ...] = tuple(c.candidate_id for c in CANDIDATES)


def candidate_by_id(candidate_id: str, candidates: Sequence[TriggerCandidate] = CANDIDATES) -> TriggerCandidate:
    for c in candidates:
        if c.candidate_id == candidate_id:
            return c
    raise KeyError(candidate_id)
