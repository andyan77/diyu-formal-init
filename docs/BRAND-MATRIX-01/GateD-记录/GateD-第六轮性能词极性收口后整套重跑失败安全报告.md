# BRAND-MATRIX-01 · Gate D 第六轮性能词极性收口后整套重跑失败安全报告

状态：**`GATE-D FAILED_SAFE · PROVIDER_REQUEST_FAILURE`**。

本报告是执行侧脱敏证据，不是监理独立复验或 founder 逐篇终审。第六轮性能词极性收口、
非阻断复核标注和全部确定性工程门已经通过；唯一运行候选的完整套件在第 13 张卡
`S06-S04-P3` 发起唯一一次 provider 请求时失败，未取得可接受响应。temperature 为 `0`、
max_retries 为 `0`，执行侧没有重试、补跑或改动冻结实现。依据 `UNLOCK-D-RERUN-06`，本轮
立即失败安全收口，不自行开启第七轮。

## 1. 十项完成门

1. V2 projection 的 React/API 创建、确认、读取和任务消费纵向：**PASS**。
2. 10 逻辑根账号、20 carrier、30 矩阵账号行、40 平台/形式目标及旧 9 账号归档：
   **PASS**。
3. 31 条资料去向及真实组织任务消费：**PASS**；`RK-EC-08` 新任务消费为 0。
4. J、authorization、qualification 与反馈观察正式消费者：**PASS（机制与确定性消费者）**；
   两条人物原句授权保持 `AMD-AUTH-20260809-01` 可重复版本。
5. 26 份技术母版、checksum 及十项门裁决：**PASS**。
6. P5 媒体前置：**PASS**。6 份 PASS 母版绑定 4 个正式商品；`S01-P5` 已在本候选落版。
7. 八剧本 8/8 + 八异常 8/8：**FAIL**。12 张卡落版，第 13 张 provider 请求失败，后 2 张
   未运行；scenario 级最终断言未到达。
8. provider 账本、预算与唯一 SHA：**PASS（失败证据口径）**。历史 29 次、本候选 13 次
   请求尝试（12 次取得响应、1 次失败），累计 `42/80`；transport retry `0`、失败后请求 `0`。
9. 全量工程门、显式 Chrome 与 CI：**PASS**。本地 `1047 passed / 2 skipped`；CI run
   `31307989195` 四查全绿。
10. 生产接触、密钥泄漏、二进制入 Git：**PASS**，均为 0。

第 7 门未达成，Gate D 不得报 `IMPLEMENTED`。

## 2. 性能词极性收口与双向回归

修复前，性能词只要在文案中出现，就可能被机器误判成商品性能主张。修复后：

- 裸性能词不再阻断；机器只硬拦 `保证/100%/永不/绝不/绝对 + 性能词` 的明确肯定组合；
- 未确认性能可用否定式、边界式语言说明，不能写成肯定卖点；
- 裸性能词进入非阻断复核标注，自动记录卡 ID、命中词和完整所在句，不改变二元判定；
- 成分比例、价格、精确工艺、年龄段、改值、画像照抄等既有硬边界均未放松。

双向回归锚点：

- `tests/test_deepseek_adapter.py::test_publication_v3_allows_prior_s05_r01_negated_performance_boundary`
- `tests/test_deepseek_adapter.py::test_bare_performance_terms_are_non_blocking_review_annotations`
- `tests/test_deepseek_adapter.py::test_negated_guarantee_phrases_do_not_become_affirmative_machine_claims`
- `tests/test_deepseek_adapter.py::test_publication_v3_rejects_changed_or_unconfirmed_product_specifics`
- `tests/test_gated_d0.py::test_gate_d_review_package_records_bare_performance_terms_without_blocking`
- 失败快照夹具：`tests/fixtures/gated_s05_r01_p1_negated_performance_v1.json`

本轮实际 12 份成品共登记 4 条非阻断标注：`S01-P2` 的“耐穿”“好打理”，以及
`S05-H01-P1`、`S05-S04-P1` 的“百搭”。例如：

> 至于它耐不耐穿、好不好打理，这些我没有确切依据，不会给你保证。

这条只进入 founder 审阅清单，没有触发拒稿，证明标注通道与机器阻断已经分离。

## 3. 本轮失败与停止线

