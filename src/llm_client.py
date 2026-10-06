import json
import logging
import os
import time
from collections.abc import Callable

from dotenv import load_dotenv
from groq import Groq, RateLimitError
from openai import OpenAI

load_dotenv()

logger = logging.getLogger(__name__)

# Modèles Groq essayés dans l'ordre (le plus gros/meilleur en premier), chacun
# ayant son propre quota séparé sur le plan gratuit. Groq expose deux quotas
# distincts par modèle (visibles dans les headers x-ratelimit-* de chaque
# réponse) : un plafond de requêtes qui se recharge sur ~1h glissante, et un
# plafond de tokens qui se recharge en quelques secondes à quelques minutes —
# aucun des deux n'est "journalier". Quand un modèle est à quota, on passe au
# suivant plutôt que d'attendre — voir _create_completion. On exclut
# volontairement gpt-oss-safeguard-20b (variante durcie pour la modération de
# contenu, pas conçue pour rédiger des rapports).
GROQ_MODELS = [
    "openai/gpt-oss-120b",
    "openai/gpt-oss-20b",
    "qwen/qwen3.8-27b",
]
# Modèle de secours sur OpenRouter, utilisé uniquement quand tous les modèles
# Groq ci-dessus sont épuisés. À revérifier sur https://openrouter.ai/models si
# ce modèle gratuit n'est plus disponible (leur catalogue évolue, comme celui
# de Groq).
OPENROUTER_MODEL = "nvidia/nemotron-3-super-120b-a12b:free"

MAX_RATE_LIMIT_RETRIES = 3
MAX_RETRY_WAIT_SECONDS = 20
MAX_OPENROUTER_RETRIES = 2

# Modèles Groq vus comme à quota durant ce process, avec l'instant (time.time())
# où ils redeviennent utilisables (lu dans le header "retry-after" de Groq).
# Sans ce cache, chaque tour de conversation retentait depuis le début de
# GROQ_MODELS et payait à nouveau les retries (jusqu'à MAX_RATE_LIMIT_RETRIES x
# MAX_RETRY_WAIT_SECONDS) sur un modèle qu'on sait déjà à quota. Le quota se
# rechargeant en minutes/heure (pas par jour, voir commentaire GROQ_MODELS
# ci-dessus), on retente le modèle dès que ce délai est passé plutôt que de le
# bannir pour le reste du process.
_exhausted_until: dict[str, float] = {}


def get_groq_client() -> Groq:
    if not os.environ.get("GROQ_API_KEY"):
        raise RuntimeError("GROQ_API_KEY n'est pas défini. Copie .env.example vers .env et renseigne ta clé.")
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
                # patienter mais un quota (requêtes ou tokens, voir les headers
                # x-ratelimit-* de Groq) qui prendra plus longtemps à se
                # recharger : on laisse l'appelant basculer sur le modèle
                # suivant plutôt que de bloquer le pipeline en silence.
                raise
            logger.warning(
                "limite de débit Groq atteinte, nouvelle tentative dans %.1fs",
                wait_seconds,
                extra={"wait_s": wait_seconds},
            )
            time.sleep(wait_seconds)


def _create_completion(messages: list[dict], tools: list[dict] | None, max_tokens: int, force_no_tool: bool = False):
    """Essaie chaque modèle Groq de GROQ_MODELS pas actuellement à quota (voir
    `_exhausted_until`), puis bascule sur OpenRouter si tous le sont.

    Chaque tour de la conversation repasse par cette fonction. Un modèle vu
    comme à quota n'est retenté qu'une fois le délai indiqué par Groq
    (`retry-after`) écoulé — voir `_exhausted_until`. C'est sans risque de
    mélanger les fournisseurs/modèles d'un tour à l'autre car les messages
    renvoyés dans la conversation sont assainis par
    `_assistant_message_for_replay` (voir plus bas) : aucun champ propre à un
    fournisseur (ex: "reasoning_details" d'OpenRouter/Nemotron) n'y subsiste.

    `force_no_tool` garde `tools` dans la requête (nécessaire : Groq refuse
    avec une 400 si l'historique contient des tool calls mais que `tools`
    n'est plus fourni) tout en interdisant au modèle de s'en resservir, via
    `tool_choice="none"`.
    """
    groq_kwargs = {"max_tokens": max_tokens, "reasoning_effort": "low"}
    if tools:
        groq_kwargs["tools"] = tools
        if force_no_tool:
            groq_kwargs["tool_choice"] = "none"

    now = time.time()
    remaining_models = [m for m in GROQ_MODELS if _exhausted_until.get(m, 0) <= now]
    if remaining_models:
        groq_client = get_groq_client()
        for i, model in enumerate(remaining_models):
            try:
                return _create_with_retry(groq_client, model=model, messages=messages, **groq_kwargs), model
            except RateLimitError as e:
                wait_seconds = float(e.response.headers.get("retry-after", 60))
                _exhausted_until[model] = time.time() + wait_seconds
                is_last_model = i == len(remaining_models) - 1
                logger.warning(
                    "quota épuisé pour %s (retente dans %.0fs)%s",
                    model,
                    wait_seconds,
                    "" if is_last_model else ", essai du modèle suivant",
                    extra={"model": model, "wait_s": wait_seconds},
                )
                if not is_last_model:
                    continue

    openrouter_client = get_openrouter_client()
    if openrouter_client is None:
        raise RuntimeError("Tous les modèles Groq sont à quota et OPENROUTER_API_KEY n'est pas défini.")
    logger.warning(
        "quota épuisé pour tous les modèles Groq, bascule sur OpenRouter",
        extra={"model": OPENROUTER_MODEL},
    )
    return _create_openrouter_completion(openrouter_client, messages, tools, max_tokens, force_no_tool)


