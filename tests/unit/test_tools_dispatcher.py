from refcheck.llm.tools import (
    METADATA_TOOLS,
    CONTENT_TOOLS,
    SUBMIT_METADATA_FINAL,
    SUBMIT_CONTENT_FINAL,
)


def test_metadata_tools_include_all_search_apis():
    names = {t["function"]["name"] for t in METADATA_TOOLS}
    assert "search_crossref" in names
    assert "search_openalex" in names
    assert "search_semantic_scholar" in names
    assert "search_pubmed" in names
    assert "lookup_doi_crossref" in names
    assert "submit_final" in names


def test_content_tools_include_passage_search():
    names = {t["function"]["name"] for t in CONTENT_TOOLS}
    assert "find_passage" in names
    assert "fetch_full_text" in names
    assert "fetch_abstract" in names
    assert "submit_final" in names


def test_final_tools_have_strict_schemas():
    assert SUBMIT_METADATA_FINAL["function"]["strict"] is True
    assert "status" in SUBMIT_METADATA_FINAL["function"]["parameters"]["properties"]
    assert SUBMIT_CONTENT_FINAL["function"]["strict"] is True
    assert "category" in SUBMIT_CONTENT_FINAL["function"]["parameters"]["properties"]
