import pytest

from src import agents

REAL_URL = "https://real.example/a"
FABRICATED_URL = "https://invented.example/x"


def test_extract_urls_strips_trailing_punctuation():
    text = "Voir (https://example.com/a), puis https://example.com/b. Fin https://example.com/c;"

    assert agents._extract_urls(text) == {
        "https://example.com/a",
        "https://example.com/b",
        "https://example.com/c",
    }


@pytest.fixture
def run_chercheur_with_answer(monkeypatch):
    """Run the Researcher with a fake LLM that performs one real-looking search then answers.

    Returns a function (answer, **kwargs) -> (research text, captured data).
    """
    monkeypatch.setattr(agents.prompts, "load_prompt", lambda domain, name: "system prompt")
    monkeypatch.setattr(agents.prompts, "load_search_config", lambda domain: {})

    def fake_web_search(query, use_cache=True, **search_config):
        meta = {"cached": False, "result_count": 1, "urls": [REAL_URL]}
        return f"- Titre ({REAL_URL}): contenu", meta

    monkeypatch.setattr(agents, "web_search", fake_web_search)

    def run(answer, **kwargs):
        captured = {}

        def fake_call_agent(system, user_message, tools=None, tool_executors=None, max_tokens=800, on_call=None):
            captured["user_message"] = user_message
            tool_executors["web_search"](query="requête de test")
            return answer

        monkeypatch.setattr(agents.llm_client, "call_agent", fake_call_agent)
        return agents.run_chercheur("FC Nantes", "football", **kwargs), captured

    return run


def test_answer_citing_only_real_urls_is_returned_untouched(run_chercheur_with_answer):
    answer = f"Résultat : voir {REAL_URL}"

    research, _ = run_chercheur_with_answer(answer)

    assert research == answer


def test_fabricated_url_triggers_an_automatic_alert(run_chercheur_with_answer):
    research, _ = run_chercheur_with_answer(f"Sources : {REAL_URL} et {FABRICATED_URL}")

    assert "Alerte automatique" in research
    assert f"- {FABRICATED_URL}" in research
    assert f"- {REAL_URL}" not in research


def test_feedback_and_previous_research_reach_the_prompt(run_chercheur_with_answer):
    _, captured = run_chercheur_with_answer(
        "ok", feedback="- il manque le score", previous_research="recherche précédente"
    )

    assert "- il manque le score" in captured["user_message"]
    assert "recherche précédente" in captured["user_message"]


def test_search_events_are_reported_through_on_call(run_chercheur_with_answer):
    events = []

    run_chercheur_with_answer("ok", on_call=events.append)

    assert events == [
        {"tool_call": {"query": "requête de test", "cached": False, "result_count": 1, "urls": [REAL_URL]}}
    ]
