"""Base class for all API modules — retry, rate limiting, progress tracking."""

import logging
import threading
import time

import requests


class BaseAPI:
    name = "base"
    base_url = ""
    request_delay = 1.0  # seconds between requests
    max_retries = 5
    timeout = 30
    requires_key = True  # False for APIs that work without authentication

    def __init__(self, api_key, db, stop_event=None):
        self.api_key = api_key
        self.db = db
        self.stop_event = stop_event or threading.Event()
        self.request_counter = 0
        self.start_time = time.time()
        self.log = logging.getLogger(self.name)

    def _should_stop(self):
        return self.stop_event.is_set()

    def _get_headers(self):
        return {"User-Agent": "SystematicReviewTool/1.0"}

    def _request_get(self, url, params=None, headers=None):
        """HTTP GET with exponential-backoff retry on 429 / 5xx / network errors."""
        time.sleep(self.request_delay)

        hdrs = self._get_headers()
        if headers:
            hdrs.update(headers)

        for attempt in range(self.max_retries):
            if self._should_stop():
                return None
            try:
                resp = requests.get(
                    url, params=params, headers=hdrs, timeout=self.timeout
                )
                if resp.status_code == 200:
                    self.request_counter += 1
                    return resp
                if resp.status_code == 429:
                    wait = min(60 * (2 ** attempt), 600)
                    self.log.warning(
                        "Rate limited (429). Waiting %ds (attempt %d/%d)",
                        wait, attempt + 1, self.max_retries,
                    )
                    time.sleep(wait)
                elif resp.status_code >= 500:
                    wait = min(10 * (2 ** attempt), 300)
                    self.log.warning(
                        "Server error %d. Retrying in %ds (attempt %d/%d)",
                        resp.status_code, wait, attempt + 1, self.max_retries,
                    )
                    time.sleep(wait)
                else:
                    self.log.error("HTTP %d for %s", resp.status_code, url)
                    return None
            except requests.RequestException as exc:
                wait = min(10 * (2 ** attempt), 300)
                self.log.warning(
                    "Request error: %s. Retrying in %ds (attempt %d/%d)",
                    exc, wait, attempt + 1, self.max_retries,
                )
                time.sleep(wait)

        self.log.error("Failed after %d retries for %s", self.max_retries, url)
        return None

    # -- Abstract interface ------------------------------------------------

    def search_term(self, term):
        """Override in subclass.  Generator that yields paper dicts."""
        raise NotImplementedError

    # -- Orchestration -----------------------------------------------------

    def run(self, terms, progress_callback=None):
        """Search all terms, skip already-completed, save to MongoDB."""
        total = len(terms)
        for idx, term in enumerate(terms, 1):
            if self._should_stop():
                self.log.info("Stop requested")
                break

            if self.db.is_search_done(self.name, term):
                self.log.info("[%d/%d] '%s' — skipped (already done)", idx, total, term)
                if progress_callback:
                    progress_callback(idx, total)
                continue

            self.log.info("[%d/%d] Searching '%s'…", idx, total, term)
            count = 0
            try:
                for paper in self.search_term(term):
                    if self._should_stop():
                        break
                    self.db.upsert_paper(paper, source_api=self.name, search_term=term)
                    count += 1
            except Exception as exc:
                self.log.error("Error searching '%s': %s", term, exc)
                # Move on to the next term rather than crashing the whole API
                continue

            if not self._should_stop():
                self.db.mark_search_done(self.name, term, count)
                self.log.info("[%d/%d] '%s' — %d papers", idx, total, term, count)

            if progress_callback:
                progress_callback(idx, total)
