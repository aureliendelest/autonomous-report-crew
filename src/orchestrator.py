from datetime import datetime
from pathlib import Path

from . import agents

MAX_RESEARCH_LOOPS = 2
OUTPUTS_DIR = Path(__file__).resolve().parent.parent / "outputs"


def run_pipeline(topic: str, domain: str = "football") -> Path:
    print(f"[Chercheur] recherche sur : {topic}")
    research = agents.run_chercheur(topic, domain)

    critique = ""
    for i in range(MAX_RESEARCH_LOOPS + 1):
        print(f"[Critique] relecture (tour {i + 1})")
        critique = agents.run_critique(topic, domain, research)

        if critique.strip().startswith("STATUT: OK") or i == MAX_RESEARCH_LOOPS:
            break

        print("[Critique] demande des recherches complémentaires, on relance le Chercheur")
        research = agents.run_chercheur(topic, domain, feedback=critique)

    print("[Rédacteur] rédaction du rapport final")
    report = agents.run_redacteur(topic, domain, research, critique)

    OUTPUTS_DIR.mkdir(exist_ok=True)
    slug = topic.lower().replace(" ", "-")
    filename = f"{domain}-{slug}-{datetime.now():%Y%m%d-%H%M}.md"
    output_path = OUTPUTS_DIR / filename
    output_path.write_text(report, encoding="utf-8")

    print(f"Rapport enregistré : {output_path}")
    return output_path
