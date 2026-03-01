# CLAUDE.md — Agent Loop

## Project Overview

Single-file Python script (`agent_loop.py`) that orchestrates three AI CLI tools (Claude, Codex, Gemini) to collaboratively research open-ended questions through a 6-phase pipeline.

## Architecture

- **No external dependencies** — pure Python 3.10+ stdlib
- **Single file** — all logic in `agent_loop.py`
- **CLI subprocess model** — each agent is called via its CLI in non-interactive mode
- **Parallel execution** — Phase 2 (Research) and Phase 3 (Challenge) use `ThreadPoolExecutor`

## Key Design Decisions

- Prompts are passed via **stdin** (not CLI args) to avoid shell escaping and ARG_MAX limits
- Claude requires **`env -u CLAUDECODE`** to avoid nested session detection
- Gemini's `-p` flag requires a value, so we pass `" "` (space) and pipe the real prompt via stdin from a temp file
- Codex uses `--full-auto` (not `-a never`, which is interactive-only)
- Gemini thinking config is set in `~/.gemini/settings.json` because the CLI has no flag for it

## Models

- Claude: `claude-opus-4-6` with `--effort high`
- Codex: `gpt-5.3-codex` with `-c model_reasoning_effort="high"`
- Gemini: `gemini-3.1-pro-preview` with `thinkingLevel: "HIGH"` in settings

## File Structure

```
agent_loop.py          # Everything — CLI callers, prompts, phases, HTML template, main()
workspace/             # Auto-created per run, stores all intermediate outputs
```

## Common Issues

- **Claude "nested session" error**: The `CLAUDECODE` env var must be unset. Already handled in `call_claude()`.
- **Codex "not inside a trusted directory"**: Use `--skip-git-repo-check`. Already handled.
- **Gemini "ModelNotFoundError"**: Check that the model ID is valid. Current: `gemini-3.1-pro-preview`.
- **Gemini timeout**: Gemini can be slow with thinking enabled. Default timeout is 600s.
- **Codex `-a` flag error**: The `-a` flag is for interactive mode only. Use `--full-auto` for `exec`.

## Extending

- To add a new agent: add a `call_X()` function, add it to the `AGENTS` dict, and update `parse_sub_questions()` to handle assignment key `D`.
- To add a new phase: write the function, add it to `main()` between existing phases.
- To change models: edit the CLI args in the respective `call_*()` function.
