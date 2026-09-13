import os
import time

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


def web_search(query: str) -> str:
    client = get_tavily_client()

    for attempt in range(MAX_TIMEOUT_RETRIES + 1):
        try:
            response = client.search(
                query=query, max_results=3, topic="news", time_range="month"
            )
            break
        except TavilyTimeoutError:
            if attempt == MAX_TIMEOUT_RETRIES:
                raise
            print("[web_search] timeout Tavily, nouvelle tentative")
            time.sleep(2)

    lines = []
    for result in response["results"]:
        content = result["content"][:MAX_CONTENT_CHARS]
        lines.append(f"- {result['title']} ({result['url']}): {content}")
    return "\n".join(lines)
