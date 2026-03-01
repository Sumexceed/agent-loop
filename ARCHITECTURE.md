# 架构文档

## 整体结构

Agent Loop 是一个单文件 Python 脚本，通过子进程调用三个 AI CLI 工具，按阶段流水线执行协作研究。

```
┌─────────────────────────────────────────────────────────┐
│                    agent_loop.py                         │
│                                                         │
│  ┌──────────┐  ┌──────────┐  ┌──────────────────────┐  │
│  │ CLI 调用层 │  │ Prompt 模板│  │    阶段函数          │  │
│  │           │  │           │  │                      │  │
│  │ call_claude│  │ DECOMPOSE │  │ phase_decompose()    │  │
│  │ call_codex │  │ RESEARCH  │  │ phase_research()     │  │
│  │ call_gemini│  │ CHALLENGE │  │ phase_challenge()    │  │
│  │           │  │ EVIDENCE_ │  │ phase_evidence_audit()│  │
│  │           │  │   AUDIT   │  │ phase_reframe()      │  │
│  │           │  │ REFRAME   │  │ phase_synthesize()   │  │
│  │           │  │ SYNTHESIZE│  │ phase_report()       │  │
│  │           │  │ CONDENSED │  │                      │  │
│  └──────────┘  └──────────┘  └──────────────────────┘  │
│                                                         │
│  ┌──────────┐  ┌──────────┐  ┌──────────────────────┐  │
│  │ Workspace │  │ HTML 模板 │  │     main()           │  │
│  │ 工作区管理 │  │           │  │   流水线编排          │  │
│  └──────────┘  └──────────┘  └──────────────────────┘  │
└─────────────────────────────────────────────────────────┘
```

## CLI 调用层

每个 Agent 通过其 CLI 的非交互模式调用，Prompt 通过 stdin 传入，输出通过 stdout 捕获。

```
┌───────────┐    stdin (prompt)     ┌──────────────┐
│ Python    │ ─────────────────────→│ CLI 子进程    │
│ 主进程    │←───────────────────── │ (claude/codex │
│           │    stdout (response)  │  /gemini)     │
└───────────┘                       └──────────────┘
```

### 各 Agent 调用细节

```
Claude:
  命令: claude -p --model claude-opus-4-6 --effort high --output-format text
        --allowedTools WebSearch,WebFetch,Read,Bash(grep:*),Bash(curl:*),Grep,Glob
  输入: stdin（直接传入 prompt 字符串）
  特殊: 必须从环境变量中去掉 CLAUDECODE，否则触发嵌套会话检测

Codex:
  命令: codex exec --skip-git-repo-check --full-auto
        -m gpt-5.3-codex -c model_reasoning_effort="high"
  输入: stdin（直接传入 prompt 字符串）
  特殊: --skip-git-repo-check 避免目录信任检查

Gemini:
  命令: gemini --yolo -m gemini-3.1-pro-preview -p " "
  输入: stdin（从临时文件管道传入，-p " " 是占位符）
  特殊: 思考配置通过 ~/.gemini/settings.json 设置
        首次运行时自动写入 thinkingLevel: "HIGH"
```

## 执行流水线

```
main()
 │
 ├─ 1. 解析命令行参数
 ├─ 2. 配置 Gemini 思考设置
 ├─ 3. 创建工作区
 │
 ├─ Phase 1: DECOMPOSE ──────────────────────────────────
 │  │  执行者: Claude（单独）
 │  │  输入: 原始研究问题
 │  │  输出: 3-6 个子问题 + 分配方案（A=Claude, B=Codex, C=Gemini）
 │  │  解析: parse_sub_questions() 提取结构化子问题
 │  └─ 保存: phase1-decomposition.md
 │
 ├─ Phase 2: RESEARCH ───────────────────────────────────
 │  │  执行者: Claude + Codex + Gemini（并行）
 │  │  并行方式: ThreadPoolExecutor(max_workers=3)
 │  │  每个 Agent 收到: 原始问题 + 自己被分配的子问题
 │  │  要求: 必须使用网络搜索，引用具体来源
 │  └─ 保存: phase2-research-{agent}.md × 3
 │
 ├─ Phase 3: CHALLENGE ──────────────────────────────────
 │  │  执行者: Claude + Codex + Gemini（并行）
 │  │  审查轮换: Claude→Codex的研究, Codex→Gemini的研究, Gemini→Claude的研究
 │  │  要求: 搜索验证关键引用，查找反面证据，指出逻辑漏洞
 │  └─ 保存: phase3-review-{reviewer}-of-{target}.md × 3
 │
 ├─ Phase 3.5: EVIDENCE AUDIT ──────────────────────────
 │  │  执行者: Claude（单独）
 │  │  输入: 所有研究发现 + 所有交叉审查结果
 │  │  工作内容:
 │  │    - 逐一搜索验证引用的 URL 和来源
 │  │    - 检查来源是否真正支持声明
 │  │    - 对每条声明分级: ✅已验证 / ⚠️部分验证 / ❌无法验证 / 🚫虚假
 │  │  输出: 证据清单 + 可靠性统计 + 关键风险标记
 │  └─ 保存: phase3.5-evidence-audit.md
 │
 ├─ Phase 4: REFRAME ────────────────────────────────────
 │  │  执行者: Gemini（单独）
 │  │  输入: 拆解结果 + 研究发现 + 审查结果 + 证据审计
 │  │  判断: 原始框架是否足够？
 │  │    ├─ ADEQUATE → 继续
 │  │    └─ REVISE → 提出新子问题 → 触发 Phase 2b 补充研究（并行）
 │  └─ 保存: phase4-reframe.md（+ phase2b-research-*.md）
 │
 ├─ Phase 5: SYNTHESIZE ─────────────────────────────────
 │  │  执行者: Claude（单独）
 │  │  输入: 所有研究 + 审查 + 证据审计 + 框架修正
 │  │  输出: 结构化最终报告
 │  │    包含: 执行摘要 / 关键发现 / 共识 / 争议 / 证据质量 / 开放问题 / 来源
 │  └─ 保存: phase5-synthesis.md
 │
 ├─ Phase 6: REPORT ─────────────────────────────────────
 │  │  步骤 1: Claude 生成浓缩摘要（~500 字）
 │  │  步骤 2: 将摘要 + 完整报告嵌入 HTML 模板
 │  │  步骤 3: 保存到 ~/Desktop/ 并自动打开浏览器
 │  └─ 保存: phase6-briefing.md + report.html
 │
 └─ 完成: 输出耗时，刷新日志
```

