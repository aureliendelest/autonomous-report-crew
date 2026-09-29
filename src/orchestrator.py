import json
import re
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Callable

from . import agents

MAX_RESEARCH_LOOPS = 2
OUTPUTS_DIR = Path(__file__).resolve().parent.parent / "outputs"


def _slugify(topic: str) -> str:
    normalized = unicodedata.normalize("NFKD", topic)
    ascii_only = normalized.encode("ascii", errors="ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_only.lower())
    return slug.strip("-")


def _new_step_recorder():
    """Accumule les événements bruts (`on_call`) d'un tour d'agent, puis les
    résume en une entrée de trace unique pour ce tour."""
    events: list[dict] = []

    def on_call(event: dict) -> None:
        events.append(event)

    def summarize(agent: str, turn: int) -> dict:
        llm_events = [e for e in events if "tool_call" not in e]
        return {
            "agent": agent,
            "turn": turn,
            "duration_s": round(sum(e["duration_s"] for e in llm_events), 3),
            "input_tokens": sum(e["input_tokens"] for e in llm_events),
            "output_tokens": sum(e["output_tokens"] for e in llm_events),
            "providers": [e["provider"] for e in llm_events],
            "tool_calls": [e["tool_call"] for e in events if "tool_call" in e],
        }

    return on_call, summarize


def _format_audit_log(topic: str, domain: str, steps: list[tuple[str, str]], trace_steps: list[dict]) -> str:
    lines = [f"# Journal d'audit — {topic}", f"*Domaine : {domain}*", ""]
    for (title, content), trace_step in zip(steps, trace_steps):
        lines.append(f"## {title}")
        lines.append(
            f"*{trace_step['duration_s']}s, {trace_step['input_tokens']} tokens entrée / "
            f"{trace_step['output_tokens']} tokens sortie, "
            f"provider(s) : {', '.join(trace_step['providers'])}*"
        )
        for tool_call in trace_step["tool_calls"]:
            cached = "cache" if tool_call["cached"] else "web"
            lines.append(f"- recherche ({cached}) : \"{tool_call['query']}\" — {tool_call['result_count']} résultat(s)")
        lines.append("")
        lines.append(content)
        lines.append("")
    return "\n".join(lines)


def run_pipeline(
    topic: str,
    domain: str = "football",
    on_step: Callable[[str], None] | None = None,
    use_cache: bool = True,
) -> Path:
    notify = on_step or print
    steps: list[tuple[str, str]] = []
    trace_steps: list[dict] = []

    notify(f"[Chercheur] recherche sur : {topic}")
    on_call, summarize = _new_step_recorder()
    research = agents.run_chercheur(topic, domain, use_cache=use_cache, on_call=on_call)
    steps.append(("Chercheur — tour 1", research))
    trace_steps.append(summarize("chercheur", 1))

    critique = ""
    validated = False
    for i in range(MAX_RESEARCH_LOOPS + 1):
        notify(f"[Critique] relecture (tour {i + 1})")
        on_call, summarize = _new_step_recorder()
        critique = agents.run_critique(topic, domain, research, on_call=on_call)
        steps.append((f"Critique — tour {i + 1}", critique))
        trace_steps.append(summarize("critique", i + 1))

        if critique.strip().startswith("STATUT: OK"):
            validated = True
            break
        if i == MAX_RESEARCH_LOOPS:
            break

        notify("[Critique] demande des recherches complémentaires, on relance le Chercheur")
        on_call, summarize = _new_step_recorder()
        research = agents.run_chercheur(
            topic, domain, feedback=critique, previous_research=research, use_cache=use_cache, on_call=on_call
        )
        steps.append((f"Chercheur — tour {i + 2}", research))
        trace_steps.append(summarize("chercheur", i + 2))

    notify("[Rédacteur] rédaction du rapport final")
    on_call, summarize = _new_step_recorder()
    report = agents.run_redacteur(topic, domain, research, critique, incomplete=not validated, on_call=on_call)
    steps.append(("Rédacteur", report))
    trace_steps.append(summarize("redacteur", 1))

    OUTPUTS_DIR.mkdir(exist_ok=True)
    slug = _slugify(topic)
    timestamp = f"{datetime.now():%Y%m%d-%H%M}"

    output_path = OUTPUTS_DIR / f"{domain}-{slug}-{timestamp}.md"
    output_path.write_text(report, encoding="utf-8")

    trace_path = OUTPUTS_DIR / f"{domain}-{slug}-{timestamp}.trace.json"
    trace_path.write_text(
        json.dumps(
            {"topic": topic, "domain": domain, "timestamp": timestamp, "steps": trace_steps},
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    audit_path = OUTPUTS_DIR / f"{domain}-{slug}-{timestamp}.audit.md"
    audit_path.write_text(_format_audit_log(topic, domain, steps, trace_steps), encoding="utf-8")

    notify(f"Rapport enregistré : {output_path}")
    notify(f"Trace enregistrée : {trace_path}")
    notify(f"Journal d'audit enregistré : {audit_path}")
    return output_path
