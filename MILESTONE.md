# 当前里程碑

- 里程碑：`M3-2` P1 扩展攻击面与最小远程 CI
- 状态：`CLOSED`
- 起点：M3-1 已在 `80fc263` 正式关闭
- 实现基线：`ec564b1`
- 唯一执行端：用户转交本执行包后的 WSL 执行端
- 当前任务包：`docs/M3-2-P1扩展攻击面与最小远程CI执行包.md`

## 进入条件

- M3-1 的 P1 用户闭环、20 项确定性回归和真实 DeepSeek 人工审阅继续作为不可回退基线；
- 通用工程执行准则和最新版 Medium 字重 VI/Logo 已进入唯一主仓；
- 用户已确认公开仓库 `andyan77/diyu-formal-init`，并要求 CI 受明确时长限制；任务包已冻结为单一作业、10 分钟硬超时。
- 公开仓库已创建、首次推送成功，`origin` 已连接；外部前置已经关闭。
- 已新增最小高信号历史池诱饵：外租户、同租户兄弟品牌、同品牌另一账号/操作人均不能成为当前自然承接或显式复用的前情；捕获的 `GenerationInput` 仅含当前合法品牌、账号、角色、受众、资产与历史正文。
- 已建立单一 Ubuntu Linux CI（`timeout-minutes: 10`），锁定依赖后运行 `make lint`、`make typecheck`、`make golden`；PostgreSQL 工具路径和迁移驱动均已跨 Linux 版本收敛。最终实现提交 `ec564b1` 的远程绿色运行：[29984882408](https://github.com/andyan77/diyu-formal-init/actions/runs/29984882408)。
- 本地统一回归为 22 passed；CI 不读取 DeepSeek、ECS、生产数据库或密钥，也不上传内容、数据库或运行日志产物。
- 主控已独立复核任务包八项验收：本地 `make lint`、`make typecheck`、`make golden` 全部通过，远程 CI 与最终实现提交一致；M3-1 用户能力未回退。
- 笛语正式 VI/Logo 源已在主仓 `assets/brand/diyu-vi/`，共 36 个受 Git 跟踪文件；无需在后续执行包重复迁移。

## 本里程碑唯一结果

补足最小高信号的租户/品牌/账号/用户/历史池诱饵反证，并把既有 `make lint`、`make typecheck`、`make golden` 接入一个最小远程 Linux CI。M3-2 不新增内容产品、不重做 M3-1、不调用真实模型、不部署 ECS。

唯一下一动作：形成并转交 M4-1“D-005 墙面双层挂杆可用闭环”执行包；M3-2 不再重开。
