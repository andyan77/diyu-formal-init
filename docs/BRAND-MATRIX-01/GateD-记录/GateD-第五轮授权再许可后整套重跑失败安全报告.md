# BRAND-MATRIX-01 · Gate D 第五轮授权再许可后整套重跑失败安全报告

状态：**`GATE-D FAILED_SAFE · NEGATED_ALTERNATIVE_PERFORMANCE_TERM_REJECTED`**。

本报告是执行侧脱敏证据，不是监理独立复验或 founder 逐篇终审。第五轮授权再许可与编排
隔离已进入正式导入及消费链，上一轮的授权阻断已经关闭；新候选完整套件在第 8 张卡
`S05-R01-P1` 收到唯一一次模型响应后，被商品具体性机器守卫失败关闭。依据
`UNLOCK-D-RERUN-05`，执行侧已停止，不开启第六轮修复、不补跑失败卡、不拼接旧候选成品。

## 1. 十项完成门

1. V2 projection 的 React/API 创建、确认、读取和任务消费纵向：**PASS**。
2. 10 逻辑根账号、20 carrier、30 矩阵账号行、40 平台/形式目标及旧 9 账号归档：
   **PASS**。
3. 31 条资料去向及真实组织任务消费：**PASS**；`RK-EC-08` 新任务消费为 0。
4. J、authorization、qualification 与反馈观察正式消费者：**PASS（机制与确定性消费者）**；
   两条人物原句授权已按 `AMD-AUTH-20260809-01` 升级为可重复版本。
5. 26 份技术母版、checksum 及十项门裁决：**PASS**。
6. P5 媒体前置：**PASS**。6 份 PASS 母版绑定 4 个正式商品；`S01-P5` 已在本候选落版。
7. 八剧本 8/8 + 八异常 8/8：**FAIL**。7 张卡成功，第 8 张失败安全，后 7 张未运行；
   scenario 级最终断言未到达。
8. provider 账本、预算与唯一 SHA：**PASS（失败证据口径）**。历史 21 次、本候选 8 次，
   累计 `29/80`；temperature `0`、max_retries `0`、transport retry `0`、失败后请求 `0`。
9. 全量工程门、显式 Chrome 与 CI：**PASS**。本地 `1041 passed / 2 skipped`；CI run
   `31306058996` 四查全绿。
10. 生产接触、密钥泄漏、二进制入 Git：**PASS**，均为 0。

第 7 门未达成，Gate D 不得报 `IMPLEMENTED`。

## 2. 第五轮授权再许可与编排隔离

- `PS-S02-05`、`PS-S04-03` 的旧 `v1`、`single_use=true` 记录与 digest 保留；新 `v2`
  以 append-only supersede 方式登记为 `single_use=false`，正式 qualification 只引用 v2。
- 修订单：`授权修订单-AMD-AUTH-20260809-01.md`；修订单 digest
  `e5c3ae916a1d3663c0a7df0a40a9b24094044417236d57c1550cec4d66d00291`。
- `PS-S02-05`：v1 digest `6400927f6262a1e1cb0c7d5f9b6da7af5450e2105066495f52bd8731acd332b4`
  → v2 digest `4060c76d3faeedd89ce919d31f00fe49633a59bc3458dce3b53d985a82941ae6`。
- `PS-S04-03`：v1 digest `247a8ae5db07cd34c410ebd18f1fda1c1bad4d94b9ff7ad2248db92c90fc5c1e`
  → v2 digest `d0b99d2f07ac48e51eff3309be777b0b05cddc7a22f6c910000c163ddb194900`。
- `ANOM-07` 改由 `DEMO-TEST-QUOTE-S02-01` 与 `DEMO-TEST-QUOTE-S04-01` 两条合成
  single-use fixture 承重；两者各自证明一次成功、重复拒绝与失败释放。
- 正式前置确定性测试对两条 PS 业务授权产生的 reservation/event 均为 0；正式业务行不再
  被测试预先核销。编排隔离断言位于 `scripts/gated/assert_rehearsal_semantics.py`、
  `scripts/gated/assert_gated_semantics.py` 与相应仓储回归测试。

双向回归锚点：

- `tests/test_gatec_postgres.py::test_repeatable_authorization_allows_independent_lineages_without_consumption`
- `tests/test_gatec_postgres.py::test_single_use_authorization_follows_lineage_and_release_contract`
- `tests/test_gated_d0.py::test_relicensed_persona_quotes_can_complete_repeated_formal_cards`
- `tests/test_gated_d0.py::test_importer_versions_business_authorizations_and_isolates_demo_single_use_fixtures`

