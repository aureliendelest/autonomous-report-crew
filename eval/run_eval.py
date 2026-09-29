"""Script d'évaluation de la session 5 : fait tourner le pipeline sur un jeu
de sujets fixe, pour plusieurs configurations (ablations), et calcule des
métriques automatiques à partir des fichiers écrits par chaque run.

Limites connues :
- le Chercheur choisit lui-même ses requêtes de recherche (tool-calling),
  donc deux ablations sur le même sujet peuvent poser des requêtes Tavily
  légèrement différentes et ne pas réutiliser 100% du cache. Le cache reste
  très utile pour limiter le coût réseau global du testset, mais ne garantit
  pas une reproductibilité bit-à-bit entre ablations.
- chaque agent reçoit la date réelle du jour de l'exécution (`_today()` dans
  `src/agents.py`), pas une date figée : deux évaluations lancées à des jours
  différents ne sont donc pas strictement comparables sur les métriques
  sensibles au temps (fraîcheur des sources notamment). Figer artificiellement
  cette date sans figer aussi ce que retourne Tavily (un vrai moteur de
  recherche, pas rejouable à une date passée) créerait une incohérence pire :
  le Chercheur recevrait des sources "du futur" par rapport à la date qu'on
  lui indique. Les comparaisons entre ablations *au sein d'une même
  évaluation* restent valides (quelques minutes d'écart, même jour).

Usage : python -m eval.run_eval
"""
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.agents import _extract_urls
from src.models import RunConfig
from src.orchestrator import run_pipeline
from src.prompts import load_search_config

EVAL_DIR = Path(__file__).resolve().parent
TOPICS_PATH = EVAL_DIR / "topics.yaml"

ABLATIONS = [
    RunConfig(max_research_loops=2, skip_critic=False, label="baseline"),
    RunConfig(max_research_loops=0, skip_critic=False, label="0-tour"),
    RunConfig(max_research_loops=1, skip_critic=False, label="1-tour"),
    RunConfig(skip_critic=True, label="sans-critique"),
]

SECTIONS_ATTENDUES = {
    "football": ["Résumé", "Points clés", "Résultats récents", "Actualités", "Prochaine échéance", "Sources"],
    "ia-entreprise": ["Résumé", "Cas d'usage", "ROI et résultats observés", "Freins à l'adoption", "Actualités récentes", "Sources"],
}

# Le seuil "périmé" est dérivé du time_range de recherche de chaque domaine
# (search.json), avec une marge : une source trouvée un peu au-delà de la
# fenêtre de recherche visée n'est pas forcément un problème, juste un
# résultat intéressant que le Chercheur a remonté. Sans ce mapping par
# domaine, un seuil unique de 30 jours marquerait presque toutes les sources
# ia-entreprise (time_range="year") comme périmées à tort, alors que
# retrouver du contenu vieux de plusieurs mois est le comportement attendu
# sur ce domaine.
JOURS_PAR_TIME_RANGE = {"day": 1, "week": 7, "month": 30, "year": 365}
MARGE_PERIME = {"day": 3, "week": 7, "month": 15, "year": 60}


def _seuil_perime_jours(domain: str) -> int:
    time_range = load_search_config(domain).get("time_range", "week")
    base = JOURS_PAR_TIME_RANGE.get(time_range, JOURS_PAR_TIME_RANGE["week"])
    marge = MARGE_PERIME.get(time_range, MARGE_PERIME["week"])
    return base + marge


def charger_topics(path: Path) -> list[dict]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _urls_vues_et_dates(trace: dict) -> tuple[set[str], dict[str, str | None]]:
    urls_vues: set[str] = set()
    dates_par_url: dict[str, str | None] = {}
    for step in trace["steps"]:
        for tool_call in step.get("tool_calls", []):
            urls_vues.update(tool_call.get("urls", []))
            dates_par_url.update(tool_call.get("published_dates", {}))
    return urls_vues, dates_par_url


def calculer_urls_fabriquees(report_md: str, trace: dict) -> dict:
    urls_rapport = _extract_urls(report_md)
    urls_vues, _ = _urls_vues_et_dates(trace)
    fabriquees = urls_rapport - urls_vues
    return {
        "urls_fabriquees": sorted(fabriquees),
        "urls_totales_rapport": len(urls_rapport),
    }


def calculer_sources_perimees(report_md: str, trace: dict) -> dict:
    urls_rapport = _extract_urls(report_md)
    _, dates_par_url = _urls_vues_et_dates(trace)
    now = datetime.now(timezone.utc)
    seuil_jours = _seuil_perime_jours(trace["domain"])

    perimees, fraiches, date_inconnue = 0, 0, 0
    for url in urls_rapport:
        raw_date = dates_par_url.get(url)
        if not raw_date:
            date_inconnue += 1
            continue
        try:
            age_jours = (now - parsedate_to_datetime(raw_date)).days
        except (TypeError, ValueError):
            date_inconnue += 1
            continue
        if age_jours > seuil_jours:
            perimees += 1
        else:
            fraiches += 1

    return {"sources_perimees": perimees, "sources_fraiches": fraiches, "sources_date_inconnue": date_inconnue}


