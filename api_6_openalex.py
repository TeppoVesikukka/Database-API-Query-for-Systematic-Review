"""OpenAlex API — cursor-based pagination, inverted-index abstracts."""

import re

from base_api import BaseAPI

SELECT_FIELDS = (
    "id,doi,display_name,publication_year,publication_date,type,language,"
    "primary_location,open_access,authorships,cited_by_count,"
    "abstract_inverted_index,is_retracted"
)


def _reconstruct_abstract(inv_index):
    """Rebuild plain text from OpenAlex's inverted-index format."""
    if not inv_index:
        return None
    words = [
        (pos, word)
        for word, positions in inv_index.items()
        for pos in positions
    ]
    return " ".join(w for _, w in sorted(words))


class OpenAlexAPI(BaseAPI):
    name = "openalex"
    base_url = "https://api.openalex.org/works"
    request_delay = 1.1
    requires_key = False

    def _get_headers(self):
        ua = "SystematicReviewTool/1.0"
        if self.api_key:  # email for polite pool
            ua += f" (mailto:{self.api_key})"
        return {"User-Agent": ua}

    def search_term(self, term):
        query = f'"{term}"'
        cursor = "*"

        while cursor:
            if self._should_stop():
                return

            params = {
                "search": query,
                "per-page": 100,
                "select": SELECT_FIELDS,
                "cursor": cursor,
            }

            resp = self._request_get(self.base_url, params=params)
            if not resp:
                return

            data = resp.json()
            results = data.get("results", [])
            if not results:
                return

            for work in results:
                primary_loc = work.get("primary_location") or {}
                source = primary_loc.get("source") or {}
                issn_list = source.get("issn") or []
                doi_raw = work.get("doi") or ""
                doi = (
                    re.sub(r"^https?://doi\.org/", "", doi_raw)
                    if doi_raw
                    else None
                )
                pub_date = work.get("publication_date") or ""
                year_raw = work.get("publication_year")

                yield {
                    "title": work.get("display_name"),
                    "abstract": _reconstruct_abstract(
                        work.get("abstract_inverted_index")
                    ),
                    "authors": ", ".join(
                        a.get("author", {}).get("display_name", "")
                        for a in work.get("authorships", [])
                    ) or None,
                    "doi": doi,
                    "isbn": None,
                    "issn": issn_list[0] if issn_list else None,
                    "publication_year": (
                        pub_date[:4]
                        if pub_date
                        else str(year_raw) if year_raw else None
                    ),
                    "cited_by_count": work.get("cited_by_count"),
                    "is_open_access": (work.get("open_access") or {}).get(
                        "is_oa"
                    ),
                    "type": work.get("type"),
                    "language": work.get("language"),
                    "is_retracted": work.get("is_retracted"),
                }

            cursor = data.get("meta", {}).get("next_cursor")