## 各 Agent 的职责分工

```
┌─────────────────────────────────────────────────┐
│                    Claude                        │
│  Phase 1:   问题拆解（策略制定者）               │
│  Phase 2:   研究子问题 A                         │
│  Phase 3:   审查 Codex 的研究                    │
│  Phase 3.5: 证据审计（质量把关者）               │
│  Phase 5:   最终综合（报告撰写者）               │
│  Phase 6:   生成浓缩摘要                         │
├─────────────────────────────────────────────────┤
│                    Codex                         │
│  Phase 2:   研究子问题 B                         │
│  Phase 3:   审查 Gemini 的研究                   │
├─────────────────────────────────────────────────┤
│                    Gemini                        │
│  Phase 2:   研究子问题 C                         │
│  Phase 3:   审查 Claude 的研究                   │
│  Phase 4:   框架修正评估（架构评审者）           │
└─────────────────────────────────────────────────┘
```

## 数据流

```
原始问题
    │
    ▼
┌─ DECOMPOSE ─┐
│ 子问题 A/B/C │
└──────────────┘
    │  │  │
    ▼  ▼  ▼  （并行）
┌──────┐ ┌──────┐ ┌──────┐
│研究 A│ │研究 B│ │研究 C│
└──┬───┘ └──┬───┘ └──┬───┘
   │        │        │
   ▼        ▼        ▼  （并行，交叉）
┌──────┐ ┌──────┐ ┌──────┐
│审查 B│ │审查 C│ │审查 A│
└──┬───┘ └──┬───┘ └──┬───┘
   │        │        │
   └────────┼────────┘
            ▼
    ┌─ EVIDENCE AUDIT ─┐
    │   证据质量报告     │
    └───────┬───────────┘
            ▼
    ┌─── REFRAME ───┐
    │ ADEQUATE/REVISE│──→ (REVISE 时触发补充研究)
    └───────┬───────┘
            ▼
    ┌── SYNTHESIZE ──┐
    │   最终报告      │
    └───────┬────────┘
            ▼
    ┌─── REPORT ────┐
    │  HTML + 摘要   │
    └───────────────┘
```

## 并行执行模型

Phase 2 和 Phase 3 使用 `ThreadPoolExecutor` 并行执行三个 Agent：

```python
with ThreadPoolExecutor(max_workers=3) as executor:
    futures = {
        executor.submit(run_agent, name, prompt, timeout): name
        for name, prompt in tasks
    }
    for future in as_completed(futures):
        name = futures[future]
        _, response = future.result()
```

串行执行约需 30-45 分钟，并行执行约需 10-15 分钟（取决于最慢的 Agent）。

## 工作区与审计日志

每次运行创建独立的工作区目录（`~/agent-loop/workspace/{时间戳}/`），所有阶段的输入输出都保存为 Markdown 文件。`Workspace` 类同时维护一个带时间戳的执行日志（`full-log.md`），记录每个阶段的开始、完成或失败。

这个设计确保：
- 每次研究过程完全可追溯
- 某个阶段失败时，之前的研究成果不会丢失
- 可以事后分析每个 Agent 的研究质量

## 错误处理策略

- 每个阶段独立 try/catch，失败不影响后续阶段（尽力执行）
- Phase 3.5 证据审计失败时，audit_text 为空字符串，下游阶段正常运行（只是少了审计信息）
- Phase 4 框架修正失败时，跳过修正继续综合
- 每次 Agent 调用有超时保护（默认 600 秒）
- 所有错误记录到工作区日志

## HTML 报告架构

报告使用内嵌 CSS + CDN 版 marked.js（Markdown → HTML 渲染）：

```
┌─ HTML ─────────────────────────────┐
│ <header>                           │
│   研究问题 / 日期 / Agent 标签     │
│ </header>                          │
│                                    │
│ <briefing>                         │
│   浓缩摘要（marked.js 渲染）      │
│ </briefing>                        │
│                                    │
│ <divider>                          │
│                                    │
│ <report>                           │
│   完整报告（marked.js 渲染）      │
│ </report>                          │
│                                    │
│ <footer>                           │
│   耗时 / 版本信息                  │
│ </footer>                          │
│                                    │
│ <script>                           │
│   marked.parse(briefingMd)         │
│   marked.parse(reportMd)           │
│ </script>                          │
└────────────────────────────────────┘
```

Markdown 内容以 JSON 字符串嵌入 `<script>` 标签，页面加载时由 marked.js 渲染。支持深色模式（`prefers-color-scheme: dark`）。