正式实证中，前置夹具核销完成后 7 张卡均正常创建并落版，说明上一轮
`SINGLE_USE_AUTHORIZATION_PRECONSUMED` 阻断已关闭。本轮失败与授权状态机无关。

## 3. 新共享根因与失败安全

失败卡 `S05-R01-P1` 的用户输入是：家庭考虑 `DIYU-CSPU-008` 时，给出适用条件清楚、保留
取舍的穿衣建议。模型响应中出现的边界句为：

> 如果你需要的是防风防水的功能外套……那它就不是那个答案。

这句话没有声称 `DIYU-CSPU-008` 防水，语义上是在明确排除该能力。但机器守卫只识别到词语
`防水`，返回 `guaranteed_performance_assertion:防水`，并以“Writer 新增了未确认商品具体信息”
拒绝落版。只读诊断通过三项证据交叉成立：私有原始响应、隔离库失败 run 的 failure_reason、
冻结守卫函数对该响应的确定性检测结果。

这是新的共享边界根因：机器没有区分“声称本商品具有防水能力”和“明确说明本商品不是防水
外套”。执行侧没有修改守卫、Prompt、代码或数据，也没有再次调用模型。响应中其他创作表达
是否适合发布仍留给 founder 逐篇审阅，本报告只认定实际触发原子，不代替内容终审。

## 4. D0、导入、授权与媒体

- D0：React/API 预览、服务端派生治理字段、候选保存、管理员确认及新任务冻结 V2 item 成立；
  客户端越权治理字段拒绝。
- 新 import batch digest：
  `20e1d00aa527d31312748ed84a22119d28784776ed3d2c40824b3775d8bdd6ed`；两轮一致。
- 新对象指纹：
  `1ec150e8f992e4d8f2439e7a791f744c5d3ee7bb7c69f25d735a6999bfbb2f98`；两轮一致。
- 账号/载体/目标回读 `10/20/30/40`；6 个合同组织、31 条区域/门店资料、34 个 V2 item、
  4 个 J、6 个 authorization（2 个旧业务 v1、2 个可重复业务 v2、2 个 DEMO-TEST）、
  30 个 qualification。
- 媒体 PASS(scope)/FAIL/QUARANTINED=`26/0/0`，作用域
  `internal_demo_and_demo_tenant_operation`；原片 P5 资格 0、母版 P5 资格 6、覆盖 4 个商品。
  26 个母版不等于 26 个商品绑定。
- media manifest：解锁前 `ab81e01fba2a83880c6d5ce38907cab849b60420a1f8fac2b181ddc34ca71a52`，
  解锁后 `587d821315d896c414b382a1f277a07e1f7290f95cb8e0d829334cc53efc335b`；
  本轮隔离库媒体回读 digest：`2c4200e73df5e54b1f633febf412df4a13724d5d5dbe333253867b29ef1d8d09`。

## 5. 候选、工程门与 CI

候选链：

1. `997e6b55c1c40dacd44a46ff6617b28766011958`：请求 1—6；
2. `f7e8e81c80ebc8552794f82aab81ef509e242b14`：请求 7；
3. `ba4208a6ea96775683ecd89f41b6cd869b45eead`：请求 8；
4. `596b87e7e9d0551c6b62834137e03eed2bf52c82`：请求 9—10；
5. `7e48f7a7d96d4a196a8cbc8e503efe55f36291f9`：请求 11—21；
6. `e0dba46689397f16a967efbc126621df0683f385`：本轮唯一 runtime candidate，请求 22—29。

冻结登记：

- registration digest：`61ac1c23d7f9288b1f7355b196423c48a9698e472d45d01d798149150897d56f`；
- Gate A manifest：`14fed12141dc3b277c09c878a2a30ef71b445ce8ea31457c0122b403aeb48a06`；
- formal suite contract SHA-256：`65e1948353b43eddd4a7d1b741348eccb8d5a697fa1537fa1919c824b4aa6b5c`；
- publication projection digest：`cb6b2cf509c31e9864ea632449e41ff06d553e7f2ed93cf758fce7c77e978962`；
- 隔离数据库输入指纹：`b30c3aaa116888f93f9b4a7b67f29cdb3d21c5524bae210577f3e163054cd4cf`；
- 模型 `deepseek-v4-flash`，temperature `0`，max_retries `0`。

本地全绿：Ruff、mypy、Golden、EXE-V0、EXE-01、前端 lint/typecheck/test/build、显式 Chrome、
两套 secrets、Gate D scope/semantics/privacy、`scripts/test.sh`、`git diff --check`；pytest
观察值为 `1041 passed / 2 skipped`。

