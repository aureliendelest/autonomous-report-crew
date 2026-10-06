import json

import pytest

from src import orchestrator
from src.models import RunConfig

CRITIQUE_OK = json.dumps({"status": "OK", "gaps": []})


def critique_ko(*gaps):
    return json.dumps({"status": "KO", "gaps": list(gaps)})


def run(topic="Olympique de Marseille", **kwargs):
    return orchestrator.run_pipeline(topic, "football", on_step=lambda message: None, **kwargs)


def read_trace(report_path):
    return json.loads((report_path.parent / "trace.json").read_text(encoding="utf-8"))


def agent_sequence(trace):
    return [(step["agent"], step["turn"]) for step in trace["steps"]]


def test_a_validated_run_writes_report_trace_and_audit(install_fake_agents):
    fake = install_fake_agents(CRITIQUE_OK)

    report_path = run()

    assert report_path == orchestrator.OUTPUTS_DIR / "football" / "olympique-de-marseille-20260101-1200" / "report.md"
    assert sorted(path.name for path in report_path.parent.iterdir()) == ["audit.md", "report.md", "trace.json"]
    assert report_path.read_text(encoding="utf-8") == "rapport final"
    assert len(fake.chercheur_calls) == 1
    assert fake.redacteur_calls[0]["incomplete"] is False


def test_trace_records_every_step_with_its_text_and_usage(install_fake_agents):
    install_fake_agents(CRITIQUE_OK)

    trace = read_trace(run())

    assert trace["topic"] == "Olympique de Marseille"
    assert trace["domain"] == "football"
    assert agent_sequence(trace) == [("chercheur", 1), ("critique", 1), ("redacteur", 1)]
    chercheur, critique, _ = trace["steps"]
    assert chercheur["text"] == "recherche n°1"
    assert critique["critique_result"] == {"status": "OK", "gaps": []}
    assert chercheur["input_tokens"] == 10
    assert chercheur["providers"] == ["fake-model"]


def test_audit_log_is_rendered_from_the_trace(install_fake_agents):
    install_fake_agents(CRITIQUE_OK)

    audit = (run().parent / "audit.md").read_text(encoding="utf-8")

    assert "## Chercheur — tour 1" in audit
    assert "## Critique — tour 1" in audit
    assert "- statut : OK" in audit


def test_a_ko_critique_sends_the_researcher_back_with_its_feedback(install_fake_agents):
    fake = install_fake_agents(critique_ko("score manquant"), CRITIQUE_OK)

    trace = read_trace(run())

    assert agent_sequence(trace) == [
        ("chercheur", 1),
        ("critique", 1),
        ("chercheur", 2),
        ("critique", 2),
        ("redacteur", 1),
    ]
    assert fake.chercheur_calls[1] == {"feedback": "- score manquant", "previous_research": "recherche n°1"}
    assert fake.critique_calls == ["recherche n°1", "recherche n°2"]
    assert fake.redacteur_calls[0]["research"] == "recherche n°2"
    assert fake.redacteur_calls[0]["incomplete"] is False


def test_a_critique_that_never_validates_stops_and_marks_the_report_incomplete(install_fake_agents):
    fake = install_fake_agents(*[critique_ko("toujours faux")] * 3)

    run()

    assert len(fake.critique_calls) == RunConfig().max_research_loops + 1
    assert len(fake.chercheur_calls) == RunConfig().max_research_loops + 1
    assert fake.redacteur_calls[0]["incomplete"] is True
    assert "toujours faux" in fake.redacteur_calls[0]["critique"]


def test_an_unparsable_critique_counts_as_ko_and_is_traced(install_fake_agents):
    fake = install_fake_agents("ceci n'est pas du JSON", CRITIQUE_OK)

    trace = read_trace(run())

    first_critique = trace["steps"][1]
    assert first_critique["critique_result"]["status"] == "KO"
    assert first_critique["critique_parse_error"]
    assert len(fake.chercheur_calls) == 2


def test_with_the_critic_disabled_the_writer_follows_the_researcher(install_fake_agents):
    fake = install_fake_agents()

    report_path = run(config=RunConfig(skip_critic=True, label="sans-critique"))

    assert fake.critique_calls == []
    assert agent_sequence(read_trace(report_path)) == [("chercheur", 1), ("redacteur", 1)]
    assert report_path.parent.name == "olympique-de-marseille-sans-critique-20260101-1200"


def test_resume_from_trace_reuses_the_research_without_calling_the_researcher(install_fake_agents):
    install_fake_agents(CRITIQUE_OK)
    original = run()
    original_trace = (original.parent / "trace.json").read_text(encoding="utf-8")

    replay_fake = install_fake_agents(CRITIQUE_OK)
    replay = orchestrator.resume_from_trace(original.parent / "trace.json", on_step=lambda message: None)

    assert replay_fake.chercheur_calls == []
    assert replay_fake.critique_calls == ["recherche n°1"]
    assert replay.parent != original.parent
    assert (original.parent / "trace.json").read_text(encoding="utf-8") == original_trace


def test_resume_from_trace_rejects_an_unsupported_start_step(tmp_path):
    with pytest.raises(ValueError, match="start_at non supporté"):
        orchestrator.resume_from_trace(tmp_path / "trace.json", start_at="redacteur")


def test_resume_from_trace_rejects_a_trace_without_researcher_text(tmp_path):
    trace_path = tmp_path / "trace.json"
    trace_path.write_text(
        json.dumps({"topic": "x", "domain": "football", "steps": [{"agent": "chercheur", "turn": 1}]}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Aucune recherche exploitable"):
        orchestrator.resume_from_trace(trace_path)
