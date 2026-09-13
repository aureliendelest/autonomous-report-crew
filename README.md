# autonomous-report-crew

Multi-agent research system — researcher, critic, and writer agents collaborate to
produce structured briefs on a given topic. Built on Groq (open-weight LLMs) with
Tavily for web search.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# then edit .env and add your GROQ_API_KEY and TAVILY_API_KEY
```

## Usage

```bash
python main.py --topic "Olympique de Marseille"
```

The generated report is saved under `/outputs`. `--domain` defaults to `football`
(the only domain wired up so far); it selects which prompt set under `/prompts` to use.

## How it works

Three agents run in sequence for each report:

1. **Chercheur** — searches the web (via Tavily) for recent results, news, and the
   next fixture for the given topic.
2. **Critique** — reviews the research for completeness, sourcing, and freshness,
   and can send the Chercheur back for another round (capped to avoid infinite loops).
3. **Rédacteur** — synthesizes everything into a final Markdown report.

See `CLAUDE.md` for the full project design and roadmap.