CI run `31306058996`：event=`workflow_dispatch`；headSha=
`e0dba46689397f16a967efbc126621df0683f385`；conclusion=`success`；非成功步骤=0，且与触发时远端
分支 HEAD 精确一致。CI 只承重其实际运行的工程回归门；Gate D 专属断言由本地退出码承重。

## 6. Provider ledger 与私有证据

- 本轮请求 22—28 对应 `S01-P1/P2/P5`、`S02-R01-P4`、`S03-S01-P4`、`S04-S04-P2`、
  `S05-H01-P1`，均完成卡级持久化。
- 请求 29 对应 `S05-R01-P1`，收到一次响应后由本地边界拒绝；task/run/version=`1/1/0`。
- 后 7 张卡未运行；累计 `29/80`，本轮 8，transport retry 0，择优/补跑 0，失败后请求 0。
- 私有证据：`~/diyu-evidence-brand-matrix-gated-e0dba46689397f16a967efbc126621df0683f385/`；
  目录 0700、文件 0600，16 个文件进入 `SHA256SUMS`；该文件 digest 为
  `22e5c4beb67eefa270574844a4e385c5787d36ba0667c72bf6a513a5412afda1`。
- Git 中 raw response、完整 artifact、完整任务快照、密钥均为 0。

## 7. 八剧本与八异常

剧本：

1. 总部 F/J/G：三卡完成，`CARD_SET_COMPLETE_FINAL_ASSERTION_NOT_REACHED`。
2. 华东资料：卡完成，`CARD_SET_COMPLETE_FINAL_ASSERTION_NOT_REACHED`。
3. 杭州资料：卡完成，`CARD_SET_COMPLETE_FINAL_ASSERTION_NOT_REACHED`。
4. 成都错误普通文件：卡完成，`CARD_SET_COMPLETE_FINAL_ASSERTION_NOT_REACHED`。
5. 同一 SKU 四节点：`FAILED_SAFE`；H01 完成，R01 响应被守卫拒绝，S01/S04 未运行。
6. 同一种子三账号：`NOT_RUN_SUITE_ABORTED`。
7. AMD v1/v2：`NOT_RUN_SUITE_ABORTED`。
8. 反馈观察：`NOT_RUN_SUITE_ABORTED`。

异常：

1. 过期成分口径版本对：`INCOMPLETE_SUITE_ABORTED`。
2. 门店错误成分文件：`PASS_ZERO_PROVIDER`。
3. 同字段正式事实冲突：`PASS_ZERO_PROVIDER`。
4. 过期区域活动：`PASS_ZERO_PROVIDER`。
5. 跨门店读取：`PASS_ZERO_PROVIDER`。
6. 两名用户操作同一逻辑账号：`PASS_ZERO_PROVIDER`。
7. 专用合成单次授权：确定性机制 PASS，套件内只读复核 `NOT_RUN_SUITE_ABORTED`。
8. 知识更新前后两版任务：`INCOMPLETE_SUITE_ABORTED`。

## 8. 四层口径与诚实边界

- **已存储**：两轮隔离导入完整；10 根账号、20 carrier、31 条资料、4 商品、4 J、2 系列、
  6 授权、30 资格、26 技术母版元数据可回读。本候选正式卡 task/run/version=`8/8/7`。
- **已进入 projection**：34 个 V2 item，其中 28 个区域/门店条目；过期 `RK-EC-08` 被阻断。
- **已被任务快照引用**：D0/组织消费证据成立；本候选 7 个完成版本均冻结正式输入与 Writer
  审计字段；失败卡没有版本快照。
- **已进入最终成品**：本候选 7 张；第 5 剧本未完成、后 7 卡未运行、最终剧本断言未执行，
  不能与旧候选成品拼接，也不能据此称八剧本通过。

代码候选提交 `e0dba46689397f16a967efbc126621df0683f385`；候选后的冻结输入提交
`291621f` 与本失败收口只改 Gate D 证据、治理日志和 `MILESTONE.md`。首次 provider 请求后
`src/`、`frontend/`、`tests/`、`scripts/`、Prompt、数据/媒体 manifest 差异为 0。

本轮生产/SSH/ECS 0、alembic 修改 0、`frontend/src/**` 修改 0、二进制入 Git 0。密钥仅由
精确三键解析器注入，不回显、不落盘。Gate D 尚未实现，founder 与监理独立终审未发生，
Gate E 不得签发。

唯一下一动作：监理复核第五轮授权再许可、编排隔离、否定性边界词误拦诊断、冻结纪律与累计
ledger；继续须由主控另行签发，执行侧不得自行第六轮修复或 provider 重跑。
