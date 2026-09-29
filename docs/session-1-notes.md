# Session 1 — Notes

## What was built
CLI pipeline with 3 agents (Researcher → Critic → Writer) for the football
domain, with a capped feedback loop between Critic and Researcher.

## Technical decisions
- **LLM**: Groq (`openai/gpt-oss-120b`), OpenAI-compatible API, classic
  function calling (unlike Anthropic's native server-side tool, our own code
  executes the search call and returns the result to the model).
- **Web search**: Tavily (`topic="news"`, `time_range="month"` to favor
  recent results).
- **Token limit**: the Groq free tier caps at 8000 tokens/minute. The
  `max_tokens` per call was reduced (800) and Tavily content truncated to
  stay under this limit.
- **Today's date** injected into messages sent to the agents (Researcher and
  Critic), without which the Critic can't judge whether information is
  outdated.
- **Capped research loop** (`MAX_RESEARCH_LOOPS = 2`) to prevent a bug in the
  `STATUS: OK` marker detection from draining the entire Tavily quota.

## Known limitations
- Source quality entirely depends on what Tavily returns: the Critic can
  detect missing or outdated info, but can't verify the factual accuracy of
  a source it judges correct.
- `openai/gpt-oss-120b` model: needs monitoring in case Groq changes its
  model catalog again (the previous choice, `llama-3.3-70b-versatile`, was
  already unavailable).