- 失败卡：`S06-S04-P3`，同一种子三账号剧本中的 S04 卡。
- 阶段：provider request；task/run/version=`1/1/0`。
- 请求尝试：1；transport retry：0；没有取得可供落版的响应，私有失败包的 response 列表为空。
- 失败类型：`ProviderRequestFailure`。失败安全记录没有保存足以进一步区分 HTTP 拒绝、服务暂时
  不可用或传输失败的内部类别，因此本报告不臆测原因。
- 已完成的前 12 张卡保留为本候选失败证据，但不得与旧候选或未来候选拼接成 8/8 结果。
- 失败后 provider 请求 0，代码、Prompt、数据、媒体和冻结合同修改 0。

这不是新的内容守卫误拦证据，也没有证明模型内容违规；它是一次正式 provider 请求未完成。
按照一次响应、禁重试和不得自行第七轮的纪律，执行侧只能停止并如实报告。

## 4. D0、导入、授权与媒体

- D0：React/API 预览、服务端派生治理字段、候选保存、管理员确认及新任务冻结 V2 item 成立；
  客户端越权治理字段拒绝。
- import batch digest：
  `20e1d00aa527d31312748ed84a22119d28784776ed3d2c40824b3775d8bdd6ed`；两轮一致。
- 对象指纹：
  `1ec150e8f992e4d8f2439e7a791f744c5d3ee7bb7c69f25d735a6999bfbb2f98`；两轮一致。
- 账号/载体/目标回读 `10/20/30/40`；6 个合同组织、31 条区域/门店资料、34 个 V2 item、
  4 个 J、6 个 authorization、30 个 qualification。
- 媒体 PASS(scope)/FAIL/QUARANTINED=`26/0/0`，作用域
  `internal_demo_and_demo_tenant_operation`；原片 P5 资格 0、母版 P5 资格 6、覆盖 4 个商品。
  26 个母版不等于 26 个商品绑定。
- media manifest：解锁前 `ab81e01fba2a83880c6d5ce38907cab849b60420a1f8fac2b181ddc34ca71a52`，
  解锁后及本轮 `587d821315d896c414b382a1f277a07e1f7290f95cb8e0d829334cc53efc335b`；
  本轮隔离库媒体回读 digest：`96295c2df507c6063ed098e2d9dad1b3b8afb33f698163ed81b9e4dc835b6b65`。

## 5. 候选、工程门与 CI

候选链：

1. `997e6b55c1c40dacd44a46ff6617b28766011958`：请求 1—6；
2. `f7e8e81c80ebc8552794f82aab81ef509e242b14`：请求 7；
3. `ba4208a6ea96775683ecd89f41b6cd869b45eead`：请求 8；
4. `596b87e7e9d0551c6b62834137e03eed2bf52c82`：请求 9—10；
5. `7e48f7a7d96d4a196a8cbc8e503efe55f36291f9`：请求 11—21；
6. `e0dba46689397f16a967efbc126621df0683f385`：请求 22—29；
7. `3399dc4cd58e0235a06cb469fe6dfe1ea2cdcc5b`：本轮唯一 runtime candidate，请求 30—42。

冻结登记：

- registration digest：`56a474986fa7eb7d32333f6244e7e0cc2304a483460cdda8bcbfb9da053e3449`；
- Gate A manifest：`14fed12141dc3b277c09c878a2a30ef71b445ce8ea31457c0122b403aeb48a06`；
- formal suite contract SHA-256：`d99e2224dc77fd8e05c24a2740820e5e7da47579ce74998cf02b58c359b546b3`；
- publication projection digest：`cb6b2cf509c31e9864ea632449e41ff06d553e7f2ed93cf758fce7c77e978962`；
- 隔离数据库输入指纹：`b2f61f7662421feafbf73695b9923e5ec551f5221b06169b90a804b2ebab6dcd`；
- 模型 `deepseek-v4-flash`，temperature `0`，max_retries `0`。

本地全绿：Ruff、mypy、Golden、EXE-V0、EXE-01、前端 lint/typecheck/test/build、显式 Chrome、
两套 secrets、Gate D scope/semantics/privacy、`scripts/test.sh`、`git diff --check`；pytest
观察值为 `1047 passed / 2 skipped`。

CI run `31307989195`：event=`workflow_dispatch`；headSha=
`3399dc4cd58e0235a06cb469fe6dfe1ea2cdcc5b`；conclusion=`success`；非成功步骤=0，且与触发时
远端分支 HEAD 精确一致。CI 只承重其实际运行的工程回归门；Gate D 专属断言由本地退出码承重。

## 6. Provider ledger 与私有证据

