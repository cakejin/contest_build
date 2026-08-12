"""레드팀 최우선 시나리오(1·2·4·9) 라이브 데모 CLI — Week4 Done기준
"레드팀 프롬프트를 라이브로 입력했을 때 보호규율대로 반응"의 실물.

인자 없이 실행하면 시나리오 1/2/4/9 체크를 전부 돌려 PASS/FAIL을 출력한다.
`--reviewer-note`를 주면 그 문구를 실제 감사로그 확인 메모 경로
(policy/audit_log.record_reviewer_ack)에 그대로 흘려보내, 금지어가 있으면
그 자리에서 ForbiddenPhraseError가 라이브로 발생하는 것을 보여준다(감사로그
파일에는 실제로 쓰지 않도록 임시 경로를 쓴다).

사용 예:
    python scripts/run_redteam_demo.py
    python scripts/run_redteam_demo.py --reviewer-note "이 지역은 LTV 하향이 필요합니다"
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from climate_risk.policy.audit_log import ForbiddenPhraseError, record_reviewer_ack  # noqa: E402
from climate_risk.policy.redteam_checks import run_all_redteam_checks  # noqa: E402


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="레드팀 시나리오 1/2/4/9 방어 확인")
    parser.add_argument(
        "--reviewer-note",
        help="심사역 확인 메모로 흘려보낼 텍스트 — 금지어가 있으면 즉시 ForbiddenPhraseError 발생",
    )
    args = parser.parse_args()

    results = run_all_redteam_checks()
    print(json.dumps({"redteam_checks": results}, ensure_ascii=False, indent=2, default=str))

    all_passed = all(r["passed"] for r in results)
    print(f"\n시나리오1/2/4/9 전체 통과: {all_passed}", file=sys.stderr)

    if args.reviewer_note is not None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            log_path = Path(tmp_dir) / "reviewer_ack_log.jsonl"
            print(f"\n--reviewer-note 라이브 시연: {args.reviewer_note!r}", file=sys.stderr)
            try:
                record = record_reviewer_ack(
                    collateral_id="DEMO", reviewer_id="DEMO", note=args.reviewer_note, log_path=log_path
                )
                print(f"기록 성공(금지어 없음): {record}", file=sys.stderr)
            except ForbiddenPhraseError as e:
                print(f"차단됨(ForbiddenPhraseError): {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
