#!/usr/bin/env python3
"""
Agent Loop v2: Collaborative Research System

Three AI agents (Claude, Codex, Gemini) collaborate through structured phases:
  1.   DECOMPOSE      — break the question into researchable sub-questions
  2.   RESEARCH       — each agent independently researches assigned sub-questions (with tools)
  3.   CHALLENGE      — cross-review each other's findings
  3.5  EVIDENCE AUDIT — Claude audits evidence quality (verifies sources, flags fabrications)
  4.   REFRAME        — revise the framework if needed, then do supplementary research
  5.   SYNTHESIZE     — produce the final research report
  6.   REPORT         — generate HTML report with executive briefing

Usage:
    python3 agent_loop.py "your research question"
    python3 agent_loop.py "your question" --no-reframe
    python3 agent_loop.py "your question" --workspace ./my-research
"""

import argparse
import html
import json
import os
import platform
import re
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# ANSI colors
# ---------------------------------------------------------------------------

COLORS = {
    "Claude": "\033[38;5;208m",
    "Codex": "\033[38;5;48m",
    "Gemini": "\033[38;5;75m",
    "phase": "\033[38;5;141m",
    "summary": "\033[38;5;226m",
    "dim": "\033[2m",
    "bold": "\033[1m",
    "reset": "\033[0m",
}
NO_COLOR = {k: "" for k in COLORS}


def c(name: str, text: str, palette: dict) -> str:
    return f"{palette[name]}{text}{palette['reset']}"


# ---------------------------------------------------------------------------
# CLI callers — with tool permissions enabled for real research
# ---------------------------------------------------------------------------

def call_claude(prompt: str, timeout: int = 600) -> str:
    env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}
    result = subprocess.run(
        [
            "claude", "-p",
            "--model", "claude-opus-4-6",
            "--effort", "high",
            "--output-format", "text",
            "--allowedTools", "WebSearch,WebFetch,Read,Bash(grep:*),Bash(curl:*),Grep,Glob",
        ],
        input=prompt,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"claude exit {result.returncode}")
    return result.stdout.strip()


def call_codex(prompt: str, timeout: int = 600) -> str:
    result = subprocess.run(
        [
            "codex", "exec",
            "--skip-git-repo-check",
            "--full-auto",
            "-m", "gpt-5.3-codex",
            "-c", 'model_reasoning_effort="high"',
        ],
        input=prompt,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"codex exit {result.returncode}")
    return result.stdout.strip()


def _ensure_gemini_thinking_config():
    """Ensure ~/.gemini/settings.json has thinkingLevel=HIGH for Gemini 3 models."""
    settings_path = Path.home() / ".gemini" / "settings.json"
    settings = {}
    if settings_path.exists():
        settings = json.loads(settings_path.read_text(encoding="utf-8"))

    # Add thinkingConfig if not already present
    model_configs = settings.setdefault("modelConfigs", {})
    default_cfg = model_configs.setdefault("default", {})
    gen_cfg = default_cfg.setdefault("generateContentConfig", {})
    thinking = gen_cfg.setdefault("thinkingConfig", {})
    if thinking.get("thinkingLevel") != "HIGH":
        thinking["thinkingLevel"] = "HIGH"
        settings_path.parent.mkdir(parents=True, exist_ok=True)
        settings_path.write_text(
            json.dumps(settings, indent=2, ensure_ascii=False), encoding="utf-8"
        )


def call_gemini(prompt: str, timeout: int = 600) -> str:
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write(prompt)
        tmp = f.name
    try:
        with open(tmp) as f:
            result = subprocess.run(
                ["gemini", "--yolo", "-m", "gemini-3.1-pro-preview", "-p", " "],
                stdin=f,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
    finally:
        os.unlink(tmp)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"gemini exit {result.returncode}")
    return result.stdout.strip()


AGENTS = {
    "Claude": call_claude,
    "Codex": call_codex,
    "Gemini": call_gemini,
}


# ---------------------------------------------------------------------------
# Workspace helper
# ---------------------------------------------------------------------------

class Workspace:
    def __init__(self, base: Path):
        self.base = base
        self.base.mkdir(parents=True, exist_ok=True)
        self.log_lines: list[str] = []

    def save(self, filename: str, content: str):
        (self.base / filename).write_text(content, encoding="utf-8")

    def log(self, line: str):
        self.log_lines.append(f"[{datetime.now().strftime('%H:%M:%S')}] {line}")

    def flush_log(self):
        self.save("full-log.md", "\n".join(self.log_lines))


# ---------------------------------------------------------------------------
# Prompt templates
# ---------------------------------------------------------------------------

