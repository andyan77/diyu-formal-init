# BRAND-MATRIX-01 · Gate D 最终整套重跑失败安全报告

状态：**`GATE-D FAILED_SAFE · FORMAL_SUITE_UNCONFIRMED_PRODUCT_SPECIFICITY_REJECTED`**。

本报告是执行侧脱敏证据，不是监理独立复验或 founder 逐篇终审。新候选已完成工程冻结，
但整套模型验收在第一张卡收到唯一响应后，被确定性商品事实边界正确拒绝。按
`UNLOCK-D-RERUN-FINAL`，本轮不进行第二次共享修复、不补跑失败卡、不拼接旧候选成品。

## 1. 完成门逐项结果

1. V2 projection 的 React/API 创建、确认、读取和任务消费纵向：**PASS**。
2. 10 逻辑根账号、20 carrier、30 矩阵账号行、40 平台/形式目标及旧 9 账号归档：
   **PASS**。
3. 31 条资料去向及真实组织任务消费：**PASS**；RK-EC-08 新任务消费为 0。
4. J、authorization、qualification 与反馈观察正式消费者：**PASS**。
5. 26 份技术母版、checksum 及十项门裁决：**PASS**。
6. P5 媒体前置：**PASS**。6 份 PASS 母版绑定 4 个不同已导入正式商品；但新套件在
   首张 P1 卡停止，因此本候选的 P5 模型卡未运行。
7. 八剧本 8/8 + 八异常 8/8：**FAIL**。首卡 `S01-P1` 失败安全，不能拼接上一候选的
   5 张完成卡。
8. provider 账本、预算与唯一 SHA：**PASS（失败证据口径）**。上一候选 6 次、本候选
   1 次，累计 `7/80`；temperature `0`、max_retries `0`、transport retry `0`、补跑 `0`。
9. 全量工程门、显式 Chrome 与 CI：**PASS**。本地 `1016 passed / 2 skipped`；CI run
   `31297635710` 四查全绿。
10. 生产接触、密钥泄漏、二进制入 Git：**PASS**，均为 0。

第 7 门未达成，Gate D 不得报 `IMPLEMENTED`。

## 2. R-1 共享根因修复与补充授权

### 守卫反转前后

- 修复前：只要 Writer 文案逐字出现服务端商品事实原子，就可能触发“不得复述商品事实块”；
  因而已确认的 `针织开衫` 也被误拒。
- 修复后：已冻结的 V 级品类、商品名、主色等真值允许直接面向消费者表述；机器只拒绝
  可确定的改值和未确认具体信息。现行未确认具体信息守卫包括成分百分比、价格数字加元、
  精确工艺名、年龄段和性能断言；账号画像逐字复制及内部商品选择计划照抄继续拒绝。
- 人设经历：Writer 提示合同只允许使用已获准的 `PS-S02-*` / `PS-S04-*` 原句，所用原句
  ID 冻结进任务快照；无授权原句时禁止自传式经历。未新增语义检测器。
- 表达合同：已确认事实必须直说实际值；J 判断保持用户侧条件语态；未确认信息不补答案、
  不写成卖点。

实现锚点：`src/shared/factual_basis.py` 的 `product_fact_value_conflicts()`、
`unconfirmed_product_specificity_spans()`；`src/tool/llm_gateway/deepseek.py` 的
`_writer_truth_and_persona_instruction()` 与 Writer 快照字段。

双向回归锚点：

- `tests/test_deepseek_adapter.py::test_publication_v3_allows_confirmed_v_facts_and_prior_s04_response`
- `tests/test_deepseek_adapter.py::test_publication_v3_allows_exact_confirmed_category_and_color`
- `tests/test_deepseek_adapter.py::test_publication_v3_rejects_changed_or_unconfirmed_product_specifics`
- `tests/test_deepseek_adapter.py::test_publication_v3_still_rejects_exact_account_profile_copy`
- `tests/test_deepseek_adapter.py::test_publication_v3_freezes_authorized_persona_quote_id_in_snapshot`

### 验收话术出清

- 旧：`请只依据总部已确认事实解释 DIYU-CSPU-008，不采用门店普通文件中的成分说法。`
- 新：`请介绍 DIYU-CSPU-008，只陈述已经正式确认的商品信息；未确认的不要作确定表述。`
- `formal-suite-contract.json` 的 15 张卡全部改为消费者/运营者可理解的话术；后台权威过滤
  继续由确定性测试承重。

