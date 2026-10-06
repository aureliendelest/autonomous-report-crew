FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    STREAMLIT_SERVER_HEADLESS=true \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false

WORKDIR /app

# Dependencies first: this layer is only rebuilt when pyproject.toml changes,
# not on every code edit. Only runtime dependencies are installed (no [dev] extra).
COPY pyproject.toml .
RUN pip install .

RUN useradd --create-home --uid 1000 app

# API keys are never copied here: they are injected at runtime (see docker-compose.yml).
COPY --chown=app:app src ./src
COPY --chown=app:app prompts ./prompts
COPY --chown=app:app eval ./eval
COPY --chown=app:app app.py main.py ./

# Written at runtime; created here so the non-root user can write to them.
RUN mkdir -p outputs .cache && chown app:app outputs .cache

USER app

EXPOSE 8501

# Default command: the Streamlit app. Override it to run the CLI or the eval, e.g.
#   docker compose run --rm app python main.py --topic "FC Nantes"
CMD ["streamlit", "run", "app.py", "--server.address=0.0.0.0", "--server.port=8501"]
