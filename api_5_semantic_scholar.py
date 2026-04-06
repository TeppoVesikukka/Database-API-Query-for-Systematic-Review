"""Semantic Scholar API — bulk search endpoint, token-based pagination."""

from base_api import BaseAPI

FIELDS = (
    "title,abstract,authors,year,publicationDate,externalIds,"
    "publicationVenue,citationCount,isOpenAccess"
)


class SemanticScholarAPI(BaseAPI):
    name = "semantic_scholar"
    base_url = "https://api.semanticscholar.org/graph/v1/paper/search/bulk"
    request_delay = 1.1  # 1 req/s with key
    requires_key = False  # works without, just slower

    def _get_headers(self):
        headers = super()._get_headers()
        if self.api_key:
            headers["x-api-key"] = self.api_key
        return headers

    def search_term(self, term):
        query = f'"{term}"'
        token = None

        while True:
            if self._should_stop():
                return

            params = {"query": query, "fields": FIELDS, "limit": 1000}
            if token:
                params["token"] = token

            resp = self._request_get(self.base_url, params=params)
            if not resp:
                return

            data = resp.json()

            for paper in data.get("data", []):
                ext_ids = paper.get("externalIds") or {}
                venue = paper.get("publicationVenue") or {}
                pub_date = paper.get("publicationDate") or ""
                year_raw = paper.get("year")

                yield {
                    "title": paper.get("title"),
                    "abstract": paper.get("abstract"),
                    "authors": ", ".join(
                        a.get("name", "") for a in paper.get("authors", [])
                    ) or None,
                    "doi": ext_ids.get("DOI"),
                    "isbn": None,
                    "issn": venue.get("issn"),
                    "publication_year": (
                        pub_date[:4]
                        if pub_date
                        else str(year_raw) if year_raw else None
                    ),
                    "citation_count": paper.get("citationCount"),
                    "is_open_access": paper.get("isOpenAccess"),
                }

            token = data.get("token")
            if not token:
                return
