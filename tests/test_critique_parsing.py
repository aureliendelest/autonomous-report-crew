import pytest

from src.orchestrator import _parse_critique, _strip_markdown_fence

INVALID_FALLBACK_GAP = "Réponse du Critique invalide ou non-JSON"


def test_valid_ok():
    result, error = _parse_critique('{"status": "OK", "gaps": []}')
    assert result.status == "OK"
    assert result.gaps == []
    assert error is None


def test_valid_ko_keeps_gaps():
    result, error = _parse_critique('{"status": "KO", "gaps": ["score manquant", "source périmée"]}')
    assert result.status == "KO"
    assert result.gaps == ["score manquant", "source périmée"]
    assert error is None


def test_gaps_default_to_empty():
    result, _ = _parse_critique('{"status": "OK"}')
    assert result.gaps == []


@pytest.mark.parametrize(
    "text",
    [
        '```json\n{"status": "OK", "gaps": []}\n```',
        '```\n{"status": "OK", "gaps": []}\n```',
        '  ```json\n{"status": "OK", "gaps": []}\n```  ',
    ],
)
def test_markdown_fence_is_stripped(text):
    result, error = _parse_critique(text)
    assert result.status == "OK"
    assert error is None


@pytest.mark.parametrize(
    "text",
    [
        "STATUT: OK",
        "",
        "[]",
        '{"status": "MAYBE", "gaps": []}',
        '{"gaps": ["pas de statut"]}',
        '{"status": "OK", "gaps": "pas une liste"}',
    ],
)
def test_invalid_answer_falls_back_to_ko_and_keeps_the_error(text):
    result, error = _parse_critique(text)
    assert result.status == "KO"
    assert result.gaps == [INVALID_FALLBACK_GAP]
    assert error


def test_strip_markdown_fence_leaves_plain_text_alone():
    assert _strip_markdown_fence('  {"status": "OK"}  ') == '{"status": "OK"}'
