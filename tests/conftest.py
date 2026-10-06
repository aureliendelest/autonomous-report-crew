"""Shared fixtures. No test may touch the network, the real outputs/ or the real cache."""

from datetime import datetime, timedelta

import pytest

from src import orchestrator, web_search


@pytest.fixture(autouse=True)
def isolate_from_real_world(tmp_path, monkeypatch):
    """Redirect every file the code writes to a temp dir and remove the API keys.

    Without keys, a test that forgets to fake an LLM or Tavily call fails
    immediately with a RuntimeError instead of silently spending quota.
    """
    monkeypatch.setattr(orchestrator, "OUTPUTS_DIR", tmp_path / "outputs")
    monkeypatch.setattr(web_search, "CACHE_DIR", tmp_path / "cache")
    for key in ("GROQ_API_KEY", "TAVILY_API_KEY", "OPENROUTER_API_KEY"):
        monkeypatch.delenv(key, raising=False)


class _AdvancingClock:
    """Stands in for `datetime`: each now() call is one minute after the previous one.

    Run directories are named with a minute-resolution timestamp, so two runs of the
    same topic within the same real minute would otherwise share a directory.
    """

    def __init__(self):
        self._current = datetime(2026, 1, 1, 12, 0)

    def now(self):
        value = self._current
        self._current += timedelta(minutes=1)
        return value


@pytest.fixture(autouse=True)
def advancing_clock(monkeypatch):
    monkeypatch.setattr(orchestrator, "datetime", _AdvancingClock())


class FakeAgents:
    """Scripted replacement for the three agents: records calls, never calls an LLM."""

    def __init__(self, critiques):
        self._critiques = iter(critiques)
        self.chercheur_calls = []
        self.critique_calls = []
        self.redacteur_calls = []

    @staticmethod
    def _report_usage(on_call):
        if on_call:
            on_call({"provider": "fake-model", "input_tokens": 10, "output_tokens": 5, "duration_s": 0.1})

    def run_chercheur(self, topic, domain, feedback=None, previous_research=None, use_cache=True, on_call=None):
        self.chercheur_calls.append({"feedback": feedback, "previous_research": previous_research})
        self._report_usage(on_call)
        return f"recherche n°{len(self.chercheur_calls)}"

    def run_critique(self, topic, domain, research, on_call=None):
        self.critique_calls.append(research)
        self._report_usage(on_call)
        return next(self._critiques)

    def run_redacteur(self, topic, domain, research, critique, incomplete=False, on_call=None):
        self.redacteur_calls.append({"research": research, "critique": critique, "incomplete": incomplete})
        self._report_usage(on_call)
        return "rapport final"


@pytest.fixture
def install_fake_agents(monkeypatch):
    """Call it with the raw texts the Critic should answer, in order; returns the fake."""

    def install(*critiques):
        fake = FakeAgents(critiques)
        monkeypatch.setattr(orchestrator.agents, "run_chercheur", fake.run_chercheur)
        monkeypatch.setattr(orchestrator.agents, "run_critique", fake.run_critique)
        monkeypatch.setattr(orchestrator.agents, "run_redacteur", fake.run_redacteur)
        return fake

    return install
