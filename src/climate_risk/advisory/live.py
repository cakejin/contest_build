"""라이브 기상청 특보 API 모드 — HANDOVER.md §⑦ 축소우선순위 항목③ "라이브 특보 API 모드"는
Week3 스트레치(스킵 가능) 항목으로 명시됐다. 힌남노 리플레이(정적 재생)만으로 클라이맥스
시연이 가능하므로 이 모듈은 스텁만 둔다 — 조용히 가짜 데이터를 반환하지 않고, 미구현임을
예외로 명시한다(설계원칙1 "데이터 없음≠위험 없음"과 같은 정신: 미구현을 구현된 것처럼
둔갑시키지 않는다).
"""

from __future__ import annotations


def run_live_query(*args, **kwargs):
    raise NotImplementedError(
        "라이브 특보 API 모드는 Week3 미구현입니다 — HANDOVER.md §⑦ 축소우선순위 항목③ "
        "(힌남노 리플레이가 우선 경로). 필요 시 기상청 WthrWrnInfoService/getWthrWrnList "
        "실호출 경로를 이 함수에 구현할 것."
    )
