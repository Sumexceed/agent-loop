# 架构文档

## 整体结构

Agent Loop 是一个单文件 Python 脚本，通过子进程调用两个 AI CLI 工具，按阶段流水线执行协作研究。

```
┌─────────────────────────────────────────────────────────┐
│                    agent_loop.py                         │
│                                                         │
│  ┌──────────┐  ┌──────────┐  ┌──────────────────────┐  │
│  │ CLI 调用层 │  │ Prompt 模板│  │    阶段函数          │  │
│  │           │  │           │  │                      │  │
│  │ call_claude│  │ DECOMPOSE │  │ phase_decompose()    │  │
│  │ call_gemini│  │ RESEARCH  │  │ phase_research()     │  │
│  │           │  │ CHALLENGE │  │ phase_challenge()    │  │
│  │           │  │ EVIDENCE_ │  │ phase_evidence_audit()│  │
│  │           │  │   AUDIT   │  │ phase_repair()       │  │
│  │           │  │ REPAIR    │  │ phase_reframe()      │  │
│  │           │  │ REFRAME   │  │ phase_synthesize()   │  │
│  │           │  │ SYNTHESIZE│  │ phase_gap_analysis() │  │
│  │           │  │ GAP_      │  │ phase_report()       │  │
│  │           │  │  ANALYSIS │  │                      │  │
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
│ 主进程    │←───────────────────── │ (claude/      │
│           │    stdout (response)  │  gemini)      │
└───────────┘                       └──────────────┘
```

### 各 Agent 调用细节

