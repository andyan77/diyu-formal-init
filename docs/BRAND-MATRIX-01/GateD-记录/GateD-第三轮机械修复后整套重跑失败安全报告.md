# BRAND-MATRIX-01 · Gate D 第三轮机械修复后整套重跑失败安全报告

状态：**`GATE-D FAILED_SAFE · WRITER_ABSOLUTE_CLAIM_FALSE_POSITIVE`**。

本报告是执行侧脱敏证据，不是监理独立复验或 founder 逐篇终审。第三轮快照白名单机械收尾
已在真实运行链成功生效；完整套件在第二张卡遇到一个新的通用守卫误报后立即停止。依据
`UNLOCK-D-RERUN-03`，执行侧不得自行开启第四轮修复、补跑失败卡或拼接旧候选成品。

## 1. 十项完成门

1. V2 projection 的 React/API 创建、确认、读取和任务消费纵向：**PASS**。
2. 10 逻辑根账号、20 carrier、30 矩阵账号行、40 平台/形式目标及旧 9 账号归档：
   **PASS**。
3. 31 条资料去向及真实组织任务消费：**PASS**；`RK-EC-08` 新任务消费为 0。
4. J、authorization、qualification 与反馈观察正式消费者：**PASS**。
5. 26 份技术母版、checksum 及十项门裁决：**PASS**。
6. P5 媒体前置：**PASS**。6 份 PASS 母版绑定 4 个正式商品；本轮套件在 P5 卡前停止。
7. 八剧本 8/8 + 八异常 8/8：**FAIL**。`S01-P1` 成功，`S01-P2` 失败安全，其余
   成品卡不运行且不拼接旧候选结果。
8. provider 账本、预算与唯一 SHA：**PASS（失败证据口径）**。历史 8 次、本候选 2 次，
   累计 `10/80`；temperature `0`、max_retries `0`、transport retry `0`、失败后请求 `0`。
9. 全量工程门、显式 Chrome 与 CI：**PASS**。本地 `1033 passed / 2 skipped`；CI run
   `31302112683` 四查全绿。
10. 生产接触、密钥泄漏、二进制入 Git：**PASS**，均为 0。

第 7 门未达成，Gate D 不得报 `IMPLEMENTED`。

## 2. Rerun 03 白名单机械收尾

publication-v3 completion 精确允许集新增合法审计字段：

- `writer_confirmed_product_fact_refs`：必须是列表、元素唯一且属于任务开始前冻结的
  ProductFact ID；
- `used_persona_quote_ids`：必须是 `PS-S02-*` / `PS-S04-*` 合法条目并属于冻结发布合同；
  两个 single-use 条目还必须匹配冻结 authorization。

名单外字段、只提交其中一个字段、重复或未冻结事实 ID、非法原句 ID、单次原句缺授权仍全部
失败关闭。旧 completion 快照可继续按原精确字段集读取，不回填两字段，旧 publication digest
与 artifact digest 不改变。

双向回归锚点：

- `tests/test_gated_d0.py::test_gated_rerun03_completion_snapshot_commits_the_failed_shape`
- `tests/test_gated_d0.py::test_gated_rerun03_completion_snapshot_stays_fail_closed_and_legacy_safe`
- `tests/test_gated_d0.py::test_gated_rerun03_completion_grounding_rejects_invalid_shapes`
- `tests/test_gated_d0.py::test_gated_rerun03_single_use_quote_matches_frozen_authorization`
- `tests/fixtures/gated_rerun03_completion_snapshot_regression.json`

正式实证：本候选 `S01-P1` 已成功提交 version 1；版本审计快照同时存在两字段，冻结
ProductFact 引用 3 条、人物原句引用 0 条。这证明上一候选的白名单缺口已真实闭合，不是仅单测绿。

## 3. 新共享根因与失败安全

第二张卡 `S01-P2` 收到一次正常 provider 响应，HTTP 内容结构完整、finish reason=`stop`。
文案中的条件建议短摘录为：

> 整套搭配里最好不要再出现第二个强色

`unconfirmed_product_specificity_spans()` 的绝对化模式把日常建议副词“最好”匹配为
`absolute_claim:最好`，继而抛出“Writer 新增了未确认商品具体信息”。这里没有“全网最好”、
“同类最好”等商品最高级声明，命中对象是 L3 搭配条件，因此属于通用机器守卫误报，不是模型
改写 ProductFact、补写成分/价格/工艺，也不是快照白名单回归。

隔离库回读：

- 成功卡：task `f34874d3-e0b8-44c0-98b7-dfc2f20f3780`，run
  `8930e048-1471-4baa-8b9b-23f1fc58427d`，version
  `b11cc265-5054-48d0-9e28-d08907eff844`；
- 失败卡：task `5c71339d-0cff-4d39-a4c5-8df17a82d789`，run
  `d7df9a05-9936-4331-adb8-b34c50bc5633`，status=`failed`，version=0；
- 本候选 task/run/version=`2/2/1`，失败卡没有成品版本；失败后请求=0。

这是首次观察到的新共享根因。本轮授权只允许第三轮机械收尾，故执行侧未修改正则、Prompt、
测试或套件定义，也未再调用 provider。

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
  本轮隔离库媒体回读 digest：`d7d292be562841610a38d627594bffb23868a0a0f9fcd7efe05aa93c960b1886`。

## 5. 候选、工程门与 CI

候选链：