def _create_openrouter_completion(
    openrouter_client, messages: list[dict], tools: list[dict] | None, max_tokens: int, force_no_tool: bool
):
    openrouter_kwargs = {"max_tokens": max_tokens}
    if tools:
        openrouter_kwargs["tools"] = tools
        if force_no_tool:
            openrouter_kwargs["tool_choice"] = "none"

    # Les modèles gratuits OpenRouter peuvent renvoyer un accroc ponctuel
    # côté fournisseur sous-jacent (réponse sans "choices") ; un modèle
    # gratuit tolère bien une nouvelle tentative immédiate.
    for attempt in range(MAX_OPENROUTER_RETRIES + 1):
        response = openrouter_client.chat.completions.create(
            model=OPENROUTER_MODEL, messages=messages, **openrouter_kwargs
        )
        if response.choices:
            return response, OPENROUTER_MODEL
        if attempt < MAX_OPENROUTER_RETRIES:
            logger.warning("réponse OpenRouter invalide, nouvelle tentative", extra={"attempt": attempt + 1})
    return response, OPENROUTER_MODEL


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


MAX_TOOL_CALLS = 6


def _timed_completion(
    on_call: Callable[[dict], None] | None,
    messages: list[dict],
    tools: list[dict] | None,
    max_tokens: int,
    force_no_tool: bool = False,
):
    start = time.perf_counter()
    response, model = _create_completion(messages, tools, max_tokens, force_no_tool)
    if on_call:
        usage = response.usage
        on_call(
            {
                "provider": model,
                "input_tokens": usage.prompt_tokens if usage else 0,
                "output_tokens": usage.completion_tokens if usage else 0,
                "duration_s": time.perf_counter() - start,
            }
        )
    return response


def call_agent(
    system_prompt: str,
    user_message: str,
    tools: list[dict] | None = None,
    tool_executors: dict | None = None,
    max_tokens: int = 800,
    on_call: Callable[[dict], None] | None = None,
) -> str:
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]

    response = _timed_completion(on_call, messages, tools, max_tokens)
    message = _get_message(response)

    # Contrairement au web_search serveur d'Anthropic, Groq et OpenRouter utilisent
    # le function calling classique : c'est notre code qui doit exécuter l'outil
    # demandé et renvoyer le résultat au modèle avant d'obtenir une réponse finale.
    tool_call_count = 0
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
            tool_call_count += 1

        # Au-delà de cette limite, un modèle qui n'arrive pas à conclure peut
        # enchaîner les appels d'outils indéfiniment (observé : 30 recherches
        # web pour un seul rapport). On lui demande explicitement de conclure
        # avec ce qu'il a. On ne peut pas simplement retirer `tools` de cet
        # appel : Groq refuse (400 "Tool choice is none, but model called a
        # tool") si l'historique contient des tool calls mais que `tools`
        # n'est plus fourni — il faut donc garder `tools` et forcer via
        # `tool_choice="none"` à la place.
        if tool_call_count >= MAX_TOOL_CALLS:
            logger.warning(
                "limite de %d appels d'outils atteinte, réponse forcée",
                MAX_TOOL_CALLS,
                extra={"limit": MAX_TOOL_CALLS},
            )
            messages.append(
                {
                    "role": "user",
                    "content": (
                        "Tu as atteint le nombre maximum de recherches autorisées. "
                        "Réponds maintenant avec ton livrable final, en utilisant "
                        "uniquement les informations déjà obtenues ci-dessus."
                    ),
                }
            )
            response = _timed_completion(on_call, messages, tools, max_tokens, force_no_tool=True)
            message = _get_message(response)
            break

        response = _timed_completion(on_call, messages, tools, max_tokens)
        message = _get_message(response)

    return message.content or ""
