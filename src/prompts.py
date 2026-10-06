import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"

DEFAULT_SEARCH_CONFIG = {
    "topic": "news",
    "time_range": "week",
    "max_results": 3,
    "search_depth": "basic",
}


def load_prompt(domain: str, agent_name: str) -> str:
    path = PROMPTS_DIR / domain / f"{agent_name}.md"
    return path.read_text(encoding="utf-8")


def load_search_config(domain: str) -> dict:
    path = PROMPTS_DIR / domain / "search.json"
    if not path.exists():
        logger.warning(
            "search.json manquant pour le domaine '%s', utilisation de la config par défaut.",
            domain,
            extra={"domain": domain},
        )
        return DEFAULT_SEARCH_CONFIG
    return json.loads(path.read_text(encoding="utf-8"))


def list_domains() -> list[str]:
    return sorted(p.name for p in PROMPTS_DIR.iterdir() if p.is_dir())
