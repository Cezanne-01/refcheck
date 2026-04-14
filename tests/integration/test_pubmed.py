import pytest
import respx
from httpx import Response
from refcheck.fetch.pubmed import PubMedClient
from refcheck.schema.models import Author


ESEARCH_XML = """<?xml version="1.0"?>
<eSearchResult><IdList><Id>23500103</Id></IdList></eSearchResult>"""

EFETCH_XML = """<?xml version="1.0"?>
<PubmedArticleSet>
  <PubmedArticle><MedlineCitation>
    <PMID>23500103</PMID>
    <Article>
      <Journal><Title>Current Opinion in Neurobiology</Title>
        <JournalIssue><Volume>23</Volume><Issue>4</Issue>
          <PubDate><Year>2013</Year></PubDate></JournalIssue></Journal>
      <ArticleTitle>Neurobiology of gambling</ArticleTitle>
      <Pagination><MedlinePgn>660-7</MedlinePgn></Pagination>
      <Abstract><AbstractText>Gambling disorder is...</AbstractText></Abstract>
      <AuthorList><Author>
        <LastName>Potenza</LastName><ForeName>Marc N</ForeName>
      </Author></AuthorList>
      <ELocationID EIdType="doi">10.1016/j.conb.2013.01.020</ELocationID>
    </Article>
  </MedlineCitation></PubmedArticle>
</PubmedArticleSet>"""


@pytest.mark.asyncio
@respx.mock
async def test_search_two_step():
    respx.get("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi").mock(
        return_value=Response(200, text=ESEARCH_XML)
    )
    respx.get("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi").mock(
        return_value=Response(200, text=EFETCH_XML)
    )
    client = PubMedClient()
    result = await client.search(
        title="Neurobiology of gambling",
        authors=[Author(family="Potenza")],
        year=2013,
    )
    assert result is not None
    assert result.reference.year == 2013
    assert result.reference.doi == "10.1016/j.conb.2013.01.020"
    assert "Gambling disorder" in result.abstract
    await client.close()