```
Claude:
  命令: claude -p --verbose --model claude-opus-4-6 --effort high
        --output-format stream-json
        --allowedTools WebSearch,WebFetch,Read,Bash(grep:*),Bash(curl:*),Grep,Glob
  输入: stdin（直接传入 prompt 字符串）
  输出: stream-json 格式，由 _parse_stream_json() 提取所有 assistant text block 后拼接
  特殊: 必须从环境变量中去掉 CLAUDECODE，否则触发嵌套会话检测
        使用 stream-json 而非 text，因为 text 只返回最后一个 turn 的文本

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
 │  │  输出: 3-6 个子问题 + 分配方案（A=Claude, B=Gemini）
 │  │  解析: parse_sub_questions() 提取结构化子问题
 │  └─ 保存: phase1-decomposition.md
 │
 ├─ Phase 2: RESEARCH ───────────────────────────────────
 │  │  执行者: Claude + Gemini（并行）
 │  │  并行方式: ThreadPoolExecutor(max_workers=2)
 │  │  每个 Agent 收到: 原始问题 + 自己被分配的子问题
 │  │  要求: 必须使用网络搜索，引用具体来源
 │  └─ 保存: phase2-research-{agent}.md × 2
 │
 ├─ Phase 3: CHALLENGE ──────────────────────────────────
 │  │  执行者: Claude + Gemini（并行）
 │  │  审查轮换: Claude→Gemini的研究, Gemini→Claude的研究
 │  │  要求: 搜索验证关键引用，查找反面证据，指出逻辑漏洞
 │  └─ 保存: phase3-review-{reviewer}-of-{target}.md × 2
 │
 ├─ Phase 3.5: EVIDENCE AUDIT ──────────────────────────
 │  │  执行者: Claude（单独）
 │  │  输入: 所有研究发现 + 所有交叉审查结果
 │  │  工作内容:
 │  │    - 逐一搜索验证引用的 URL 和来源
 │  │    - 检查来源是否真正支持声明
 │  │    - 对每条声明分级: ✅已验证 / ⚠️部分验证 / ❌无法验证 / 🚫虚假
 │  │  输出: 证据清单 + 可靠性统计 + 关键风险标记
 │  │  判断: 是否存在 ❌ 或 🚫 标记的声明？
 │  │    ├─ 无 → 跳过修补，直接进入 Phase 4
 │  │    └─ 有 → 进入 Phase 3.6 修补
 │  └─ 保存: phase3.5-evidence-audit.md
 │
 ├─ Phase 3.6: REPAIR（条件触发）────────────────────────
 │  │  触发条件: 审计发现了 FABRICATED 或 UNVERIFIABLE 的声明
 │  │
 │  │  步骤 1: 定向重新研究（并行）
 │  │    执行者: Claude + Gemini
 │  │    输入: 审计报告（聚焦于被标记的问题声明）
 │  │    要求: 为虚假/缺失的声明找到真实证据
 │  │
 │  │  步骤 2: 交叉审查修补内容（并行）
 │  │    执行者: Claude + Gemini（互相审查）
 │  │
 │  │  步骤 3: 再审计
 │  │    执行者: Claude
 │  │    输入: 修补研究 + 修补审查
 │  │    输出: 更新后的证据质量评估
 │  │
 │  └─ 保存: phase3.6-repair-*.md + phase3(repair)-review-*.md
 │           + phase3.5(repair)-evidence-audit.md
 │
 ├─ Phase 4: REFRAME ────────────────────────────────────
 │  │  执行者: Gemini（单独）
 │  │  输入: 拆解结果 + 研究发现 + 审查结果 + 证据审计（含修补）
 │  │  判断: 原始框架是否足够？
 │  │    ├─ ADEQUATE → 直接进入 Phase 5
 │  │    └─ REVISE → 提出新子问题，触发完整的补充流程：
 │  │         ├─ Phase 2b: 补充研究（并行）
 │  │         ├─ Phase 3b: 补充研究的交叉审查（并行）
 │  │         └─ Phase 3.5b: 补充研究的证据审计
 │  └─ 保存: phase4-reframe.md（+ phase2b/3b/3.5b-*.md）
 │
 ├─ Phase 5: SYNTHESIZE ─────────────────────────────────
 │  │  执行者: Claude（单独）
 │  │  输入: 所有研究 + 审查 + 全部审计结果 + 框架修正
 │  │  输出: 结构化最终报告
 │  │    包含: 执行摘要 / 关键发现 / 共识 / 争议 / 证据质量 / 开放问题 / 来源
 │  └─ 保存: phase5-synthesis.md
 │
 ├─ Phase 5.5: GAP ANALYSIS（条件触发）─────────────────
 │  │  执行者: Gemini（独立评审者）
 │  │  输入: Phase 5 综合报告
 │  │  工作内容:
 │  │    - 提取所有开放问题/盲区
 │  │    - 分类为 RESEARCHABLE vs NON_PUBLIC
 │  │    - RESEARCHABLE 盲区转化为子问题
 │  │  判断: 是否有可研究的盲区？
 │  │    ├─ NO_RESEARCHABLE_GAPS → 直接进入 Phase 6
 │  │    └─ RESEARCH_NEEDED → 触发盲区补充流程：
 │  │         ├─ Phase 2c: 盲区研究（并行）
 │  │         ├─ Phase 3c: 交叉审查（并行）
 │  │         ├─ Phase 3.5c: 证据审计
 │  │         └─ 重新综合（覆写 Phase 5）
 │  └─ 保存: phase5.5-gap-analysis.md（+ phase2c/3c/3.5c-*.md）
 │           phase5-synthesis-v1.md（重新综合时保留原始版本）
 │
 ├─ Phase 6: REPORT ─────────────────────────────────────
 │  │  步骤 1: Claude 将内部综合报告改写为面向读者的正式研报
 │  │  步骤 2: Claude 生成浓缩摘要（~500 字）
 │  │  步骤 3: 将摘要 + 正式研报嵌入 HTML 模板
 │  │  步骤 4: 保存到 ~/Desktop/ 并自动打开浏览器
 │  └─ 保存: phase6-polished-report.md + phase6-briefing.md + report.html
 │
 └─ 完成: 输出耗时，刷新日志
```

## 两条主要执行路径

```
路径 A（证据质量高 + 框架充分 + 无盲区，最短路径）:
  1 → 2 → 3 → 3.5(无问题) → 4(ADEQUATE) → 5 → 5.5(无盲区) → 6

路径 B（有盲区需要补充研究）:
  1 → 2 → 3 → 3.5 → 4 → 5 → 5.5(有盲区) → 2c+3c+3.5c → 5(重新综合) → 6

路径 C（证据有问题 + 修正框架 + 有盲区，最长路径）:
  1 → 2 → 3 → 3.5(有问题) → 3.6(修补+审查+审计) → 4(REVISE) → 2b+3b+3.5b → 5 → 5.5(有盲区) → 2c+3c+3.5c → 5(重新综合) → 6
```

整个流程是**严格线性**的，没有回环。Phase 3.6 和 Phase 4 REVISE 是条件分支，不是循环。

## 各 Agent 的职责分工

