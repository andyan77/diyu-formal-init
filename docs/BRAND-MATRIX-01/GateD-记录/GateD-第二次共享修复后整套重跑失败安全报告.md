# BRAND-MATRIX-01 · Gate D 第二次共享修复后整套重跑失败安全报告

状态：**`GATE-D FAILED_SAFE · PUBLICATION_V3_COMPLETION_SNAPSHOT_KEYS_REJECTED`**。

本报告是执行侧脱敏证据，不是监理独立复验或 founder 逐篇终审。
ADJ-WRITER-BOUNDARY-03 三层制已正确生效；新候选的唯一响应通过了 Writer 内容边界，
但在创建成品版本前被仓储快照字段契约失败关闭。这是首次观察到的新共享工程根因，
不是模型胡编、不是 `耐穿` 再次被拦，也没有半成品版本污染。依据
`UNLOCK-D-RERUN-02` 的停止线，执行侧不自行开启第三次修复或再次 provider 请求。

## 1. 十项完成门

1. V2 projection 的 React/API 创建、确认、读取和任务消费纵向：**PASS**。
2. 10 逻辑根账号、20 carrier、30 矩阵账号行、40 平台/形式目标及旧 9 账号归档：
   **PASS**。
3. 31 条资料去向及真实组织任务消费：**PASS**；`RK-EC-08` 新任务消费为 0。
4. J、authorization、qualification 与反馈观察正式消费者：**PASS**。
5. 26 份技术母版、checksum 及十项门裁决：**PASS**。
6. P5 媒体前置：**PASS**。6 份 PASS 母版绑定 4 个不同正式商品；新套件在
   首张 P1 卡停止，因此本候选的 P5 模型卡未运行。
7. 八剧本 8/8 + 八异常 8/8：**FAIL**。首卡 `S01-P1` 在持久化阶段失败安全；
   不拼接任何旧候选成品。
8. provider 账本、预算与唯一 SHA：**PASS（失败证据口径）**。历史 7 次、
   本候选 1 次，累计 `8/80`；temperature `0`、max_retries `0`、transport retry `0`、
   失败后请求 `0`。
9. 全量工程门、显式 Chrome 与 CI：**PASS**。本地 `1025 passed / 2 skipped`；
   CI run `31299692372` 四查全绿。
10. 生产接触、密钥泄漏、二进制入 Git：**PASS**，均为 0。

第 7 门未达成，Gate D 不得报 `IMPLEMENTED`。

## 2. ADJ-WRITER-BOUNDARY-03 三层制实现

### 守卫收窄前后

- 收窄前：旧性能词模式把 `耐穿` 等软性体验词也当作未确认硬事实拒绝。
- 历史《GateD-最终整套重跑失败安全报告》中将 `耐穿` 定性为未授权商品性能断言的
  结论，已被 ADJ-WRITER-BOUNDARY-03 显式 supersede；旧报告仅保留为当时候选的历史证据。
- 收窄后：机器硬拦只覆盖 L1——未确认的成分比例、价格数字+元、精确工艺名、
  适穿年龄段、保证类性能和绝对化用语；已有改值、画像逐字复制、内部选择计划
  照抄守卫保持不变。
- L2 `耐穿/百搭/好打理/显精神` 可作为不取得 ProductFact 资格的自然创作表达；
  `保证耐穿`、`永不变形` 等仍属 L1 并被拒绝。
- L3 继续要求条件语态且主语在用户侧；lens 只调整分账号表达分寸，不改变
  L1/L2/L3 政策。
- 人设经历仍只能取授权原句库并冻结原句 ID；未新增语义检测器或词表。

实现锚点：

- `src/shared/factual_basis.py::unconfirmed_product_specificity_spans`
- `src/tool/llm_gateway/deepseek.py::_writer_truth_and_persona_instruction`
- `tests/test_deepseek_adapter.py::test_publication_v3_allows_l2_soft_experience_words`
- `tests/test_deepseek_adapter.py::test_publication_v3_allows_prior_s01_p1_l2_boundary_excerpt`
- `tests/test_deepseek_adapter.py::test_publication_v3_rejects_changed_or_unconfirmed_product_specifics`
- `tests/test_deepseek_adapter.py::test_publication_v3_product_prompt_exposes_confirmed_values_and_keeps_j_conditional`
- `scripts/gated/assert_gated_semantics.py`

