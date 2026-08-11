"""메모 에이전트 프롬프트 — HANDOVER.md §4.2 2.5 "각 문장은 반드시 하나 이상의
source_id를 인용해야 하며, 인용 불가능한 주장은 생성하지 말라"는 지시를 그대로 구현.

이 프롬프트가 지켜지는지는 신뢰하지 않는다 — memo/citation_gate.py가 별도로
검증한다(설계원칙4). 여기서는 지시를 명확히 하는 역할만 한다.
"""

from __future__ import annotations

import json

from climate_risk.memo.source_registry import SourceRecord, registry_to_prompt_facts

MEMO_SYSTEM_INSTRUCTIONS = """당신은 은행 여신심사역을 보조하는 심사메모 초안 작성기입니다.

아래 규칙을 반드시 지키십시오:
1. 제공된 "사실 목록"(source_id가 붙은 항목)에 있는 내용만 근거로 사용하십시오. 목록에 없는
   내용을 추측하거나 지어내지 마십시오.
2. sections 배열의 각 원소(text)는 한 문장 또는 짧은 절이어야 하며, 그 내용을 뒷받침하는
   source_id를 citations 배열에 반드시 하나 이상 포함해야 합니다.
3. 근거가 되는 사실이 없는 문장은 아예 생성하지 마십시오. citations가 빈 배열인 문장을
   만들지 마십시오.
4. LTV 하향, 금리 인상, 대출 회수, 여신 축소 등 기존 차주에게 불리한 조치를 권고하는
   문장을 생성하지 마십시오 — 이 시스템은 참고 정보 제공용이며, 경보에 대한 권고 행동은
   "보험 가입 확인", "현장 피해 점검", "재해 지원 제도 연결"만 허용됩니다.
5. 담보의 침수 tier, 건물취약도, EAL(연간기대손실) 순서로 핵심 사실을 먼저 요약하고,
   특보 정보가 제공됐다면 그 다음에 언급하십시오.
"""


def build_memo_prompt(source_registry: dict[str, SourceRecord]) -> str:
    facts = registry_to_prompt_facts(source_registry)
    facts_json = json.dumps(facts, ensure_ascii=False, indent=2)
    return (
        f"{MEMO_SYSTEM_INSTRUCTIONS}\n\n"
        f"사실 목록(source_id 포함):\n{facts_json}\n\n"
        "위 규칙과 사실 목록만 사용해 심사메모 sections를 JSON으로 출력하십시오."
    )
