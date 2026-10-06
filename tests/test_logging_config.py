import json
import logging

import pytest

from src import prompts
from src.logging_config import HANDLER_NAME, JsonFormatter, setup_logging


@pytest.fixture
def clean_root_logger():
    """Give each test a root logger without our handler, and restore the global state after."""
    root = logging.getLogger()
    handlers, level = root.handlers[:], root.level
    httpx_level = logging.getLogger("httpx").level
    root.handlers = [h for h in handlers if h.get_name() != HANDLER_NAME]
    yield root
    root.handlers = handlers
    root.setLevel(level)
    logging.getLogger("httpx").setLevel(httpx_level)


def our_handlers(root):
    return [h for h in root.handlers if h.get_name() == HANDLER_NAME]


def test_json_formatter_exports_extra_fields():
    record = logging.LogRecord("src.llm_client", logging.WARNING, __file__, 1, "quota épuisé pour %s", ("m1",), None)
    record.model = "m1"  # what logging does with extra={"model": "m1"}
    record.wait_s = 12.5

    payload = json.loads(JsonFormatter().format(record))

    assert payload["level"] == "WARNING"
    assert payload["logger"] == "src.llm_client"
    assert payload["message"] == "quota épuisé pour m1"
    assert payload["model"] == "m1"
    assert payload["wait_s"] == 12.5
    assert "time" in payload


def test_setup_logging_is_idempotent(clean_root_logger):
    setup_logging()
    setup_logging()

    assert len(our_handlers(clean_root_logger)) == 1


def test_log_format_json_selects_the_json_formatter(clean_root_logger, monkeypatch):
    monkeypatch.setenv("LOG_FORMAT", "json")

    setup_logging()

    assert isinstance(our_handlers(clean_root_logger)[0].formatter, JsonFormatter)


def test_default_format_is_plain_text(clean_root_logger, monkeypatch):
    monkeypatch.delenv("LOG_FORMAT", raising=False)

    setup_logging()

    assert not isinstance(our_handlers(clean_root_logger)[0].formatter, JsonFormatter)


def test_log_level_is_read_from_the_environment(clean_root_logger, monkeypatch):
    monkeypatch.setenv("LOG_LEVEL", "error")

    setup_logging()

    assert clean_root_logger.level == logging.ERROR


def test_an_invalid_log_level_falls_back_to_info(clean_root_logger, monkeypatch):
    monkeypatch.setenv("LOG_LEVEL", "n'importe quoi")

    setup_logging()

    assert clean_root_logger.level == logging.INFO


def test_missing_search_config_logs_a_structured_warning(monkeypatch, tmp_path, caplog):
    monkeypatch.setattr(prompts, "PROMPTS_DIR", tmp_path)
    (tmp_path / "football").mkdir()

    with caplog.at_level(logging.WARNING, logger="src.prompts"):
        config = prompts.load_search_config("football")

    assert config == prompts.DEFAULT_SEARCH_CONFIG
    assert caplog.records[0].domain == "football"
