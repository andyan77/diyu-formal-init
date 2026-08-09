# BRAND-MATRIX-01 · Gate D 第七轮 provider 端点不匹配前置阻断报告

状态：**`GATE-D PRECONDITION_BLOCKED · PROVIDER_ENDPOINT_MISMATCH`**。

## 1. 阻断事实

- `UNLOCK-D-RERUN-07` 与主线 `f783c37` 的 accepted fact 把 provider 目标冻结为
  `*.aliyuncs.com` 境内 DashScope 端点。
- 执行时仅用授权的进程内解析器读取三个精确 `DEEPSEEK_*` 键，不回显值；其中
  `DEEPSEEK_API_BASE_URL` 的安全可报主机名实际为 `api.deepseek.com`。
- 套件前 TCP/TLS 握手探针因端点不在冻结范围内，在建立 socket 和任何补全请求前
  fail-closed，输出 `GATED_FORMAL_SUITE_PRECONDITION_BLOCKED`。
- 这与已采认的 provider 主机事实直接冲突。执行端不能擅自改写 `.env`，也不能将
  `api.deepseek.com` 静默视为本轮获准目标。

## 2. 已完成但不构成 Gate D 完成的证据

- 直连客户端 `trust_env=False`、内容重试 0、传输重试最多 2 次、传输账本和零预算
  握手探针已实现；污染代理、重试入账、有效内容不重发等双向回归通过。
- 完整本地门绿：Ruff、mypy、Golden、EXE-V0、EXE-01、前端四门、Chrome、两套
  secrets、Gate D scope/semantics/privacy、`scripts/test.sh`；pytest `1055 passed / 2 skipped`。
- 运行候选：`f00e5d44098e2ef2ef70d76dab67a3e3fdd03ea4`。CI run `31310993995`
  四查：event=`workflow_dispatch`，headSha=运行候选，conclusion=`success`，
  非成功步骤=0。
- 两轮导入 batch digest：
  `20e1d00aa527d31312748ed84a22119d28784776ed3d2c40824b3775d8bdd6ed`；
  对象指纹：`1ec150e8f992e4d8f2439e7a791f744c5d3ee7bb7c69f25d735a6999bfbb2f98`。
- 冻结登记 digest：
  `93a49a1d0cebcb62d2cc52c93594e0dd891bf69bb79dd1c82331a7887cfb3bf1`。
- 媒体 PASS(scope)/FAIL/QUARANTINED=`26/0/0`；P5 合格母版 6 份，覆盖 4 个正式商品。

## 3. 诚实边界

- 本轮 provider completion request=`0`，累计账本保持 `44/80`，传输重试=`0`。
- 八剧本和八异常未启动；本轮 task/run/version=`0/0/0`，无新成品，无旧候选拼接。
- 私有证据目录未创建；生产/SSH/ECS 0，alembic 修改 0，密钥泄漏 0，二进制入 Git 0。
- 数据已存储且 projection 已备妥，但本轮尚无新任务快照引用或最终成品；前两层不代替后两层。

唯一下一动作：主控确认并修正授权环境中 `DEEPSEEK_API_BASE_URL` 与 `f783c37`
冻结的 `*.aliyuncs.com` 端点一致；或另行签发允许 `api.deepseek.com` 的端点政策修订。
在此之前不得续跑正式套件。
