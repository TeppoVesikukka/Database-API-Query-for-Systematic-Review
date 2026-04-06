"""Springer Nature API — follows nextPage links, up to 100 per page."""

from base_api import BaseAPI


class SpringerAPI(BaseAPI):
    name = "springer"
    base_url = "https://api.springernature.com/openaccess/json"
    request_delay = 1.0

    def search_term(self, term):
        query = f'"{term}"'
        next_url = None

        while True:
            if self._should_stop():
                return

            if next_url:
                resp = self._request_get(next_url)
            else:
                resp = self._request_get(self.base_url, params={
                    "q": query,
                    "api_key": self.api_key,
                    "p": 100,
                    "s": 1,
                })

            if not resp:
                return

            data = resp.json()

            for record in data.get("records", []):
                creators = record.get("creators", [])
                pub_date = record.get("publicationDate") or ""
                yield {
                    "title": record.get("title"),
                    "abstract": record.get("abstract"),
                    "authors": ", ".join(
                        c.get("creator", "") for c in creators
                    ),
                    "doi": record.get("doi"),
                    "isbn": record.get("isbn"),
                    "issn": record.get("issn"),
                    "publication_year": pub_date[:4] if pub_date else None,
                }

            next_page = data.get("nextPage")
            if not next_page:
                return
            next_url = "https://api.springernature.com" + next_page
