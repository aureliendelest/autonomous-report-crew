from datetime import datetime
from pathlib import Path

from . import agents

MAX_RESEARCH_LOOPS = 2
OUTPUTS_DIR = Path(__file__).resolve().parent.parent / "outputs"


def _format_audit_log(topic: str, domain: str, steps: list[tuple[str, str]]) -> str:
    lines = [f"# Journal d'audit — {topic}", f"*Domaine : {domain}*", ""]
    for title, content in steps:
        lines.append(f"## {title}")
        lines.append(content)
        lines.append("")
    return "\n".join(lines)


def run_pipeline(topic: str, domain: str = "football") -> Path:
    steps: list[tuple[str, str]] = []

    print(f"[Chercheur] recherche sur : {topic}")
    research = agents.run_chercheur(topic, domain)
    steps.append(("Chercheur — tour 1", research))

    critique = ""
    for i in range(MAX_RESEARCH_LOOPS + 1):
        print(f"[Critique] relecture (tour {i + 1})")
        critique = agents.run_critique(topic, domain, research)
        steps.append((f"Critique — tour {i + 1}", critique))

        if critique.strip().startswith("STATUT: OK") or i == MAX_RESEARCH_LOOPS:
            break

        print("[Critique] demande des recherches complémentaires, on relance le Chercheur")
        research = agents.run_chercheur(topic, domain, feedback=critique)
        steps.append((f"Chercheur — tour {i + 2}", research))

    print("[Rédacteur] rédaction du rapport final")
    report = agents.run_redacteur(topic, domain, research, critique)

    OUTPUTS_DIR.mkdir(exist_ok=True)
    slug = topic.lower().replace(" ", "-")
    timestamp = f"{datetime.now():%Y%m%d-%H%M}"

    output_path = OUTPUTS_DIR / f"{domain}-{slug}-{timestamp}.md"
    output_path.write_text(report, encoding="utf-8")

    audit_path = OUTPUTS_DIR / f"{domain}-{slug}-{timestamp}.audit.md"
    audit_path.write_text(_format_audit_log(topic, domain, steps), encoding="utf-8")

    print(f"Rapport enregistré : {output_path}")
    print(f"Journal d'audit enregistré : {audit_path}")
    return output_path
