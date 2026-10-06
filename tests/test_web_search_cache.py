import pytest

from src import web_search

PARAMS = {
    "query": "FC Nantes",
    "topic": "news",
    "time_range": "week",
    "max_results": 3,
    "search_depth": "basic",
}

RESPONSE = {
    "results": [
        {"title": "Premier", "url": "https://example.com/a", "content": "x" * 600},
        {"title": "Second", "url": "https://example.com/b", "content": "court"},
    ]
}


@pytest.fixture
def tavily_calls(monkeypatch):
    """Replace the Tavily API with a fake and return the list of queries it received."""
    calls = []

    def fake_fetch(query, topic, time_range, max_results, search_depth):
        calls.append(query)
        return RESPONSE

    monkeypatch.setattr(web_search, "_fetch_from_tavily", fake_fetch)
    return calls


def test_cache_key_does_not_depend_on_argument_order():
    reordered = dict(reversed(list(PARAMS.items())))
    assert web_search._cache_key(**PARAMS) == web_search._cache_key(**reordered)


@pytest.mark.parametrize(
    ("name", "other_value"),
    [
        ("query", "Olympique de Marseille"),
        ("topic", "general"),
        ("time_range", "year"),
        ("max_results", 5),
        ("search_depth", "advanced"),
    ],
)
def test_every_search_parameter_changes_the_cache_key(name, other_value):
    changed = {**PARAMS, name: other_value}
    assert web_search._cache_key(**PARAMS) != web_search._cache_key(**changed)


def test_second_identical_search_is_served_from_the_cache(tavily_calls):
    text_1, meta_1 = web_search.web_search("FC Nantes")
    text_2, meta_2 = web_search.web_search("FC Nantes")

    assert tavily_calls == ["FC Nantes"]
    assert meta_1["cached"] is False
    assert meta_2["cached"] is True
    assert text_1 == text_2
    assert len(list(web_search.CACHE_DIR.glob("*.json"))) == 1


def test_a_different_search_depth_does_not_reuse_the_cache(tavily_calls):
    web_search.web_search("FC Nantes", search_depth="basic")
    web_search.web_search("FC Nantes", search_depth="advanced")

    assert len(tavily_calls) == 2


def test_use_cache_false_always_calls_tavily_and_writes_nothing(tavily_calls):
    web_search.web_search("FC Nantes", use_cache=False)
    web_search.web_search("FC Nantes", use_cache=False)

    assert len(tavily_calls) == 2
    assert not web_search.CACHE_DIR.exists()


def test_meta_describes_the_results(tavily_calls):
    _, meta = web_search.web_search("FC Nantes")

    assert meta["result_count"] == 2
    assert meta["urls"] == ["https://example.com/a", "https://example.com/b"]


def test_result_content_is_truncated(tavily_calls):
    text, _ = web_search.web_search("FC Nantes")

    assert "x" * web_search.MAX_CONTENT_CHARS in text
    assert "x" * (web_search.MAX_CONTENT_CHARS + 1) not in text
