import json
import logging
import os
import sys
from datetime import UTC, datetime

HANDLER_NAME = "report_crew"

# Attributes every LogRecord has by default: anything else found on a record
# was added through `extra=` and is exported as a structured field.
_RECORD_ATTRS = set(logging.makeLogRecord({}).__dict__) | {"message", "asctime"}


class JsonFormatter(logging.Formatter):
    """One JSON object per line: easy to filter with jq or to load into a database."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "time": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="seconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        payload.update({key: value for key, value in vars(record).items() if key not in _RECORD_ATTRS})
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


def setup_logging() -> None:
    """Send logs to stderr. LOG_LEVEL (default INFO) and LOG_FORMAT (text or json) tune it."""
    root = logging.getLogger()
    # Streamlit re-runs app.py on every interaction: without this guard each run
    # would add another handler and every line would be printed several times.
    if any(handler.get_name() == HANDLER_NAME for handler in root.handlers):
        return

    level = logging.getLevelNamesMapping().get(os.environ.get("LOG_LEVEL", "INFO").upper(), logging.INFO)
    if os.environ.get("LOG_FORMAT", "text").lower() == "json":
        formatter = JsonFormatter()
    else:
        formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s", "%Y-%m-%d %H:%M:%S")

    handler = logging.StreamHandler(sys.stderr)
    handler.set_name(HANDLER_NAME)
    handler.setFormatter(formatter)
    root.addHandler(handler)
    root.setLevel(level)

    # httpx logs one INFO line per HTTP request: too noisy unless debugging.
    if level > logging.DEBUG:
        for noisy in ("httpx", "httpcore"):
            logging.getLogger(noisy).setLevel(logging.WARNING)
