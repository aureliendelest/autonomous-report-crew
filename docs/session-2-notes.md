# Session 2 — Notes

## What was built
Streamlit front-end (`app.py`) with domain selection from a pre-configured
list (football, ia-entreprise), report generation with live progress
tracking, `.md` download, and a history tab listing already-generated
reports (grouped by domain). Added the second "serious" domain
(ia-entreprise) and a fallback LLM provider to make the pipeline more
reliable.

## Technical decisions
- **Second domain (`ia-entreprise`)**: dedicated Researcher/Critic/Writer
  prompts in `/prompts/ia-entreprise`, same architecture as football.
- **Per-domain search window** (`src/agents.py`): football stays on
  `topic="news"` / `time_range="week"` (needs the very latest results),
  ia-entreprise switches to `topic="general"` / `time_range="year"` to reach
  study reports and press releases, which a one-week "news" window would miss.
- **OpenRouter fallback** (`src/llm_client.py`): when the Groq quota (free
  tier, 8000 tokens/min) is exhausted, automatic switch to a free OpenRouter
  model (`nvidia/nemotron-3-super-120b-a12b:free`). Each turn of the
  conversation retries Groq then falls back to OpenRouter independently (the
  quota can run out mid-conversation, not just on the first call).
- **Sanitizing replayed messages**: assistant messages re-injected into the
  conversation (for tool-calling) are reduced to standard fields (`role`,
  `content`, `tool_calls`). Necessary because OpenRouter/Nemotron adds a
  `reasoning_details` field that the Groq API rejects if the conversation
  falls back to Groq on a later turn.
- **Anti-hallucination guardrail for URLs** (`src/agents.py`): the Researcher
  can cite a plausible-looking URL that was never actually returned by
  Tavily, especially under pressure from the Critic requesting more sources.
  The code (not just the prompt) compares URLs cited in the response against
  those actually seen in `web_search` results, and adds a visible automatic
  warning for any unverified URL. The Critic and Writer are instructed to
  treat this warning as reliable and exclude flagged URLs.
- **Continuity between research loops**: the Researcher now receives its own
  research from the previous turn (not just the Critic's feedback), so it
  only fills in what's missing instead of redoing everything each loop.
- **Anti chain-of-thought leak**: the Researcher must produce only the final
  deliverable, never its intermediate reasoning — a model that sometimes
  wrote its reasoning instead of the report would systematically break the
  Critic loop, and the Writer would end up copying the Critic's raw text
  verbatim (e.g. `STATUS: MORE_RESEARCH_NEEDED`) into the final report.
- **Report produced even if the Critic never approves it** (beyond
  `MAX_RESEARCH_LOOPS`): the orchestrator explicitly flags this to the
  Writer, which must then note the uncertain points in the summary instead
  of staying silent about them or copying the Critic's opinion verbatim.
- **Writer's `max_tokens` increased to 1500**: the final report (tables +
  prose) exceeded the default budget, especially with the more verbose
  OpenRouter fallback model.
- **Report history in the front-end**: `.audit.md` files (audit logs
  generated alongside the report) are excluded from the list; each report's
  domain is determined by matching the filename against known domains rather
  than splitting on the first hyphen, since a domain name can itself contain
  a hyphen (`ia-entreprise`).

## Known limitations
- The OpenRouter fallback model (`nvidia/nemotron-3-super-120b-a12b:free`) is
  a free model: needs rechecking on openrouter.ai/models in case its
  availability changes, as already happened with Groq.
- Free OpenRouter models sometimes return a 200 OK without `choices` due to a
  transient hiccup from the underlying provider; the code retries
  automatically (2 attempts) but the exact root cause on OpenRouter's side
  remains opaque.
- The anti-hallucination guardrail detects fabricated URLs, but can't verify
  the accuracy of a real URL that's cited incorrectly.