双向回归结果：L2 软词和上一候选 `S01-P1` 脱敏失败片段均放行；改值、
成分比例、价格、工艺、年龄、保证类断言和绝对化用语均拒绝。这次正式响应也已通过
新边界，证明本轮修复不是“测试写绿、运行时仍拒绝”。

## 3. 新共享根因与失败安全

正式链路已走到 `ContentService → DeepSeek adapter → Writer 边界通过 → 成品持久化`。
DeepSeek adapter 为冻结 Writer 真实消费依据，在 completion snapshot patch 增加了：

- `writer_confirmed_product_fact_refs`
- `used_persona_quote_ids`

但 `PostgresContentRepository._PUBLICATION_V3_COMPLETION_KEYS` 的精确允许集未包含这两个字段。
因此 `_validated_completion_snapshot()` 以
`创作内核快照补丁字段不完整或越界` 失败关闭。私有响应的离线重放显示：多余字段精确为上述两项，
缺失字段为 0；该诊断的 provider request 为 0。

隔离库回读：

- task `3bafbf45-fb92-45ae-b832-984ef425a5f8`；
- run `27b810b8-f219-4d72-aaf8-b2b1aee1f80e`，status=`failed`；
- version `0`，completion snapshot patch 未提交；
- 公开失败码：`PUBLICATION_V3_COMPLETION_SNAPSHOT_KEYS_REJECTED`。

这是通用快照契约不同步，不是某张验收卡的专用补丁问题。修复会再次改动代码并生成新候选，
而本指令明令“发现新的共享根因即停”，故执行侧未修改仓储允许集、未重跑模型。

## 4. D0、导入与媒体

- D0 纵向：React/API 预览 → 服务端派生治理字段 → 候选保存 → 管理员确认 →
  新任务冻结 projection item ID/版本/组织作用域/source refs 成立；客户端越权治理字段被拒绝。
- 两轮 import batch digest：
  `f15d0efe63173b1b6c72b5b4cf4681673cf29e4536fe600e3d92066e52781750`。
- 两轮对象指纹：
  `e48dc6542db65593bb3830eda9cebad425d54b756d34a1ce469b88931eef6b88`；两轮逐字节一致。
- 账号/载体/目标回读 `10/20/30/40`；6 个合同组织、31 条区域/门店资料、34 个
  V2 projection item（其中 28 个区域/门店条目）、4 个 J、2 个授权、30 个 qualification。
- 媒体十项门：PASS(scope) `26` / FAIL `0` / QUARANTINED `0`；作用域
  `internal_demo_and_demo_tenant_operation`。原片 P5 资格 `0`，母版 P5 资格 `6`，
  绑定 4 个不同正式商品。26 份母版不等于 26 份商品绑定。
- media manifest digest：解锁前
  `ab81e01fba2a83880c6d5ce38907cab849b60420a1f8fac2b181ddc34ca71a52`，解锁后
  `587d821315d896c414b382a1f277a07e1f7290f95cb8e0d829334cc53efc335b`。
- 本轮隔离库媒体回读 digest：
  `167b174ee4bd8afa52d69c2d1bc0dadd17aba671af0479e6d13f5c314a98b5ee`。

## 5. 候选、本地门与 CI

候选链：

1. `997e6b55c1c40dacd44a46ff6617b28766011958`：首次媒体解锁候选，请求 1–6。
2. `f7e8e81c80ebc8552794f82aab81ef509e242b14`：第一次共享修复候选，请求 7。
3. `ba4208a6ea96775683ecd89f41b6cd869b45eead`：本轮唯一 runtime candidate，请求 8。

冻结登记：

- registration digest：`4815beafe39394db8e43ace33e5cf33721e5f1f989795ba19df2a7955d8c9cf4`；
- Gate A manifest：`14fed12141dc3b277c09c878a2a30ef71b445ce8ea31457c0122b403aeb48a06`；
- formal suite contract SHA-256：
  `ea336543270e9fa9024688fd59cd76f454a62112ecc4a6518e9c6c3b9e2b76dc`；
- publication projection digest：
  `cb6b2cf509c31e9864ea632449e41ff06d553e7f2ed93cf758fce7c77e978962`；
