#!/usr/bin/env python3
"""
Resume a previous agent_loop run from Phase 5.5 (Gap Analysis) onwards.

Loads the existing workspace data and continues with:
  5.5  GAP ANALYSIS   → 2c/3c/3.5c (if needed) → 5 (re-synthesize) → 6 (report)

Usage:
    python3 resume_from_gap.py ~/agent-loop/workspace/20260302-114904
"""

import sys
import time
from pathlib import Path

# Import everything from agent_loop
sys.path.insert(0, str(Path(__file__).parent))
from agent_loop import (
    COLORS,
    Workspace,
    c,
    parse_sub_questions,
    parse_gaps_status,
    phase_gap_analysis,
    phase_research,
    phase_challenge,
    phase_evidence_audit,
    phase_synthesize,
    phase_report,
    _ensure_gemini_thinking_config,
)


def load_file(ws_path: Path, filename: str) -> str:
    f = ws_path / filename
    return f.read_text(encoding="utf-8") if f.exists() else ""


def load_research(ws_path: Path) -> dict[str, str]:
    """Load all research files (phase2-*, phase2b-*) into a dict."""
    research = {}
    for f in sorted(ws_path.glob("phase2-research-*.md")):
        agent = f.stem.split("-")[-1].capitalize()
        research[agent] = f.read_text(encoding="utf-8")
    for f in sorted(ws_path.glob("phase2b-research-*.md")):
        agent = f.stem.split("-")[-1].capitalize()
        research[f"{agent} (supplementary)"] = f.read_text(encoding="utf-8")
    return research


def load_reviews(ws_path: Path) -> dict[str, str]:
    """Load all review files (phase3-*, phase3b-*) into a dict."""
    reviews = {}
    for f in sorted(ws_path.glob("phase3-review-*.md")):
        name = f.stem.replace("phase3-review-", "")
        reviews[name] = f.read_text(encoding="utf-8")
    for f in sorted(ws_path.glob("phase3b-review-*.md")):
        name = f.stem.replace("phase3b-review-", "")
        reviews[f"{name} (supp review)"] = f.read_text(encoding="utf-8")
    return reviews


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 resume_from_gap.py <workspace_path>")
        sys.exit(1)

    ws_path = Path(sys.argv[1])
    if not ws_path.exists():
        print(f"Workspace not found: {ws_path}")
        sys.exit(1)

    palette = COLORS
    _ensure_gemini_thinking_config()

    # Load existing data
    question = load_file(ws_path, "00-question.md").strip()
    synthesis = load_file(ws_path, "phase5-synthesis.md")
    reframe_text = load_file(ws_path, "phase4-reframe.md")
    all_research = load_research(ws_path)
    all_reviews = load_reviews(ws_path)

    # Load all audit texts
    audit_parts = []
    for name in ["phase3.5-evidence-audit.md", "phase3.5(repair)-evidence-audit.md", "phase3.5b-evidence-audit.md"]:
        text = load_file(ws_path, name)
        if text:
            audit_parts.append(text)
    audit_text = "\n\n---\n\n".join(audit_parts)

    if not question or not synthesis:
        print("Missing question or synthesis in workspace.")
        sys.exit(1)

    # Use the existing workspace (files will be added alongside existing ones)
    ws = Workspace(ws_path)

    print(f"\n{palette['bold']}{'═' * 60}")
    print(f"  Agent Loop — Resuming from Phase 5.5")
    print(f"{'═' * 60}{palette['reset']}")
    print(f"{palette['dim']}Question:  {question}")
    print(f"Workspace: {ws.base}")
    print(f"Loaded:    {len(all_research)} research files, {len(all_reviews)} review files{palette['reset']}\n")

    ws.log("Resumed from Phase 5.5 (Gap Analysis)")
    start_time = time.time()

    # ── Phase 5.5: Gap Analysis ──
    try:
        gap_status, gap_response = phase_gap_analysis(
            question, synthesis, palette, ws, 600,
        )
        if gap_status == "RESEARCH_NEEDED":
            print(f"{palette['bold']}Researchable gaps found — running gap research...{palette['reset']}\n")
            gap_assignments = parse_sub_questions(gap_response)

            # Phase 2c: Gap research (parallel)
            gap_research = phase_research(
                question, gap_assignments, palette, ws, 600, tag="c",
            )

            # Phase 3c: Cross-review gap findings (parallel)
            gap_reviews = phase_challenge(
                question, gap_research, palette, ws, 600, tag="c",
            )

            # Phase 3.5c: Audit gap findings
            gap_audit = phase_evidence_audit(
                question, gap_research, gap_reviews, palette, ws, 600, tag="c",
            )

            # Merge gap findings into main results
            all_research.update({f"{k} (gap)": v for k, v in gap_research.items()})
            all_reviews.update({f"{k} (gap review)": v for k, v in gap_reviews.items()})
            audit_text = audit_text + "\n\n---\n\n## Gap Research Audit\n" + gap_audit

            # Save original synthesis as v1
            ws.save("phase5-synthesis-v1.md", synthesis)

            # Re-synthesize with enriched evidence
            synthesis = phase_synthesize(
                question, all_research, all_reviews, audit_text, reframe_text,
                palette, ws, 600,
            )
        else:
            print(f"{palette['dim']}No researchable gaps found — using original synthesis.{palette['reset']}\n")
    except Exception as e:
        print(f"  {palette['dim']}Phase 5.5 error: {e} — continuing with original synthesis{palette['reset']}\n")
        ws.log(f"Phase 5.5 FAILED: {e}")

    elapsed = time.time() - start_time
    minutes = int(elapsed // 60)
    seconds = int(elapsed % 60)
    elapsed_str = f"{minutes}m{seconds}s"

    # ── Phase 6: HTML Report ──
    if synthesis:
        try:
            report_path = phase_report(
                question, synthesis, palette, ws, 600, elapsed_str,
            )
        except Exception as e:
            print(f"  {palette['dim']}Report generation failed: {e}{palette['reset']}\n")
            ws.log(f"Phase 6 FAILED: {e}")

    ws.log(f"Resume completed in {elapsed_str}")
    ws.flush_log()

    print(f"{palette['dim']}Completed in {elapsed_str}")
    print(f"Workspace: {ws.base}{palette['reset']}\n")


if __name__ == "__main__":
    main()
