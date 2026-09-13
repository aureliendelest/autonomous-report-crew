import json
import os
import time

from dotenv import load_dotenv
from groq import Groq, RateLimitError
from openai import OpenAI

load_dotenv()

GROQ_MODEL = "openai/gpt-oss-120b"
# Modèle de secours sur OpenRouter, utilisé uniquement quand le quota Groq est
# épuisé. À revérifier sur https://openrouter.ai/models si ce modèle gratuit
# n'est plus disponible (leur catalogue évolue, comme celui de Groq).
OPENROUTER_MODEL = "meta-llama/llama-3.3-70b-instruct:free"

MAX_RATE_LIMIT_RETRIES = 3
MAX_RETRY_WAIT_SECONDS = 20


def get_groq_client() -> Groq:
    if not os.environ.get("GROQ_API_KEY"):
        raise RuntimeError(
            "GROQ_API_KEY n'est pas défini. Copie .env.example vers .env et renseigne ta clé."
        )
    return Groq()


def get_openrouter_client() -> OpenAI | None:
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        return None
    return OpenAI(base_url="https://openrouter.ai/api/v1", api_key=api_key)


def _create_with_retry(client, **kwargs):
    for attempt in range(MAX_RATE_LIMIT_RETRIES + 1):
        try:
            return client.chat.completions.create(**kwargs)
        except RateLimitError as e:
            wait_seconds = float(e.response.headers.get("retry-after", 2))
            if attempt == MAX_RATE_LIMIT_RETRIES or wait_seconds > MAX_RETRY_WAIT_SECONDS:
                # Au-delà de ce seuil, ce n'est plus un simple pic de trafic à
                # patienter mais probablement un quota bien plus large épuisé
                # (ex: limite journalière) : on laisse l'appelant basculer sur
                # OpenRouter plutôt que de bloquer le pipeline en silence.
                raise
            print(f"[llm_client] limite de débit Groq atteinte, nouvelle tentative dans {wait_seconds:.1f}s")
            time.sleep(wait_seconds)


def _create_completion(messages: list[dict], tools: list[dict] | None, max_tokens: int):
    groq_kwargs = dict(
        model=GROQ_MODEL, messages=messages, max_tokens=max_tokens, reasoning_effort="low"
    )
    if tools:
        groq_kwargs["tools"] = tools

    try:
        return _create_with_retry(get_groq_client(), **groq_kwargs)
    except RateLimitError:
        openrouter_client = get_openrouter_client()
        if openrouter_client is None:
            raise
        print("[llm_client] quota Groq épuisé, bascule sur OpenRouter")

        openrouter_kwargs = dict(model=OPENROUTER_MODEL, messages=messages, max_tokens=max_tokens)
        if tools:
            openrouter_kwargs["tools"] = tools
        return openrouter_client.chat.completions.create(**openrouter_kwargs)


def call_agent(
    system_prompt: str,
    user_message: str,
    tools: list[dict] | None = None,
    tool_executors: dict | None = None,
    max_tokens: int = 800,
) -> str:
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]

    response = _create_completion(messages, tools, max_tokens)
    message = response.choices[0].message

    # Contrairement au web_search serveur d'Anthropic, Groq et OpenRouter utilisent
    # le function calling classique : c'est notre code qui doit exécuter l'outil
    # demandé et renvoyer le résultat au modèle avant d'obtenir une réponse finale.
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
        response = _create_completion(messages, tools, max_tokens)
        message = response.choices[0].message

    return message.content or ""
