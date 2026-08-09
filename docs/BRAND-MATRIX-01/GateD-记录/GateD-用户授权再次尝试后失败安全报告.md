# BRAND-MATRIX-01 · Gate D 用户授权再次尝试后失败安全报告

状态：**`GATE-D FAILED_SAFE · PROVIDER_REQUEST_FAILURE`**。

用户明确要求“再次尝试”后，执行侧没有补跑上一候选的失败卡，而是保留历史 42 次请求账本，
建立新候选、重建隔离栈并从第 1 张卡重新运行完整套件。本轮第 1 张 `S01-P1` 成功落版；
第 2 张 `S01-P2` 的唯一 provider 请求没有取得可接受响应，系统随即停止。后 13 张未运行，
没有重试、择优或跨候选拼接。

## 1. 当前结论

- 性能词极性收口和非阻断标注代码没有出现回归；全部本地工程门与 CI 通过。
- 本次失败发生在 DeepSeek provider 请求阶段，不是 Writer 内容边界或快照守卫拒绝。
- 现有脱敏失败证据只确认 `ProviderRequestFailure`；不足以诚实区分 HTTP 拒绝、服务暂时
  不可用或传输失败，因此不臆测更细原因。
- 上一轮第 13 次请求失败，本轮第 2 次请求再次失败；中间有正常响应，说明调用链表现为
  间歇性不可用，但仍不能仅凭现有证据归因到网络或 DeepSeek 服务端的某一侧。
- 八剧本 8/8 和八异常 8/8 未完成，Gate D 不得报 `IMPLEMENTED`。

## 2. 冻结、工程门与 CI

- runtime candidate：`587bed9168e92db7444db81ba9123b92a80cbacf`。
- 冻结登记提交：`5f2cdf6`；registration digest：
  `bc7846da9f16ec928d06e102bd558b2e00bcbbe8f8a7dd16b53116106af64896`。
- formal suite contract SHA-256：
  `89a5e0a4489857c36b73ef1ddc03b6c808d3680d25849e0bda3ac52dce2c0818`。
- 本地门：Ruff、mypy、Golden、EXE-V0、EXE-01、前端四门、显式 Chrome、两套 secrets、
  Gate D scope/semantics/privacy、`scripts/test.sh` 与 `git diff --check` 全绿；pytest
  `1048 passed / 2 skipped`。
- CI run `31309326766`：event=`workflow_dispatch`；headSha=
  `587bed9168e92db7444db81ba9123b92a80cbacf`；conclusion=`success`；非成功步骤=0。

## 3. 导入、媒体与固定输入

- import batch digest：`20e1d00aa527d31312748ed84a22119d28784776ed3d2c40824b3775d8bdd6ed`，
  两轮逐字一致。
- object fingerprint：`1ec150e8f992e4d8f2439e7a791f744c5d3ee7bb7c69f25d735a6999bfbb2f98`，
  两轮逐字一致。
- 本地隔离数据库输入指纹：
  `426b163dc7ff464bab3b4810568d23ab92aa1baf72217717cb072f1a22ec254c`。
- 媒体 PASS(scope)/FAIL/QUARANTINED=`26/0/0`；母版 P5 资格 6，覆盖 4 个正式商品；
  media manifest digest=`587d821315d896c414b382a1f277a07e1f7290f95cb8e0d829334cc53efc335b`。
- 模型 `deepseek-v4-flash`，temperature `0`，max_retries `0`。

## 4. Provider ledger 与私有证据

- 历史请求：42。
- 本轮请求尝试：2；`S01-P1` 取得响应并落版，`S01-P2` 请求失败。
- 累计：`44/80`；transport retry 0；失败后请求 0。
- `S01-P1` task/run/version=`1/1/1`；`S01-P2` task/run/version=`1/1/0`。
- 私有证据：`~/diyu-evidence-brand-matrix-gated-587bed9168e92db7444db81ba9123b92a80cbacf/`；
  目录 0700、文件 0600，4 个证据文件进入 `SHA256SUMS`，该文件 digest 为
  `5011405886a88fb33308f92b132e4f8f3f5d456dfe9e1d64fc26cfa6587661a7`。
- Git 中 raw response、完整 artifact、完整任务快照、密钥和媒体二进制均为 0。

## 5. 八剧本、八异常和四层口径

- 剧本 1：`FAILED_SAFE`；P1 卡完成，P2 provider 请求失败，P5 未运行。
- 剧本 2—8：`NOT_RUN_SUITE_ABORTED`。
- 异常 2—6：确定性 `PASS_ZERO_PROVIDER`；异常 1/8 因对应正式卡未运行而 incomplete；
  异常 7 的独立机制证据 PASS，套件内最终复核未运行。

四层口径：

- **已存储**：隔离导入完整；本轮正式 task/run/version=`2/2/1`。
- **已进入 projection**：34 个 V2 item；过期 `RK-EC-08` 不进入新任务。
- **已被任务快照引用**：本轮 1 个完成版本冻结正式输入；失败卡没有版本快照。
- **已进入卡级成品**：本轮 1 张；不得与此前 12 张或其他候选拼接。

本轮生产/SSH/ECS 0、alembic 修改 0、产品代码与 Prompt 修改 0、密钥泄漏 0、二进制入 Git 0。
Gate D 尚未实现，founder 与监理独立终审未发生，Gate E 不得签发。

唯一下一动作：监理复核两次 `ProviderRequestFailure` 的证据与调用纪律，并决定是否暂停等待
provider 恢复或另行签发更明确的服务诊断/重跑指令；执行侧不再自动尝试。
