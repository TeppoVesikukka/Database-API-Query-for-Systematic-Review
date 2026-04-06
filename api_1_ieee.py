"""IEEE Xplore API — 25 results per page, offset-based pagination."""

from base_api import BaseAPI


class IEEEAPI(BaseAPI):
    name = "ieee"
    base_url = "https://ieeexploreapi.ieee.org/api/v1/search/articles"
    request_delay = 1.0

    def search_term(self, term):
        query_text = f'"{term}"'
        start_record = 1
        total_records = None

        while True:
            if self._should_stop():
                return

            params = {
                "apikey": self.api_key,
                "format": "json",
                "max_records": 25,
                "start_record": start_record,
                "querytext": query_text,
            }

            resp = self._request_get(self.base_url, params=params)
            if not resp:
                return

            data = resp.json()

            if total_records is None:
                total_records = data.get("total_records", 0)
                if total_records == 0:
                    return

            for article in data.get("articles", []):
                authors_raw = article.get("authors", {}).get("authors", [])
                yield {
                    "title": article.get("title"),
                    "abstract": article.get("abstract"),
                    "authors": ", ".join(
                        a.get("full_name", "") for a in authors_raw
                    ),
                    "doi": article.get("doi"),
                    "isbn": article.get("isbn"),
                    "issn": article.get("issn"),
                    "publication_year": article.get("publication_year"),
                }

            if start_record + 24 >= total_records:
                return
            start_record += 25
