"""`claude -p` 서브프로세스 래퍼 — 메모 에이전트가 쓰는 유일한 LLM 호출 지점.

HANDOVER.md §A3은 "Anthropic API 직접 호출"을 확정했으나, 이 저장소는 별도
ANTHROPIC_API_KEY를 발급하지 않고 이미 인증된 `claude` CLI(Claude Code)를
서브프로세스로 호출한다 — 같은 Claude 모델을 쓰는 것이므로 벤더·리전 결정과
배치되지 않는다(DEV_LOG.md 참조). 착수 전 실측 확인 사항 셋:

1. `--json-schema`는 파일 경로가 아니라 **인라인 JSON 문자열**을 받는다(경로를 넘기면
   "not valid JSON" 파싱 에러). 스키마 파일은 읽어서 문자열로 넘긴다.
2. `--bare`는 CLAUDE.md/hooks/memory 오버헤드를 없애 훨씬 저렴하지만, "Anthropic auth is
   strictly ANTHROPIC_API_KEY or apiKeyHelper"라 OAuth 세션 인증을 읽지 않는다 —
   API 키가 없는 이 저장소 조건과 정면으로 충돌해 실측 결과 "Not logged in" 에러가 났다.
   **`--bare`를 쓰지 않는다** — 대신 일반 모드로 이 세션의 기존 인증을 그대로 재사용한다.
3. `--output-format json` 응답에는 스키마 검증이 이미 끝난 `structured_output` 필드가
   파싱된 객체로 들어있다 — `result`(문자열)를 다시 `json.loads`할 필요가 없다.

일반 모드는 CLAUDE.md/프로젝트 컨텍스트를 불러오는 만큼 비용이 실측 확인됐다(1회당 약
$0.20, 5~10초) — 데모에서 메모 생성 몇 건 정도는 문제없는 규모이지 반복 배치 호출에는
부적합하다(포트폴리오 배치 재계산은 이 함수를 호출하지 않는다 — 화이트박스 계량 코어만
쓴다, 설계원칙5).

**보안**: 프롬프트 인젝션 방어를 위해 이 호출은 Bash/Read/Write/Edit 등 부작용 있는
도구에 접근할 수 없도록 `--disallowedTools`로 명시 차단하고 `--strict-mcp-config`로
외부 MCP 서버 접근도 막는다 — 메모 생성이라는 좁은 텍스트 변환 작업에 파일시스템·네트워크
부작용을 허용할 이유가 없다(HANDOVER §⑥ 레드팀 시나리오3 "인용 검증 우회" 방어와 같은 정신).
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

_DISALLOWED_TOOLS = ["Bash", "Read", "Write", "Edit", "NotebookEdit", "WebFetch", "WebSearch"]


class ClaudeCliError(RuntimeError):
    """claude -p 호출 실패의 공통 베이스."""


class ClaudeCliUnavailableError(ClaudeCliError):
    """`claude` 실행 파일을 찾을 수 없음(FileNotFoundError)."""


class ClaudeCliTimeoutError(ClaudeCliError):
    """지정 시간 내 응답이 오지 않음."""


class ClaudeCliOutputError(ClaudeCliError):
    """비정상 종료 코드이거나 응답이 예상 JSON 구조가 아님."""


def call_claude_structured(
    prompt: str,
    json_schema_path: Path,
    model: str = "sonnet",
    timeout_s: float = 90.0,
) -> dict:
    """`prompt`를 `claude -p`로 실행해 `json_schema_path`에 맞는 구조화 출력을 반환한다.

    이 저장소에서 `claude` 바이너리를 서브프로세스로 호출하는 유일한 함수 —
    테스트는 이 함수 자체를 monkeypatch해 실제 CLI를 부르지 않는다.
    """
    schema_text = json_schema_path.read_text(encoding="utf-8")

    cmd = [
        "claude",
        "-p",
        "--output-format",
        "json",
        "--json-schema",
        schema_text,
        "--model",
        model,
        "--disallowedTools",
        *_DISALLOWED_TOOLS,
        "--strict-mcp-config",
        "--no-session-persistence",
        prompt,
    ]

    try:
        # Windows에서 subprocess.run(text=True)는 로케일 기본 코드페이지(cp949)로 디코드를
        # 시도해 claude -p의 UTF-8 한글 출력이 깨진다(scripts/run_assessment.py의 stdout
        # reconfigure와 같은 계열의 문제, DEV_LOG.md 2026-08-09 참조) — encoding을 명시한다.
        proc = subprocess.run(
            cmd, capture_output=True, text=True, encoding="utf-8", timeout=timeout_s
        )
    except FileNotFoundError as exc:
        raise ClaudeCliUnavailableError("claude CLI를 찾을 수 없습니다 (PATH 확인 필요)") from exc
    except subprocess.TimeoutExpired as exc:
        raise ClaudeCliTimeoutError(f"claude -p 응답이 {timeout_s}초 내 오지 않았습니다") from exc

    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise ClaudeCliOutputError(
            f"claude -p 출력이 JSON이 아닙니다 (exit={proc.returncode}): {proc.stdout[:500]!r}"
        ) from exc

    if proc.returncode != 0 or data.get("is_error"):
        raise ClaudeCliOutputError(
            f"claude -p 실행 실패 (exit={proc.returncode}): {data.get('result', proc.stderr)[:500]!r}"
        )

    structured = data.get("structured_output")
    if structured is not None:
        return structured

    # 폴백 — structured_output 필드가 없는 CLI 버전을 대비해 result 문자열을 직접 파싱.
    try:
        return json.loads(data["result"])
    except (KeyError, json.JSONDecodeError) as exc:
        raise ClaudeCliOutputError(f"claude -p 응답에서 구조화 출력을 찾을 수 없습니다: {data!r}") from exc
