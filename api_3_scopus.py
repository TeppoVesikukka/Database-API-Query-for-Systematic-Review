"""Scopus (Elsevier) API — follows next links, 25 results per page."""

from base_api import BaseAPI


class ScopusAPI(BaseAPI):
    name = "scopus"
    base_url = "https://api.elsevier.com/content/search/scopus"
    request_delay = 1.0

    def __init__(self, api_key, db, stop_event=None, insttoken=""):
        super().__init__(api_key, db, stop_event)
        self.insttoken = insttoken

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
                    "query": query,
                    "httpAccept": "application/json",
                    "count": 25,
                    "view": "COMPLETE",
                    "apikey": self.api_key,
                    "insttoken": self.insttoken,
                })

            if not resp:
                return

            data = resp.json()
            search_results = data.get("search-results", {})

            for entry in search_results.get("entry", []):
                # Skip error entries (Scopus returns these for empty results)
                if entry.get("error"):
                    continue
                authors = entry.get("author") or []
                cover_date = entry.get("prism:coverDate", "")
                yield {
                    "title": entry.get("dc:title"),
                    "abstract": entry.get("dc:description"),
                    "authors": ", ".join(
                        a.get("authname", "") for a in authors
                    ),
                    "doi": entry.get("prism:doi"),
                    "isbn": entry.get("prism:isbn"),
                    "issn": entry.get("prism:issn"),
                    "publication_year": cover_date[:4] if cover_date else None,
                }

            # Follow the 'next' link for pagination
            links = search_results.get("link", [])
            next_link = next(
                (lk["@href"] for lk in links if lk.get("@ref") == "next"),
                None,
            )
            if not next_link:
                return
            next_url = next_link
