# UI-10 Reviewer 证据提取与服务端事实裁决闭环执行包

- 当前状态：`SUPERSEDED → UI-11`（此前 `BLOCKED` 事实保持；不表示 UI-10 成功）
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

Reviewer A/B/C 新 pipeline 已在第 11 节证明。G3 在一次允许修复后仍失败；G4、D1、完整
本地与生产 G1—G7/H1/D1、最终前端门、两份候选审查、CI、部署和回退均未执行或未证明。
临时 runner、源码归档与本地原始响应副本已清理，但因没有进入生产验收，不存在生产业务
对象清理证明。真实员工／品牌采用、真实发布、流量、排名、爆款、GMV／销售、企业采用、
跨真实租户市场差异、企业 SLA 和 `20/55/44` 全组合继续不在本里程碑证明范围内。

## 10. 确定性实现与 mutation proof

状态交接提交为 `ad7b41f`，实现提交为
`ada98ff47e5655fea9e23d6e3d3fc06b00e4f566`。新共享对象
`ReviewEvidenceV1` 只含版本、逐 clause exact evidence 与 implicit subject；服务端按可见
顺序切分 clause，并在 evidence 完整后独立执行 frozen fact、wrapper、protected subject、
institutional speaker、event evidence 和 constraint 闭世界对账。新路径拒绝
`observation_type`、pass/fail、资源和修复建议字段；legacy 路径不改。

正式 `_generate_kernel` 不再过滤 Frame 明确允许且能解析到精确原句的 brand fact；该事实
由服务端 frozen unit 插入，Writer prompt 不含其原文。新任务默认 `allowed_brand_fact_ids`
为空，避免把品牌资料长文无差别当成事实；无法解析的允许 ID 在 Writer 前失败。

确定性回归为 Golden `221 passed`（含 OpenAPI），ruff 与 mypy（93 个源文件）通过。实际
mutation proof：

- 删除 protected-subject 对账后，C 消费者变红；
- 允许旧 `observation_type` 重新进入新 evidence schema 后，C 消费者变红；
- 删除 event evidence 对账后，B 消费者变红；
- 放宽漏 clause 覆盖后，漏审消费者变红；
- 再次从正式 skeleton 过滤合法 brand frozen fact 后，品牌事实合同消费者变红。

每项临时 mutation 均逐项恢复；恢复后的定向测试与 lint 转绿。没有建立新测试平台。

## 11. Reviewer 真实资格

同一实现 SHA 使用当前 `deepseek-v4-flash`、`temperature=0`、`max_retries=0`、
thinking disabled，在无 repository／数据库环境中先重放 UI-09 样本 C，再对 A/B/C 各
调用一次。

- UI-09 C 重放：旧 raw 自报 `abstract_principle`；其 exact evidence 中“相信”作为谓词，
  服务端结合可信主体“笛语”仍判 `unsupported_institutional_assertion`。
- A raw evidence：主体“换位思考”、谓词“不等于没有边界”，无 event evidence；服务端通过。
- B raw evidence：`action_or_event_spans=["沉默"]`、
  `location_spans=["饭桌上"]`；服务端判 `situated_event_in_observation`。
- C raw evidence：`subject_spans=["笛语"]`、`predicate_spans=["相信"]`；服务端判
  `unsupported_institutional_assertion`。

三次 evidence 均完整、精确、无 uncertain，pipeline `3/3`；Raw evidence 标签不再是完成
门。root-only 证据目录为
`/var/lib/diyu-ui10-evidence/ada98ff47e5655fea9e23d6e3d3fc06b00e4f566/`，
目录／文件 `0700/0600 root:root`，资格 summary SHA-256 为
`b5a57f36ace71b1b893354004c61f0f377c15c886eddffec6ec76bebe59c3eb4`。

## 12. G3 业务预检与停止

资格通过后，同 SHA 开始 G3→G4→D1。G3 初稿一次、Reviewer 一次、允许的唯一 affected
body unit 修复一次、完整 Reviewer 复审一次，共 4 次模型调用，全部零重试：

- 初稿写入未提供的“两个……女人，因为同一个男人而成为家人”“共同生活经历”“同一个屋檐
  下”“婆婆来帮忙带孩子”等具体家庭设定；
- 修复把“同一个男人”改为“同一个重要的人”，但仍保留同住、育儿、带孩子、儿媳是孩子的
  妈妈等具体设定；
- 初审与复审均恰好覆盖 `25/25` clause，所有 exact text/span 真实存在且
  `uncertain=false`，不是 Reviewer 漏审或证据资格失败；
- 服务端初审与复审均产生 `situated_event_in_observation`；复审精确违规 evidence 包含
  “成为家人”“和平共处”“来帮忙带孩子”“试图主导或改变另一方”等。

唯一修复后仍失败，命中冻结停止线。G4、D1 未调用，完整 G1—G7/H1/D1、最终前端门、两份
候选审查、push、CI、备份、部署、生产验收与回退均未开始。没有第二修复、随机重跑、Prompt
补丁、换模或第二 Reviewer。业务 summary SHA-256 为
`589a0d0186d4d382ff10bc376554acf0d60b902ae11e5ea6fcee86b2a27a8c56`。

同一执行端人工完整阅读了 G3 初稿四个 unit、修复后的完整 body 及两轮全部 evidence；这是
失败归因阅读，不冒充两名独立人类、完整成品审查或生产验收。生成在 Compiler 前失败，没有
可冒充完成 V1 的成品。

## 13. 阻断收口

UI-10 置为 `BLOCKED`，不是 `REVIEW` 或 `CLOSED`。生产再次只读核实为干净
`845f63291ba5060e60f87d1afa5cfc1cdb057e3b`，运行镜像
`sha256:1171b153cbc709a760caf4a5db1fb14fe00e0bca3ef9c7b79c85f737a3a6bdb9`，
schema `20260801_28`，回环 readiness `ready`、公网 `200`、备份 timer `active`。
没有创建业务 task/run/version/session 或生产备份；本地和远端 runner、源码归档及本地原始
响应副本已精确清理，正式 root-only 证据保留。

RLS、历史版本、系列、DM01、AIGC 与资产 `41/243/25/119` 的本地确定性回归通过；由于没有
部署，只能证明生产现状未被本轮改变，不能把 UI-10 代码写成生产已证明。

唯一下一动作：主控只裁决是否另开 **Writer 单角色 successor**，重构
general-observation 的生成职责；CreationIntentGate、Reviewer evidence、服务端事实裁决和
DeliveryCompiler 保持，不换模型、不形成 fallback。

## 14. UI-11 取代说明

主控随后裁决 UI-10 的服务端 Reviewer evidence 与事实裁决成果继续保留，但否决
“general-observation 可写单元只能容纳纯抽象观点”的产品合同。UI-11 以服务端所有、明确
可见的假设范围承载一般创作情境，同时继续隔离真人现实事实、机构事实与制作资源。UI-10
据此为 `SUPERSEDED → UI-11`；本执行包中的 Reviewer `3/3`、G3 一次修复后失败和未
push/CI/部署历史均保持原样。
