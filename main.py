import argparse

from src.orchestrator import run_pipeline


def main():
    parser = argparse.ArgumentParser(
        description="Génère un rapport de veille automatisé."
    )
    parser.add_argument(
        "--topic", required=True, help="Sujet du rapport, ex: 'Olympique de Marseille'"
    )
    parser.add_argument(
        "--domain",
        default="football",
        help="Domaine de prompts à utiliser (dossier sous /prompts)",
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Désactive le cache disque des recherches Tavily (.cache/)",
    )
    args = parser.parse_args()

    try:
        run_pipeline(args.topic, args.domain, use_cache=not args.no_cache)
    except RuntimeError as e:
        print(f"Erreur : {e}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