### frontend/test 补充授权

依据 `AUTH-D-FIX-FRONTEND-TEST-01`，仅在 `frontend/test/**` 补齐 `team-usage`、
`admin/readiness` 测试端点 stub，并延长临时 profile 删除的既有重试窗口。Chrome 原断言未删、
未弱化；`frontend/src/**` 产品代码差异为 0。

## 3. D0、导入与媒体证据

- D0 纵向：React/API 预览 → 服务端派生治理字段 → 候选保存 → 管理员确认 → 新任务冻结
  projection item ID/版本/组织作用域/source refs 成立；客户端越权治理字段被拒绝。
- 浏览器证据：`d0-chrome-evidence.json`；preview `2`、candidate `1`、confirm `1`，
  headless Chrome PASS。
- 正式消费者证据：`formal-consumer-evidence.json`。
- 两轮 import batch digest：
  `f15d0efe63173b1b6c72b5b4cf4681673cf29e4536fe600e3d92066e52781750`。
- 两轮对象指纹：
  `e48dc6542db65593bb3830eda9cebad425d54b756d34a1ce469b88931eef6b88`。
- 两轮结果逐字节一致。账号/载体/作用域回读为 `10/20/30/40`；6 个合同组织、31 条
  区域/门店资料、34 个 V2 projection item、28 个区域/门店 projection item、4 个 J、
  2 个授权、30 个 qualification 均可回读。
- 媒体：PASS(scope) `26` / FAIL `0` / QUARANTINED `0`；授权作用域为
  `internal_demo_and_demo_tenant_operation`。原片 P5 资格 `0`，母版 P5 资格 `6`，
  覆盖 4 个正式商品；26 份母版不等于 26 份商品绑定。
- 媒体 manifest digest：解锁前
  `ab81e01fba2a83880c6d5ce38907cab849b60420a1f8fac2b181ddc34ca71a52`，解锁后
  `587d821315d896c414b382a1f277a07e1f7290f95cb8e0d829334cc53efc335b`。
- 本轮隔离库媒体回读 digest：
  `82eca64e21ebacbb2bd392ce9ae944bd3ab60108b00a462e663566975cc75e8d`。

## 4. 候选、工程门与 CI

- 上一失败候选：`997e6b55c1c40dacd44a46ff6617b28766011958`；其 5 张完成卡只保留为历史证据。
- 新 runtime candidate：`f7e8e81c80ebc8552794f82aab81ef509e242b14`。
- 新候选登记 digest：`90d1ad5a0d31c22e0c0904cd5c9a2d6653b4ec52dad2b11fcbad0252bc6a399a`。
- Gate A manifest：`14fed12141dc3b277c09c878a2a30ef71b445ce8ea31457c0122b403aeb48a06`。
- publication projection digest：
  `cb6b2cf509c31e9864ea632449e41ff06d553e7f2ed93cf758fce7c77e978962`。
- 本地隔离数据库输入指纹：
  `a64ad156461d0aa744f7b3005d0200d74ede12799bfd70c2931fb48c89b31ff7`。
- 模型 `deepseek-v4-flash`，temperature `0`，max_retries `0`。
- 本地门：pytest 全量、Ruff、mypy、Golden、EXE-V0、EXE-01、前端 lint/typecheck/test/build、
  显式 Chrome、两套 secrets、Gate D scope/semantics/privacy、`scripts/test.sh`、
  `git diff --check` 全绿；全量为 `1016 passed / 2 skipped`。
- CI run `31297635710`：event=`workflow_dispatch`；headSha=`f7e8e81c…` 且等于远端候选；
  conclusion=`success`；非成功步骤=`0`。
- CI 承重其实际运行的工程回归门；Gate D 专属断言由本地退出码承重。

## 5. 正式套件失败与 ledger

首张卡输入为：

`家庭正在考虑 DIYU-CSPU-001 时，请给一条条件清楚、取舍明确的日常穿衣建议。`

该卡收到一次响应。离线重放同一私有响应时，确定性边界命中
`performance_assertion:耐穿`，并抛出 `Writer 新增了未确认商品具体信息`。`耐穿` 是商品
性能断言，现有 V 级事实与 J 条件没有授予该真值，因此这不是已确认事实的合法直说，也不是
旧守卫误报。该响应未形成 task/run/version，数据库没有半成品污染。

