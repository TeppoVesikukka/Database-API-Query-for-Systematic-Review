"""MongoDB wrapper — paper storage, deduplication, search progress tracking."""

import logging
import re
from datetime import datetime, timezone

from pymongo import MongoClient

log = logging.getLogger(__name__)


def _normalize_title(title):
    """Lowercase, strip punctuation and extra whitespace for dedup matching."""
    if not title:
        return None
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", "", title.lower())).strip()


def _clean_doi(doi):
    """Return a usable DOI string or None."""
    if not doi or doi in ("null", "No DOI", ""):
        return None
    # Strip URL prefix if present (OpenAlex returns full URLs)
    return re.sub(r"^https?://doi\.org/", "", doi.strip())


class Database:
    def __init__(self, uri, db_name):
        self.client = MongoClient(uri)
        self.db = self.client[db_name]
        self.papers = self.db["papers"]
        self.progress = self.db["search_progress"]
        self._ensure_indexes()

    def _ensure_indexes(self):
        # DOI-based dedup — sparse so papers without DOI can coexist
        self.papers.create_index("doi", unique=True, sparse=True)
        # Fallback dedup for papers without DOI
        self.papers.create_index(
            [("title_normalized", 1), ("publication_year", 1)]
        )
        # Fast progress lookups
        self.progress.create_index(
            [("api_name", 1), ("search_term", 1)], unique=True
        )

    def upsert_paper(self, paper, source_api, search_term):
        """Insert or update a paper with cross-API deduplication."""
        now = datetime.now(timezone.utc)
        doi = _clean_doi(paper.get("doi"))
        paper["doi"] = doi
        paper["title_normalized"] = _normalize_title(paper.get("title"))

        # Fields that should not collide with $addToSet
        update_fields = {
            k: v for k, v in paper.items()
            if k not in ("source_apis", "search_terms")
        }
        update_fields["updated_at"] = now

        update_op = {
            "$set": update_fields,
            "$setOnInsert": {"created_at": now},
            "$addToSet": {
                "source_apis": source_api,
                "search_terms": search_term,
            },
        }

        if doi:
            self.papers.update_one({"doi": doi}, update_op, upsert=True)
        else:
            # Fallback: match on normalized title + year
            title_norm = paper.get("title_normalized")
            year = paper.get("publication_year")
            if title_norm and year:
                self.papers.update_one(
                    {"title_normalized": title_norm, "publication_year": year},
                    update_op,
                    upsert=True,
                )
            else:
                # No dedup possible — insert as-is
                paper.update({
                    "source_apis": [source_api],
                    "search_terms": [search_term],
                    "created_at": now,
                    "updated_at": now,
                })
                self.papers.insert_one(paper)

    # -- Search progress tracking ------------------------------------------

    def is_search_done(self, api_name, term):
        return self.progress.find_one(
            {"api_name": api_name, "search_term": term, "status": "completed"}
        ) is not None

    def mark_search_done(self, api_name, term, count):
        self.progress.update_one(
            {"api_name": api_name, "search_term": term},
            {"$set": {
                "status": "completed",
                "result_count": count,
                "completed_at": datetime.now(timezone.utc),
            }},
            upsert=True,
        )

    # -- Stats -------------------------------------------------------------

    def get_stats(self):
        total = self.papers.count_documents({})
        dois = self.papers.count_documents({"doi": {"$ne": None}})
        searches = self.progress.count_documents({"status": "completed"})
        return {
            "total_papers": total,
            "papers_with_doi": dois,
            "searches_completed": searches,
        }

    def close(self):
        self.client.close()
