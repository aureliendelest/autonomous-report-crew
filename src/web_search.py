import hashlib
import json
import os
import time
from pathlib import Path

from tavily import TavilyClient
from tavily.errors import TimeoutError as TavilyTimeoutError

TAVILY_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "web_search",
        "description": "Recherche des informations récentes sur le web à partir d'une requête.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "La requête de recherche à envoyer.",
                }
            },
            "required": ["query"],
        },
    },
}


def get_tavily_client() -> TavilyClient:
    if not os.environ.get("TAVILY_API_KEY"):
        raise RuntimeError(
            "TAVILY_API_KEY n'est pas défini. Copie .env.example vers .env et renseigne ta clé."
        )
    return TavilyClient()


MAX_CONTENT_CHARS = 500
MAX_TIMEOUT_RETRIES = 2
CACHE_DIR = Path(__file__).resolve().parent.parent / ".cache"


def _cache_key(query: str, topic: str, time_range: str, max_results: int, search_depth: str) -> str:
    # JSON avec clés triées pour que le hash soit stable quel que soit l'ordre
    # d'appel des paramètres.
    payload = {
        "query": query,
        "topic": topic,
        "time_range": time_range,
        "max_results": max_results,
        "search_depth": search_depth,
    }
    canonical = json.dumps(payload, sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _read_cache(key: str) -> dict | None:
    path = CACHE_DIR / f"{key}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _write_cache(key: str, response: dict) -> None:
    CACHE_DIR.mkdir(exist_ok=True)
    path = CACHE_DIR / f"{key}.json"
    path.write_text(json.dumps(response), encoding="utf-8")


def _fetch_from_tavily(
    query: str, topic: str, time_range: str, max_results: int, search_depth: str
) -> dict:
    client = get_tavily_client()

    for attempt in range(MAX_TIMEOUT_RETRIES + 1):
        try:
            return client.search(
                query=query,
                max_results=max_results,
                topic=topic,
                time_range=time_range,
                search_depth=search_depth,
            )
        except TavilyTimeoutError:
            if attempt == MAX_TIMEOUT_RETRIES:
                raise
            print("[web_search] timeout Tavily, nouvelle tentative")
            time.sleep(2)


def _format_results(response: dict) -> str:
    lines = []
    for result in response["results"]:
        content = result["content"][:MAX_CONTENT_CHARS]
        lines.append(f"- {result['title']} ({result['url']}): {content}")
    return "\n".join(lines)


def web_search(
    query: str,
    topic: str = "news",
    time_range: str = "week",
    max_results: int = 3,
    search_depth: str = "basic",
    use_cache: bool = True,
) -> tuple[str, dict]:
    key = _cache_key(query, topic, time_range, max_results, search_depth)
    response = _read_cache(key) if use_cache else None
    cached = response is not None

    if response is None:
        response = _fetch_from_tavily(query, topic, time_range, max_results, search_depth)
        if use_cache:
            _write_cache(key, response)

    meta = {
        "cached": cached,
        "result_count": len(response["results"]),
        "urls": [result["url"] for result in response["results"]],
        # Utilisé par l'évaluation (session 5) pour détecter les sources
        # périmées sans avoir à retrouver après coup quelle entrée du cache
        # correspond à quelle URL.
        "published_dates": {result["url"]: result.get("published_date") for result in response["results"]},
    }
    return _format_results(response), meta
