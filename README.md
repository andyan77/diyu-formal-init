# 笛语 M3-1 · P1 弱种子内容闭环

本仓库提供本地合成演示：自然弱种子生成可执行 P1 视频文字成品、自然语言生成 V2、保留 V1、主动保存，以及只在同一用户、品牌与发布账号原作用域内的明确复用。用户说“接着上一条”且当前范围内目标唯一时，无需先保存即可承接；输入普通交流不会创建任务。默认是可重复的离线替身模式，页面会明确标记，不冒充真实模型。

领域候选由本项目迁移后的系统公共目录登记：243 条均可追溯，当前 P1 仅按条件消费 `B-TPO-001`、`C-COMMUTE-001`、`D-DIRECT-001`、`D-CRAFT-001`；每个生成运行记录实际使用的资产 ID 与版本。全量登记不等于全量生产激活，用户页面不显示资产 ID、提示词或运行轨迹。

本地启动：

```bash
export DIYU_SESSION_SECRET='仅限本机的随机值'
scripts/run_app.sh
```

随后打开 `http://127.0.0.1:8000`。本地完整回归入口为 `make golden`；它创建/使用工作区内 PostgreSQL、合成演示数据和模型替身，并固定项目内 Linux 临时目录，不受 Windows `TEMP`/`TMP` 继承影响。

每次推送到 `main`、面向 `main` 的 PR 和手动触发都会在单个 Linux CI 作业中运行同一组 `make lint`、`make typecheck`、`make golden`；CI 不读取模型、ECS、生产数据库或密钥。

真实 DeepSeek 模式必须由服务器环境提供 `DIYU_GENERATOR_MODE=deepseek`、`DEEPSEEK_API_BASE_URL`、`DEEPSEEK_API_KEY` 和已核验的 `DEEPSEEK_MODEL`。受保护配置只能在服务器环境安全引用，绝不提交；本仓不会内置密钥。本轮已用临时、本机回环且仅限该 HTTPS 端点的 SSH 出站隧道完成真实同页验收；该隧道不是部署方式，也不改变 ECS、Nginx 或 DNS。
