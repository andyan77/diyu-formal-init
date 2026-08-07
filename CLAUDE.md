# CLAUDE.md · 笛语正式立项项目（Claude Code 执行端）

> 本文件面向在本仓开工的 Claude Code 执行端会话。主控协作与裁决规则见根 `AGENTS.md`
> （其"Codex 是唯一主协作入口"条款描述主控窗口分工，不改变本执行端在 Brief 内的职责）。
> 不整体导入 `AGENTS.md`——按下列指定章节遵守，避免角色条款冲突。

- 状态真源：根 `MILESTONE.md`（当前主线 `COMM-01 · IN-PROGRESS`）；任务真源：当轮执行 Brief。
- 执行端必须遵守 `AGENTS.md` 以下章节：§5 权威与状态诚实、§7 执行自主性与停止边界、
  §9 主控窗口与执行端、§10 里程碑承接与架构裁决门、§11 视觉资产真源、§12 前端交互真源、
  §13 审查工具边界（系统级"审查测试验证"Skill 已确认假绿，禁止调用）、
  **§14 COMM-01 前端执行契约**（前端工作的强制契约）。
- 未获当轮执行 Brief 显式批准，不安装任何新依赖（生产/开发分别审批）。
- 触发 §14.9 停止条件或 Brief 前置门失败时：输出 BLOCKED / PRECONDITION_BLOCKED 报告，
  不得绕行、不得顺手修范围外问题。
- 提交纪律：断言门控（`python3 <assert> && git add <files> && git commit`）；
  完成后必须 push 执行分支并记录远端 HEAD SHA——不 push 视为未交付。
