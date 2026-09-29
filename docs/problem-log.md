# Problem log

This file is the project's technical memory. It serves two purposes:

1. **Before changing code or prompts**, read it to avoid reintroducing a
   problem that was already solved.
2. **After solving a new problem**, add an entry at the bottom of the
   relevant section (without waiting for the user to ask), using this format:

   - **Symptom**: what was observed
   - **Cause**: why it happened
   - **Solution**: what was done
   - **Where**: affected file(s)
   - **Rule**: what to always do / never do going forward

Write entries in English, with simple beginner/intermediate-level explanations.
Commit the log update together with the fix (e.g. "fix rate limit, update problem log").

---

## A. API, quotas and LLM providers

### A1. Groq model removed from the catalog
- **Symptom**: the call fails because `llama-3.3-70b-versatile` no longer exists.
- **Cause**: Groq changes its model catalog without warning.
- **Solution**: switched to `openai/gpt-oss-120b`.
- **Where**: `src/llm_client.py` (`GROQ_MODEL` and `OPENROUTER_MODEL` constants).
- **Rule**: model names stay as constants at the top of `llm_client.py`, never
  hardcoded elsewhere. If a "model not found" error appears, check the Groq /
  OpenRouter catalog before looking for a bug elsewhere.

### A2. 8000 tokens/minute limit on the Groq free tier
- **Symptom**: `RateLimitError` errors in the middle of the pipeline.
- **Cause**: content returned by Tavily plus agent responses exceeded the
  tokens-per-minute quota.
- **Solution**: `max_tokens` reduced to 800 by default, Tavily content
  truncated to 500 characters per result, 3 results max per search.
- **Where**: `src/llm_client.py` (`call_agent`), `src/web_search.py`
  (`MAX_CONTENT_CHARS`, `max_results=3`).
- **Rule**: don't raise these values without checking the quota. Any new
  feature that adds text to prompts must account for the 8000 tokens/min budget.

### A3. Rate limit errors: wait or switch over
- **Symptom**: the pipeline crashed or got stuck on a rate limit.
- **Cause**: two different situations were hiding behind the same error: a
  brief spike (a few seconds to wait) or an exhausted quota (daily limit,
  much longer).
- **Solution**: retry respecting the `retry-after` header (3 attempts max).
  If the wait exceeds 20 seconds, the quota is considered exhausted and the
  pipeline switches to OpenRouter.
- **Where**: `src/llm_client.py` (`_create_with_retry`, `_create_completion`).
- **Rule**: never block the pipeline silently on a long wait. Always print a
  console message when retrying or switching provider.

### A4. Incompatibility between providers in the conversation history
- **Symptom**: risk of the next call failing after a Groq ↔ OpenRouter
  switch mid-conversation.
- **Cause**: the message returned by one provider contains provider-specific
  fields (e.g. `reasoning_details` from OpenRouter/Nemotron) that the other
  provider doesn't understand.
- **Solution**: only replay standard fields (`role`, `content`, `tool_calls`)
  into the conversation.
- **Where**: `src/llm_client.py` (`_assistant_message_for_replay`).
- **Rule**: never append a provider's message as-is to `messages`. Always go
  through `_assistant_message_for_replay`.

### A5. OpenRouter returns "200 OK" without `choices`
- **Symptom**: unclear `TypeError` on `response.choices[0]`.
- **Cause**: the underlying provider behind a free model occasionally fails,
  and OpenRouter returns an error body with a 200 status code.
- **Solution**: 2 extra immediate retries, then `_get_message` raises a
  `RuntimeError` with a readable message.
- **Where**: `src/llm_client.py` (`_create_completion`, `_get_message`).
- **Rule**: always check `response.choices` before reading a message.

### A6. Function calling: our own code executes the tool
- **Symptom**: confusion with Anthropic's native server-side search tool
  (documentation and an earlier version of the project).
- **Cause**: Groq and OpenRouter use classic function calling: the model
  requests a call, but doesn't execute it.
- **Solution**: a `while message.tool_calls` loop that executes `web_search`,
  returns the result with the `tool` role, then calls the model again.
- **Where**: `src/llm_client.py` (`call_agent`), `src/web_search.py`.
- **Rule**: any new tool must have a schema (like `TAVILY_TOOL_SCHEMA`) AND a
  Python function registered in `tool_executors`.

---

## B. Web search (Tavily)

### B1. Results too old
- **Symptom**: the report talked about news several months old.
- **Cause**: a default Tavily search doesn't prioritize freshness.
- **Solution**: `topic="news"` and `time_range="month"`.
- **Where**: `src/web_search.py`.
- **Rule**: keep these two parameters for any news-based domain. If a future
  domain needs older sources, make it a parameter — don't remove the filter
  for everyone.

