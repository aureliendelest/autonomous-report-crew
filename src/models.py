from typing import Literal

from pydantic import BaseModel


class CritiqueResult(BaseModel):
    status: Literal["OK", "KO"]
    gaps: list[str] = []
