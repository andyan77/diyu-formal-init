# BRAND-MATRIX-01 · Gate D 第四轮守卫修复后整套重跑失败安全报告

状态：**`GATE-D FAILED_SAFE · SINGLE_USE_AUTHORIZATION_PRECONSUMED`**。

本报告是执行侧脱敏证据，不是监理独立复验或 founder 逐篇终审。第四轮绝对化守卫收窄已
进入正式运行链并通过了此前误拦的卡；新候选完整套件在 `S06-S02-P3` 的上下文选择阶段发现
单次人物授权已被同一隔离栈的前置确定性证明核销，因而在创建任务和请求 provider 之前失败
关闭。依据 `UNLOCK-D-RERUN-04`，执行侧已停止，不开启第五轮修复、不补跑单卡、不拼接旧候选。

## 1. 十项完成门

1. V2 projection 的 React/API 创建、确认、读取和任务消费纵向：**PASS**。
2. 10 逻辑根账号、20 carrier、30 矩阵账号行、40 平台/形式目标及旧 9 账号归档：
   **PASS**。
3. 31 条资料去向及真实组织任务消费：**PASS**；`RK-EC-08` 新任务消费为 0。
4. J、authorization、qualification 与反馈观察正式消费者：**PASS（机制与确定性消费者）**；
   本次正式套件暴露了确定性核销证明与随后成品套件共用单次授权状态的编排冲突。
5. 26 份技术母版、checksum 及十项门裁决：**PASS**。
6. P5 媒体前置：**PASS**。6 份 PASS 母版绑定 4 个正式商品；`S01-P5` 已在本候选落版。
7. 八剧本 8/8 + 八异常 8/8：**FAIL**。11 张卡成功，`S06-S02-P3` 失败安全，后 3 张卡
   未运行；scenario 级最终断言未到达。
8. provider 账本、预算与唯一 SHA：**PASS（失败证据口径）**。历史 10 次、本候选 11 次，
   累计 `21/80`；temperature `0`、max_retries `0`、transport retry `0`、失败后请求 `0`。
9. 全量工程门、显式 Chrome 与 CI：**PASS**。本地 `1037 passed / 2 skipped`；CI run
   `31303644503` 四查全绿。
10. 生产接触、密钥泄漏、二进制入 Git：**PASS**，均为 0。

第 7 门未达成，Gate D 不得报 `IMPLEMENTED`。

## 2. Rerun 04 守卫收窄实证

修复前，`absolute_claim` 把 `最`、`第一` 等单字或歧义词作为机器硬门，导致
“整套搭配里最好不要再出现第二个强色”被误拦。修复后：

- 机器只保留 `100%`、`永不/绝不`与保证类性能硬断言的精确路径；
- `最`、`第一` 不再由正则机器判定；
- Writer 合同明文禁止“最舒适／业内第一／全网最好”等商品品质超级断言；
- “最好不要／最好先／第一眼”等日常建议或观察表达正常使用。

双向回归锚点：

- `tests/test_deepseek_adapter.py::test_publication_v3_allows_ambiguous_daily_suggestion_words`
- `tests/test_deepseek_adapter.py::test_publication_v3_allows_prior_s01_p2_absolute_claim_false_positive`
- `tests/test_deepseek_adapter.py::test_publication_v3_rejects_changed_or_unconfirmed_product_specifics`
- `tests/fixtures/gated_s01_p2_absolute_claim_false_positive_v1.json`

正式实证：上一候选失败的 `S01-P2` 在本候选成功落版；`S01-P1/P2/P5` 三卡全部完成，说明
旧 `absolute_claim:最好` 误拦已经从真实运行链消失。未确认成分、价格、精确工艺、年龄、
保证类性能和精确绝对化表述的机器硬门未放松。

## 3. 新共享根因与失败安全

失败卡为 `S06-S02-P3`。其私有失败 bundle 记录 `responses=[]`，隔离库中也没有对应
task/run/version，因此本卡 provider request=`0`。执行侧只读交叉核验发现：

- `PS-S02-05` 对应 authorization
  `0559324c-860b-5cb0-ab33-b637d1bd6972` 为 single-use；
- 重建隔离栈后执行的正式确定性消费者证明，先完成了“失败释放→成功核销”流程；
- reservation 已由证明任务 `7920f010-3e91-4614-9b7c-b7ea04732029` 置为 `consumed`；
- `S06-S02-P3` 选择 S02 资格时，仓储按 fail-closed 规则拒绝已核销授权，未进入 Writer。

