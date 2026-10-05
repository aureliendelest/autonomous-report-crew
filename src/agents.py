import re
from collections.abc import Callable
from datetime import date

from . import llm_client, prompts
from .web_search import TAVILY_TOOL_SCHEMA, web_search

URL_RE = re.compile(r"https?://[^\s\)\]\>\"'】]+")


def _extract_urls(text: str) -> set[str]:
    return {url.rstrip(".,;:)]}>»") for url in URL_RE.findall(text)}


def _today() -> str:
    return date.today().strftime("%d %B %Y")


def run_chercheur(
    topic: str,
    domain: str,
    feedback: str | None = None,
    previous_research: str | None = None,
    use_cache: bool = True,
    on_call: Callable[[dict], None] | None = None,
) -> str:
    system = prompts.load_prompt(domain, "chercheur")
    user_message = f"Nous sommes le {_today()}.\n\nSujet : {topic}"
    if previous_research:
        user_message += (
            f"\n\nTes recherches précédentes :\n{previous_research}\n\n"
            "Conserve les informations ci-dessus qui n'ont pas été signalées "
            "comme problématiques : ne relance pas une recherche sur ce qui "
            "est déjà validé, complète uniquement ce qui manque."
        )
    if feedback:
        user_message += f"\n\nLe critique a demandé des recherches complémentaires :\n{feedback}"

    search_config = prompts.load_search_config(domain)
    seen_urls: set[str] = set()

    def scoped_web_search(query: str) -> str:
        result, meta = web_search(query, use_cache=use_cache, **search_config)
        seen_urls.update(meta["urls"])
        if on_call:
            on_call({"tool_call": {"query": query, **meta}})
        return result

    research = llm_client.call_agent(
        system,
        user_message,
        tools=[TAVILY_TOOL_SCHEMA],
        tool_executors={"web_search": scoped_web_search},
        on_call=on_call,
    )

    # Garde-fou anti-hallucination : un LLM peut citer une URL plausible mais
    # jamais retournée par une vraie recherche, surtout sous pression du
    # Critique qui en redemande. On ne peut pas compter sur le seul prompt
    # pour l'en empêcher, donc on vérifie ici, en code, que chaque URL citée
    # provient bien d'un résultat de web_search réellement obtenu.
    fabricated_urls = _extract_urls(research) - seen_urls
    if fabricated_urls:
        research += (
            "\n\n**⚠️ Alerte automatique (vérification technique, pas le Chercheur) "
            "— URLs non vérifiées :** les URLs suivantes apparaissent ci-dessus "
            "mais ne proviennent d'aucun résultat de recherche web réel obtenu "
            "durant cette session ; elles sont probablement fabriquées et ne "
            "doivent pas être considérées comme fiables :\n" + "\n".join(f"- {url}" for url in sorted(fabricated_urls))
        )

    return research


def run_critique(topic: str, domain: str, research: str, on_call: Callable[[dict], None] | None = None) -> str:
    system = prompts.load_prompt(domain, "critique")
    user_message = f"Nous sommes le {_today()}.\n\nSujet : {topic}\n\nRecherches du Chercheur :\n{research}"
    return llm_client.call_agent(system, user_message, on_call=on_call)


def run_redacteur(
    topic: str,
    domain: str,
    research: str,
    critique: str,
    incomplete: bool = False,
    on_call: Callable[[dict], None] | None = None,
) -> str:
    system = prompts.load_prompt(domain, "redacteur")
    user_message = (
        f"Nous sommes le {_today()}.\n\nSujet : {topic}\n\nRecherches :\n{research}\n\nAvis du Critique :\n{critique}"
    )
    if incomplete:
        user_message += (
            "\n\nLe Critique n'a pas validé ces recherches malgré plusieurs tentatives "
            "(les points qu'il soulève ci-dessus n'ont pas pu être résolus). "
            "Rédige quand même le rapport final avec les informations disponibles, "
            "en indiquant clairement dans le Résumé que certains points restent "
            "incertains ou non vérifiés plutôt que de les passer sous silence. "
            "N'inclus jamais le texte de l'avis du Critique tel quel : reformule "
            "uniquement ce qui concerne le lecteur du rapport."
        )
    # Le rapport final (tableaux + prose) dépasse souvent le budget par défaut,
    # surtout avec le modèle de secours OpenRouter, plus verbeux.
    return llm_client.call_agent(system, user_message, max_tokens=1500, on_call=on_call)
