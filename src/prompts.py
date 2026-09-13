from pathlib import Path

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"


def load_prompt(domain: str, agent_name: str) -> str:
    path = PROMPTS_DIR / domain / f"{agent_name}.md"
    return path.read_text(encoding="utf-8")


def list_domains() -> list[str]:
    return sorted(p.name for p in PROMPTS_DIR.iterdir() if p.is_dir())
