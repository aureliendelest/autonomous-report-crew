from pathlib import Path

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"


def load_prompt(domain: str, agent_name: str) -> str:
    path = PROMPTS_DIR / domain / f"{agent_name}.md"
    return path.read_text(encoding="utf-8")
