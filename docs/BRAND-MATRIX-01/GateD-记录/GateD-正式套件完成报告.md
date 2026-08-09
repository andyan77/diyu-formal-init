# BRAND-MATRIX-01 · Gate D 正式套件完成报告

状态：**`GATE-D IMPLEMENTED · AWAITING_SUPERVISOR_REVERIFICATION`**。

> 本报告是执行侧脱敏证据索引，不代表监理已独立复验，也不代表 founder
> 已完成 15 份成品的逐篇人工终审。本 Gate 未触及生产、SSH 或 ECS。

## 1. 完成门结果

1. **V2 projection 正式纵向：PASS**。React/API 预览、保存、管理员确认、
   读回和新任务冻结共用正式 V2 item；客户端不能自行授予权威、来源
   或 digest。
2. **账号与载体：PASS**。逻辑根账号 `10`、carrier `20`、矩阵相关
   content_accounts `30`、platform/format target `40`；旧账号 `9`个归档默认隐藏，
   代表性旧任务仍可按旧 ID 回读。
3. **31 条区域/门店资料：PASS**。`31/31` 均有明确去向，其中 `28`条进入
   V2 projection，internal 项按合同不进 Writer；`RK-EC-08` 当前消费数为 `0`。
4. **J、授权、资格、观察：PASS**。四组 J 均在 P1/P2 消费证据中有引用；
   `PS-S02-05` / `PS-S04-03` 的 v2 可重复授权正式可用；两条 DEMO-TEST
   single-use fixture 独立证明核销/重复拒绝/失败释放；反馈观察不升格。
5. **媒体母版：PASS**。技术母版 `26/26`，十项门
   PASS(scope)/FAIL/QUARANTINED=`26/0/0`，原片 P5 资格 `0`。
6. **P5 前置：PASS**。`6`份合格母版正式绑定 `4`个不同商品，P5 卡
   `S01-P5` 已在本候选上成功生成和落版。
7. **八剧本 + 八异常：PASS**。剧本 `8/8`，异常 `8/8`；异常样本均由
   确定性机制在 provider 前完成，provider request=`0`。
8. **provider 纪律：PASS**。本轮有效内容请求 `15`，历史累计 `59/80`；
   仅 `S05-S04-P1` 出现 `1`次未取得内容的传输重试，同卡同语义入账。
   内容重试 `0`，temperature `0`，无择优、无单卡补丁、无跨 SHA 拼接。
9. **工程门与 CI：PASS**。本地全量 `1057 passed / 2 skipped`，Ruff、mypy、
   Golden、EXE-V0、EXE-01、前端四门、Chrome、两套 secrets 和 Gate D 专属断言全绿；
   CI 四查全绿。
10. **安全与隔离：PASS**。生产/SSH/ECS 接触 `0`，alembic 差异 `0`，
    密钥泄漏 `0`，媒体二进制进 Git `0`，raw response 进 Git `0`。

## 2. D0 正式纵向证据

- `d0-chrome-evidence.json`：headless Chrome 的 V2 preview/save/confirm/readback 合同
  PASS，preview/candidate/confirm request=`2/1/1`，provider request=`0`。
- `formal-consumer-evidence.json`：总部、华东、四川、杭州、湖州、成都的正向
  消费与兄弟组织反向隔离成立；过期 `RK-EC-08` 消费数 `0`。
- `media-database-readback.json`：正式 repository/service 可回读媒体资格和不可用
  原因，本轮 readback digest
  `76499760d6ebef67046d4e72269183df2d4d50a510c0ddabbb29d3c00bc5e44e`。

## 3. 导入两轮与回读

- 两轮 batch digest：
  `20e1d00aa527d31312748ed84a22119d28784776ed3d2c40824b3775d8bdd6ed`。
- 两轮对象指纹：
  `1ec150e8f992e4d8f2439e7a791f744c5d3ee7bb7c69f25d735a6999bfbb2f98`。
- 盘点：组织 `6`，根账号 `10`，carrier `20`，平台/形式目标 `40`，商品
  `4`，系列 `2`，区域/门店条目 `31`，J `4`，authorization `6`，qualification
  `30`，projection item `34`。
- 账号过渡：管理列表只呈现 `10`个逻辑根账号；`20`个 carrier 仅作为
  平台目标；旧 `9`账号隐藏但代表性历史任务仍可回读。

## 4. 媒体台账与 P5

- 权利范围：`internal_demo_and_demo_tenant_operation`，证据
  `ATT-MEDIA-20260808-01`。
- 旧 manifest digest：
  `ab81e01fba2a83880c6d5ce38907cab849b60420a1f8fac2b181ddc34ca71a52`。
- 解锁后 manifest digest：
  `587d821315d896c414b382a1f277a07e1f7290f95cb8e0d829334cc53efc335b`。
- 技术母版 `26`份不等于 `26`份商品绑定；正式绑定为 `6`份，覆盖
  `DIYU-CSPU-001/006/008/013` 四个商品。原片 P5 eligibility 始终为 `0`。

## 5. 八剧本与八异常

### 八剧本

