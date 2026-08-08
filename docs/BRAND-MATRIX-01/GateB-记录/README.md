# BRAND-MATRIX-01 · Gate B 执行记录

> 状态：`GATE-B IMPLEMENTED · AWAITING_SUPERVISOR_REVERIFICATION`（执行侧核验稿，待监理复验确认）
>
> 基线：`64d040ebf2c8a10404f6ad8aae328a076babfc08`
>
> Gate A 冻结 manifest：`14fed12141dc3b277c09c878a2a30ef71b445ce8ea31457c0122b403aeb48a06`

## 1. 正式运行链与版本策略

新任务统一调用 `resolve_account_editorial_context(...)`，生成
`account-editorial-resolution-v1`。该结果一次解析、整对象冻结，并由下列消费者共同使用：

`ContentService → PublicationContractV3 → content-context snapshot → WriterRequestV3 →
DeepSeek adapter / deterministic stub`。

当前新任务 lens 为 `account-editorial-lens-v4`，产品键精确覆盖 ADR-013 的 P1—P5。V1—V3
类和解析分支保留原字段与原版本，不在读取时升级；修订和平台改编只搬运冻结的
PublicationContract，不重新读取当前画像。V4 只允许账号语义改变观察角度、判断顺序、受众
关系与收束方式；账号画像不是人物、经历、商品、门店、媒体或组织资格的事实来源。

五个稳定降级码为：

1. `unsupported_content_product`
2. `account_profile_missing`
3. `account_profile_identity_incomplete`
4. `account_profile_not_confirmed`
5. `brand_context_incompatible`

解析结果始终返回 `{applied, contract_version, lens/editorial_permission,
degraded_reasons[], source_refs, source_digest}`，不存在静默 `None`。任务冻结快照和现有
`task detail/context_basis` 只投影脱敏状态、原因、品牌关联状态与族名，不暴露画像全文、内部
Prompt、未授权素材元数据或数据库结构；本 Gate 未新增 React 页面。

## 2. P1 商品决策合同

P1 新增 `product-decision-basis-v3`：合法选定一件商品且有足够已确认事实时，冻结来源包
digest、事实引用、J 判断引用/版本、适用条件及合同 digest，并把同一依据送入 WriterRequest。
正式 ProductFact 继续只消费既有已确认事实链，候选价格、效果、性能、精确工艺与 P/C/R
信息不会因进入 P1 而升格。

- 未选择商品：P1 仍成立，可使用 `audience_relationship` 或 `brand_stance` 自然路径；仅
  `product_expertise` 不可用。
- 明确要求基于商品但商品多选、缺失适用条件或事实不足：失败关闭并要求澄清，不生成伪商品建议。
- 已选择且依据充分：`product_expertise` 可 applied，WriterRequest 收到冻结依据。

## 3. 七族品牌关联合同

| 路径族 | 类型化来源 | applied 必需资格引用 | 正向证据锚点 |
|---|---|---|---|
| `product_expertise` | `product_decision_basis` | 已消费商品事实引用 | `ContentService._brand_relevance_evidence` |
| `existing_series` | `series_episode` | 冻结系列及历史版本引用 | `ContentService._brand_relevance_evidence` |
| `audience_relationship` | `account_profile` | 已确认画像版本与 digest | `resolve_account_editorial_context` |
| `brand_stance` | `account_profile` | 已确认画像版本与 digest | `resolve_account_editorial_context` |
| `brand_visual` | `brand_visual_qualification` | `media_ref` | `assert_brand_relevance_evidence` |
| `local_trust` | `local_trust_qualification` | `organization_ref` | `assert_brand_relevance_evidence` |
| `organization_people` | `organization_people_qualification` | `organization_ref`＋`authorization_ref` | `assert_brand_relevance_evidence` |

每个 applied path 冻结 family、source object type、source ID、version、digest、actual consumed
refs，以及适用的组织/授权/媒体引用。必要引用被删除或来源类型错误即失败关闭；画像自称本地、
店员或组织成员不能生成后三族，ProductFact 不能自动生成品牌视觉资格。没有自然路径时保留普通
内容交付，显式标记 `brand_relevance_state=degraded`、
`demonstration_eligible=false`，不硬插商品、不加品牌式结尾、不改变生活题材。

七族合同能力成立；后三族的正式组织、素材和人物资格由 Gate C 承重验证。

## 4. 确定性实证

`tests/test_gateb_semantics.py` 覆盖：

- P1—P5 账号语义正向消费；五个降级码逐项正反例及快照/API 脱敏投影；
- 相同自然输入、事实、平台、内容产品和资源，仅切换 H01/H03/S02，central job 与事实引用
  不变，观察顺序、回应姿态、受众关系或允许立场至少两个维度实质变化，profile ID/digest
  随账号变化；无账号专用固定成稿或测试卡分支；
- P1 有商品、无商品、明确商品但依据不足三条路径；
- 七族逐族装配、实际消费引用、后三族资格反证、无自然路径与 topic fidelity；
- 一条零模型正式纵向：创建合同 → 冻结解析 → PublicationContract → WriterRequest →
  deterministic stub 捕获 → 快照/context_basis 回读；版本和 digest 一致；
- 画像后续变化不污染既有任务，平台改编继续搬运冻结账号合同。

Gate B 专属脚本：

- `scripts/gateb/assert_gateb_scope.py`
- `scripts/gateb/assert_gateb_semantics.py`
- `scripts/gateb/assert_gateb_no_secrets.py`

## 5. 诚实边界

- 已实现：账号语义正式消费、P1 商品决策合同、七族类型化合同、显性降级和脱敏读取投影。
- 尚未实现：Gate C 的组织作用域、生命周期、人物授权与媒体资格正式执行。
- 未导入 Gate A 素材、未创建十账号、未接触生产或 SSH、未调用模型、未制作媒体母版。
- CI 承担其实际运行的工程测试和回归门；若 workflow 未显式调用 `scripts/gateb/**`，Gate B
  专属脚本只由本地门承重，不宣称远程覆盖。
