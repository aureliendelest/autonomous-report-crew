from . import llm_client, prompts
from .web_search import TAVILY_TOOL_SCHEMA, web_search


def run_chercheur(topic: str, domain: str, feedback: str | None = None) -> str:
    system = prompts.load_prompt(domain, "chercheur")
    user_message = f"Sujet : {topic}"
    if feedback:
        user_message += (
            f"\n\nLe critique a demandé des recherches complémentaires :\n{feedback}"
        )
    return llm_client.call_agent(
        system,
        user_message,
        tools=[TAVILY_TOOL_SCHEMA],
        tool_executors={"web_search": web_search},
    )


def run_critique(topic: str, domain: str, research: str) -> str:
    system = prompts.load_prompt(domain, "critique")
    user_message = f"Sujet : {topic}\n\nRecherches du Chercheur :\n{research}"
    return llm_client.call_agent(system, user_message)


def run_redacteur(topic: str, domain: str, research: str, critique: str) -> str:
    system = prompts.load_prompt(domain, "redacteur")
    user_message = (
        f"Sujet : {topic}\n\nRecherches :\n{research}\n\nAvis du Critique :\n{critique}"
    )
    return llm_client.call_agent(system, user_message)
