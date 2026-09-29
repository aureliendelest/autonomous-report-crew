import json
import re
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Callable

from pydantic import ValidationError

from . import agents
from .models import CritiqueResult, RunConfig

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

    def summarize(agent: str, turn: int, text: str | None = None) -> dict:
        llm_events = [e for e in events if "tool_call" not in e]
        return {
            "agent": agent,
            "turn": turn,
            "text": text,
            "duration_s": round(sum(e["duration_s"] for e in llm_events), 3),
            "input_tokens": sum(e["input_tokens"] for e in llm_events),
            "output_tokens": sum(e["output_tokens"] for e in llm_events),
            "providers": [e["provider"] for e in llm_events],
            "tool_calls": [e["tool_call"] for e in events if "tool_call" in e],
        }

    return on_call, summarize


def _strip_markdown_fence(text: str) -> str:
    # Certains modèles entourent leur JSON de ```json ... ``` malgré la
    # consigne de ne pas le faire : plutôt que de payer un tour de boucle
    # supplémentaire pour un simple problème de formatage, on le retire ici.
    text = text.strip()
    if text.startswith("```"):
        text = text.removeprefix("```json").removeprefix("```")
        text = text.removesuffix("```")
        text = text.strip()
    return text


def _parse_critique(text: str) -> tuple[CritiqueResult, str | None]:
    try:
        return CritiqueResult.model_validate_json(_strip_markdown_fence(text)), None
    except ValidationError as e:
        # JSON absent, malformé, ou champ "status" invalide : on traite ça
        # comme un statut KO normal (pas de retry LLM dédié) plutôt que de
        # planter le pipeline. L'erreur est conservée pour la trace, pour
        # pouvoir diagnostiquer après coup si ça devient fréquent.
        fallback = CritiqueResult(status="KO", gaps=["Réponse du Critique invalide ou non-JSON"])
        return fallback, str(e)


def _format_audit_log(topic: str, domain: str, trace_steps: list[dict]) -> str:
    lines = [f"# Journal d'audit — {topic}", f"*Domaine : {domain}*", ""]
    for trace_step in trace_steps:
        lines.append(f"## {trace_step['agent'].capitalize()} — tour {trace_step['turn']}")
        lines.append(
            f"*{trace_step['duration_s']}s, {trace_step['input_tokens']} tokens entrée / "
            f"{trace_step['output_tokens']} tokens sortie, "
            f"provider(s) : {', '.join(trace_step['providers'])}*"
        )
        for tool_call in trace_step["tool_calls"]:
            cached = "cache" if tool_call["cached"] else "web"
            lines.append(f"- recherche ({cached}) : \"{tool_call['query']}\" — {tool_call['result_count']} résultat(s)")
        if trace_step.get("critique_result"):
            result = trace_step["critique_result"]
            lines.append(f"- statut : {result['status']}")
            if result["gaps"]:
                lines.append("- manques : " + "; ".join(result["gaps"]))
        if trace_step.get("critique_parse_error"):
            lines.append(f"- ⚠️ JSON du Critique invalide : {trace_step['critique_parse_error']}")
        lines.append("")
        lines.append(trace_step["text"] or "")
        lines.append("")
    return "\n".join(lines)


def _run_critique_and_redact(
    topic: str,
    domain: str,
    research: str,
    use_cache: bool,
    notify: Callable[[str], None],
    config: RunConfig,
) -> tuple[str, list[dict]]:
    """Boucle Critique↔Chercheur puis rédaction du rapport final, à partir
    d'une recherche déjà disponible (fraîche ou rechargée depuis une trace)."""
    trace_steps: list[dict] = []

    if config.skip_critic:
        notify("[Rédacteur] rédaction du rapport final (Critique désactivé)")
        on_call, summarize = _new_step_recorder()
        report = agents.run_redacteur(
            topic, domain, research,
            "Le Critique a été désactivé pour ce run (ablation).",
            incomplete=False, on_call=on_call,
        )
        trace_steps.append(summarize("redacteur", 1, text=report))
        return report, trace_steps

    critique_result = CritiqueResult(status="KO", gaps=[])
    validated = False
    for i in range(config.max_research_loops + 1):
        notify(f"[Critique] relecture (tour {i + 1})")
        on_call, summarize = _new_step_recorder()
        critique = agents.run_critique(topic, domain, research, on_call=on_call)
        critique_result, parse_error = _parse_critique(critique)
        trace_step = summarize("critique", i + 1, text=critique)
        trace_step["critique_result"] = critique_result.model_dump()
        trace_step["critique_parse_error"] = parse_error
        trace_steps.append(trace_step)

        if critique_result.status == "OK":
            validated = True
            break
        if i == config.max_research_loops:
            break

        notify("[Critique] demande des recherches complémentaires, on relance le Chercheur")
        feedback = "\n".join(f"- {gap}" for gap in critique_result.gaps)
        on_call, summarize = _new_step_recorder()
        research = agents.run_chercheur(
            topic, domain, feedback=feedback, previous_research=research, use_cache=use_cache, on_call=on_call
        )
        trace_steps.append(summarize("chercheur", i + 2, text=research))

    notify("[Rédacteur] rédaction du rapport final")
    if critique_result.gaps:
        critique_summary = "Points signalés par le Critique :\n" + "\n".join(
            f"- {gap}" for gap in critique_result.gaps
        )
    else:
        critique_summary = "Le Critique n'a signalé aucun point à vérifier."
    on_call, summarize = _new_step_recorder()
    report = agents.run_redacteur(
        topic, domain, research, critique_summary, incomplete=not validated, on_call=on_call
    )
    trace_steps.append(summarize("redacteur", 1, text=report))

    return report, trace_steps