- 请求 30—41 各取得一份响应并形成 12 个完成版本；由于整套最终断言未到达，只记
  `CARD_COMPLETE_FINAL_ASSERTION_NOT_REACHED`，不冒充 scenario PASS。
- 请求 42 对应 `S06-S04-P3`，task/run/version=`1/1/0`，失败类型
  `ProviderRequestFailure`；没有可接受 response digest，失败后请求 0。
- 本轮 13 次请求尝试，12 次取得响应、1 次失败；累计 `42/80`，transport retry 0，
  择优/补跑/跨候选拼接均为 0。
- 私有证据：`~/diyu-evidence-brand-matrix-gated-3399dc4cd58e0235a06cb469fe6dfe1ea2cdcc5b/`；
  目录 0700、文件 0600，26 个证据文件进入 `SHA256SUMS`；该文件 digest 为
  `8a030cd535f039ce3fa1efa2d1fd07204fbf2c3d3eba500eeb969775390b69c5`。
- Git 中 raw response、完整 artifact、完整任务快照、密钥均为 0。

## 7. 八剧本与八异常

剧本：

1. 总部 F/J/G：三卡完成，`CARD_SET_COMPLETE_FINAL_ASSERTION_NOT_REACHED`。
2. 华东资料：卡完成，`CARD_SET_COMPLETE_FINAL_ASSERTION_NOT_REACHED`。
3. 杭州资料：卡完成，`CARD_SET_COMPLETE_FINAL_ASSERTION_NOT_REACHED`。
4. 成都错误普通文件：卡完成，`CARD_SET_COMPLETE_FINAL_ASSERTION_NOT_REACHED`。
5. 同一 SKU 四节点：四卡完成，`CARD_SET_COMPLETE_FINAL_ASSERTION_NOT_REACHED`。
6. 同一种子三账号：H01、S02 完成；S04 provider 请求失败，`FAILED_SAFE`。
7. AMD v1/v2：`NOT_RUN_SUITE_ABORTED`。
8. 反馈观察：`NOT_RUN_SUITE_ABORTED`。

异常：

1. 过期成分口径版本对：`INCOMPLETE_SUITE_ABORTED`。
2. 门店错误成分文件：`PASS_ZERO_PROVIDER`。
3. 同字段正式事实冲突：`PASS_ZERO_PROVIDER`。
4. 过期区域活动：`PASS_ZERO_PROVIDER`。
5. 跨门店读取：`PASS_ZERO_PROVIDER`。
6. 两名用户操作同一逻辑账号：`PASS_ZERO_PROVIDER`。
7. 专用合成单次授权：确定性机制 PASS，套件内最终只读复核 `NOT_RUN_SUITE_ABORTED`。
8. 知识更新前后两版任务：`INCOMPLETE_SUITE_ABORTED`。

## 8. 四层口径与诚实边界

- **已存储**：两轮隔离导入完整；10 根账号、20 carrier、31 条资料、4 商品、4 J、2 系列、
  6 授权、30 资格、26 技术母版元数据可回读。本候选正式卡 task/run/version=`13/13/12`。
- **已进入 projection**：34 个 V2 item，其中 28 个区域/门店条目；过期 `RK-EC-08` 被阻断。
- **已被任务快照引用**：D0/组织消费证据成立；本候选 12 个完成版本均冻结正式输入与 Writer
  审计字段；失败卡没有版本快照。
- **已进入最终成品**：本候选 12 张卡级成品；第 6 剧本未完成，后 2 卡未运行，最终剧本断言
  未执行。这 12 张不得与旧候选或未来候选拼接，也不能据此称八剧本通过。

代码候选提交 `3399dc4cd58e0235a06cb469fe6dfe1ea2cdcc5b`；候选后的冻结输入提交 `925436b` 与
本失败收口只改 Gate D 证据、治理日志和 `MILESTONE.md`。首次 provider 请求后 `src/`、
`frontend/`、`tests/`、`scripts/`、Prompt、数据/媒体 manifest 差异为 0。

本轮生产/SSH/ECS 0、alembic 修改 0、`frontend/src/**` 修改 0、二进制入 Git 0。密钥仅由
精确三键解析器注入，不回显、不落盘。Gate D 尚未实现，founder 与监理独立终审未发生，
Gate E 不得签发。

唯一下一动作：监理复核第六轮极性收口、非阻断标注、provider 失败安全、冻结纪律与累计
ledger；继续须由主控另行签发，执行侧不得自行第七轮或再次调用 provider。
