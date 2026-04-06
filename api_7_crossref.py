"""CrossRef API — cursor-based pagination, JATS XML abstracts."""

import re

from base_api import BaseAPI


def _strip_jats(text):
    """Remove JATS XML tags from CrossRef abstract strings."""
    if not text:
        return None
    return re.sub(r"<[^>]+>", "", text).strip() or None


def _parse_year(item):
    """Extract publication year from CrossRef date-parts structure."""
    for field in ("published", "published-print", "published-online", "issued"):
        obj = item.get(field)
        if obj and isinstance(obj.get("date-parts"), list):
            parts = obj["date-parts"]
            if parts and parts[0]:
                return str(parts[0][0])
    return None


class CrossRefAPI(BaseAPI):
    name = "crossref"
    base_url = "https://api.crossref.org/works"
    request_delay = 1.1
    requires_key = False  # mailto email is optional (polite pool)

    def _get_headers(self):
        ua = "SystematicReviewTool/1.0"
        if self.api_key:  # mailto email
            ua += f" (mailto:{self.api_key})"
        return {"User-Agent": ua}

    def search_term(self, term):
        query = f'"{term}"'
        cursor = "*"

        while cursor:
            if self._should_stop():
                return

            params = {
                "query": query,
                "rows": 100,
                "cursor": cursor,
                "select": (
                    "DOI,title,abstract,author,ISSN,ISBN,"
                    "published,issued,type,publisher"
                ),
            }
            if self.api_key:
                params["mailto"] = self.api_key

            resp = self._request_get(self.base_url, params=params)
            if not resp:
                return

            data = resp.json()
            message = data.get("message", {})
            items = message.get("items", [])
            if not items:
                return

            for item in items:
                # title and container-title are always lists in CrossRef
                authors_raw = item.get("author") or []
                author_names = []
                for a in authors_raw:
                    name = f"{a.get('given', '')} {a.get('family', '')}".strip()
                    if name:
                        author_names.append(name)

                issn_list = item.get("ISSN") or []
                isbn_list = item.get("ISBN") or []

                yield {
                    "title": (item.get("title") or [None])[0],
                    "abstract": _strip_jats(item.get("abstract")),
                    "authors": ", ".join(author_names) or None,
                    "doi": item.get("DOI"),
                    "isbn": isbn_list[0] if isbn_list else None,
                    "issn": issn_list[0] if issn_list else None,
                    "publication_year": _parse_year(item),
                    "type": item.get("type"),
                    "publisher": item.get("publisher"),
                }

            cursor = message.get("next-cursor")
            # Last page: fewer items than requested
            if len(items) < 100:
                return
