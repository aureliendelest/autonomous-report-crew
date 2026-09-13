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
OPENROUTER_MODEL = "nvidia/nemotron-3-super-120b-a12b:free"

MAX_RATE_LIMIT_RETRIES = 3
MAX_RETRY_WAIT_SECONDS = 20
MAX_OPENROUTER_RETRIES = 2


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
    """Essaie Groq, bascule sur OpenRouter si le quota est épuisé.

    Chaque tour de la conversation retente cette même logique indépendamment
    (le quota Groq peut s'épuiser entre deux tours, pas seulement avant le
    premier appel). C'est sans risque de mélanger les fournisseurs d'un tour à
    l'autre car les messages renvoyés dans la conversation sont assainis par
    `_assistant_message_for_replay` (voir plus bas) : aucun champ propre à un
    fournisseur (ex: "reasoning_details" d'OpenRouter/Nemotron) n'y subsiste.
    """
    groq_kwargs = dict(max_tokens=max_tokens, reasoning_effort="low")
    if tools:
        groq_kwargs["tools"] = tools

    try:
        return _create_with_retry(get_groq_client(), model=GROQ_MODEL, messages=messages, **groq_kwargs)
    except RateLimitError:
        openrouter_client = get_openrouter_client()
        if openrouter_client is None:
            raise
        print("[llm_client] quota Groq épuisé, bascule sur OpenRouter")

        openrouter_kwargs = dict(max_tokens=max_tokens)
        if tools:
            openrouter_kwargs["tools"] = tools

        # Les modèles gratuits OpenRouter peuvent renvoyer un accroc ponctuel
        # côté fournisseur sous-jacent (réponse sans "choices") ; un modèle
        # gratuit tolère bien une nouvelle tentative immédiate.
        for attempt in range(MAX_OPENROUTER_RETRIES + 1):
            response = openrouter_client.chat.completions.create(
                model=OPENROUTER_MODEL, messages=messages, **openrouter_kwargs
            )
            if response.choices:
                return response
            if attempt < MAX_OPENROUTER_RETRIES:
                print("[llm_client] réponse OpenRouter invalide, nouvelle tentative")
        return response


def _assistant_message_for_replay(message) -> dict:
    # On ne garde que les champs standards nécessaires pour poursuivre une
    # conversation avec tool-calling. Renvoyer tel quel le message d'un
    # fournisseur (ex: champ "reasoning_details" propre à OpenRouter/Nemotron)
    # peut faire échouer l'appel suivant si jamais il repart chez un autre
    # fournisseur ou une autre version d'API.
    result: dict = {"role": "assistant", "content": message.content}
    if message.tool_calls:
        result["tool_calls"] = [
            {
                "id": tool_call.id,
                "type": tool_call.type,
                "function": {
                    "name": tool_call.function.name,
                    "arguments": tool_call.function.arguments,
                },
            }
            for tool_call in message.tool_calls
        ]
    return result


def _get_message(response):
    # OpenRouter renvoie parfois un 200 OK avec un corps d'erreur (pas de
    # "choices") quand le fournisseur sous-jacent d'un modèle gratuit échoue
    # ponctuellement. Sans ce garde-fou, ça plante avec un TypeError peu clair.
    if not response.choices:
        error = getattr(response, "error", None)
        raise RuntimeError(f"Réponse invalide du fournisseur LLM (pas de 'choices') : {error or response}")
    return response.choices[0].message


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
    message = _get_message(response)

    # Contrairement au web_search serveur d'Anthropic, Groq et OpenRouter utilisent
    # le function calling classique : c'est notre code qui doit exécuter l'outil
    # demandé et renvoyer le résultat au modèle avant d'obtenir une réponse finale.
    while message.tool_calls:
        messages.append(_assistant_message_for_replay(message))
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
        message = _get_message(response)

    return message.content or ""
