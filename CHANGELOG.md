# Changelog

## [2.1.0] - 2026-03-02

### Changed
- Claude upgraded to **Opus 4.6** with extended thinking (`--effort high`)
- Codex upgraded to **GPT-5.3-Codex** with reasoning effort high
- Gemini upgraded to **Gemini 3.1 Pro Preview** with thinking level HIGH
- Auto-configures Gemini thinking settings in `~/.gemini/settings.json`

### Fixed
- Codex `exec` mode: replaced `-a never` (interactive-only) with `--full-auto`

## [2.0.0] - 2026-03-02

### Added
- **Phase-based research pipeline** replacing round-robin discussion
  - Phase 1: DECOMPOSE — structured problem decomposition
  - Phase 2: RESEARCH — parallel independent research with web search
  - Phase 3: CHALLENGE — cross-review and verification
  - Phase 4: REFRAME — framework revision with supplementary research
  - Phase 5: SYNTHESIZE — evidence-based final report
  - Phase 6: REPORT — HTML report generation, saved to Desktop, auto-opened
- **Tool permissions enabled** — agents use web search, file reading, and code execution
- **Parallel execution** — Phase 2 and Phase 3 run all agents concurrently
- **Workspace directory** — all intermediate outputs saved for audit trail
- **HTML report** with executive briefing + full report, dark mode support
- **Framework revision** — Phase 4 can trigger supplementary research when original framework is inadequate
- `--no-reframe` flag to skip framework revision
- `--workspace` flag for custom output directory
- `--timeout` flag for per-agent call timeout

### Changed
- Complete rewrite from opinion-sharing to research-driven architecture
- Prompts now explicitly require web search, citations, and evidence
- Default timeout increased from 300s to 600s

## [1.0.0] - 2026-03-01

### Added
- Initial version: round-robin discussion loop
- Three agents (Claude, Codex, Gemini) take turns responding
- Configurable number of rounds (`--rounds`)
- Color-coded terminal output
- Final synthesis by Claude
- Basic error handling and timeout support
