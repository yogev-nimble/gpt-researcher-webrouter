"""Offline tests for the webrouter retriever plugin (WebRouter replaced by a fake)."""

from __future__ import annotations

import asyncio
import logging
import warnings
from importlib.metadata import entry_points
from typing import Any

import pytest
from web_router import ConfigurationError, SearchResponse, SearchResult

import gpt_researcher_webrouter as plugin
from gpt_researcher_webrouter import WebRouterSearch

RESULTS = [
    SearchResult(url="https://gptr.dev/", title="GPT Researcher", description="Autonomous research.", content="x"),
    SearchResult(url="https://example.com/", title="No description", content="Page body."),
    SearchResult(url="ftp://example.com/", title="Not a web link", description="skip me"),
    SearchResult(url="https://third.example/", title="Third", description="d" * 2000),
]


class FakeRouter:
    calls: list[dict[str, Any]] = []
    error: Exception | None = None
    results: list[SearchResult] = RESULTS

    def __enter__(self) -> FakeRouter:
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def search(self, query: str, **kwargs: Any) -> SearchResponse:
        FakeRouter.calls.append({"query": query, **kwargs})
        try:  # WebRouter warns when its sync API runs inside an event loop
            asyncio.get_running_loop()
            warnings.warn("WebRouter.search() was called inside a running event loop", RuntimeWarning, stacklevel=2)
        except RuntimeError:
            pass
        if FakeRouter.error is not None:
            raise FakeRouter.error
        return SearchResponse(provider="fake", query=query, results=FakeRouter.results)


@pytest.fixture(autouse=True)
def fake_router(monkeypatch: pytest.MonkeyPatch) -> type[FakeRouter]:
    FakeRouter.calls = []
    FakeRouter.error = None
    FakeRouter.results = RESULTS
    monkeypatch.setattr(plugin, "WebRouter", FakeRouter)
    monkeypatch.delenv("WEBROUTER_PROVIDER", raising=False)
    return FakeRouter


def test_entry_point_is_registered() -> None:
    names = {ep.name: ep.value for ep in entry_points(group="gpt_researcher.retrievers")}
    assert names["webrouter"] == "gpt_researcher_webrouter:WebRouterSearch"


def test_search_returns_href_body_title() -> None:
    results = WebRouterSearch("gpt researcher").search(max_results=7)

    assert results[:2] == [
        {"href": "https://gptr.dev/", "body": "Autonomous research.", "title": "GPT Researcher"},
        {"href": "https://example.com/", "body": "Page body.", "title": "No description"},
    ]
    assert results[2]["href"] == "https://third.example/"
    assert len(results[2]["body"]) == plugin.MAX_BODY_CHARS
    assert len(results) == 3
    assert WebRouterSearch.requires_scraping is True


def test_keyless_defaults_reach_webrouter(fake_router: type[FakeRouter]) -> None:
    WebRouterSearch("q").search(max_results=5)

    assert fake_router.calls == [
        {
            "query": "q",
            "provider": None,
            "max_results": 5,
            "include_domains": None,
            "timeout": plugin.TIMEOUT,
            "data_apis": False,
        }
    ]


def test_provider_and_domains_are_passed(fake_router: type[FakeRouter], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WEBROUTER_PROVIDER", " tavily ")
    WebRouterSearch("q", query_domains=[" docs.gptr.dev ", "", None, "github.com"]).search()

    assert fake_router.calls[0]["provider"] == "tavily"
    assert fake_router.calls[0]["include_domains"] == ["docs.gptr.dev", "github.com"]


def test_max_results(fake_router: type[FakeRouter]) -> None:
    assert len(WebRouterSearch("q").search(max_results=1)) == 1
    assert WebRouterSearch("q").search(max_results=0) == []
    assert len(fake_router.calls) == 1


def test_failure_returns_empty_and_warns(fake_router: type[FakeRouter], caplog: pytest.LogCaptureFixture) -> None:
    fake_router.error = TimeoutError("took too long")
    with caplog.at_level(logging.WARNING, logger="gpt_researcher_webrouter"):
        assert WebRouterSearch("q").search() == []
    assert [(r.levelname, r.getMessage()) for r in caplog.records] == [
        ("WARNING", "WebRouter search failed: TimeoutError: took too long")
    ]


def test_misconfiguration_is_an_error(fake_router: type[FakeRouter], caplog: pytest.LogCaptureFixture) -> None:
    fake_router.error = ConfigurationError("unknown provider 'nope'")
    with caplog.at_level(logging.WARNING, logger="gpt_researcher_webrouter"):
        assert WebRouterSearch("q").search() == []
    assert [r.levelname for r in caplog.records] == ["ERROR"]
    assert "unknown provider 'nope'" in caplog.text


def test_result_without_text_has_empty_body(fake_router: type[FakeRouter]) -> None:
    fake_router.results = [SearchResult(url="https://bare.example/")]
    assert WebRouterSearch("q").search() == [{"href": "https://bare.example/", "body": "", "title": ""}]


def test_loads_through_gpt_researcher() -> None:
    retriever = pytest.importorskip("gpt_researcher.actions.retriever")
    assert retriever.get_retriever("webrouter") is WebRouterSearch


def test_search_inside_event_loop_runs_off_loop() -> None:
    async def in_loop() -> list[dict[str, Any]]:
        return WebRouterSearch("q").search()

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        filters_before = list(warnings.filters)
        assert len(asyncio.run(in_loop())) == 3
        assert warnings.filters == filters_before
    assert caught == []


def test_search_from_worker_threads() -> None:
    async def planning_path() -> list[list[dict[str, Any]]]:
        calls = [asyncio.to_thread(WebRouterSearch(f"q{i}").search) for i in range(4)]
        return await asyncio.gather(*calls)

    assert [len(results) for results in asyncio.run(planning_path())] == [3, 3, 3, 3]
