# 更新日志

## [2.5.0] - 2026-03-03

### 新增
- **Phase 5.5: GAP ANALYSIS（盲区分析）** — 在综合报告产出后自动识别研究盲区
  - Gemini 作为独立评审者分析综合报告中的开放问题
  - 将每个盲区分类为 RESEARCHABLE（可通过公开信息搜索）或 NON_PUBLIC（需要非公开数据）
  - 分类准则倾向 RESEARCHABLE：宁可搜了没结果，也不跳过能搜到的
  - RESEARCHABLE 盲区触发完整的补充研究流程：Phase 2c → 3c → 3.5c → 重新综合
  - 重新综合时保留原始报告为 `phase5-synthesis-v1.md`
- `--no-gap-research` 参数跳过盲区分析阶段
- 新增文件：`phase5.5-gap-analysis.md`、`phase2c-*`、`phase3c-*`、`phase3.5c-*`
- **Phase 6 报告改写** — 内部综合报告在输出前经过 Claude 改写为面向读者的正式研报
  - 去除所有内部审计标签（VERIFIED/FABRICATED/✅/🚫）和过程性语言
  - 按主题逻辑重组（而非按研究发现顺序）
  - 以专业研报语言呈现不确定性，而非内部标记
  - 新增文件：`phase6-polished-report.md`

## [2.4.0] - 2026-03-02

### 变更
- **移除 Codex** — 从三 Agent 架构（Claude + Codex + Gemini）简化为双 Agent 架构（Claude + Gemini）。
  Codex 通过 shell 命令做网络研究（curl + python 解析 HTML），耗时波动极大（300s-600s+），频繁超时。
  Claude 和 Gemini 均有原生搜索工具，研究效率和稳定性远优于 Codex。
- 子问题分配从 A/B/C 改为 A/B（Claude/Gemini）
- `ThreadPoolExecutor` max_workers 从 3 降为 2
- 更新所有 prompt 模板、HTML 报告模板、文档

### 修复
- **Claude 研究输出截断** — `--output-format text` 仅返回最后一个 assistant turn 的 text，
  当 Claude 使用工具进行多轮搜索时，中间 turn 的研究内容（通常是主体报告）会丢失。
  改用 `--output-format stream-json --verbose` 并收集所有 assistant text block 后拼接。
  新增 `_parse_stream_json()` 辅助函数。
- **`parse_sub_questions()` 只识别 A/B 键** — Phase 4 (Gemini) 输出非标准键时，
  子问题被静默丢弃导致补充研究为空。改为接受任意大写字母（A-Z），非标准键 round-robin 分配。

## [2.3.0] - 2026-03-02

### 新增
- **Phase 3.6: REPAIR（证据修补）** — 审计发现虚假/缺失证据后触发定向修补
  - 三个 Agent 并行针对被标记的问题声明重新研究
  - 修补内容经过交叉审查 + 再审计，形成完整质控闭环
  - 条件触发：仅在审计发现 FABRICATED 或 UNVERIFIABLE 时执行
- **补充研究完整质控** — Phase 4 REVISE 触发的补充研究现在也经过交叉审查 + 证据审计
- `phase_challenge()` 和 `phase_evidence_audit()` 新增 `tag` 参数，支持在不同阶段复用

## [2.2.0] - 2026-03-02

### 新增
- **Phase 3.5: 证据审计** — Claude 在交叉审查之后执行专门的证据质量审计
  - 通过网络搜索验证引用的 URL 和来源
  - 检查来源是否真正支持研究者的声明
  - 对每条声明分级：已验证 / 部分验证 / 无法验证 / 虚假信息
  - 输出证据清单、可靠性统计和关键风险标记
- 审计结果传入 Phase 4（框架修正）和 Phase 5（综合），实现证据感知的决策
- SYNTHESIZE prompt 现在包含每条关键发现的验证状态
- REFRAME prompt 现在参考审计标记来决定是否需要补充研究

## [2.1.0] - 2026-03-02

### 变更
- Claude 升级至 **Opus 4.6**，启用扩展思考（`--effort high`）
- Codex 升级至 **GPT-5.3-Codex**，推理努力度设为 high
- Gemini 升级至 **Gemini 3.1 Pro Preview**，思考级别设为 HIGH
- 首次运行时自动配置 Gemini 思考设置（`~/.gemini/settings.json`）

### 修复
- Codex `exec` 模式：`-a never`（仅交互模式）替换为 `--full-auto`

## [2.0.0] - 2026-03-02

### 新增
- **分阶段研究流水线**，取代轮流发言模式
  - Phase 1: DECOMPOSE — 结构化问题拆解
  - Phase 2: RESEARCH — 并行独立研究（启用网络搜索）
  - Phase 3: CHALLENGE — 交叉审查与验证
  - Phase 4: REFRAME — 框架修正与补充研究
  - Phase 5: SYNTHESIZE — 基于证据的最终报告
  - Phase 6: REPORT — 生成 HTML 报告，保存到桌面并自动打开
- **工具权限启用** — Agent 可使用网络搜索、文件读取、代码执行
- **并行执行** — Phase 2 和 Phase 3 所有 Agent 并发运行
- **工作区目录** — 所有中间输出保存，供审计追溯
- **HTML 报告** — 包含核心摘要 + 完整报告，支持深色模式
- **框架修正** — Phase 4 在原始框架不足时可触发补充研究
- `--no-reframe` 跳过框架修正阶段
- `--workspace` 自定义输出目录
- `--timeout` 设置每次 Agent 调用超时

### 变更
- 从观点分享架构完全重写为研究驱动架构
- Prompt 明确要求网络搜索、引用和证据
- 默认超时从 300 秒增加到 600 秒

## [1.0.0] - 2026-03-01

### 新增
- 初始版本：轮流发言讨论循环
- 三个 Agent（Claude、Codex、Gemini）轮流回应
- 可配置发言轮数（`--rounds`）
- 彩色终端输出
- Claude 进行最终综合
- 基本错误处理和超时支持
