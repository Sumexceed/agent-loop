#!/usr/bin/env python3
"""Re-run Phase 6 (polish + briefing + HTML) on an existing workspace."""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from agent_loop import (
    COLORS,
    Workspace,
    phase_report,
    _ensure_gemini_thinking_config,
)


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 rerun_report.py <workspace_path>")
        sys.exit(1)

    ws_path = Path(sys.argv[1])
    question = (ws_path / "00-question.md").read_text(encoding="utf-8").strip()
    synthesis = (ws_path / "phase5-synthesis.md").read_text(encoding="utf-8")

    ws = Workspace(ws_path)
    palette = COLORS

    start = time.time()
    phase_report(question, synthesis, palette, ws, 600, "—")
    elapsed = time.time() - start
    print(f"Done in {int(elapsed)}s")


if __name__ == "__main__":
    main()