失败脚本只在 `suite-failure.json` 保存了 `DomainError` 类型，没有保存异常原文；因此上述
具体错误按“失败 bundle 无响应 + reservation/event 数据库回读 + 同一路径 fail-closed 代码”
三方证据诊断，不伪造未被捕获的异常文本。

这是套件编排/冻结输入覆盖的新共享根因：本轮在正式模型套件前运行的确定性授权消费者已经
消耗单次授权，而 runtime freeze 的输入指纹登记了 authorization 本体、未登记 reservation
核销状态，readiness 没有提前发现授权不可用。授权状态机本身正确失败关闭；问题是同一隔离
栈内证明顺序让正式卡失去了可用资格。执行侧未改脚本、仓储、Prompt 或数据，也未重跑。

## 4. D0、导入与媒体

- D0：React/API 预览、服务端派生治理字段、候选保存、管理员确认及新任务冻结 V2 item 成立；
  客户端越权治理字段拒绝。
- 两轮 import batch digest：
  `f15d0efe63173b1b6c72b5b4cf4681673cf29e4536fe600e3d92066e52781750`。
- 两轮对象指纹：
  `e48dc6542db65593bb3830eda9cebad425d54b756d34a1ce469b88931eef6b88`；两轮逐字节一致。
- 账号/载体/目标回读 `10/20/30/40`；6 个合同组织、31 条区域/门店资料、34 个 V2 item、
  4 个 J、2 个授权、30 个 qualification。
- 媒体 PASS(scope)/FAIL/QUARANTINED=`26/0/0`，作用域
  `internal_demo_and_demo_tenant_operation`；原片 P5 资格 0、母版 P5 资格 6、覆盖 4 个商品。
  26 个母版不等于 26 个商品绑定。
- media manifest：解锁前 `ab81e01fba2a83880c6d5ce38907cab849b60420a1f8fac2b181ddc34ca71a52`，
  解锁后 `587d821315d896c414b382a1f277a07e1f7290f95cb8e0d829334cc53efc335b`；
  本轮隔离库媒体回读 digest：`602c6d47151b40535d6f08195f41c7c5f07856a9aad4b20276bc19ec1fc26cd3`。

## 5. 候选、工程门与 CI

候选链：

1. `997e6b55c1c40dacd44a46ff6617b28766011958`：请求 1—6；
2. `f7e8e81c80ebc8552794f82aab81ef509e242b14`：请求 7；
3. `ba4208a6ea96775683ecd89f41b6cd869b45eead`：请求 8；
4. `596b87e7e9d0551c6b62834137e03eed2bf52c82`：请求 9—10；
5. `7e48f7a7d96d4a196a8cbc8e503efe55f36291f9`：本轮唯一 runtime candidate，请求 11—21。

冻结登记：

- registration digest：`3a5bdec4ba6c3bbf464150080da1bdc8715c8085e85780383f196738bc3cec83`；
- Gate A manifest：`14fed12141dc3b277c09c878a2a30ef71b445ce8ea31457c0122b403aeb48a06`；
- formal suite contract SHA-256：`cebf27debec5192159636d92cbf2c4338cd607f72f1c923c443b3f819cdf640e`；
- publication projection digest：`cb6b2cf509c31e9864ea632449e41ff06d553e7f2ed93cf758fce7c77e978962`；
- 隔离数据库输入指纹：`94e4ebfdf252de272c1a994074cda464f16aec145c62215cbcb97f7b14ec6c93`；
- 模型 `deepseek-v4-flash`，temperature `0`，max_retries `0`。

本地全绿：Ruff、mypy、Golden、EXE-V0、EXE-01、前端 lint/typecheck/test/build、显式 Chrome、
两套 secrets、Gate D scope/semantics/privacy、`scripts/test.sh`、`git diff --check`；pytest
观察值为 `1037 passed / 2 skipped`。

CI run `31303644503`：event=`workflow_dispatch`；headSha=
`7e48f7a7d96d4a196a8cbc8e503efe55f36291f9`；conclusion=`success`；非成功步骤=0，且与当时远端
分支 HEAD 精确一致。CI 只承重其实际运行的工程回归门；Gate D 专属断言由本地退出码承重。

## 6. Provider ledger 与私有证据