DECOMPOSE_PROMPT = """\
You are a research strategist. Your job is to analyze a research question and \
decompose it into specific, researchable sub-questions.

## Research Question
{question}

## Your Task
1. Analyze the question — identify what makes it hard, what assumptions it contains, \
what dimensions it spans.
2. Decompose it into 3-6 **specific sub-questions** that can each be independently \
researched using web searches, data analysis, or literature review.
3. For each sub-question, suggest what kind of evidence would be needed \
(data, case studies, expert opinions, academic papers, etc.).
4. Assign each sub-question to one of three researchers: Agent-A, Agent-B, Agent-C. \
Distribute the workload roughly evenly.

## Output Format (follow strictly)
Write your analysis first, then output the sub-questions in this exact format:

SUB_QUESTIONS_START
[A1] <sub-question text>
EVIDENCE: <what evidence to look for>
---
[B1] <sub-question text>
EVIDENCE: <what evidence to look for>
---
[C1] <sub-question text>
EVIDENCE: <what evidence to look for>
---
(continue as needed with A2, B2, C2, etc.)
SUB_QUESTIONS_END
"""

RESEARCH_PROMPT = """\
You are a research agent. You have access to web search and other tools.

## Original Research Question
{question}

## Your Assigned Sub-Questions
{assignments}

## Instructions
You MUST use web search to find real data, studies, and evidence. Do NOT answer \
purely from your training knowledge.

For each sub-question:
1. **Search** — conduct multiple web searches with different queries
2. **Collect** — gather specific data points, statistics, study results, expert quotes
3. **Source** — cite every claim with a URL or specific source name
4. **Assess** — rate the reliability of each source (high/medium/low)
5. **Conclude** — state your findings and what remains uncertain

Clearly separate FACTS (with sources) from your INTERPRETATION.
Be thorough. Aim for depth over breadth.
"""

CHALLENGE_PROMPT = """\
You are a critical research reviewer. Your job is to rigorously examine \
another researcher's findings.

## Original Research Question
{question}

## Research Findings to Review (by {author})
{findings}

## Your Task
1. **Verify** — pick the 2-3 most important claims and search the web to verify them. \
Do the cited sources actually say what the researcher claims?
2. **Counter-evidence** — search for data or studies that contradict the findings. \
Are there important counter-examples or confounding factors?
3. **Gaps** — what important angles did the researcher miss entirely?
4. **Logic** — are there logical leaps, unsupported generalizations, or \
correlation-causation errors?
5. **Verdict** — which findings are solid, which are shaky, and what needs more research?

You MUST use web search to do your verification. Don't just critique from intuition.
"""

REFRAME_PROMPT = """\
You are a research architect. Three researchers have independently investigated \
sub-questions of a larger research question, and their work has been cross-reviewed \
and the evidence has been audited.

## Original Research Question
{question}

## Original Sub-Questions
{decomposition}

## Research Findings
{research}

## Cross-Review Results
{reviews}

## Evidence Audit Results
{audit}

## Your Task
Evaluate whether the original research framework is adequate. \
Pay special attention to the evidence audit — areas flagged as FABRICATED or \
UNVERIFIABLE should be treated as gaps that need to be addressed.

1. Were the right sub-questions asked? Or did the research reveal that the \
problem should be framed differently?
2. Are there critical gaps that no sub-question addressed?
3. Did any findings contradict the premises of the original question?
4. Are there new sub-questions that emerged from the research?
5. Did the evidence audit reveal areas where claims lack reliable support \
and supplementary research is needed?

## Output Format
First give your analysis, then:

If the framework is adequate, write:
FRAMEWORK_STATUS: ADEQUATE

If revision is needed, write:
FRAMEWORK_STATUS: REVISE
Then list new sub-questions in the same format as Phase 1:
SUB_QUESTIONS_START
[A1] <new sub-question>
EVIDENCE: <what to look for>
---
(etc.)
SUB_QUESTIONS_END
"""

SYNTHESIZE_PROMPT = """\
You are a research synthesizer producing a final report.

## Original Research Question
{question}

## All Research Findings
{research}

## Cross-Review Results
{reviews}

## Evidence Audit Results
{audit}

## Framework Assessment
{reframe}

## Your Task
Produce a comprehensive research report that:

1. **Executive Summary** — answer the research question in 2-3 paragraphs, \
clearly stating what the evidence shows.
2. **Key Findings** — the most important discoveries, each backed by specific evidence \
and sources found during research.
3. **Points of Consensus** — where all researchers agreed, with supporting evidence.
4. **Contested Areas** — where evidence is contradictory or researchers disagreed, \
explaining both sides.
5. **Evidence Quality** — incorporate the evidence audit results. For each key finding, \
indicate whether the supporting evidence was VERIFIED, PARTIALLY VERIFIED, \
UNVERIFIABLE, or FABRICATED. Exclude or clearly flag any claims that were found \
to be fabricated during the audit. Do not present unverified claims as established facts.
6. **Open Questions** — what remains unanswered and would need further research.
7. **Sources** — consolidated list of key sources used, with verification status from the audit.

Ground every claim in evidence found during the research phases. \
If something wasn't verified through research or was flagged in the audit, say so explicitly. \
The evidence audit is your primary guide for what to trust and what to qualify.
"""

