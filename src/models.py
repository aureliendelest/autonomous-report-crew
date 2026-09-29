from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel


class CritiqueResult(BaseModel):
    status: Literal["OK", "KO"]
    gaps: list[str] = []


@dataclass
class RunConfig:
    max_research_loops: int = 2
    skip_critic: bool = False  # si True, max_research_loops est ignoré : pas de Critique, donc pas de boucle
    label: str = "baseline"
