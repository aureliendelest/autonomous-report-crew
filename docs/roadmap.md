# Roadmap

The order is designed around the project's quota constraint: **first the
tools to iterate without spending, then measurement, then improvements
guided by that measurement**. Fixing the AI domain before having a way to
measure it means guessing blindly with rare requests.

## Session 3: Pay down the debt (short, ~½ session)

**Goal:** a pipeline that doesn't sabotage itself.

- [x] **Accumulate research** in the loop (`research += ...`) instead of
  overwriting it.
- [x] **Slugify**: Unicode normalization (accents), removal of apostrophes
  and `/`, lowercase, dashes.
- [x] **Search config per domain** (`prompts/<domain>/search.json`: `topic`,
  `time_range`, `max_results`, `search_depth`), read by
  `prompts.load_search_config(domain)`.
- [x] **Truncated writer output**: writer `max_tokens` increased (1500) to
  avoid output cut off mid-sentence in the Sources section.
- [ ] **Clean up `.env.example`**: remove the superfluous `STREAMLIT_API_KEY`.
- [ ] **Clean up `CLAUDE.md`**: stack (Groq/OpenRouter/Tavily instead of
  Anthropic), updated roadmap, reference to this document.

**Done when:** the AI domain produces a readable report, even if imperfect,
and football reports are no longer truncated.

## Session 4: Iteration and tracing tools (~1 to 2 sessions)

**Goal:** never pay twice for the same thing again, and see what the agents
are actually doing.

- [ ] **Tavily disk cache** (`.cache/`, key = hash of the query + params,
  added to `.gitignore`), with a flag to disable it.
- [ ] **Structured JSON trace** per run (`outputs/<run>.trace.json`) with,
  for each step:
  - the agent, the turn, the duration;
  - input and output tokens;
  - the provider actually used (Groq or OpenRouter);
  - for each tool call: query, number of results, URLs, `cached: true/false`.
- [ ] **Step replay**: `--from-trace file --start-at critic` to rerun Critic
  and Writer without going back through Researcher.
- [ ] **Structured Critic output**: replace the fragile `STATUS: OK` text
  parsing with JSON (`{"status": "...", "gaps": [...]}`). This removes an
  entire class of format bugs.
- [ ] The `.audit.md` file stays a **readable view generated from the
  trace**, not a source of truth.

**Done when:** you can iterate 20 times on the Critic prompt with 0 Tavily
requests, and you can say for any run where the tokens and time went.

## Session 5: Mini-evaluation (~2 sessions, the core of the project)

**Goal:** turn "I judge by eye" into actual numbers.

- [ ] **Test set of 10 to 15 topics**: about 6 in football, 6 in AI,
  including a few tricky cases (homonymous club, club in crisis, very niche
  sector).
- [ ] **Frozen fixtures**: a first run populates the cache, subsequent
  evaluations replay it. Comparisons then run on the same starting data,
  without costing more requests.
- [ ] **Metrics, favoring what's verifiable by code:**

| Metric | How |
|---|---|
| Fabricated URLs | Does each URL in the report appear in the results Tavily actually returned? (automatic) |
| Stale sources | Source date vs. today's date (automatic if Tavily returns the date) |
| Format coverage | Are the expected sections present? (automatic) |
| Attribution errors | Player or figure attributed to the wrong club or study (**manual**, on a sub-sample) |
| Cost | Tokens, Tavily calls, latency, number of loop turns |

- [ ] **Ablations**: with/without Critic, and 0/1/2 loop turns. Compare
  quality *and* cost.
- [ ] If an LLM judge is added, **validate it by hand** on a few examples and
  say so in the report. An unvalidated judge is a weakness, not a strength.

**Done when:** a table like "the Critic reduces fabricated URLs by X% but
doubles the cost; the 2nd loop turn adds nothing for football but helps for
AI."

## Session 6: Improve the pipeline, guided by measurement (~1 to 2 sessions)

**Goal:** fix what the evaluation shows, not what's guessed.

- [ ] **Full content extraction** (Tavily `extract`, or
  `include_raw_content`) for key sources in the AI domain, since figures are
  rarely in the first 500 characters.
- [ ] **Figure verification**: automatic check that every figure in the
  report appears in the text of the cited source.
- [ ] **Tune prompts and `search.json`** for the AI domain, re-running the
  evaluation after each change.
- [ ] Document each fix as **problem → measurement before → change →
  measurement after**.

**Done when:** at least two improvements have a measured before/after.

## Session 7: Polish and presentation (~1 session)

- [ ] **Minimal pytest tests**, no network calls: Critic parsing, `slugify`,
  loop accumulation, cache, fabricated URL detection.
- [ ] **Streamlit**: show the trace (steps, tokens, queries) next to the
  report.
- [ ] **README rewrite**: architecture diagram, evaluation results, known
  limitations, how to reproduce.
- [ ] **`docs/report.md`**, 2 to 4 pages: the approach, the failures, the
  measurements. This is what gets sent with the job application.
- [ ] A short GIF or demo video.

## Optional: only if time remains

- **Dynamic domain creation** (the original session 3 idea). Nice as a demo,
  but it adds the least value for a recruiter: do it last, or drop it
  entirely.
- **Export the trace to an observability tool** (OpenTelemetry or Langfuse).
  Relevant only if specifically targeting Datadog, and only once everything
  else is solid.

## Priorities if time is short

| Priority | Content |
|---|---|
| **Essential** | Sessions 3, 4, 5, and the report |
| **Strongly recommended** | Session 6 (at least one measured improvement) and tests |
| **Bonus** | Enriched Streamlit, video, optional items |

For an end-of-studies internship, a smaller project that is **measured and
documented** will always be worth more than a larger project that relies on
"it works on my examples."
