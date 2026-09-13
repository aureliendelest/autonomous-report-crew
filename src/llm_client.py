import json
import os
import time

from dotenv import load_dotenv
from groq import Groq, RateLimitError

load_dotenv()

MODEL = "openai/gpt-oss-120b"
MAX_RATE_LIMIT_RETRIES = 3


def get_client() -> Groq:
    if not os.environ.get("GROQ_API_KEY"):
        raise RuntimeError(
            "GROQ_API_KEY n'est pas défini. Copie .env.example vers .env et renseigne ta clé."
        )
    return Groq()


def _create_with_retry(client: Groq, **kwargs):
    for attempt in range(MAX_RATE_LIMIT_RETRIES + 1):
        try:
            return client.chat.completions.create(**kwargs)
        except RateLimitError as e:
            if attempt == MAX_RATE_LIMIT_RETRIES:
                raise
            wait_seconds = float(e.response.headers.get("retry-after", 2))
            print(f"[llm_client] limite de débit atteinte, nouvelle tentative dans {wait_seconds:.1f}s")
            time.sleep(wait_seconds)


def call_agent(
    system_prompt: str,
    user_message: str,
    tools: list[dict] | None = None,
    tool_executors: dict | None = None,
    max_tokens: int = 800,
) -> str:
    client = get_client()

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]
    kwargs = dict(
        model=MODEL, messages=messages, max_tokens=max_tokens, reasoning_effort="low"
    )
    if tools:
        kwargs["tools"] = tools

    response = _create_with_retry(client, **kwargs)
    message = response.choices[0].message

    # Contrairement au web_search serveur d'Anthropic, Groq utilise le function
    # calling classique : c'est notre code qui doit exécuter l'outil demandé et
    # renvoyer le résultat au modèle avant d'obtenir une réponse finale.
    while message.tool_calls:
        messages.append(message.model_dump(exclude_none=True))
        for tool_call in message.tool_calls:
            function_name = tool_call.function.name
            arguments = json.loads(tool_call.function.arguments)
            result = tool_executors[function_name](**arguments)
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": result,
                }
            )
        response = _create_with_retry(client, **kwargs)
        message = response.choices[0].message

    return message.content or ""