def _write_run_outputs(
    topic: str,
    domain: str,
    report: str,
    trace_steps: list[dict],
    notify: Callable[[str], None],
    slug: str | None = None,
    label: str = "baseline",
) -> Path:
    slug = slug or _slugify(topic)
    timestamp = f"{datetime.now():%Y%m%d-%H%M}"
    dir_name = f"{slug}-{timestamp}" if label == "baseline" else f"{slug}-{label}-{timestamp}"
    run_dir = OUTPUTS_DIR / domain / dir_name
    run_dir.mkdir(parents=True, exist_ok=True)

    output_path = run_dir / "report.md"
    output_path.write_text(report, encoding="utf-8")

    trace_path = run_dir / "trace.json"
    trace_path.write_text(
        json.dumps(
            {"topic": topic, "domain": domain, "timestamp": timestamp, "steps": trace_steps},
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    audit_path = run_dir / "audit.md"
    audit_path.write_text(_format_audit_log(topic, domain, trace_steps), encoding="utf-8")

    notify(f"Rapport enregistré : {output_path}")
    notify(f"Trace enregistrée : {trace_path}")
    notify(f"Journal d'audit enregistré : {audit_path}")
    return output_path


def run_pipeline(
    topic: str,
    domain: str = "football",
    on_step: Callable[[str], None] | None = None,
    use_cache: bool = True,
    config: RunConfig | None = None,
) -> Path:
    config = config or RunConfig()
    notify = on_step or print

    notify(f"[Chercheur] recherche sur : {topic}")
    on_call, summarize = _new_step_recorder()
    research = agents.run_chercheur(topic, domain, use_cache=use_cache, on_call=on_call)
    trace_steps: list[dict] = [summarize("chercheur", 1, text=research)]

    report, more_trace_steps = _run_critique_and_redact(topic, domain, research, use_cache, notify, config)
    trace_steps += more_trace_steps

    return _write_run_outputs(topic, domain, report, trace_steps, notify, label=config.label)


def resume_from_trace(
    trace_path: Path,
    start_at: str = "critic",
    on_step: Callable[[str], None] | None = None,
    use_cache: bool = True,
    config: RunConfig | None = None,
) -> Path:
    """Rejoue le pipeline à partir d'une trace existante, sans repasser par
    le Chercheur : utile pour itérer sur le prompt du Critique sans repayer
    de requêtes Tavily/LLM sur la recherche."""
    if start_at != "critic":
        raise ValueError(f"start_at non supporté : {start_at!r} (seul 'critic' est disponible)")

    config = config or RunConfig()
    notify = on_step or print
    trace_data = json.loads(trace_path.read_text(encoding="utf-8"))
    topic = trace_data["topic"]
    domain = trace_data["domain"]

    research = next(
        (step.get("text") for step in reversed(trace_data["steps"]) if step["agent"] == "chercheur"),
        None,
    )
    if not research:
        raise ValueError(
            f"Aucune recherche exploitable dans {trace_path} : cette trace ne contient pas de "
            "texte de Chercheur (traces générées avant l'ajout du replay, par exemple)."
        )

    notify(f"[Replay] recherche rechargée depuis {trace_path}")
    report, trace_steps = _run_critique_and_redact(topic, domain, research, use_cache, notify, config)

    return _write_run_outputs(topic, domain, report, trace_steps, notify, label=config.label)
