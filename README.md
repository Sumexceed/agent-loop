# Agent Loop

Three AI agents (Claude, Codex, Gemini) collaboratively research open-ended questions through structured phases — not by taking turns writing essays, but by independently researching with real tools, cross-reviewing each other's findings, and revising their framework when evidence demands it.

## Why

A single LLM can give you multiple perspectives on any topic. But it's drawing from one knowledge base, one set of biases, and zero real-time research. Agent Loop is different:

- Each agent **actually searches the web**, finds data, and cites sources
- Agents **challenge each other's findings** with verification searches
- The research framework **can be revised mid-process** when evidence contradicts initial assumptions
- The final report is grounded in **cross-validated evidence**, not opinion

## How It Works

```
Question
   ↓
Phase 1: DECOMPOSE — Break into researchable sub-questions
   ↓
Phase 2: RESEARCH  — 3 agents research in parallel (with web search)
   ↓
Phase 3: CHALLENGE — Cross-review findings, verify claims, find counter-evidence
   ↓
Phase 4: REFRAME   — Revise framework if needed → triggers supplementary research
   ↓
Phase 5: SYNTHESIZE — Produce evidence-based research report
   ↓
Phase 6: REPORT    — Generate HTML report, save to Desktop, auto-open
```

## Prerequisites

Three CLI tools installed and authenticated:

| Tool | Install | Auth |
|------|---------|------|
| [Claude Code](https://docs.anthropic.com/en/docs/claude-code) | `npm install -g @anthropic-ai/claude-code` | `claude auth` |
| [Codex CLI](https://github.com/openai/codex) | `brew install codex` | `codex login` |
| [Gemini CLI](https://github.com/google-gemini/gemini-cli) | `npm install -g @google/gemini-cli` | `gemini` (OAuth on first run) |

Python 3.10+ (no external dependencies).

## Usage

```bash
# Basic usage (all 6 phases)
python3 agent_loop.py "Your research question here"

# Skip framework revision phase
python3 agent_loop.py "Your question" --no-reframe

# Custom timeout per agent call (default: 600s)
python3 agent_loop.py "Your question" --timeout 900

# Custom workspace directory
python3 agent_loop.py "Your question" --workspace ./my-research

# Disable colored terminal output
python3 agent_loop.py "Your question" --no-color

# Pipe-friendly (no color, useful for logging)
python3 agent_loop.py "Your question" --no-color 2>&1 | tee research.log
```

## Models

| Agent | Model | Thinking |
|-------|-------|----------|
| Claude | Opus 4.6 | Extended thinking (high effort) |
| Codex | GPT-5.3-Codex | Reasoning effort: high |
| Gemini | Gemini 3.1 Pro | Thinking level: HIGH |

Models are configured in the `call_*` functions in `agent_loop.py`. The script auto-configures Gemini's thinking settings in `~/.gemini/settings.json` on first run.

## Output

### Terminal
Each phase prints color-coded output in real-time (orange=Claude, green=Codex, blue=Gemini).

### Workspace
All intermediate results are saved to `~/agent-loop/workspace/{timestamp}/`:

```
workspace/20260302-143000/
├── 00-question.md
├── phase1-decomposition.md
├── phase2-research-claude.md
├── phase2-research-codex.md
├── phase2-research-gemini.md
├── phase3-review-*.md
├── phase4-reframe.md
├── phase5-synthesis.md
├── phase6-briefing.md
├── report.html
└── full-log.md
```

### HTML Report
A styled HTML report is saved to `~/Desktop/` and auto-opened in the browser. The report has:
- **Top half**: Condensed executive briefing (key takeaways in ~500 words)
- **Bottom half**: Full research report with evidence and sources

## How It Differs from v1

v1 was a round-robin discussion — three LLMs taking turns writing paragraphs. Indistinguishable from asking one LLM to "analyze from multiple perspectives."

v2 is a research system:

| | v1 | v2 |
|---|---|---|
| What agents do | Share opinions | Research with tools |
| Web search | No | Yes (all agents) |
| Evidence | Training knowledge | Real-time citations |
| Structure | Round-robin rounds | Phased pipeline |
| Framework | Fixed | Can be revised mid-research |
| Cross-validation | None | Agents verify each other's claims |
| Output | Text in terminal | Terminal + workspace + HTML report |

## License

MIT
