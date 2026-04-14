from refcheck.extract.linker import check_orphans
from refcheck.schema.models import Reference, Author, Citation


def test_detects_orphan_citation():
    refs = [Reference(id="ref_001", authors=[Author(family="A")], year=2020,
                      title="T", raw_text="...", style_detected="APA")]
    cits = [Citation(id="cit_001", surface="(Unknown, 2025)", ref_ids=[],
                     char_offset=0, containing_sentence="...", surrounding_paragraph="...")]
    orphan_cits, orphan_refs = check_orphans(cits, refs)
    assert "cit_001" in orphan_cits
    assert "ref_001" in orphan_refs


def test_detects_orphan_reference():
    refs = [
        Reference(id="ref_001", authors=[Author(family="A")], year=2020,
                  title="Used", raw_text="...", style_detected="APA"),
        Reference(id="ref_002", authors=[Author(family="B")], year=2021,
                  title="Unused", raw_text="...", style_detected="APA"),
    ]
    cits = [Citation(id="cit_001", surface="(A, 2020)", ref_ids=["ref_001"],
                     char_offset=0, containing_sentence="...", surrounding_paragraph="...")]
    orphan_cits, orphan_refs = check_orphans(cits, refs)
    assert orphan_cits == []
    assert orphan_refs == ["ref_002"]


def test_all_linked():
    refs = [Reference(id="ref_001", authors=[Author(family="A")], year=2020,
                      title="T", raw_text="...", style_detected="APA")]
    cits = [Citation(id="cit_001", surface="(A, 2020)", ref_ids=["ref_001"],
                     char_offset=0, containing_sentence="...", surrounding_paragraph="...")]
    orphan_cits, orphan_refs = check_orphans(cits, refs)
    assert orphan_cits == []
    assert orphan_refs == []
