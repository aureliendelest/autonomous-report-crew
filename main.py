import argparse
from pathlib import Path

from src.orchestrator import resume_from_trace, run_pipeline


def main():
    parser = argparse.ArgumentParser(description="Génère un rapport de veille automatisé.")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--topic", help="Sujet du rapport, ex: 'Olympique de Marseille'")
    source.add_argument(
        "--from-trace",
        metavar="FICHIER",
        help=(
            "Rejoue le pipeline depuis une trace existante (outputs/<domaine>/<run>/trace.json) "
            "au lieu de partir d'un nouveau sujet, sans repasser par le Chercheur."
        ),
    )
    parser.add_argument(
        "--domain",
        default="football",
        help="Domaine de prompts à utiliser (dossier sous /prompts). Ignoré avec --from-trace.",
    )
    parser.add_argument(
        "--start-at",
        default="critic",
        choices=["critic"],
        help="Avec --from-trace, l'étape à partir de laquelle rejouer (défaut : critic).",
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Désactive le cache disque des recherches Tavily (.cache/)",
    )
    args = parser.parse_args()

    try:
        if args.from_trace:
            resume_from_trace(Path(args.from_trace), args.start_at, use_cache=not args.no_cache)
        else:
            run_pipeline(args.topic, args.domain, use_cache=not args.no_cache)
    except (RuntimeError, ValueError) as e:
        print(f"Erreur : {e}")
        raise SystemExit(1) from e


if __name__ == "__main__":
    main()
