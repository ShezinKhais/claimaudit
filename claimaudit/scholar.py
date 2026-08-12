"""Semantic Scholar API client for fetching papers and their citations."""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field

import requests

from claimaudit import demo_data

log = logging.getLogger(__name__)

BASE_URL   = "https://api.semanticscholar.org/graph/v1"
RATE_SLEEP = 1.5   # seconds between requests (free tier limit)
MAX_RETRY  = 5


class ScholarError(RuntimeError):
    """Raised when the Semantic Scholar API cannot be reached or keeps rate-limiting.

    The message is written for a CLI user, since the API throttles
    unauthenticated traffic aggressively.
    """


@dataclass
class Author:
    name: str
    author_id: str = ""


@dataclass
class Paper:
    paper_id: str
    title: str
    abstract: str
    year: int | None
    authors: list[Author] = field(default_factory=list)
    citation_count: int = 0


@dataclass
class CitationContext:
    paper_id: str
    title: str
    year: int | None
    intents: list[str]       # "methodology", "background", "result"
    is_influential: bool
    context_text: str = ""


class ScholarClient:
    """Wrapper around the Semantic Scholar Graph API.

    An API key is optional but strongly recommended: unauthenticated requests
    share a very low rate limit and are often throttled. Provide one via the
    api_key argument or the SEMANTIC_SCHOLAR_API_KEY environment variable.
    Set demo=True to serve bundled sample data instead of calling the API.
    """

    def __init__(self, api_key: str = "", demo: bool = False):
        self.demo = demo
        self._session = requests.Session()
        key = api_key or os.environ.get("SEMANTIC_SCHOLAR_API_KEY")
        if key:
            self._session.headers["x-api-key"] = key

    def _get(self, path: str, params: dict) -> dict:
        """GET with retry and exponential backoff on rate limiting.

        Raises ScholarError if the API keeps returning 429 or cannot be reached,
        so the CLI can report it clearly instead of crashing with a traceback.

        Every other failure is funnelled into ScholarError too. A 5xx is treated
        as transient and retried like a 429, since the free tier serves them
        under load; a 4xx is permanent and reported at once rather than spending
        the retry budget on a request that cannot succeed.
        """
        if self.demo:
            return _demo_response(path, params)

        url = f"{BASE_URL}/{path}"
        for attempt in range(MAX_RETRY):
            try:
                # Throttle per request. This used to sit in the loops that parse
                # a response, which slept once per returned paper even though the
                # rate limit applies to requests, so asking for 20 papers cost
                # 30 seconds of doing nothing.
                time.sleep(RATE_SLEEP)
                resp = self._session.get(url, params=params, timeout=10)
            except requests.RequestException as e:
                log.error("Request failed (attempt %d/%d): %s", attempt + 1, MAX_RETRY, e)
                if attempt == MAX_RETRY - 1:
                    raise ScholarError(f"Could not reach Semantic Scholar ({e}).") from e
                time.sleep(2 ** attempt)
                continue

            if resp.status_code == 429:
                retry_after = resp.headers.get("Retry-After")
                wait = int(retry_after) if retry_after and retry_after.isdigit() \
                    else RATE_SLEEP * (2 ** (attempt + 1))
                log.warning("Rate limited (attempt %d/%d) - waiting %.0fs",
                            attempt + 1, MAX_RETRY, wait)
                time.sleep(wait)
                continue

            if resp.status_code >= 500:
                log.warning("Server error %d (attempt %d/%d) - retrying",
                            resp.status_code, attempt + 1, MAX_RETRY)
                time.sleep(2 ** attempt)
                continue

            if resp.status_code >= 400:
                raise ScholarError(
                    f"Semantic Scholar rejected the request "
                    f"(HTTP {resp.status_code}). {resp.text[:200]}"
                )

            try:
                return resp.json()
            except ValueError as e:
                raise ScholarError(
                    f"Semantic Scholar returned a response that is not JSON ({e})."
                ) from e

        raise ScholarError(
            "Semantic Scholar kept rate-limiting the request. Its free tier "
            "throttles unauthenticated traffic heavily. Set an API key in the "
            "SEMANTIC_SCHOLAR_API_KEY environment variable, or run with --demo "
            "to use bundled sample data."
        )

    def search_topic(self, query: str, limit: int = 20,
                     from_year: int = 2000, to_year: int = 2025) -> list[Paper]:
        """Search for papers on a topic with year filters."""
        data   = self._get("paper/search", {
            "query":  query,
            "limit":  limit,
            "fields": "paperId,title,abstract,year,authors,citationCount",
            "year":   f"{from_year}-{to_year}",
        })
        papers = []
        for item in data.get("data", []):
            authors = [Author(a.get("name",""), a.get("authorId",""))
                       for a in item.get("authors", [])]
            papers.append(Paper(
                paper_id=item.get("paperId",""),
                title=item.get("title",""),
                abstract=item.get("abstract","") or "",
                year=item.get("year"),
                authors=authors,
                citation_count=item.get("citationCount", 0),
            ))
        return papers

    def fetch_citations(self, paper_id: str, limit: int = 50) -> list[CitationContext]:
        """Fetch citing papers and their citation context/intent."""
        data  = self._get(f"paper/{paper_id}/citations", {
            "limit":  limit,
            "fields": "paperId,title,year,intents,isInfluential,contexts",
        })
        ctxs  = []
        for item in data.get("data", []):
            citing = item.get("citingPaper", {})
            ctxs.append(CitationContext(
                paper_id=citing.get("paperId",""),
                title=citing.get("title",""),
                year=citing.get("year"),
                intents=item.get("intents", []),
                is_influential=item.get("isInfluential", False),
                context_text=" ".join(item.get("contexts", [])),
            ))
        return ctxs


def _demo_response(path: str, params: dict) -> dict:
    """Serve bundled sample data in the shape the API would return.

    Interposing here rather than in each public method means demo runs go
    through exactly the same parsing code as live ones, so the sample path
    cannot quietly drift away from the real one.
    """
    if path == "paper/search":
        return demo_data.search_response(int(params.get("limit", 10)))
    if path.startswith("paper/") and path.endswith("/citations"):
        paper_id = path.split("/")[1]
        return demo_data.citations_response(paper_id, int(params.get("limit", 50)))
    return {"data": []}
