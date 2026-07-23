# 当前里程碑

- 里程碑：`M3-2` P1 扩展攻击面与最小远程 CI
- 状态：`REVIEW`
- 起点：M3-1 已在 `80fc263` 正式关闭
- 实现基线：`b20a9d8`
- 唯一执行端：用户转交本执行包后的 WSL 执行端
- 当前任务包：`docs/M3-2-P1扩展攻击面与最小远程CI执行包.md`

## 进入条件

- M3-1 的 P1 用户闭环、20 项确定性回归和真实 DeepSeek 人工审阅继续作为不可回退基线；
- 通用工程执行准则和最新版 Medium 字重 VI/Logo 已进入唯一主仓；
- 用户已确认公开仓库 `andyan77/diyu-formal-init`，并要求 CI 受明确时长限制；任务包已冻结为单一作业、10 分钟硬超时。
- 公开仓库已创建、首次推送成功，`origin` 已连接；外部前置已经关闭。
- 已新增最小高信号历史池诱饵：外租户、同租户兄弟品牌、同品牌另一账号/操作人均不能成为当前自然承接或显式复用的前情；捕获的 `GenerationInput` 仅含当前合法品牌、账号、角色、受众、资产与历史正文。
- 已建立单一 Ubuntu Linux CI（`timeout-minutes: 10`），锁定依赖后运行 `make lint`、`make typecheck`、`make golden`；PostgreSQL 工具路径和迁移驱动均已跨 Linux 版本收敛。远程绿色运行：[29984807655](https://github.com/andyan77/diyu-formal-init/actions/runs/29984807655)。
- 本地统一回归为 22 passed；CI 不读取 DeepSeek、ECS、生产数据库或密钥，也不上传内容、数据库或运行日志产物。

## 本里程碑唯一结果

补足最小高信号的租户/品牌/账号/用户/历史池诱饵反证，并把既有 `make lint`、`make typecheck`、`make golden` 接入一个最小远程 Linux CI。M3-2 不新增内容产品、不重做 M3-1、不调用真实模型、不部署 ECS。

唯一下一动作：主控终审 M3-2；未审为 `CLOSED` 前不得启动 M4-1。
