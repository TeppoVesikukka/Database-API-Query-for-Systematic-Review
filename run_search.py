#!/usr/bin/env python3
"""CLI entry point for systematic review — multi-API search."""

import argparse
import concurrent.futures
import logging
import signal
import sys
import threading

from rich.console import Console
from rich.logging import RichHandler
from rich.progress import (
    BarColumn,
    MofNColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeRemainingColumn,
)

from config import MONGO_DB, MONGO_URI, load_api_keys, load_search_terms
from db import Database
from api_1_ieee import IEEEAPI
from api_2_springer import SpringerAPI
from api_3_scopus import ScopusAPI
from api_4_pubmed import PubMedAPI
from api_5_semantic_scholar import SemanticScholarAPI
from api_6_openalex import OpenAlexAPI
from api_7_crossref import CrossRefAPI

console = Console()

# Placeholder strings used in api_keys.json that mean "not configured"
_PLACEHOLDERS = {"", "IEEE API key", "Springer API key", "Scopus API key",
                 "PubMed API key", "Semantic Scholar API key"}


def _key_is_set(value):
    return bool(value) and value not in _PLACEHOLDERS


def build_apis(keys, db, stop_event):
    """Instantiate API objects for all configured APIs."""
    apis = []

    if _key_is_set(keys.get("ieee_api_key")):
        apis.append(IEEEAPI(keys["ieee_api_key"], db, stop_event))

    if _key_is_set(keys.get("springer_api_key")):
        apis.append(SpringerAPI(keys["springer_api_key"], db, stop_event))

    if _key_is_set(keys.get("scopus_api_key")):
        apis.append(ScopusAPI(
            keys["scopus_api_key"], db, stop_event,
            insttoken=keys.get("scopus_insttoken", ""),
        ))

    if _key_is_set(keys.get("pubmed_api_key")):
        apis.append(PubMedAPI(keys["pubmed_api_key"], db, stop_event))

    # These three work without a key (key is optional / email for polite pool)
    apis.append(SemanticScholarAPI(
        keys.get("semantic_scholar_api_key", ""), db, stop_event
    ))
    apis.append(OpenAlexAPI(
        keys.get("openalex_email", ""), db, stop_event
    ))
    apis.append(CrossRefAPI(
        keys.get("crossref_mailto", ""), db, stop_event
    ))

    return apis


def main():
    parser = argparse.ArgumentParser(
        description="Systematic review — search academic databases for cognitive biases"
    )
    parser.add_argument(
        "--apis", nargs="*",
        help="Run only specific APIs (e.g. --apis ieee scopus openalex)",
    )
    parser.add_argument(
        "--terms-file", default="search_terms.json",
        help="Path to search terms JSON file",
    )
    parser.add_argument(
        "--keys-file", default="api_keys.json",
        help="Path to API keys JSON file",
    )
    args = parser.parse_args()

    # -- Logging -----------------------------------------------------------
    logging.basicConfig(
        level=logging.INFO,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[
            RichHandler(console=console, show_path=False, markup=True),
            logging.FileHandler("search.log"),
        ],
    )
    log = logging.getLogger("main")

    # -- Load configuration ------------------------------------------------
    keys = load_api_keys(args.keys_file)
    terms = load_search_terms(args.terms_file)
    log.info("Loaded %d search terms", len(terms))

    db = Database(MONGO_URI, MONGO_DB)
    stop_event = threading.Event()

    # Ctrl+C → graceful shutdown
    def handle_sigint(_sig, _frame):
        console.print("\n[yellow]Ctrl+C — stopping gracefully…[/yellow]")
        stop_event.set()

    signal.signal(signal.SIGINT, handle_sigint)

    # -- Build API list ----------------------------------------------------
    all_apis = build_apis(keys, db, stop_event)

    if args.apis:
        all_apis = [a for a in all_apis if a.name in args.apis]

    if not all_apis:
        console.print("[red]No APIs configured. Check api_keys.json.[/red]")
        sys.exit(1)

    api_names = ", ".join(a.name for a in all_apis)
    console.print(
        f"[bold]Starting search: {len(all_apis)} APIs × {len(terms)} terms[/bold]"
    )
    console.print(f"APIs: {api_names}\n")

    # -- Run search with progress bars ------------------------------------
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNColumn(),
        TimeRemainingColumn(),
        console=console,
    ) as progress:
        tasks = {}
        for api in all_apis:
            tasks[api.name] = progress.add_task(
                f"[cyan]{api.name}", total=len(terms)
            )

        def run_one(api):
            def cb(done, _total):
                progress.update(tasks[api.name], completed=done)
            api.run(terms, progress_callback=cb)

        with concurrent.futures.ThreadPoolExecutor(
            max_workers=len(all_apis)
        ) as pool:
            futures = {pool.submit(run_one, api): api for api in all_apis}
            for future in concurrent.futures.as_completed(futures):
                api = futures[future]
                try:
                    future.result()
                except Exception as exc:
                    log.error("%s crashed: %s", api.name, exc)

    # -- Summary -----------------------------------------------------------
    stats = db.get_stats()
    console.print("\n[bold green]Done![/bold green]")
    console.print(f"  Total papers in DB:   {stats['total_papers']}")
    console.print(f"  Papers with DOI:      {stats['papers_with_doi']}")
    console.print(f"  Searches completed:   {stats['searches_completed']}")

    db.close()


if __name__ == "__main__":
    main()
