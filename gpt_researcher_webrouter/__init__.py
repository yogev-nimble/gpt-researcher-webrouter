"""GPT Researcher retriever plugin for WebRouter (https://docs.webrouter.net).

Install it next to GPT Researcher and set ``RETRIEVER=webrouter``. No API key is needed:
WebRouter searches keylessly, and uses every provider key it finds in the environment
(``TAVILY_API_KEY``, ``EXA_API_KEY``, ``BRAVE_API_KEY``, ...) to route and fall back.
Set ``WEBROUTER_PROVIDER`` to pin one provider. The results are links that GPT Researcher
scrapes, so ``requires_scraping`` is True.
"""

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from web_router import ConfigurationError, SearchResponse, WebRouter

try:  # Subclassing is optional; it documents the contract when GPT Researcher is installed.
    from gpt_researcher.retrievers.base import BaseRetriever
except ImportError:  # pragma: no cover - GPT Researcher is always present at runtime
    BaseRetriever = object  # type: ignore[misc,assignment]

__all__ = ["WebRouterSearch"]
__version__ = "0.1.0"

logger = logging.getLogger(__name__)

TIMEOUT = 30.0
#: Snippets are only a preview (the page is scraped), so keep them short for the planning prompt.
MAX_BODY_CHARS = 500


def _off_loop[T](call: Callable[[], T]) -> T:
    """Run ``call`` on a worker thread when this thread has a running event loop.

    GPT Researcher calls ``search()`` both from a worker thread and directly in its event loop.
    The synchronous WebRouter warns when used inside a loop; the call blocks either way, as every
    built-in retriever's HTTP call does.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return call()
    with ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(call).result()


class WebRouterSearch(BaseRetriever):  # type: ignore[misc]
    """Search the web through WebRouter for GPT Researcher.

    Reads ``WEBROUTER_PROVIDER`` (optional) and any provider keys WebRouter supports.
    """

    requires_scraping = True

    def __init__(self, query: str, query_domains: list[str] | None = None) -> None:
        self.query = query
        self.query_domains = [d.strip() for d in (query_domains or []) if isinstance(d, str) and d.strip()]
        self.provider = (os.environ.get("WEBROUTER_PROVIDER") or "").strip() or None

    def search(self, max_results: int = 7) -> list[dict[str, Any]]:
        """Return up to ``max_results`` results as ``{"href", "body", "title"}`` dicts, or ``[]`` on any error."""
        if max_results <= 0:
            return []
        try:
            response = _off_loop(lambda: self._search(max_results))
        except ConfigurationError as exc:  # e.g. a mistyped WEBROUTER_PROVIDER: not a transient failure
            logger.error("WebRouter is misconfigured: %s", exc)
            return []
        except Exception as exc:  # one failing provider must not stop a research run
            logger.warning("WebRouter search failed: %s: %s", type(exc).__name__, exc)
            return []
        results = []
        for result in response.results:
            if not result.url.startswith(("http://", "https://")):
                continue
            body = result.description or result.content
            results.append({"href": result.url, "body": body[:MAX_BODY_CHARS], "title": result.title})
            if len(results) >= max_results:
                break
        return results

    def _search(self, max_results: int) -> SearchResponse:
        with WebRouter() as router:
            return router.search(
                self.query,
                provider=self.provider,
                max_results=max_results,
                include_domains=self.query_domains or None,
                timeout=TIMEOUT,
                data_apis=False,
            )
