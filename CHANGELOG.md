# 更新日志

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
