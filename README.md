# autonomous-report-crew

Multi-agent research system — researcher, critic, and writer agents collaborate to
produce structured briefs on a given topic. Built on Groq (open-weight LLMs) with
Tavily for web search.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install ".[dev]"          # dependencies + dev tools (ruff, pre-commit)
pre-commit install            # run ruff automatically on every commit
cp .env.example .env
# then edit .env and add your GROQ_API_KEY and TAVILY_API_KEY
```

Dependencies and tool configuration live in `pyproject.toml`. Check the code with:

```bash
ruff check .            # lint
ruff format --check .   # formatting
```

## Usage

```bash
python main.py --topic "Olympique de Marseille"
```

The generated report is saved under `/outputs`. `--domain` defaults to `football`
(the only domain wired up so far); it selects which prompt set under `/prompts` to use.

### Logging

Diagnostic events (rate limits, model fallback, search timeouts...) are logged to stderr.
Two optional environment variables (set them in your shell or in `.env`) tune them:

| Variable | Values | Default |
|---|---|---|
| `LOG_LEVEL` | `DEBUG`, `INFO`, `WARNING`, `ERROR` | `INFO` |
| `LOG_FORMAT` | `text` (readable), `json` (one JSON object per line) | `text` |

```bash
LOG_FORMAT=json python main.py --topic "Olympique de Marseille" 2> run.log.jsonl
```

## Docker

Requires Docker Desktop. The same image runs the Streamlit app and the CLI.

```bash
cp .env.example .env          # then add your own API keys
docker compose up --build     # Streamlit on http://localhost:8501

# CLI or evaluation, using the same image
docker compose run --rm app python main.py --topic "Olympique de Marseille"
docker compose run --rm app python -m eval.run_eval
```

- API keys are read from your local `.env` at runtime and are never copied into the image.
- The app is published on `127.0.0.1` only, so it is not reachable from other machines.
- `outputs/`, `.cache/` and `eval/` are mounted from the host, so reports, the Tavily
  cache and evaluation results survive the container.
- Code and prompts are baked into the image: rebuild (`docker compose up --build`) after editing them.

## How it works

Three agents run in sequence for each report:

1. **Chercheur** — searches the web (via Tavily) for recent results, news, and the
   next fixture for the given topic.
2. **Critique** — reviews the research for completeness, sourcing, and freshness,
   and can send the Chercheur back for another round (capped to avoid infinite loops).
3. **Rédacteur** — synthesizes everything into a final Markdown report.

See `CLAUDE.md` for the full project design and roadmap.