1. `997e6b55c1c40dacd44a46ff6617b28766011958`：请求 1—6；
2. `f7e8e81c80ebc8552794f82aab81ef509e242b14`：请求 7；
3. `ba4208a6ea96775683ecd89f41b6cd869b45eead`：请求 8；
4. `596b87e7e9d0551c6b62834137e03eed2bf52c82`：本轮唯一 runtime candidate，请求 9—10。

冻结登记：

- registration digest：`538b0ae11eb1dc7511e54d40beee7e56dd3e9d35ded7c2b06aa6bbe66bc77304`；
- Gate A manifest：`14fed12141dc3b277c09c878a2a30ef71b445ce8ea31457c0122b403aeb48a06`；
- formal suite contract SHA-256：`7d4ee66fd774d8a03d696629fbc346b398751d648a2ea25a1c65b771b3d57311`；
- publication projection digest：`cb6b2cf509c31e9864ea632449e41ff06d553e7f2ed93cf758fce7c77e978962`；
- 隔离数据库输入指纹：`ab6917b2f0db0cef78a5cdd73d9caf702b9701f03c20807648b85e50f25d4174`；
- 模型 `deepseek-v4-flash`，temperature `0`，max_retries `0`。

本地全绿：Ruff、mypy、Golden、EXE-V0、EXE-01、前端 lint/typecheck/test/build、显式 Chrome、
两套 secrets、Gate D scope/semantics/privacy、`scripts/test.sh`、`git diff --check`；pytest
观察值为 `1033 passed / 2 skipped`。

CI run `31302112683`：event=`workflow_dispatch`；headSha=`596b87e7e9d0551c6b62834137e03eed2bf52c82`；
status=`completed`，conclusion=`success`；非成功步骤=0。CI 只承重其实际运行的既有工程回归门，
Gate D 专属断言由本地退出码承重。

## 6. Provider ledger 与私有证据

- 请求 9（`S01-P1`）：request SHA-256
  `74be18ac8356c26c55fcef681cdc716aa22d8d4f2056a4109b417cc080f058d4`，response SHA-256
  `9aef5331be908b53ce5d1f556d4562f54826d31d4737c569f4f14bd503c158f3`，PASS。
- 请求 10（`S01-P2`）：request SHA-256
  `717cba563f6b8484e2aa1d3f8ec557e079761b7c5eca56de5ada6d4b74b4ade7`，response SHA-256
  `b7d660a98db2ef2c149c967bf8b1a8961aa0dced8cf3556a9c994c445406d004`，FAILED_SAFE。
- 累计 `10/80`；本轮 2；transport retry 0；择优/补跑 0；失败后请求 0。
- 私有证据：`~/diyu-evidence-brand-matrix-gated-596b87e7e9d0551c6b62834137e03eed2bf52c82/`；
  目录 0700、文件 0600，`sha256sum -c` 通过；`SHA256SUMS` digest 为
  `7272ac9a0abc845794ec46062817a5b5c577fa8d31745cac1a7a5d9f67965724`。
- Git 中 raw response、完整 artifact、完整任务快照、密钥均为 0。

## 7. 八剧本与八异常

剧本：

1. 总部 F/J/G：`FAILED_SAFE`（`S01-P1` PASS；`S01-P2` 条件建议被绝对化守卫误报）。
2. 华东资料：`NOT_RUN_SUITE_ABORTED`。
3. 杭州资料：`NOT_RUN_SUITE_ABORTED`。
4. 成都错误普通文件：`NOT_RUN_SUITE_ABORTED`；不拼接旧候选结果。
5. 同一 SKU 四节点：`NOT_RUN_SUITE_ABORTED`。
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
7. 私人经历单次授权：`NOT_RUN_SUITE_ABORTED`。
8. 知识更新前后两版任务：`INCOMPLETE_SUITE_ABORTED`。

## 8. 四层口径与诚实边界

- **已存储**：两轮隔离导入完整；10 根账号、20 carrier、31 条资料、4 商品、4 J、2 系列、
  2 授权、30 资格、26 技术母版元数据可回读。本轮正式 task/run/version=`2/2/1`。
- **已进入 projection**：34 个 V2 item，其中 28 个区域/门店条目；过期 `RK-EC-08` 被阻断。
- **已被任务快照引用**：D0/组织消费证据成立；本轮两张卡均冻结输入，成功卡审计快照已提交
  两个新增字段，失败卡保留 failed run。
- **已进入最终成品**：本候选 1 张，仅为 `S01-P1`；完整套件未通过，不能与旧候选成品拼接。

代码候选提交 `596b87e7e9d0551c6b62834137e03eed2bf52c82`；候选后的冻结输入提交
`aa7ec2c` 及本失败收口均只改 Gate D 证据、治理日志和 `MILESTONE.md`。首次 provider 请求后
`src/`、`frontend/`、`tests/`、`scripts/`、Prompt、数据/媒体 manifest 差异为 0。

本轮生产/SSH/ECS 0、alembic 修改 0、`frontend/src/**` 修改 0、二进制入 Git 0。密钥仅由
精确三键解析器注入，不回显、不落盘。Gate D 尚未实现，founder 与监理独立终审未发生，
Gate E 不得签发。

唯一下一动作：监理复核第三轮白名单实证、冻结纪律、ledger 和“最好”误报证据；如需继续，
必须由主控另行签发，不得由执行侧自行第四轮修复或 provider 重跑。
