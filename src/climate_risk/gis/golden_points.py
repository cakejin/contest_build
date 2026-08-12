"""커버리지 게이트 골든 좌표셋 — tests/test_coverage_gate.py에서 이관(Week4).

원래 이 두 리스트는 테스트 파일 안에만 있었다. Week4 평가 대시보드(evaluation/metrics.py)와
레드팀 체크(policy/redteam_checks.py)가 "같은 골든셋으로 커버리지 게이트가 항상 같은 결과를
내는가"를 pytest 밖(런타임/라이브 데모)에서도 확인해야 해서, 진실의 원천을 여기 하나로
모은다 — 테스트와 런타임이 각자 좌표 리스트를 따로 들고 있으면 조용히 어긋날 위험이 있다
(DEV_LOG.md 2026-08-09, 신천 판정보류 좌표 1~110m 오차 전례와 같은 종류의 리스크).

좌표 출처는 tests/test_coverage_gate.py 원본 docstring 그대로:
- 냉천 3지점: contest_research §1.10 (PM 직접 실측, WGS84 좌표 원본 그대로).
- 신천 5지점: 남구(신천대로·봉덕동)는 §1.11 "내부(0.0m)" 서술을 만족하는 신천대로
  선형 위 좌표. 나머지 4개(판정보류)는 gis/coverage.py KNOWN_UNCERTAIN_POINTS와 동일 좌표.
"""

from __future__ import annotations

from climate_risk.gis.query import TIER_FAR, TIER_INNER, TIER_NEAR

# (label, lat, lon, expected in_polygon, expected tier)
NAECHEON_POINTS: list[tuple[str, float, float, bool, str]] = [
    ("오어지(냉천 발원지)", 35.92159, 129.37452, False, TIER_NEAR),
    ("포항직업전문학교(냉천 중류·인덕동)", 35.98768, 129.39979, True, TIER_INNER),
    ("냉천교(냉천 하류·청림동)", 35.99347, 129.40130, False, TIER_NEAR),
]

SINCHEON_POINTS: list[tuple[str, float, float, bool, str]] = [
    ("신천대로(봉덕동·남구, 확정)", 35.833993, 128.605565, True, TIER_INNER),
    ("대봉교(중구·남구 경계, 판정보류)", 35.854937, 128.606197, False, TIER_NEAR),
    ("수성교(수성동, 판정보류)", 35.861410, 128.608928, False, TIER_NEAR),
    ("신천동(신천역 인근, 판정보류)", 35.874481, 128.616722, False, TIER_FAR),
    ("침산교(신천-금호강 합류부, 판정보류)", 35.900975, 128.592748, False, TIER_NEAR),
]
