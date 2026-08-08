# BRAND-MATRIX-01 · Gate C 执行记录

> 状态：`GATE-C IMPLEMENTED · AWAITING_SUPERVISOR_REVERIFICATION`
> （执行侧核验稿，待监理复验确认）
>
> 基线：`5aa37d65168ab7fe2277ce4fbb8d27a9a41a353a`
>
> Gate A 冻结 manifest：
> `14fed12141dc3b277c09c878a2a30ef71b445ce8ea31457c0122b403aeb48a06`

## 1. 增量迁移与兼容策略

唯一新增迁移为 `20260818_45_brand_scope_authorization.py`：

- schema revision：`20260817_44 → 20260818_45`，只前向扩展；没有 `DROP`、删数据、缩窄类型
  或数据库降级。
- `brand_publication_projections` 仅新增合同版本标识。该表已有的 tenant、brand、version、
  status、digest 不重复建设。
- 不可变投影条目新增 `visibility_scope`、`scope_organization_ids[]`、`effective_at`、
  `expires_at`、`authority_class`、`claim_key`、`scope_contract_version`，以及结构化冲突身份所需
  的 `semantic_subject_type/semantic_subject_id`。
- 新增六张租户表：`brand_feedback_observations`、`content_authorizations`、
  `content_authorization_reservations`、`content_authorization_events`、
  `brand_relevance_qualifications`、`brand_publication_claim_conflicts`。全部启用并强制 RLS；
  治理事实和事件采用 append-only 或受限状态转换。
- 存量投影和条目继续按 V1 解释为 `brand_all`、无到期时间；旧 V1 digest 算法、旧快照及旧
  digest 不增加新字段、不原地升级。新建 scope-aware 投影使用
  `brand-publication-projection-v2`，V2 digest 纳入发布角色、正文、来源、作用域、时效、权威
  类和 claim 身份。
- `downgrade()` 明确 fail-closed，拒绝删除作用域、冲突、反馈或授权历史。本 Gate 未执行
  database downgrade，也未用 `stamp`、`IF NOT EXISTS` 或空 downgrade 伪造回退。

迁移兼容验证按修订合同执行：从 schema 33 建兼容夹具并升级至 44，记录 V1 digest；再执行
44→45，验证旧读取和旧快照在新 schema 上仍按 V1 工作；再次执行 upgrade head，由 Alembic
确认 head 已是 45。新表和新列不被旧读取路径误消费。

## 2. 正式读取路径

改造前，正式任务读取把数据库条目无条件改写/过滤为 `brand_all`。改造后，唯一执行组织只
来自：

`COALESCE(carrier_of_account_id, id) → root logical account.control_organization_id`

读取不使用登录用户组织、账号名、组织名、画像、文件名或备注猜测作用域：

- `brand_all`：仅同 tenant、同 brand 可见；
- `headquarters`：根逻辑账号的 `control_organization_id` 必须与指定 company 精确一致；
- `organizations`：指定组织及其登记后代可见，兄弟区域和兄弟门店不可见；
- 生命周期由数据库服务端时钟冻结为 `task_context_as_of`，新任务只选择
  `effective_at <= as_of < expires_at`（无 `expires_at` 时持续有效）。

选择结果把作用域、时效、权威类、claim 身份、合同版本和 digest 一起冻结进 V2 条目、任务
快照及 BrandContextPacket。修订、历史回读和平台改编重放原冻结值，不用当前时间或当前资料
重新解释旧任务。同一失败请求安全重试时，只有其余冻结上下文完全一致才重放原可信时间；
账号、资料、商品或作用域发生真实变化仍失败关闭。

## 3. 冲突、生命周期与观察层

冲突只依据 tenant、brand、结构化 subject/type/id、`claim_key`、同级 `authority_class`、
重叠组织作用域和重叠有效窗口判定，不使用标题、关键词、文本相似度或模型：

- 总部正式品牌/商品 claim 优先于区域/门店普通资料，普通资料不能污染正式事实；
- 明确本地 claim 不被总部资料无条件覆盖；
- 同级、同 claim、重叠作用域和时段且值/source digest 不同，登记 `needs_review`；
- 不同 claim、非重叠作用域或非重叠时段不误报；
- `needs_review` 不能成为 confirmed projection，也不能被实际需要该 claim 的任务或 Writer
  消费；不相关 claim 不阻断普通任务。

