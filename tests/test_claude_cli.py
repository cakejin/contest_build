"""llm/claude_cli.py — claude -p 서브프로세스 래퍼 검증.

실제 CLI를 부르지 않는다(비용·비결정성) — subprocess.run 자체를 monkeypatch해
4가지 실패 모드(성공/바이너리 없음/타임아웃/비정상 출력)만 검증한다.
"""

import json
import subprocess

import pytest

from climate_risk.llm import claude_cli


@pytest.fixture
def schema_path(tmp_path):
    path = tmp_path / "schema.json"
    path.write_text('{"type":"object"}', encoding="utf-8")
    return path


class _FakeCompletedProcess:
    def __init__(self, stdout: str, returncode: int = 0, stderr: str = ""):
        self.stdout = stdout
        self.returncode = returncode
        self.stderr = stderr


def test_call_claude_structured_returns_structured_output(monkeypatch, schema_path):
    fake_stdout = json.dumps(
        {
            "is_error": False,
            "result": '{"sections":[]}',
            "structured_output": {"sections": []},
        }
    )

    def fake_run(cmd, **kwargs):
        assert "--json-schema" in cmd
        assert "--bare" not in cmd  # bare는 API 키 인증만 읽어 이 저장소 조건과 충돌 — 실측 확인됨
        assert kwargs.get("encoding") == "utf-8"  # cp949 디코드 깨짐 방지 — 실측으로 필요성 확인됨
        return _FakeCompletedProcess(stdout=fake_stdout)

    monkeypatch.setattr(claude_cli.subprocess, "run", fake_run)

    result = claude_cli.call_claude_structured("프롬프트", schema_path)

    assert result == {"sections": []}


def test_call_claude_structured_falls_back_to_result_field(monkeypatch, schema_path):
    """structured_output 필드가 없는 CLI 버전 대비 폴백 — result 문자열을 직접 파싱."""
    fake_stdout = json.dumps({"is_error": False, "result": '{"sections":[{"text":"x","citations":[]}]}'})

    monkeypatch.setattr(
        claude_cli.subprocess, "run", lambda *a, **k: _FakeCompletedProcess(stdout=fake_stdout)
    )

    result = claude_cli.call_claude_structured("프롬프트", schema_path)

    assert result == {"sections": [{"text": "x", "citations": []}]}


def test_call_claude_structured_missing_binary_raises_unavailable(monkeypatch, schema_path):
    def fake_run(*a, **k):
        raise FileNotFoundError("claude not found")

    monkeypatch.setattr(claude_cli.subprocess, "run", fake_run)

    with pytest.raises(claude_cli.ClaudeCliUnavailableError):
        claude_cli.call_claude_structured("프롬프트", schema_path)


def test_call_claude_structured_timeout_raises(monkeypatch, schema_path):
    def fake_run(*a, **k):
        raise subprocess.TimeoutExpired(cmd="claude", timeout=90.0)

    monkeypatch.setattr(claude_cli.subprocess, "run", fake_run)

    with pytest.raises(claude_cli.ClaudeCliTimeoutError):
        claude_cli.call_claude_structured("프롬프트", schema_path)


def test_call_claude_structured_non_json_output_raises(monkeypatch, schema_path):
    monkeypatch.setattr(
        claude_cli.subprocess, "run", lambda *a, **k: _FakeCompletedProcess(stdout="not json")
    )

    with pytest.raises(claude_cli.ClaudeCliOutputError):
        claude_cli.call_claude_structured("프롬프트", schema_path)


def test_call_claude_structured_is_error_flag_raises(monkeypatch, schema_path):
    fake_stdout = json.dumps({"is_error": True, "result": "Not logged in"})
    monkeypatch.setattr(
        claude_cli.subprocess, "run", lambda *a, **k: _FakeCompletedProcess(stdout=fake_stdout)
    )

    with pytest.raises(claude_cli.ClaudeCliOutputError):
        claude_cli.call_claude_structured("프롬프트", schema_path)


def test_call_claude_structured_nonzero_exit_raises(monkeypatch, schema_path):
    fake_stdout = json.dumps({"is_error": False, "result": "internal error"})
    monkeypatch.setattr(
        claude_cli.subprocess,
        "run",
        lambda *a, **k: _FakeCompletedProcess(stdout=fake_stdout, returncode=1, stderr="boom"),
    )

    with pytest.raises(claude_cli.ClaudeCliOutputError):
        claude_cli.call_claude_structured("프롬프트", schema_path)