| 剧本 | 卡数 | 结果 |
|---|---:|---|
| SCENARIO-01 总部 F/J/G | 3 | PASS |
| SCENARIO-02 华东资料 | 1 | PASS |
| SCENARIO-03 杭州资料 | 1 | PASS |
| SCENARIO-04 成都错误普通文件 | 1 | PASS |
| SCENARIO-05 同一 SKU 四节点 | 4 | PASS |
| SCENARIO-06 同种子三账号 | 3 | PASS |
| SCENARIO-07 AMD v1/v2 | 1 | PASS |
| SCENARIO-08 反馈观察 | 1 | PASS |

15 张成品卡为：`S01-P1`、`S01-P2`、`S01-P5`、`S02-R01-P4`、
`S03-S01-P4`、`S04-S04-P2`、`S05-H01-P1`、`S05-R01-P1`、`S05-S01-P1`、
`S05-S04-P1`、`S06-H01-P3`、`S06-S02-P3`、`S06-S04-P3`、`S07-H01-P3`、
`S08-S01-P4`，全部为 `PASS`。

### 八异常

| 异常 | 结果 | provider request |
|---|---|---:|
| ANOM-01 过期成分口径版本对 | PASS | 0 |
| ANOM-02 门店错误成分文件 | PASS | 0 |
| ANOM-03 同字段正式事实冲突 | PASS | 0 |
| ANOM-04 过期区域活动 | PASS | 0 |
| ANOM-05 跨门店读取 | PASS | 0 |
| ANOM-06 双用户同逻辑账号 | PASS | 0 |
| ANOM-07 合成 single-use 授权 | PASS | 0 |
| ANOM-08 更新前后两版任务 | PASS | 0 |

## 6. Provider ledger、握手与审阅标注

- 零预算握手：`api.deepseek.com:443`，TLS 1.3，PASS；completion request=`0`。
- 本轮请求索引 `45—59`，全部绑定候选 `81289d8…`；累计 `59/80`。
- 传输重试：`1`，发生在 `S05-S04-P1`；未取得内容后同卡自动重试，
  最终只接受一份内容响应。
- 非阻断性性能词复核标注 `9`条，涉及 `透气/显瘦/耐穿/好打理/耐磨/百搭`；
  这些不是 ProductFact，也没有改变二元结论，留给 founder 逐篇审阅。
- 私有证据目录的实际本机路径登记在
  `formal-model-suite-evidence.json.private_evidence_path`；目录权限 `0700`，
  文件权限 `0600`，`SHA256SUMS` 已生成。Git 只保存脱敏索引。

## 7. 候选、冻结项、Git 与 CI

- 候选链：`997e6b5 → f7e8e81 → ba4208a → 596b87e → 7e48f7a →
  e0dba46 → 3399dc4 → 587bed9 → f00e5d4 → 81289d8`。
- 最终 runtime candidate：
  `81289d8619ef831d9d6a79acceaac9090f17ee3a`。
- 冻结登记 digest：
  `57a5f5202559a5e55fc2314e9c7f7324eec96e4d93a925dfabcf778000f27376`。
- 模型：`deepseek-v4-flash`；provider：官方 `api.deepseek.com`；temperature=`0`；
  content max_retries=`0`；transport max_retries=`2`。
- 本次关键提交：`c96846d` 统一端点裁决；`81289d8` 官方端点代码
  与合同；`bf2ae67` 隔离导入/媒体/运行登记冻结。最终 docs-only 提交
  SHA 由本报告提交后补入 Git 历史，不改变 runtime candidate。
- CI run：`31312097476`；event=`workflow_dispatch`；
  headSha=`81289d8619ef831d9d6a79acceaac9090f17ee3a`；conclusion=`success`；
  非成功步骤=`0`。

## 8. 四层口径

- **已存储**：10 根账号、20 carrier、40 平台/形式目标、6 组织、4 商品、
  2 系列、31 区域/门店条目、4 J、6 authorization、30 qualification、26 母版资产。
- **已进入 projection**：34 个 V2 item，其中 28 个是可发布区域/门店条目；
  internal 条目不进 Writer，过期 `RK-EC-08` 不进当前选择。
- **已被任务快照引用**：组织消费确定性纵向已覆盖总部/区域/门店；
  当前候选 15 张正式卡均有 task/run/version，并冻结候选 SHA、投影、账号
  语义、商品/J/媒体引用及 digest。
- **已进入最终成品**：当前候选 `15/15`张成品落版，旧候选产物不参与本结论；
  执行侧二元初审全部 PASS，尚待 founder 逐篇审阅。

## 9. 诚实边界与下一动作

- 这是本地隔离库机制、正式消费链与模型套件证明，不是生产部署或真实公开发布证明。
- 26 份母版的当前 PASS 只适用于已授权的
  `internal_demo_and_demo_tenant_operation` 范围；真实对外公开发布前仍须补齐
  真实模特/监护人授权债务。
- 本报告没有代替监理复验，也没有代替 founder 对 15 篇文案的内容质量裁决。
- 唯一下一动作：**监理独立复验 + founder 逐篇审阅**。
