# CLAUDE.md — Agent Loop

## 项目概述

单文件 Python 脚本（`agent_loop.py`），编排两个 AI CLI 工具（Claude、Gemini）通过多阶段流水线（含证据审计、盲区分析）协作研究开放性问题。

## 架构要点

- **零外部依赖** — 纯 Python 3.10+ 标准库
- **单文件** — 所有逻辑在 `agent_loop.py` 中
- **CLI 子进程模型** — 每个 Agent 通过其 CLI 的非交互模式调用
- **并行执行** — Phase 2（研究）和 Phase 3（质疑）使用 `ThreadPoolExecutor`
- **证据审计** — Phase 3.5 由 Claude 验证所有引用来源并标记虚假信息
- **证据修补** — Phase 3.6 在审计发现问题时定向重新研究，含交叉审查和再审计
- **补充研究质控** — Phase 4 REVISE 的补充研究也经过完整的审查+审计流程
- **盲区分析** — Phase 5.5 由 Gemini 独立识别可研究的盲区，触发补充研究→审查→审计→重新综合

## 关键设计决策

- Prompt 通过 **stdin** 传递（而非 CLI 参数），避免 shell 转义和 ARG_MAX 限制
- Claude 需要**去掉 `CLAUDECODE` 环境变量**，否则会触发嵌套会话检测
- Claude 使用 `--output-format stream-json --verbose` 而非 `text`，因为 `text` 模式只返回最后一个 assistant turn 的文本，多轮工具调用时中间 turn 的研究内容会丢失
- Gemini 的 `-p` 参数需要一个值，所以传 `" "`（空格）并通过临时文件 + stdin 管道传入实际 prompt
- Gemini 思考配置通过 `~/.gemini/settings.json` 设置（CLI 没有对应参数）
- `parse_sub_questions()` 接受任意大写字母键（A-Z），非标准键 round-robin 分配给两个 Agent

## 模型配置

- Claude: `claude-opus-4-6`，`--effort high`
- Gemini: `gemini-3.1-pro-preview`，`thinkingLevel: "HIGH"`（settings.json）

## 文件结构

```
agent_loop.py          # 全部代码 — CLI 调用器、prompt 模板、阶段函数、HTML 模板、main()
ARCHITECTURE.md        # 内部执行架构详解
workspace/             # 每次运行自动创建，保存所有中间输出
```

## 常见问题

- **Claude "nested session" 错误**：`CLAUDECODE` 环境变量必须去掉。已在 `call_claude()` 中处理。
- **Claude 研究输出只有一行**：`--output-format text` 只返回最后一个 turn 的文本。当 Claude 做多轮搜索时，主体报告在中间 turn 被丢弃。已改用 `stream-json` + `_parse_stream_json()` 收集所有 text block。
- **Phase 4 补充研究为空**：`parse_sub_questions()` 原来只识别 `[AB]` 键，Gemini 可能输出 `[C1]` 等非标准键。已改为接受 `[A-Z]`，非标准键 round-robin 分配。
- **Gemini "ModelNotFoundError"**：检查模型 ID 是否有效。当前：`gemini-3.1-pro-preview`。
- **Gemini 超时**：启用思考后 Gemini 可能较慢。默认超时 600 秒。

## 扩展指南

- **新增 Agent**：添加 `call_X()` 函数 → 加入 `AGENTS` 字典 → 更新 `DECOMPOSE_PROMPT` 和 `REFRAME_PROMPT` 增加分配键 → 更新 `phase_research()` 和 `phase_repair()` 的 agent_map
- **新增阶段**：编写阶段函数 → 在 `main()` 中插入到合适位置
- **更换模型**：修改对应 `call_*()` 函数中的 CLI 参数
