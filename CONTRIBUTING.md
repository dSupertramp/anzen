# Contributing to Anzen

Thank you for helping make agentic AI safer.

## Philosophy

Anzen is built on three principles:

1. **Transparency** — every detection decision must be explainable
2. **Privacy** — your prompts never leave your infrastructure
3. **Zero friction** — security shouldn't require a PhD to integrate

## What we need most

- **New attack patterns** — found a new prompt injection technique? Open a PR adding it to `anzen/guards/prompt.py`
- **False positive reports** — if a legitimate message gets blocked, that's a bug
- **Integration adapters** — LangGraph, AutoGen, CrewAI, Haystack
- **Multilingual patterns** — Layer 1 is English-heavy; help us add Italian, Spanish, French, German, Chinese
- **Benchmark datasets** — labeled examples of attacks and clean messages

## Getting started

From the repository root (Python 3.13 required):

```bash
# Install with dev dependencies (uses uv)
uv sync --group dev

# Run tests
uv run pytest tests/ -v

# Lint
uv run ruff check anzen/

# Type check
uv run mypy anzen/ --ignore-missing-imports
```

To work on the monitor dashboard UI (optional):

```bash
cd ui/frontend
npm install
npm run dev
```

The backend for the dashboard lives in `anzen/server` and runs via `anzen monitor`.

## Pull Request guidelines

- One PR per concern — don't mix features with refactors
- Add a test for every new detection pattern
- New patterns must have a false positive rate < 0.1% on the benchmark dataset
- Run `ruff check anzen/` before opening a PR
- Sign off your commits (`git commit -s`)

## Adding a new detection pattern

1. Add the regex to the appropriate list in `anzen/guards/prompt.py`
2. Add a test case to `tests/test_anzen.py` — both a positive (attack) and a negative (clean message that looks similar)
3. Document the attack technique in the PR description with a real-world example

## Adding a new integration

Create `anzen/integrations/<framework>.py` following the pattern of `anthropic.py` or `langchain.py`.

For LLM wrappers: subclass `BaseCompletions` from `anzen.integrations._base`, implement `create()` and optionally `acreate()`, then use `BaseAdapter(YourCompletions(client))` and pass to `wrap()` from `anzen.client`.

The integration must:

- Require zero mandatory dependencies (lazy import)
- Expose a `filter_documents()` equivalent if the framework supports RAG
- Work with both sync and async frameworks

## Code of Conduct

Be excellent to each other. Security research is serious — so is treating people with respect.

## License

By contributing, you agree that your contributions will be licensed under the Apache 2.0 license.