生命周期测试覆盖生效前一瞬、生效边界、失效边界、无限期，以及资料到期/升级后旧任务仍重放
原版本。反馈只写入租户级 `brand_feedback_observations` 候选观察层；数据库约束和触发器共同
拒绝 observation ID 直接成为 BrandFact、ProductFact、J/G 或正式 projection 来源。观察
记录不可原地升级或修改。

## 4. 人物授权与任务谱系

`organization_people` 永远要求完整有效授权；`local_trust` 只有涉及具体人物、第一人称经历、
原句、肖像、声音或个人服务事件时才要求授权。气候、商圈、地址、营业时间和匿名高频问题等
机构型本地资料只要求组织作用域、来源、版本和生命周期。画像、账号名及 ContentRole 不能
制造人物资格。

授权合同冻结 authorization ID、人物/身份引用、tenant/brand/logical account/organization
作用域、允许来源 digest、允许用途、single-use/reusable、时效、版本及 digest。单次授权按
任务谱系执行：

`available → reserved(task/run) → consumed(task_lineage)`；失败为
`reserved → released`。

两条独立 fixture 均验证：首个 V1 成功只核销一次；同任务 V2、历史回读和谱系派生不重复
核销；另一独立任务拒绝；失败释放后可重新使用。预留使用数据库行锁并发互斥，V1 版本提交与
核销在同一事务内；事件记录真实 actor 与数据库时间，核销历史不删除。

## 5. 所有权与隔离证据

两名自然人可分别操作同一根逻辑发布账号，但 `created_by` 所有权边界保持不变。各自创建、
修订、保存/采用自己的任务；活动、版本和授权事件记录真实操作者，同时 logical account ID
保持一致。用户 A 读取、修订或保存用户 B 的任务继续失败关闭，本 Gate 没有暗中引入跨用户
协作共享。

四级隔离分别由不同层承重，不把 RLS 与业务作用域混称：

| 层级 | 承重机制 | 反证结果 |
|---|---|---|
| tenant | 新表 `FORCE RLS`，应用角色 NOBYPASSRLS | 跨租户拒绝 |
| brand | tenant+brand 复合外键及显式应用查询 | 同租户跨品牌结果 0 |
| region | 根逻辑账号控制组织、登记祖先链及查询过滤 | 兄弟区域结果 0 |
| store | 条目级组织集合、登记祖先链及查询过滤 | 兄弟门店结果 0 |
| 正向 | `organizations` 指定组织及合法后代 | 本组织/后代可见 |

## 6. 测试与断言锚点

- `tests/test_gatec_semantics.py`：V2 digest、结构化权威/冲突、生命周期四边界、机构型
  local_trust、涉人授权、冻结版本/时钟。
- `tests/test_gatec_postgres.py`：根逻辑账号多组织读取、tenant/brand/region/store 正反隔离、
  冲突 `needs_review`、观察层变红、两条单次授权谱系、双用户所有权。
- `tests/test_ux03_gate_d.py`：44 兼容夹具前向升级、旧 V1 digest/读取/快照、新表 FORCE RLS、
  第二次 upgrade head。
- `tests/test_ui06_api.py`：失败请求在冻结上下文不变时安全重试，防止可信时钟破坏幂等重放。
- Gate C 专属门：`assert_gatec_scope.py`、`assert_gatec_semantics.py`、
  `assert_gatec_no_secrets.py`。

最终本地门和 workflow_dispatch 四查以推送后的执行报告为准；若 CI workflow 未显式运行
`scripts/gatec/**`，专属断言只由本地退出码承重，不宣称远程 CI 覆盖。

## 7. 诚实边界

- Gate C 只完成机制和本地 fixture，没有导入 Gate A 的 31 条知识、10 个账号或两条真实
  单次授权；没有把 fixture 当成品牌事实。
- 尚未生产验证，未连接生产/SSH，未调用模型，未制作媒体母版，未修改 frontend。
- Gate D 才负责隔离环境真实导入、AMD 修订单和八剧本重演；数据库不降级条件下的真实应用
  版本往返回退继续由 Gate D/E 承重。
- 唯一下一动作：监理独立复验 Gate C；通过前不得写 `COMPLETE / PASS`。
