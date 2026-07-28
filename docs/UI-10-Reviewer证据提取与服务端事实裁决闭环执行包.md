# UI-10 Reviewer 证据提取与服务端事实裁决闭环执行包

- 当前状态：`ACTIVE`
- predecessor：`UI-09 SUPERSEDED → UI-10`
- 启动提交：`9af478b0f79786184b2b74c2fc48bb3730439d66`
- `origin/main`：`7aa87ab624cf3ff64f42e49f1755d66d496cac7a`
- 生产安全锚点：`845f63291ba5060e60f87d1afa5cfc1cdb057e3b`
- schema：`20260801_28`
- 唯一执行端：当前 WSL 执行端。
- 目标终态：全部验收真实成立后进入 `REVIEW`，不得自行 `CLOSED`。

## 1. 状态交接与真实根因

UI-09 的 Reviewer 资格只有 `2/3`：A 抽象原则和 B 隐含人物微事件分类正确，C
“笛语相信婆媳关系需要换位思考”虽然返回完整跨度，却被模型自报为
`abstract_principle`，服务端信任该标签而假绿。G3/G4/D1 因资格停止线没有运行，也没有
push、CI、备份、部署或生产修改。

UI-10 只修 Reviewer 单角色的权责边界：

`CreativeKernelV1 → 服务端 clause → Reviewer exact evidence → 服务端事实裁决
→ 最多一次受影响 unit 修复 → DeliveryCompilerV1`。

Reviewer 只回答文字中出现了什么；服务端根据可信身份、冻结事实和 unit 合同决定是否合法。
UI-09 的阻断证据与线性历史不被删除或改写。

## 2. 保持不变

CreationIntentGate、CreativePlanV2、NarrativeFrame、CreativeKernelV1 Writer 的
`unit_id + text` 输出、DeliveryCompilerV1、服务端逐字事实、最多一次 unit 修复、旧任务
legacy 路径、RLS、DM01、AIGC 和资产 `41/243/25/119` 保持。不得改变 Writer 创作策略或
Compiler 业务职责，不新增表或迁移。

## 3. ReviewEvidenceV1

新内核路径使用版本化 `ReviewEvidenceV1`；旧 `ReviewerObservation` 只为 legacy 路径保留。
服务端按既有标点有界切分每个可见 unit，形成 `unit_id`、`clause_id`、`exact_text` 和
`visible_order`；没有可切标点时整段作为一条 clause。

Reviewer 必须对每个 clause 恰好返回一次：

- `clause_id`、`exact_text`
- `subject_spans`、`predicate_spans`、`action_or_event_spans`
- `dialogue_spans`、`motive_spans`、`cause_spans`、`result_spans`
- `time_spans`、`location_spans`
- `implicit_subject`：`none/current_speaker/generic/uncertain`
- `uncertain`

模型不再返回或决定 observation type、pass/fail、事实依据、发布许可、资源或修复建议。
漏 clause、重复、额外 clause、原文不一致、虚构跨度、部分覆盖或 uncertain 都是证据资格
失败，不能调用 Writer 修复。

## 4. 服务端事实裁决

服务端从可信上下文构造当前 tenant、brand、organization、store、logical publishing
account 和机构 speaker 的 protected subjects。名称来自当前数据；机构性自称仅使用一份
稳定极小语法类别，不建设题材、人物、句型或失败样句黑名单。

裁决顺序固定：

1. frozen fact 必须逐字等于唯一 `fact_ref` 对应事实，Writer 不可修改；
2. hypothesis/dramatization 只认服务端 wrapper 与 unit 合同；
3. 可写 clause 出现 protected subject 且有谓词，或机构 speaker 的
   `current_speaker` 且有谓词，产生 `unsupported_institutional_assertion`；
4. abstract-only unit 出现 action/event、dialogue、motive、cause 或 result evidence，
   产生 `situated_event_in_observation`，不因人物省略而放行；
5. 无机构主体、具体事件、不确定或漏审时，才作为抽象原则通过。

constraint ref 永远不是机构事实许可证；Reviewer 的旧标签即使保留为诊断信息，也不能降低
服务端安全裁决。

## 5. 精确品牌事实合同

正式新内核路径只允许 `NarrativeFrame.allowed_fact_ids` 明确列入的精确 brand fact 作为
服务端 frozen fact，不把全部品牌资料插入，不交给 Writer 查看、改写或补充。Reviewer 只
核对 exact text 与唯一 fact ref。无精确品牌事实时，可写 unit 不得产生机构主张。

## 6. 确定性与 mutation 门

现有 pytest/Golden 内覆盖：

- A 抽象原则通过；
- B 隐含人物微事件依据 action/result evidence 失败；
- C 即使重放 UI-09 错标 `abstract_principle` 仍由 protected subject 与 predicate 失败；
- C2 机构账号 speaker 的“我们相信……”失败；
- “这篇更想聊换位思考和边界”不被过度阻断；
- frame 明确允许的 frozen brand fact 通过且不可修改；
- 漏、重、额外、原文不一致、伪 span、部分覆盖和 uncertain 证据失败且不修 Writer；
- Writer 新品牌名或机构主张不因抽象总类假绿。

mutation proof 至少覆盖 protected subject、旧标签信任、事件 evidence、clause 完整覆盖和
合法 brand frozen fact 路径。不得为具体失败句写专用 if、正则或替换。

## 7. Reviewer 资格与停止线

确定性门通过后，先重放 UI-09 样本 C 原始响应，证明旧错标不再假绿；随后只用
`deepseek-v4-flash`、`temperature=0`、`max_retries=0`、thinking disabled，对 A/B/C
各提证一次，不连接 repository 或数据库。必须分别记录 Raw Reviewer evidence 与服务端最终
裁决，pipeline 达到 `3/3` 才可继续。

任一 evidence 漏审、虚构、uncertain 或最终裁决错误，立即把 UI-10 置为 `BLOCKED`；不补
单句 Prompt、不换模型、不随机重跑、不增加第二 Reviewer。

## 8. 后续验收与生产边界

资格通过后，同 SHA 依次进行无持久化 G3/G4/D1，继而完整本地 G1—G7/H1/D1、本地质量门、
前端门和两份不同范围的有界审查。全部通过后才可一次 push 当前线性历史并触发唯一承重 CI。

CI 绿色后才允许 root-only 新鲜备份、同 SHA 部署、连续生产 G1→G7→H1→D1、人工全文
审阅、RLS／历史／DM01／AIGC／资产复核、不降级数据库的旧健康镜像往返回退及精确清理。
任何生产语义失败立即停止、清理、回退并置 `BLOCKED`，不形成第二候选。

当前生产启动复核仍为干净 `845f632…`，镜像摘要
`sha256:1171b153cbc709a760caf4a5db1fb14fe00e0bca3ef9c7b79c85f737a3a6bdb9`，
schema `20260801_28`，回环 readiness `ready`、公网 `200`，备份 timer `active`。
Reviewer 资格通过前不 push、CI、备份、部署或修改生产。

## 9. 未证明边界

当前尚未证明 Reviewer A/B/C 新 pipeline、G3/G4/D1、完整本地与生产 G1—G7/H1/D1、
CI、部署、回退及清理。真实员工／品牌采用、真实发布、流量、排名、爆款、GMV／销售、企业
采用、跨真实租户市场差异、企业 SLA 和 `20/55/44` 全组合继续不在本里程碑证明范围内。