### B2. Tavily timeouts
- **Symptom**: the pipeline stopped on a timeout exception.
- **Cause**: the service sometimes takes too long to respond.
- **Solution**: 2 retries with a 2-second pause, then the error is allowed to
  propagate.
- **Where**: `src/web_search.py` (`MAX_TIMEOUT_RETRIES`).
- **Rule**: always cap retries so as not to burn through the Tavily quota.

---

## C. Orchestration

### C1. Risk of an infinite Critic ↔ Researcher loop
- **Symptom**: if the `STATUS: OK` marker is never detected, the Researcher
  gets relaunched endlessly and drains the Tavily quota.
- **Cause**: the model doesn't always follow the requested format.
- **Solution**: `MAX_RESEARCH_LOOPS = 2`. The marker must be on the very first
  line of the Critic's response (`startswith`).
- **Where**: `src/orchestrator.py`, `prompts/*/critique.md`.
- **Rule**: any loop between agents must have a cap. Never change the
  `STATUS: OK` / `STATUS: MORE_RESEARCH_NEEDED` format in a prompt without
  updating the code that detects it.

### C2. The Critic can't judge freshness
- **Symptom**: outdated information was being validated.
- **Cause**: the model doesn't know today's date.
- **Solution**: every message sent to the agents starts with "Today is <date>".
- **Where**: `src/agents.py` (`_today`, used in the three `run_*` functions).
- **Rule**: any new agent that judges or writes time-sensitive content must
  receive today's date.

### C3. Audit log
- **Symptom**: impossible to understand why a report was wrong or incomplete.
- **Solution**: every step (Researcher turn N, Critic turn N) is saved to an
  `.audit.md` file next to the report.
- **Where**: `src/orchestrator.py` (`_format_audit_log`).
- **Rule**: any new pipeline step must be added to `steps` to appear in the
  audit log.

---

## D. Report quality (prompts)

### D1. The Researcher couldn't find the latest matches
- **Symptom**: the OM report announced a 4-0 win from August 21st as a
  "recent result", even though the club had just lost three games in a row.
- **Cause**: a generic search on the club name surfaces the season's first
  match, not the most recent ones.
- **Solution**: the prompt asks to look up the current standings/schedule to
  identify the last matchday played, then the last 3 matches. The Critic
  requests additional research if only one result is found.
- **Where**: `prompts/football/chercheur.md`, `prompts/football/critique.md`.
- **Rule**: a football report must always contain the last 3 matches played.
  Test with a club whose current form is very marked (strong winning or
  losing streak).

### D2. Neutral tone masking a crisis
- **Symptom**: a losing streak or a sporting crisis appeared as a plain list
  of results.
- **Cause**: without guidance, the Writer defaults to a neutral tone and the
  Researcher doesn't look for reactions.
- **Solution**: the Researcher specifically looks for reactions around a
  notable event, the Critic checks that it's highlighted, and the Writer
  must place it in the Summary and Key Points.
- **Where**: `prompts/football/chercheur.md`, `critique.md`, `redacteur.md`.
- **Rule**: every new domain must define what counts as a "notable event" in
  its three prompts.

### D3. Wrong attributions (player → wrong club, figure → wrong source)
- **Symptom**: players or figures were attributed to the wrong club or company.
- **Cause**: the model fills gaps from its own memory instead of sticking to
  the source.
- **Solution**: all three prompts require verifying the attribution
  explicitly in the source text, and omitting the information if in doubt.
- **Where**: all `chercheur.md`, `critique.md` and `redacteur.md` prompts.
- **Rule**: every new prompt must include this anti-fabrication instruction.
  Never remove "if in doubt, leave it out".

### D4. Final report cut off (or too long)
- **Symptom**: the Writer's report stops mid-sentence or mid-URL (e.g. the
  sources list in `football-olympique-de-marseille-20260913-1222.md`).
- **Cause**: the 800-token budget is too short for table + prose + sources,
  especially with the OpenRouter fallback model, which is more verbose.
- **Partial solution**: `max_tokens=1500` for the Writer only.
- **Where**: `src/agents.py` (`run_redacteur`).
- **Status**: still an open issue on some reports. Possible directions:
  detect `finish_reason == "length"` and retry with a larger budget, or ask
  the Writer to be more concise.
- **Rule**: after any change to the Writer, verify that the generated report
  ends with a complete "Sources" section.

### D5. Promotional tone on AI adoption in business
- **Symptom**: risk of reports that only talk about benefits.
- **Solution**: the Critic requires adoption barriers and sourced figures,
  the Writer must present a balanced table.
- **Where**: `prompts/ia-entreprise/*.md`.
- **Rule**: keep the benefits / limitations balance in the "ia-entreprise" domain.

---

## Checklist before committing
- [ ] The solved problem is documented in the right section (A to D) using
      the format above
- [ ] No model, quota, or cap was changed without updating the relevant entry
- [ ] `git status` checked: no `.env` or temporary files included