- 本候选 provider request `1`；前一候选 `6`；累计 `7/80`。
- transport retry `0`；择优重跑 `0`；失败后 provider request `0`。
- 本候选完成 artifact `0`；上一候选 5 个 artifact 不进入本候选结论。
- 私有证据目录：
  `~/diyu-evidence-brand-matrix-gated-f7e8e81c80ebc8552794f82aab81ef509e242b14/`；
  目录权限 `0700`，文件权限 `0600`。
- 私有 `SHA256SUMS` digest：
  `76caae709907d1d78fc158b59fbee13bd8aaeb448d091ccdafdc36937fb48467`，逐文件校验通过。
- Git 中 raw response、完整 artifact、任务快照和密钥均为 0；只登记脱敏索引和 digest。

这是首次 provider request 后发现的新共享根因。续行指令只授权一次 R-1 共享修复，因此执行侧
必须在此停止；不能自行开启第二次修复。

## 6. 八剧本与八异常逐条结果

剧本：

1. 总部 F/J/G：`FAILED_SAFE`（首卡 `S01-P1` 未确认性能断言被拒绝）。
2. 华东资料：`NOT_RUN_SUITE_ABORTED`。
3. 杭州资料：`NOT_RUN_SUITE_ABORTED`。
4. 成都错误普通文件：`NOT_RUN_SUITE_ABORTED`；不拼接旧候选结果。
5. 同一 SKU 四节点：`NOT_RUN_SUITE_ABORTED`。
6. 同一种子三账号：`NOT_RUN_SUITE_ABORTED`。
7. AMD v1/v2：`NOT_RUN_SUITE_ABORTED`。
8. 反馈观察：`NOT_RUN_SUITE_ABORTED`。

异常：

1. 过期成分口径版本对：`INCOMPLETE_SUITE_ABORTED`（冻结前置成立，完整比较未到达）。
2. 门店错误成分文件：`PASS_ZERO_PROVIDER`。
3. 同字段正式事实冲突：`PASS_ZERO_PROVIDER`。
4. 过期区域活动：`PASS_ZERO_PROVIDER`。
5. 跨门店读取：`PASS_ZERO_PROVIDER`。
6. 两名用户操作同一逻辑账号：`PASS_ZERO_PROVIDER`。
7. 私人经历单次授权：`NOT_RUN_SUITE_ABORTED`。
8. 知识更新前后两版任务：`INCOMPLETE_SUITE_ABORTED`（旧快照冻结成立，新任务比较未到达）。

## 7. 四层口径

- **已存储**：两轮隔离导入完整；10 根账号、20 carrier、31 条资料、4 商品、4 J、2 系列、
  2 授权、30 资格、26 技术母版元数据均可回读。本候选正式套件首卡事务回滚，新增
  task/run/version 为 `0/0/0`。
- **已进入 projection**：34 个 V2 条目，其中 28 个区域/门店条目；过期 RK-EC-08 被
  生命周期阻断。
- **已被任务快照引用**：D0/确定性组织消费证据成立；本候选正式模型首卡没有提交快照。
- **已进入最终成品**：本候选为 `0`。上一候选 5 张完成卡是历史证据，禁止拼接。

## 8. Git 链、冻结纪律与诚实边界

- `f7e8e81c80ebc8552794f82aab81ef509e242b14`：R-1 修复、测试、自然话术和授权范围内
  frontend/test 修复；这是唯一 runtime candidate。
- `14ec0e5bb544c4936a309f6834c44fb10aa4dbb9`：候选冻结后的输入登记，仅 Gate D 记录。
- 本报告及最终脱敏证据使用后续 docs-only 收口提交；不改变 runtime candidate。
- 从 runtime candidate 到 docs HEAD，除 Gate D 证据、治理日志与 `MILESTONE.md` 外，
  `src/`、`frontend/`、`tests/`、`scripts/`、配置和数据/media manifest 差异为 0。

本轮生产接触 0、SSH/ECS 0、alembic 修改 0、`frontend/src/**` 修改 0、二进制入 Git 0；
密钥只由精确三键解析器注入，不回显、不落盘。Gate D 尚未实现，八剧本/八异常未完成，
founder 与监理独立终审未发生，Gate E 不得签发。

唯一下一动作：监理复核本次 `耐穿` 失败证据与冻结纪律；如需继续，必须由主控另行裁决并
签发新指令，执行侧不得自行进行第二次共享修复或 provider 重跑。