- 隔离数据库输入指纹：
  `490e2a0a8fa4ebd53e4df1b56852cea85cfde404f659631e11965a4fa338fe2f`；
- 模型 `deepseek-v4-flash`，temperature `0`，max_retries `0`。

本地全绿：Ruff、mypy、Golden、EXE-V0、EXE-01、前端 lint/typecheck/test/build、显式 Chrome、
两套 secrets、Gate D scope/semantics/privacy、`scripts/test.sh`、`git diff --check`；
pytest 观察值为 `1025 passed / 2 skipped`。`frontend/test/**` 仅按既有授权收口 Chrome 孤儿进程组，
既有业务断言未删减，`frontend/src/**` 修改为 0。

CI run `31299692372`：

- event=`workflow_dispatch`；
- headSha=`ba4208a6ea96775683ecd89f41b6cd869b45eead`，与当时远程候选 HEAD 一致；
- status=`completed`，conclusion=`success`；
- 非成功步骤=`0`（共 19 步）。

## 6. Provider ledger 与私有证据

- 请求 1–6 只绑定 `997e6b5…`，请求 7 只绑定 `f7e8e81…`，请求 8 只绑定
  `ba4208a…`；三个候选的产物不拼接。
- 本轮 request SHA-256：
  `f451656934e11049831f52fb0430ee2493178ba8c8308e5845f5f042826cc783`。
- 本轮 response SHA-256：
  `8594708f414ddbca2f0714e100d7d79a0444592da595d5089a3ee8a772045fda`。
- 累计 provider request `8/80`；本轮 `1`；transport retry `0`；择优重跑 `0`；
  失败后 provider request `0`。
- 私有证据目录：
  `~/diyu-evidence-brand-matrix-gated-ba4208a6ea96775683ecd89f41b6cd869b45eead/`；
  目录 `0700`，文件 `0600`，逐文件 `sha256sum -c` 通过。
- 私有 `SHA256SUMS` 文件 digest：
  `846fb87383e2b2541296f8447e2da932ad8be0d8f2a837a3b67b19a2268d1114`。
- Git 中 raw response、完整 artifact、完整任务快照、密钥均为 0。

## 7. 八剧本与八异常

剧本：

1. 总部 F/J/G：`FAILED_SAFE`（`S01-P1` 边界通过，成品快照字段契约拒绝）。
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

## 8. 四层口径

- **已存储**：两轮隔离导入完整；10 根账号、20 carrier、31 条资料、4 商品、4 J、
  2 系列、2 授权、30 资格、26 技术母版元数据均可回读。本轮正式套件新增
  task/run/version 为 `1/1/0`；run 为 `failed`。
- **已进入 projection**：34 个 V2 条目，其中 28 个区域/门店条目；过期 `RK-EC-08`
  被生命周期阻断。
- **已被任务快照引用**：D0 和确定性组织消费证据成立；本轮正式首卡已写入
  初始冻结快照，但 Writer 完成补丁未提交。
- **已进入最终成品**：本候选为 `0`。历史候选的 5 张成品只作历史证据，不拼接。

## 9. Git 冻结纪律与诚实边界

- `ba4208a6ea96775683ecd89f41b6cd869b45eead`：三层制修复、双向测试、套件 v3 及授权范围内
  Chrome 夹具收口；唯一 runtime candidate。
- `e6e95c0a84bac5f075af9a6ac3dbd6d3fe7327c4`：候选冻结后的导入/媒体/运行登记，
  仅 Gate D 记录。
- 正式 provider 请求后只改 Gate D 脱敏证据、治理日志与 `MILESTONE.md`；
  `src/`、`frontend/`、`tests/`、`scripts/`、配置、数据/媒体 manifest 差异为 0。

本轮生产接触 0、SSH/ECS 0、alembic 修改 0、`frontend/src/**` 修改 0、
二进制入 Git 0。密钥只由精确三键解析器注入，不回显、不落盘。Gate D 尚未实现，
八剧本/八异常未完成，founder 与监理独立终审未发生，Gate E 不得签发。

唯一下一动作：监理复核本轮三层制、候选冻结、ledger 与新快照契约失败证据；
如需继续，由主控另行签发新指令，执行侧不得自行修复或重跑 provider。