- 本轮请求 11—21 对应：`S01-P1/P2/P5`、`S02-R01-P4`、`S03-S01-P4`、`S04-S04-P2`、
  `S05-H01/R01/S01/S04-P1`、`S06-H01-P3`，均完成卡级持久化。
- `S06-S02-P3` 在 provider 前失败，未增加请求；`S06-S04-P3`、`S07-H01-P3`、
  `S08-S01-P4` 未运行。
- 累计 `21/80`；本轮 11；transport retry 0；择优/补跑 0；失败后请求 0。
- 私有证据：`~/diyu-evidence-brand-matrix-gated-7e48f7a7d96d4a196a8cbc8e503efe55f36291f9/`；
  目录 0700、文件 0600，24 个文件进入 `SHA256SUMS`；其 digest 为
  `c70f899e940a42ce97dece01df2a633d9e4f4e9c8112d6d82a6ddba823f7a399`。
- Git 中 raw response、完整 artifact、完整任务快照、密钥均为 0。

## 7. 八剧本与八异常

剧本：

1. 总部 F/J/G：三卡完成，`CARD_SET_COMPLETE_FINAL_ASSERTION_NOT_REACHED`。
2. 华东资料：卡完成，`CARD_SET_COMPLETE_FINAL_ASSERTION_NOT_REACHED`。
3. 杭州资料：卡完成，`CARD_SET_COMPLETE_FINAL_ASSERTION_NOT_REACHED`。
4. 成都错误普通文件：卡完成，`CARD_SET_COMPLETE_FINAL_ASSERTION_NOT_REACHED`。
5. 同一 SKU 四节点：四卡完成且成品 digest 四不相同，最终跨卡断言未到达。
6. 同一种子三账号：`FAILED_SAFE`；H01 完成，S02 授权预先核销，S04 未运行。
7. AMD v1/v2：`NOT_RUN_SUITE_ABORTED`。
8. 反馈观察：`NOT_RUN_SUITE_ABORTED`。

异常：

1. 过期成分口径版本对：`INCOMPLETE_SUITE_ABORTED`。
2. 门店错误成分文件：`PASS_ZERO_PROVIDER`。
3. 同字段正式事实冲突：`PASS_ZERO_PROVIDER`。
4. 过期区域活动：`PASS_ZERO_PROVIDER`。
5. 跨门店读取：`PASS_ZERO_PROVIDER`。
6. 两名用户操作同一逻辑账号：`PASS_ZERO_PROVIDER`。
7. 私人经历单次授权：`NOT_RUN_SUITE_ABORTED`。
8. 知识更新前后两版任务：`INCOMPLETE_SUITE_ABORTED`。

## 8. 四层口径与诚实边界

- **已存储**：两轮隔离导入完整；10 根账号、20 carrier、31 条资料、4 商品、4 J、2 系列、
  2 授权、30 资格、26 技术母版元数据可回读。本候选正式卡 task/run/version=`11/11/11`；
  失败卡为 `0/0/0`。
- **已进入 projection**：34 个 V2 item，其中 28 个区域/门店条目；过期 `RK-EC-08` 被阻断。
- **已被任务快照引用**：D0/组织消费证据成立；本候选 11 个完成版本均冻结正式输入与
  Writer 审计字段。
- **已进入最终成品**：本候选 11 张；但第 6 剧本未完成、后 3 卡未运行、最终剧本断言未执行，
  不能与旧候选成品拼接，也不能据此称八剧本通过。

代码候选提交 `7e48f7a7d96d4a196a8cbc8e503efe55f36291f9`；候选后的冻结输入提交
`68736c9` 与本失败收口只改 Gate D 证据、治理日志和 `MILESTONE.md`。首次 provider 请求后
`src/`、`frontend/`、`tests/`、`scripts/`、Prompt、数据/媒体 manifest 差异为 0。

本轮生产/SSH/ECS 0、alembic 修改 0、`frontend/src/**` 修改 0、二进制入 Git 0。密钥仅由
精确三键解析器注入，不回显、不落盘。Gate D 尚未实现，founder 与监理独立终审未发生，
Gate E 不得签发。

唯一下一动作：监理复核守卫收窄正式实证、授权预先核销的编排诊断、冻结纪律与累计 ledger；
如需继续，必须由主控另行签发，执行侧不得自行第五轮修复或 provider 重跑。