```
┌─────────────────────────────────────────────────┐
│                    Claude                        │
│  Phase 1:   问题拆解（策略制定者）               │
│  Phase 2:   研究子问题 A                         │
│  Phase 3:   审查 Gemini 的研究                   │
│  Phase 3.5: 证据审计（质量把关者）               │
│  Phase 3.6: 定向修补研究 + 修补再审计            │
│  Phase 5:   最终综合（报告撰写者）               │
│  Phase 6:   生成浓缩摘要                         │
├─────────────────────────────────────────────────┤
│                    Gemini                        │
│  Phase 2:   研究子问题 B                         │
│  Phase 3:   审查 Claude 的研究                   │
│  Phase 3.6: 定向修补研究                         │
│  Phase 4:   框架修正评估（架构评审者）           │
│  Phase 5.5: 盲区分析（独立评审者）               │
└─────────────────────────────────────────────────┘
```

## 数据流

```
原始问题
    │
    ▼
┌─ DECOMPOSE ─┐
│ 子问题 A/B   │
└──────────────┘
    │  │
    ▼  ▼  （并行）
┌──────┐ ┌──────┐
│研究 A│ │研究 B│
└──┬───┘ └──┬───┘
   │        │
   ▼        ▼  （并行，交叉）
┌──────┐ ┌──────┐
│审查 B│ │审查 A│
└──┬───┘ └──┬───┘
   │        │
   └────┬───┘
        ▼
┌─ EVIDENCE AUDIT ─┐
│   证据质量报告     │
└───────┬───────────┘
        │
  有问题？──→ 无 ──→ 跳过修补
        │
        ▼  有
┌─── REPAIR ────────────────┐
│  2 Agent 定向修补（并行）  │
│       ↓                   │
│  交叉审查修补内容（并行） │
│       ↓                   │
│  Claude 再审计            │
└───────┬───────────────────┘
        │
        ▼
┌─── REFRAME ───┐
│ ADEQUATE/REVISE│
└───────┬───────┘
        │
  REVISE？──→ ADEQUATE ──→ 直接综合
        │
        ▼
┌─── 补充研究流程 ──────────┐
│  Phase 2b: 并行研究       │
│       ↓                   │
│  Phase 3b: 交叉审查       │
│       ↓                   │
│  Phase 3.5b: 证据审计     │
└───────┬───────────────────┘
        │
        ▼
┌── SYNTHESIZE ──┐
│   最终报告      │
└───────┬────────┘
        │
        ▼
┌─── GAP ANALYSIS ───┐
│ RESEARCHABLE/       │
│ NO_RESEARCHABLE_GAPS│
└───────┬─────────────┘
        │
  RESEARCH_NEEDED？──→ NO ──→ 直接报告
        │
        ▼
┌─── 盲区研究流程 ─────────────┐
│  Phase 2c: 并行研究           │
│       ↓                      │
│  Phase 3c: 交叉审查           │
│       ↓                      │
│  Phase 3.5c: 证据审计         │
└───────┬──────────────────────┘
        │
        ▼
┌── SYNTHESIZE (v2) ──┐
│   更新后的报告       │
└───────┬──────────────┘
        ▼
┌─── REPORT ────┐
│  HTML + 摘要   │
└───────────────┘
```

## 并行执行模型

Phase 2、Phase 3、Phase 3.6 步骤 1/2 使用 `ThreadPoolExecutor` 并行执行两个 Agent：

```python
with ThreadPoolExecutor(max_workers=2) as executor:
    futures = {
        executor.submit(run_agent, name, prompt, timeout): name
        for name, prompt in tasks
    }
    for future in as_completed(futures):
        name = futures[future]
        _, response = future.result()
```

Phase 3.6 内部复用 `phase_challenge()` 和 `phase_evidence_audit()` 函数（通过 `tag` 参数区分文件命名和日志标识）。

## 工作区与审计日志

每次运行创建独立的工作区目录（`~/agent-loop/workspace/{时间戳}/`），所有阶段的输入输出都保存为 Markdown 文件。`Workspace` 类同时维护一个带时间戳的执行日志（`full-log.md`），记录每个阶段的开始、完成或失败。

这个设计确保：
- 每次研究过程完全可追溯
- 某个阶段失败时，之前的研究成果不会丢失
- 可以事后分析每个 Agent 的研究质量

## 错误处理策略

- 每个阶段独立 try/catch，失败不影响后续阶段（尽力执行）
- Phase 3.5 证据审计失败时，audit_text 为空字符串，跳过修补，下游正常运行
- Phase 3.6 修补失败时，跳过修补，使用原始审计结果继续
- Phase 4 框架修正失败时，跳过修正继续综合
- Phase 4 REVISE 的补充审查/审计失败时，补充研究仍然并入主结果
- Phase 5.5 盲区分析失败时，使用原始综合报告继续
- Phase 5.5 盲区研究/审查/审计/重新综合失败时，使用原始综合报告继续
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
