import pytest

from climate_risk.policy.audit_log import ForbiddenPhraseError, read_audit_log, record_reviewer_ack


def test_record_and_read_round_trip(tmp_path):
    log_path = tmp_path / "ack.jsonl"

    record_reviewer_ack("COL-001", "reviewer-a", note="확인함", log_path=log_path)
    record_reviewer_ack("COL-002", "reviewer-b", log_path=log_path)

    records = read_audit_log(log_path)
    assert [r.collateral_id for r in records] == ["COL-001", "COL-002"]
    assert records[0].reviewer_id == "reviewer-a"
    assert records[0].note == "확인함"
    assert records[1].note is None


def test_forbidden_phrase_note_is_rejected_and_not_persisted(tmp_path):
    log_path = tmp_path / "ack.jsonl"

    with pytest.raises(ForbiddenPhraseError):
        record_reviewer_ack("COL-003", "reviewer-a", note="금리 인상 검토 필요", log_path=log_path)

    assert not log_path.exists()


def test_read_missing_log_returns_empty_list(tmp_path):
    assert read_audit_log(tmp_path / "does_not_exist.jsonl") == []
