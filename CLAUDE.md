# CLAUDE.md — Agent Loop

## 项目概述

单文件 Python 脚本（`agent_loop.py`），编排三个 AI CLI 工具（Claude、Codex、Gemini）通过 7 阶段流水线（含 Phase 3.5 证据审计）协作研究开放性问题。

## 架构要点

- **零外部依赖** — 纯 Python 3.10+ 标准库
- **单文件** — 所有逻辑在 `agent_loop.py` 中
- **CLI 子进程模型** — 每个 Agent 通过其 CLI 的非交互模式调用
- **并行执行** — Phase 2（研究）和 Phase 3（质疑）使用 `ThreadPoolExecutor`
- **证据审计** — Phase 3.5 由 Claude 验证所有引用来源并标记虚假信息

## 关键设计决策

- Prompt 通过 **stdin** 传递（而非 CLI 参数），避免 shell 转义和 ARG_MAX 限制
- Claude 需要**去掉 `CLAUDECODE` 环境变量**，否则会触发嵌套会话检测
- Gemini 的 `-p` 参数需要一个值，所以传 `" "`（空格）并通过临时文件 + stdin 管道传入实际 prompt
- Codex 使用 `--full-auto`（`-a never` 仅适用于交互模式，在 `exec` 模式下无效）
- Gemini 思考配置通过 `~/.gemini/settings.json` 设置（CLI 没有对应参数）

## 模型配置

- Claude: `claude-opus-4-6`，`--effort high`
- Codex: `gpt-5.3-codex`，`-c model_reasoning_effort="high"`
- Gemini: `gemini-3.1-pro-preview`，`thinkingLevel: "HIGH"`（settings.json）

## 文件结构

```
agent_loop.py          # 全部代码 — CLI 调用器、prompt 模板、阶段函数、HTML 模板、main()
ARCHITECTURE.md        # 内部执行架构详解
workspace/             # 每次运行自动创建，保存所有中间输出
```

## 常见问题

- **Claude "nested session" 错误**：`CLAUDECODE` 环境变量必须去掉。已在 `call_claude()` 中处理。
- **Codex "not inside a trusted directory"**：需要 `--skip-git-repo-check`。已处理。
- **Gemini "ModelNotFoundError"**：检查模型 ID 是否有效。当前：`gemini-3.1-pro-preview`。
- **Gemini 超时**：启用思考后 Gemini 可能较慢。默认超时 600 秒。
- **Codex `-a` 参数错误**：`-a` 仅用于交互模式。`exec` 模式使用 `--full-auto`。

## 扩展指南

- **新增 Agent**：添加 `call_X()` 函数 → 加入 `AGENTS` 字典 → 更新 `parse_sub_questions()` 支持新的分配键（如 `D`）
- **新增阶段**：编写阶段函数 → 在 `main()` 中插入到合适位置
- **更换模型**：修改对应 `call_*()` 函数中的 CLI 参数
