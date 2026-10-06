import pytest

from src.orchestrator import _slugify


@pytest.mark.parametrize(
    ("topic", "expected"),
    [
        ("Olympique de Marseille", "olympique-de-marseille"),
        ("Atlético Madrid", "atletico-madrid"),
        ("L'Équipe / Ligue 1", "l-equipe-ligue-1"),
        ("  --FC  Nantes--  ", "fc-nantes"),
        ("!!!", ""),
        ("", ""),
    ],
)
def test_slugify(topic, expected):
    assert _slugify(topic) == expected