def calculer_couverture_format(report_md: str, domain: str) -> dict:
    attendues = SECTIONS_ATTENDUES.get(domain, [])
    manquantes = [s for s in attendues if f"## {s}" not in report_md]
    return {
        "sections_attendues": len(attendues),
        "sections_presentes": len(attendues) - len(manquantes),
        "sections_manquantes": manquantes,
    }


def calculer_cout(trace: dict) -> dict:
    steps = trace["steps"]
    return {
        "input_tokens": sum(s["input_tokens"] for s in steps),
        "output_tokens": sum(s["output_tokens"] for s in steps),
        "duree_s": round(sum(s["duration_s"] for s in steps), 1),
        "appels_tavily": sum(len(s.get("tool_calls", [])) for s in steps),
        "tours_chercheur_critique": sum(1 for s in steps if s["agent"] in ("chercheur", "critique")),
    }


def evaluer_un_run(report_path: Path) -> dict:
    try:
        report_md = report_path.read_text(encoding="utf-8")
        trace = json.loads((report_path.parent / "trace.json").read_text(encoding="utf-8"))
    except Exception as e:
        return {"erreur": f"lecture des fichiers de run impossible : {e}"}

    try:
        metriques = {}
        metriques.update(calculer_urls_fabriquees(report_md, trace))
        metriques.update(calculer_sources_perimees(report_md, trace))
        metriques.update(calculer_couverture_format(report_md, trace["domain"]))
        metriques.update(calculer_cout(trace))
        return metriques
    except Exception as e:
        return {"erreur": f"calcul des métriques impossible : {e}"}


def ecrire_resultats(resultats: list[dict]) -> None:
    (EVAL_DIR / "results.json").write_text(
        json.dumps(resultats, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    groupes: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for r in resultats:
        groupes[(r["domain"], r["label"])].append(r)

    lines = ["# Résultats d'évaluation — session 5", ""]
    lines.append(
        "| Domaine | Ablation | Runs | Échecs | URLs fabriquées (moy.) | Sources périmées (moy.) | "
        "Format complet | Tokens (moy.) | Tavily (moy.) | Durée s (moy.) |"
    )
    lines.append("|---|---|---|---|---|---|---|---|---|---|")

    for (domain, label), lignes in sorted(groupes.items()):
        ok = [l for l in lignes if "erreur" not in l]
        echecs = len(lignes) - len(ok)
        if ok:
            urls_fab_moy = sum(len(l["urls_fabriquees"]) for l in ok) / len(ok)
            perimees_moy = sum(l["sources_perimees"] for l in ok) / len(ok)
            format_complet = sum(1 for l in ok if not l["sections_manquantes"])
            tokens_moy = sum(l["input_tokens"] + l["output_tokens"] for l in ok) / len(ok)
            tavily_moy = sum(l["appels_tavily"] for l in ok) / len(ok)
            duree_moy = sum(l["duree_s"] for l in ok) / len(ok)
            lines.append(
                f"| {domain} | {label} | {len(lignes)} | {echecs} | {urls_fab_moy:.1f} | {perimees_moy:.1f} | "
                f"{format_complet}/{len(ok)} | {tokens_moy:.0f} | {tavily_moy:.1f} | {duree_moy:.0f} |"
            )
        else:
            lines.append(f"| {domain} | {label} | {len(lignes)} | {echecs} | — | — | — | — | — | — |")

    lines.append("")
    lines.append(f"*Généré le {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}.*")
    lines.append("")
    seuils = ", ".join(
        f"{d} = {_seuil_perime_jours(d)}j" for d in sorted(SECTIONS_ATTENDUES)
    )
    lines.append(
        f"*Seuil de fraîcheur par domaine ({seuils}) : dérivé du `time_range` de recherche de "
        "chaque domaine (`prompts/<domaine>/search.json`) avec une marge, plutôt qu'un seuil unique "
        "— sinon presque toutes les sources ia-entreprise (`time_range=\"year\"`) seraient marquées "
        "périmées à tort, alors que retrouver du contenu vieux de plusieurs mois est attendu sur ce "
        "domaine.*"
    )
    lines.append("")
    lines.append(
        "*Limite de comparabilité dans le temps : chaque agent reçoit la date réelle du jour "
        "d'exécution, pas une date figée. Deux évaluations lancées à des jours différents ne sont "
        "donc pas strictement comparables sur les métriques sensibles au temps (fraîcheur des "
        "sources notamment) — seules les comparaisons entre ablations d'une même évaluation "
        "(même jour) sont fiables sur ce point. Voir le docstring de `run_eval.py` pour le détail.*"
    )
    (EVAL_DIR / "results.md").write_text("\n".join(lines), encoding="utf-8")


def main():
    topics = charger_topics(TOPICS_PATH)
    resultats = []

    for t in topics:
        for config in ABLATIONS:
            print(f"[eval] {t['domain']} / {t['topic']} / {config.label}")
            try:
                report_path = run_pipeline(t["topic"], t["domain"], use_cache=True, config=config)
                metriques = evaluer_un_run(report_path)
            except Exception as e:
                metriques = {"erreur": f"run_pipeline a échoué : {e}"}
            resultats.append({"topic": t["topic"], "domain": t["domain"], "tag": t["tag"], "label": config.label, **metriques})

    ecrire_resultats(resultats)
    print(f"\nRésultats écrits dans {EVAL_DIR / 'results.json'} et {EVAL_DIR / 'results.md'}")


if __name__ == "__main__":
    main()
