"""PubMed (NCBI E-Utilities) API — two-phase: esearch for PMIDs, efetch for details."""

import xml.etree.ElementTree as ET

from base_api import BaseAPI


class PubMedAPI(BaseAPI):
    name = "pubmed"
    base_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
    request_delay = 0.35  # 10 req/s with API key, 3 req/s without

    def _get_pmids(self, term):
        """Phase 1: collect all PubMed IDs matching the search term."""
        pmids = []
        retstart = 0
        retmax = 100

        while True:
            if self._should_stop():
                return pmids

            resp = self._request_get(
                f"{self.base_url}/esearch.fcgi",
                params={
                    "db": "pubmed",
                    "term": f'"{term}"',
                    "retstart": retstart,
                    "retmax": retmax,
                    "api_key": self.api_key,
                },
            )
            if not resp:
                break

            root = ET.fromstring(resp.content)
            batch = [pid.text for pid in root.findall("IdList/Id")]
            if not batch:
                break

            pmids.extend(batch)
            retstart += retmax

        return pmids

    def _fetch_details(self, pmids):
        """Phase 2: fetch full article metadata for a batch of PMIDs."""
        resp = self._request_get(
            f"{self.base_url}/efetch.fcgi",
            params={
                "db": "pubmed",
                "id": ",".join(pmids),
                "retmode": "xml",
                "api_key": self.api_key,
            },
        )
        if not resp:
            return []

        root = ET.fromstring(resp.content)
        papers = []

        for pm_article in root.findall("PubmedArticle"):
            citation = pm_article.find("MedlineCitation")
            if citation is None:
                continue
            article = citation.find("Article")
            if article is None:
                continue

            # Title
            title_el = article.find("ArticleTitle")
            title = title_el.text if title_el is not None else None

            # Abstract
            abstract_el = article.find("Abstract/AbstractText")
            abstract = abstract_el.text if abstract_el is not None else None

            # Authors
            author_list = article.find("AuthorList")
            authors = []
            if author_list is not None:
                for author in author_list.findall("Author"):
                    last = author.find("LastName")
                    fore = author.find("ForeName")
                    if last is not None and fore is not None:
                        authors.append(f"{fore.text} {last.text}")

            # DOI
            doi = None
            id_list = pm_article.find("PubmedData/ArticleIdList")
            if id_list is not None:
                for aid in id_list:
                    if aid.attrib.get("IdType") == "doi":
                        doi = aid.text

            # ISSN
            journal = article.find("Journal")
            issn_el = journal.find("ISSN") if journal is not None else None
            issn = issn_el.text if issn_el is not None else None

            # Year
            year_el = (
                article.find("Journal/JournalIssue/PubDate/Year")
                if article is not None
                else None
            )
            year = year_el.text if year_el is not None else None

            papers.append({
                "title": title,
                "abstract": abstract,
                "authors": ", ".join(authors) if authors else None,
                "doi": doi,
                "isbn": None,
                "issn": issn,
                "publication_year": year,
            })

        return papers

    def search_term(self, term):
        pmids = self._get_pmids(term)
        if not pmids:
            return

        for i in range(0, len(pmids), 100):
            if self._should_stop():
                return
            batch = pmids[i : i + 100]
            for paper in self._fetch_details(batch):
                yield paper