EVIDENCE_AUDIT_PROMPT = """\
You are an evidence auditor. Your sole job is to assess the quality and reliability \
of evidence gathered during a research process. You are rigorous, skeptical, and fair.

## Original Research Question
{question}

## Research Findings (from three agents)
{research}

## Cross-Review Results (agents reviewed each other's work)
{reviews}

## Your Task
Systematically audit the evidence quality across ALL research findings and reviews.

For EACH significant claim or data point cited in the research:
1. **Verify the source** — Use web search to check if the cited URL or source actually exists \
and contains the claimed information. Flag any broken links or misattributed sources.
2. **Check accuracy** — Does the source actually say what the researcher claims? \
Are numbers quoted correctly? Is context preserved or distorted?
3. **Assess reliability** — Rate each key piece of evidence:
   - ✅ VERIFIED: Source confirmed, claim accurate
   - ⚠️ PARTIALLY VERIFIED: Source exists but claim is somewhat distorted or oversimplified
   - ❌ UNVERIFIABLE: Cannot find the cited source or confirm the claim
   - 🚫 FABRICATED: Source does not exist, or says something materially different

4. **Cross-check contradictions** — Where different agents cited conflicting data, \
determine which version is better supported.

## Output Format

### Evidence Inventory
For each major claim, list:
- Claim summary
- Cited source
- Verification result (✅/⚠️/❌/🚫)
- Notes

### Reliability Summary
- Total claims audited: N
- Verified: N
- Partially verified: N
- Unverifiable: N
- Fabricated: N

### Critical Flags
List any evidence that is fabricated, seriously distorted, or where the conclusion \
drawn from the evidence is not supported by the actual source.

### Overall Evidence Quality Assessment
A brief paragraph assessing the overall reliability of the evidence base, \
noting which areas of the research are well-supported and which are shaky.

Be thorough. You must actually search and verify — do not rubber-stamp claims.
"""

CONDENSED_PROMPT = """\
You are an expert editor. Given the following research report, produce a \
**condensed executive briefing** in markdown format.

## Report
{report}

## Requirements
- Start with a single-paragraph **Bottom Line** that directly answers the research question.
- Then list **5-8 Key Takeaways** as bullet points. Each bullet should be one sentence, \
conveying one critical insight with its supporting evidence in parentheses.
- End with a **Confidence Assessment**: one sentence on how confident the overall conclusion is, \
and what the biggest uncertainty is.
- Total length: under 500 words. Every word must earn its place.
- Write in the same language as the report.
"""

HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title_escaped}</title>
<script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
<style>
  :root {{
    --bg: #fafafa;
    --surface: #ffffff;
    --text: #1a1a1a;
    --text2: #555;
    --accent: #2563eb;
    --border: #e5e7eb;
    --highlight-bg: #f0f7ff;
    --highlight-border: #2563eb;
    --claude: #e87b35;
    --codex: #22c55e;
    --gemini: #3b82f6;
  }}
  @media (prefers-color-scheme: dark) {{
    :root {{
      --bg: #0f0f0f;
      --surface: #1a1a1a;
      --text: #e5e5e5;
      --text2: #999;
      --accent: #60a5fa;
      --border: #333;
      --highlight-bg: #1e293b;
      --highlight-border: #60a5fa;
    }}
  }}
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
                 "Noto Sans SC", "PingFang SC", sans-serif;
    background: var(--bg);
    color: var(--text);
    line-height: 1.7;
    -webkit-font-smoothing: antialiased;
  }}
  .header {{
    background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
    color: #fff;
    padding: 3rem 2rem 2.5rem;
    text-align: center;
  }}
  .header h1 {{
    font-size: 1.6rem;
    font-weight: 600;
    max-width: 800px;
    margin: 0 auto 1rem;
    line-height: 1.4;
  }}
  .header .meta {{
    font-size: 0.85rem;
    opacity: 0.7;
  }}
  .header .agents {{
    margin-top: 1rem;
    display: flex;
    justify-content: center;
    gap: 1.5rem;
    font-size: 0.85rem;
  }}
  .header .agents span {{
    padding: 0.25rem 0.75rem;
    border-radius: 999px;
    font-weight: 500;
  }}
  .agent-claude {{ background: rgba(232,123,53,0.2); color: #f6a56c; }}
  .agent-codex  {{ background: rgba(34,197,94,0.2);  color: #6ee7a0; }}
  .agent-gemini {{ background: rgba(59,130,246,0.2); color: #93bbfc; }}
  .container {{
    max-width: 860px;
    margin: 0 auto;
    padding: 2rem 1.5rem 4rem;
  }}
  /* Key Takeaways card */
  .briefing {{
    background: var(--highlight-bg);
    border-left: 4px solid var(--highlight-border);
    border-radius: 0 12px 12px 0;
    padding: 2rem 2rem 1.5rem;
    margin-bottom: 3rem;
  }}
  .briefing-label {{
    font-size: 0.75rem;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    color: var(--accent);
    font-weight: 700;
    margin-bottom: 1rem;
  }}
  .briefing h1, .briefing h2, .briefing h3 {{
    font-size: 1.15rem;
    margin-top: 1.2rem;
    margin-bottom: 0.5rem;
    color: var(--text);
  }}
  .briefing p {{ margin-bottom: 0.7rem; color: var(--text); }}
  .briefing ul {{ padding-left: 1.3rem; margin-bottom: 0.7rem; }}
  .briefing li {{ margin-bottom: 0.4rem; }}
  /* Divider */
  .divider {{
    border: none;
    border-top: 1px solid var(--border);
    margin: 2.5rem 0;
  }}
  .section-label {{
    font-size: 0.75rem;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    color: var(--text2);
    font-weight: 700;
    margin-bottom: 1.5rem;
  }}
  /* Full report */
  .report h1 {{
    font-size: 1.5rem;
    font-weight: 700;
    margin-top: 2.5rem;
    margin-bottom: 0.8rem;
    padding-bottom: 0.4rem;
    border-bottom: 2px solid var(--border);
  }}
  .report h2 {{
    font-size: 1.25rem;
    font-weight: 600;
    margin-top: 2rem;
    margin-bottom: 0.6rem;
    color: var(--text);
  }}
  .report h3 {{
    font-size: 1.1rem;
    font-weight: 600;
    margin-top: 1.5rem;
    margin-bottom: 0.5rem;
  }}
  .report p {{
    margin-bottom: 0.9rem;
    color: var(--text);
  }}
  .report ul, .report ol {{
    padding-left: 1.5rem;
    margin-bottom: 1rem;
  }}
  .report li {{
    margin-bottom: 0.4rem;
  }}
  .report blockquote {{
    border-left: 3px solid var(--accent);
    padding: 0.5rem 1rem;
    margin: 1rem 0;
    background: var(--highlight-bg);
    border-radius: 0 8px 8px 0;
  }}
  .report code {{
    background: var(--highlight-bg);
    padding: 0.15rem 0.4rem;
    border-radius: 4px;
    font-size: 0.9em;
  }}
  .report pre {{
    background: var(--highlight-bg);
    padding: 1rem;
    border-radius: 8px;
    overflow-x: auto;
    margin-bottom: 1rem;
  }}
  .report pre code {{
    background: none;
    padding: 0;
  }}
  .report a {{
    color: var(--accent);
    text-decoration: none;
  }}
  .report a:hover {{
    text-decoration: underline;
  }}
  .report table {{
    width: 100%;
    border-collapse: collapse;
    margin: 1rem 0;
    font-size: 0.95rem;
  }}
  .report th, .report td {{
    border: 1px solid var(--border);
    padding: 0.5rem 0.75rem;
    text-align: left;
  }}
  .report th {{
    background: var(--highlight-bg);
    font-weight: 600;
  }}
  .footer {{
    text-align: center;
    padding: 2rem;
    font-size: 0.8rem;
    color: var(--text2);
    border-top: 1px solid var(--border);
    margin-top: 3rem;
  }}
  @media print {{
    .header {{ background: #1e293b !important; -webkit-print-color-adjust: exact; }}
    body {{ font-size: 11pt; }}
  }}
</style>
</head>
<body>

<div class="header">
  <h1>{title_escaped}</h1>
  <div class="meta">{date} &middot; Agent Loop v2 &middot; Collaborative Research</div>
  <div class="agents">
    <span class="agent-claude">Claude</span>
    <span class="agent-codex">Codex</span>
    <span class="agent-gemini">Gemini</span>
  </div>
</div>

<div class="container">
  <div class="briefing">
    <div class="briefing-label">Executive Briefing</div>
    <div id="briefing-content"></div>
  </div>

  <hr class="divider">

  <div class="section-label">Full Research Report</div>
  <div class="report" id="report-content"></div>
</div>

<div class="footer">
  Generated by Agent Loop v2 &mdash; Claude + Codex + Gemini collaborative research<br>
  Elapsed: {elapsed}
</div>

<script>
const briefingMd = {briefing_json};
const reportMd = {report_json};

document.getElementById('briefing-content').innerHTML = marked.parse(briefingMd);
document.getElementById('report-content').innerHTML = marked.parse(reportMd);
</script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Phase implementations
# ---------------------------------------------------------------------------

def parse_sub_questions(text: str) -> dict[str, list[str]]:
    """Parse sub-questions from decomposition output, grouped by agent."""
    assignments: dict[str, list[str]] = {"A": [], "B": [], "C": []}
    match = re.search(r"SUB_QUESTIONS_START\s*\n(.*?)SUB_QUESTIONS_END", text, re.DOTALL)
    if not match:
        # Fallback: try to extract numbered questions
        lines = text.strip().split("\n")
        qs = [l.strip() for l in lines if re.match(r"\[?[ABC]\d\]?", l.strip())]
        if not qs:
            # Last resort: treat the whole output as a single question for each agent
            return {"A": [text], "B": [], "C": []}
        for q in qs:
            agent = q[1] if q.startswith("[") else q[0]
            assignments.setdefault(agent.upper(), []).append(q)
        return assignments

    block = match.group(1)
    entries = re.split(r"\n---\n", block)
    for entry in entries:
        entry = entry.strip()
        if not entry:
            continue
        m = re.match(r"\[([ABC])\d\]", entry)
        if m:
            assignments[m.group(1)].append(entry)
    return assignments


def parse_framework_status(text: str) -> str:
    if "FRAMEWORK_STATUS: REVISE" in text:
        return "REVISE"
    return "ADEQUATE"


def run_agent(name: str, prompt: str, timeout: int) -> tuple[str, str]:
    """Run a single agent, return (name, response)."""
    fn = AGENTS[name]
    return name, fn(prompt, timeout=timeout)


def phase_decompose(question: str, palette: dict, ws: Workspace, timeout: int) -> tuple[str, dict]:
    print(f"\n{c('phase', '═══ Phase 1: DECOMPOSE ═══', palette)}")
    print(f"{palette['dim']}Breaking the question into researchable sub-questions...{palette['reset']}\n")

    prompt = DECOMPOSE_PROMPT.format(question=question)
    print(f"  {c('Claude', '[Claude]', palette)} {palette['dim']}analyzing...{palette['reset']}", end="", flush=True)

    response = call_claude(prompt, timeout=timeout)
    assignments = parse_sub_questions(response)

    ws.save("phase1-decomposition.md", response)
    ws.log("Phase 1 complete: decomposition")

    print(f"\r  {c('Claude', '[Claude]', palette)} done\n")
    print(response)
    print()

    # Show assignment summary
    agent_map = {"A": "Claude", "B": "Codex", "C": "Gemini"}
    for key, qs in assignments.items():
        if qs:
            name = agent_map[key]
            print(f"  {c(name, f'[{name}]', palette)} assigned {len(qs)} sub-question(s)")
    print()

    return response, assignments


def phase_research(
    question: str,
    assignments: dict[str, list[str]],
    palette: dict,
    ws: Workspace,
    timeout: int,
    tag: str = "",
) -> dict[str, str]:
    label = f"Phase 2{tag}: RESEARCH"
    print(f"{c('phase', f'═══ {label} ═══', palette)}")
    print(f"{palette['dim']}Agents are researching in parallel (with web search enabled)...{palette['reset']}\n")

    agent_map = {"A": "Claude", "B": "Codex", "C": "Gemini"}
    results: dict[str, str] = {}

    # Build per-agent prompts
    tasks: list[tuple[str, str]] = []
    for key, name in agent_map.items():
        qs = assignments.get(key, [])
        if not qs:
            continue
        assignment_text = "\n\n".join(qs)
        prompt = RESEARCH_PROMPT.format(question=question, assignments=assignment_text)
        tasks.append((name, prompt))

    # Status display
    for name, _ in tasks:
        print(f"  {c(name, f'[{name}]', palette)} {palette['dim']}researching...{palette['reset']}")

    # Parallel execution
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {
            executor.submit(run_agent, name, prompt, timeout): name
            for name, prompt in tasks
        }
        for future in as_completed(futures):
            name = futures[future]
            try:
                _, response = future.result()
                results[name] = response
                suffix = tag.replace(" ", "")
                ws.save(f"phase2{suffix}-research-{name.lower()}.md", response)
                ws.log(f"{label}: {name} complete")
            except Exception as e:
                print(f"  {c(name, f'[{name}]', palette)} {palette['dim']}⚠ error: {e}{palette['reset']}")
                ws.log(f"{label}: {name} FAILED: {e}")

    # Print results
    for name, response in results.items():
        print(f"\n{'─' * 50}")
        print(f"{c(name, f'[{name} Research]', palette)}\n")
        print(response)
    print()

    return results


def phase_challenge(
    question: str,
    research: dict[str, str],
    palette: dict,
    ws: Workspace,
    timeout: int,
) -> dict[str, str]:
    print(f"{c('phase', '═══ Phase 3: CHALLENGE ═══', palette)}")
    print(f"{palette['dim']}Cross-reviewing findings (with verification searches)...{palette['reset']}\n")

    # Rotation: Claude reviews Codex, Codex reviews Gemini, Gemini reviews Claude
    names = list(research.keys())
    if len(names) < 2:
        print(f"  {palette['dim']}Not enough agents to cross-review, skipping.{palette['reset']}\n")
        return {}

    review_pairs: list[tuple[str, str]] = []
    for i, reviewer in enumerate(names):
        target = names[(i + 1) % len(names)]
        review_pairs.append((reviewer, target))

    results: dict[str, str] = {}
    tasks: list[tuple[str, str]] = []

    for reviewer, target in review_pairs:
        prompt = CHALLENGE_PROMPT.format(
            question=question,
            author=target,
            findings=research[target],
        )
        tasks.append((reviewer, prompt))
        print(f"  {c(reviewer, f'[{reviewer}]', palette)} {palette['dim']}reviewing {target}'s work...{palette['reset']}")

    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {
            executor.submit(run_agent, name, prompt, timeout): (name, review_pairs[i][1])
            for i, (name, prompt) in enumerate(tasks)
        }
        for future in as_completed(futures):
            name, target = futures[future]
            try:
                _, response = future.result()
                results[name] = response
                ws.save(f"phase3-review-{name.lower()}-of-{target.lower()}.md", response)
                ws.log(f"Phase 3: {name}'s review of {target} complete")
            except Exception as e:
                print(f"  {c(name, f'[{name}]', palette)} {palette['dim']}⚠ error: {e}{palette['reset']}")
                ws.log(f"Phase 3: {name} FAILED: {e}")

    for name, response in results.items():
        target = [t for r, t in review_pairs if r == name][0]
        print(f"\n{'─' * 50}")
        print(f"{c(name, f'[{name} reviewing {target}]', palette)}\n")
        print(response)
    print()

    return results


def phase_evidence_audit(
    question: str,
    research: dict[str, str],
    reviews: dict[str, str],
    palette: dict,
    ws: Workspace,
    timeout: int,
) -> str:
    """Phase 3.5: Claude audits evidence quality across all research and reviews."""
    print(f"{c('phase', '═══ Phase 3.5: EVIDENCE AUDIT ═══', palette)}")
    print(f"{palette['dim']}Claude is auditing evidence quality (verifying sources, checking claims)...{palette['reset']}\n")

    research_text = "\n\n---\n\n".join(
        f"### {name}\n{text}" for name, text in research.items()
    )
    review_text = "\n\n---\n\n".join(
        f"### {name}\n{text}" for name, text in reviews.items()
    )

    prompt = EVIDENCE_AUDIT_PROMPT.format(
        question=question,
        research=research_text,
        reviews=review_text,
    )

    print(f"  {c('Claude', '[Claude]', palette)} {palette['dim']}auditing evidence...{palette['reset']}", end="", flush=True)
    response = call_claude(prompt, timeout=timeout)

    ws.save("phase3.5-evidence-audit.md", response)
    ws.log("Phase 3.5 complete: evidence audit")

    print(f"\r  {c('Claude', '[Claude]', palette)} audit complete\n")
    print(response)
    print()

    return response


def phase_reframe(
    question: str,
    decomposition: str,
    research: dict[str, str],
    reviews: dict[str, str],
    audit_text: str,
    palette: dict,
    ws: Workspace,
    timeout: int,
) -> tuple[str, str]:
    """Returns (status, response) where status is ADEQUATE or REVISE."""
    print(f"{c('phase', '═══ Phase 4: REFRAME ═══', palette)}")
    print(f"{palette['dim']}Evaluating if the research framework needs revision...{palette['reset']}\n")

    research_text = "\n\n---\n\n".join(
        f"### {name}\n{text}" for name, text in research.items()
    )
    review_text = "\n\n---\n\n".join(
        f"### {name}\n{text}" for name, text in reviews.items()
    )

    prompt = REFRAME_PROMPT.format(
        question=question,
        decomposition=decomposition,
        research=research_text,
        reviews=review_text,
        audit=audit_text,
    )

    print(f"  {c('Gemini', '[Gemini]', palette)} {palette['dim']}evaluating framework...{palette['reset']}", end="", flush=True)
    response = call_gemini(prompt, timeout=timeout)
    status = parse_framework_status(response)

    ws.save("phase4-reframe.md", response)
    ws.log(f"Phase 4 complete: framework status = {status}")

    print(f"\r  {c('Gemini', '[Gemini]', palette)} verdict: {palette['bold']}{status}{palette['reset']}\n")
    print(response)
    print()

    return status, response


def phase_synthesize(
    question: str,
    research: dict[str, str],
    reviews: dict[str, str],
    audit_text: str,
    reframe_text: str,
    palette: dict,
    ws: Workspace,
    timeout: int,
) -> str:
    print(f"{c('phase', '═══ Phase 5: SYNTHESIZE ═══', palette)}")
    print(f"{palette['dim']}Producing final research report...{palette['reset']}\n")

    research_text = "\n\n---\n\n".join(
        f"### {name}\n{text}" for name, text in research.items()
    )
    review_text = "\n\n---\n\n".join(
        f"### {name}\n{text}" for name, text in reviews.items()
    )

    prompt = SYNTHESIZE_PROMPT.format(
        question=question,
        research=research_text,
        reviews=review_text,
        audit=audit_text,
        reframe=reframe_text,
    )

    print(f"  {c('Claude', '[Claude]', palette)} {palette['dim']}synthesizing...{palette['reset']}", end="", flush=True)
    response = call_claude(prompt, timeout=timeout)

    ws.save("phase5-synthesis.md", response)
    ws.log("Phase 5 complete: synthesis")

    print(f"\r  {c('Claude', '[Claude]', palette)} done\n")
    print(f"{'═' * 60}")
    print(f"{c('summary', '  FINAL RESEARCH REPORT', palette)}")
    print(f"{'═' * 60}\n")
    print(response)
    print()

    return response


def phase_report(
    question: str,
    synthesis: str,
    palette: dict,
    ws: Workspace,
    timeout: int,
    elapsed_str: str,
) -> Path:
    """Phase 6: Generate HTML report, save to Desktop, and open it."""
    print(f"{c('phase', '═══ Phase 6: REPORT ═══', palette)}")
    print(f"{palette['dim']}Generating HTML report...{palette['reset']}\n")

    # Step 1: Generate condensed briefing
    print(f"  {c('Claude', '[Claude]', palette)} {palette['dim']}condensing key takeaways...{palette['reset']}", end="", flush=True)
    condensed_prompt = CONDENSED_PROMPT.format(report=synthesis)
    try:
        briefing = call_claude(condensed_prompt, timeout=timeout)
    except Exception as e:
        print(f"\r  {c('Claude', '[Claude]', palette)} {palette['dim']}⚠ condensation failed: {e}{palette['reset']}")
        briefing = "*(Condensed briefing generation failed. See full report below.)*"

    ws.save("phase6-briefing.md", briefing)
    ws.log("Phase 6: briefing generated")
    print(f"\r  {c('Claude', '[Claude]', palette)} briefing ready")

    # Step 2: Build HTML
    date_str = datetime.now().strftime("%Y-%m-%d")
    title_escaped = html.escape(question)

    report_html = HTML_TEMPLATE.format(
        title_escaped=title_escaped,
        date=date_str,
        elapsed=elapsed_str,
        briefing_json=json.dumps(briefing, ensure_ascii=False),
        report_json=json.dumps(synthesis, ensure_ascii=False),
    )

    # Step 3: Save to Desktop
    desktop = Path.home() / "Desktop"
    safe_name = re.sub(r'[^\w\u4e00-\u9fff]+', '-', question)[:60].strip('-')
    report_path = desktop / f"research-{safe_name}-{datetime.now().strftime('%m%d')}.html"
    report_path.write_text(report_html, encoding="utf-8")

    # Also save to workspace
    ws.save("report.html", report_html)
    ws.log(f"Phase 6: HTML report saved to {report_path}")

    print(f"  Report saved: {report_path}")

    # Step 4: Auto-open
    try:
        if platform.system() == "Darwin":
            subprocess.Popen(["open", str(report_path)])
        elif platform.system() == "Linux":
            subprocess.Popen(["xdg-open", str(report_path)])
        elif platform.system() == "Windows":
            os.startfile(str(report_path))
        print(f"  {palette['dim']}Opening in browser...{palette['reset']}")
    except Exception as e:
        print(f"  {palette['dim']}Could not auto-open: {e}{palette['reset']}")

    print()
    return report_path


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Agent Loop v2: Three AI agents collaboratively research a question."
    )
    parser.add_argument("question", help="The research question to investigate")
    parser.add_argument("--timeout", type=int, default=600,
                        help="Timeout per agent call in seconds (default: 600)")
    parser.add_argument("--no-reframe", action="store_true",
                        help="Skip the framework revision phase")
    parser.add_argument("--no-color", action="store_true",
                        help="Disable colored output")
    parser.add_argument("--workspace", type=str, default=None,
                        help="Custom workspace directory path")
    args = parser.parse_args()

    palette = NO_COLOR if args.no_color else COLORS

    # Ensure Gemini thinking config
    _ensure_gemini_thinking_config()

    # Setup workspace
    if args.workspace:
        ws_path = Path(args.workspace)
    else:
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        ws_path = Path.home() / "agent-loop" / "workspace" / ts
    ws = Workspace(ws_path)

    # Header
    print(f"\n{palette['bold']}{'═' * 60}")
    print(f"  Agent Loop v2 — Collaborative Research System")
    print(f"{'═' * 60}{palette['reset']}")
    print(f"{palette['dim']}Question:  {args.question}")
    print(f"Workspace: {ws.base}")
    print(f"Agents:    Claude Opus 4.6, GPT-5.3-Codex, Gemini 3.1 Pro (all w/ thinking){palette['reset']}")

    ws.save("00-question.md", args.question)
    ws.log(f"Started: {args.question}")

    start_time = time.time()

    # ── Phase 1: Decompose ──
    try:
        decomposition_text, assignments = phase_decompose(
            args.question, palette, ws, args.timeout
        )
    except Exception as e:
        print(f"\n{palette['bold']}Phase 1 failed: {e}{palette['reset']}")
        sys.exit(1)

    # ── Phase 2: Research (parallel) ──
    all_research = phase_research(
        args.question, assignments, palette, ws, args.timeout
    )
    if not all_research:
        print("No research results collected. Cannot proceed.")
        sys.exit(1)

    # ── Phase 3: Challenge (parallel) ──
    all_reviews = phase_challenge(
        args.question, all_research, palette, ws, args.timeout
    )

    # ── Phase 3.5: Evidence Audit (Claude) ──
    audit_text = ""
    try:
        audit_text = phase_evidence_audit(
            args.question, all_research, all_reviews,
            palette, ws, args.timeout,
        )
    except Exception as e:
        print(f"  {palette['dim']}Phase 3.5 error: {e} — continuing without audit{palette['reset']}\n")
        ws.log(f"Phase 3.5 FAILED: {e}")

    # ── Phase 4: Reframe ──
    reframe_text = ""
    if not args.no_reframe:
        try:
            status, reframe_text = phase_reframe(
                args.question, decomposition_text, all_research, all_reviews,
                audit_text, palette, ws, args.timeout,
            )
            if status == "REVISE":
                print(f"{palette['bold']}Framework revision triggered — running supplementary research...{palette['reset']}\n")
                new_assignments = parse_sub_questions(reframe_text)
                supplementary = phase_research(
                    args.question, new_assignments, palette, ws, args.timeout, tag="b",
                )
                all_research.update({f"{k} (supplementary)": v for k, v in supplementary.items()})
        except Exception as e:
            print(f"  {palette['dim']}Phase 4 error: {e} — continuing without reframe{palette['reset']}\n")
            ws.log(f"Phase 4 FAILED: {e}")

    # ── Phase 5: Synthesize ──
    synthesis = ""
    try:
        synthesis = phase_synthesize(
            args.question, all_research, all_reviews, audit_text, reframe_text,
            palette, ws, args.timeout,
        )
    except Exception as e:
        print(f"\n{palette['bold']}Synthesis failed: {e}{palette['reset']}")
        print("All intermediate research is saved in the workspace.")

    elapsed = time.time() - start_time
    minutes = int(elapsed // 60)
    seconds = int(elapsed % 60)
    elapsed_str = f"{minutes}m{seconds}s"

    # ── Phase 6: HTML Report ──
    if synthesis:
        try:
            report_path = phase_report(
                args.question, synthesis, palette, ws, args.timeout, elapsed_str,
            )
        except Exception as e:
            print(f"  {palette['dim']}Report generation failed: {e}{palette['reset']}\n")
            ws.log(f"Phase 6 FAILED: {e}")

    ws.log(f"Completed in {elapsed_str}")
    ws.flush_log()

    print(f"{palette['dim']}Completed in {elapsed_str}")
    print(f"Workspace: {ws.base}{palette['reset']}\n")


if __name__ == "__main__":
    main()
