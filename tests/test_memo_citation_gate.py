from climate_risk.memo.citation_gate import verify_citations
from climate_risk.memo.schema import REASON_NO_CITATION, REASON_UNKNOWN_SOURCE_ID, MemoSection

_KNOWN = {"flood:a.shp", "building:123", "scenario:mc:seed=42"}


def test_valid_citation_is_accepted():
    sections = [MemoSection(text="침수 tier는 내부입니다.", citations=["flood:a.shp"])]

    result = verify_citations(sections, _KNOWN)

    assert result.accepted == sections
    assert result.rejected == []
    assert result.citation_failure_rate == 0.0


def test_empty_citations_is_rejected_as_no_citation():
    sections = [MemoSection(text="근거 없는 문장입니다.", citations=[])]

    result = verify_citations(sections, _KNOWN)

    assert result.accepted == []
    assert len(result.rejected) == 1
    assert result.rejected[0].reason == REASON_NO_CITATION
    assert result.citation_failure_rate == 1.0


def test_unknown_source_id_is_rejected():
    sections = [MemoSection(text="지어낸 근거입니다.", citations=["flood:nonexistent.shp"])]

    result = verify_citations(sections, _KNOWN)

    assert result.accepted == []
    assert result.rejected[0].reason == REASON_UNKNOWN_SOURCE_ID


def test_mixed_batch_computes_correct_failure_rate():
    sections = [
        MemoSection(text="valid1", citations=["flood:a.shp"]),
        MemoSection(text="valid2", citations=["building:123"]),
        MemoSection(text="no citation", citations=[]),
        MemoSection(text="bad citation", citations=["made:up"]),
    ]

    result = verify_citations(sections, _KNOWN)

    assert len(result.accepted) == 2
    assert len(result.rejected) == 2
    assert result.citation_failure_rate == 0.5


def test_empty_sections_list_has_zero_failure_rate():
    result = verify_citations([], _KNOWN)

    assert result.accepted == []
    assert result.rejected == []
    assert result.citation_failure_rate == 0.0
