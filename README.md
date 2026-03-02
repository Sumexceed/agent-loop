# Agent Loop

两个 AI Agent（Claude、Gemini）通过结构化的研究流程协作探究开放性问题。它们不是轮流"写作文"，而是各自带着工具去做真正的研究、交叉审查彼此的发现、在证据不支持时推翻原有框架。

## 为什么需要这个

单个大模型可以给你任何话题的多角度分析。但它本质上用的是同一个知识库、同一套偏见、零实时研究能力。Agent Loop 不同：

- 每个 Agent **真正进行网络搜索**，查找数据，引用来源
- Agent 之间**交叉审查发现**，搜索验证对方的引用
- Claude 执行专门的**证据审计**——逐一验证引用来源，标记虚假信息
- 审计发现问题时触发**定向修补**——重新研究虚假声明，再审查、再审计
- 研究框架**可以在过程中修正**——当证据推翻原始假设时，补充研究也经过完整审查
- 最终报告基于**经审计、修补、交叉验证的证据**，而非观点

## 工作流程

```
研究问题
   ↓
Phase 1:   DECOMPOSE（拆解）      — 将问题拆解为可研究的子问题
   ↓
Phase 2:   RESEARCH（研究）       — 2 个 Agent 并行研究（启用网络搜索）
   ↓
Phase 3:   CHALLENGE（质疑）      — 交叉审查发现，验证引用，寻找反面证据
   ↓
Phase 3.5: EVIDENCE AUDIT（审计） — Claude 审计证据质量，验证来源，标记虚假信息
   ↓
Phase 3.6: REPAIR（修补）         — 定向重新研究虚假/缺失证据 → 交叉审查 → 再审计
   ↓
Phase 4:   REFRAME（修正）        — 评估框架是否需要修正 → 补充研究 + 审查 + 审计
   ↓
Phase 5:   SYNTHESIZE（综合）     — 产出基于证据的研究报告
   ↓
Phase 5.5: GAP ANALYSIS（盲区分析）— 识别可研究的盲区 → 补充研究 + 审查 + 审计 → 重新综合
   ↓
Phase 6:   REPORT（报告）         — 改写为正式研报 → 生成浓缩摘要 → HTML 报告
```

## 环境要求

两个 CLI 工具需安装并完成认证：

| 工具 | 安装 | 认证 |
|------|------|------|
| [Claude Code](https://docs.anthropic.com/en/docs/claude-code) | `npm install -g @anthropic-ai/claude-code` | `claude auth` |
| [Gemini CLI](https://github.com/google-gemini/gemini-cli) | `npm install -g @google/gemini-cli` | `gemini`（首次运行 OAuth） |

Python 3.10+，无外部依赖。

## 使用方法

```bash
# 基本用法（完整 7 阶段流程）
python3 agent_loop.py "你的研究问题"

# 跳过框架修正阶段
python3 agent_loop.py "你的问题" --no-reframe

# 跳过盲区分析阶段
python3 agent_loop.py "你的问题" --no-gap-research

# 自定义每次 Agent 调用的超时时间（默认 600 秒）
python3 agent_loop.py "你的问题" --timeout 900

# 自定义工作区目录
python3 agent_loop.py "你的问题" --workspace ./my-research

# 禁用彩色输出
python3 agent_loop.py "你的问题" --no-color

# 管道友好模式（无颜色，适合日志记录）
python3 agent_loop.py "你的问题" --no-color 2>&1 | tee research.log
```

## 模型配置

| Agent | 模型 | 推理模式 |
|-------|------|----------|
| Claude | Opus 4.6 | 扩展思考（high effort） |
| Gemini | Gemini 3.1 Pro | 思考级别：HIGH |

模型配置在 `agent_loop.py` 的 `call_*` 函数中。脚本会在首次运行时自动配置 Gemini 的思考设置（`~/.gemini/settings.json`）。

## 输出

### 终端
每个阶段实时打印彩色输出（橙色=Claude，蓝色=Gemini）。

### 工作区
所有中间结果保存到 `~/agent-loop/workspace/{时间戳}/`：

```
workspace/20260302-143000/
├── 00-question.md                          # 原始研究问题
├── phase1-decomposition.md                 # 问题拆解结果
├── phase2-research-claude.md               # Claude 的研究发现
├── phase2-research-gemini.md               # Gemini 的研究发现
├── phase3-review-*.md                      # 交叉审查结果
├── phase3.5-evidence-audit.md              # 证据审计报告
├── phase3.6-repair-*.md                    # 定向修补研究（如果触发）
├── phase3(repair)-review-*.md              # 修补内容的交叉审查
├── phase3.5(repair)-evidence-audit.md      # 修补内容的再审计
├── phase4-reframe.md                       # 框架修正评估
├── phase2b-research-*.md                   # 补充研究（如果 REVISE）
├── phase3b-review-*.md                     # 补充研究的交叉审查
├── phase3.5b-evidence-audit.md             # 补充研究的审计
├── phase5-synthesis.md                     # 最终综合报告（内部工作文档）
├── phase5.5-gap-analysis.md                # 盲区分析（如果触发）
├── phase5-synthesis-v1.md                  # 原始综合报告（重新综合时保留）
├── phase2c-research-*.md                   # 盲区补充研究
├── phase3c-review-*.md                     # 盲区研究的交叉审查
├── phase3.5c-evidence-audit.md             # 盲区研究的审计
├── phase6-polished-report.md                # 正式研报（面向读者，去除内部标签）
├── phase6-briefing.md                      # 浓缩摘要
├── report.html                             # HTML 完整报告
└── full-log.md                             # 执行日志
```

### HTML 报告
格式化的 HTML 报告保存到 `~/Desktop/` 并自动在浏览器中打开：
- **上半部分**：核心要点浓缩摘要（~500 字）
- **下半部分**：完整研究报告（含证据和来源）

## 许可证

MIT
