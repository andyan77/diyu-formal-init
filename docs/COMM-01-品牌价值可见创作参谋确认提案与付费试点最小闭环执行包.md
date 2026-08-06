# COMM-01 执行包：品牌价值可见、创作参谋、确认提案与付费试点最小闭环（完整修订草案）

- 状态：`DRAFT-FOR-REVIEW · REVISION-4`（本文件为完整修订草案，待守护审查；根目录
  `MILESTONE.md` 仍是唯一里程碑真源。本文件落盘不自行改变 TENANT-01 或任何 successor 状态）。
- 修订记录：REVISION-3（2026-08-06）落实 founder 对审查保留项的裁决——R1=选项 a
  （B 门前置建设 + 时间盒 + 最低裁剪清单，见 D-COMM-05a/05b）；R2 v3 历史回归口径
  （见 B3 与 §十三）；R3 提案字段消费者规则（见 B1.1）；§七 编号与 UX-04R 对齐。
  同批定名：去除文件名"-完整修订版"后缀，`937a881` 两份原稿自工作区删除（经 git 历史可追溯）。
- 修订记录：REVISION-4（2026-08-06）落实 founder 交互架构裁决 D-COMM-07——A7 重构为
  "有界交互编排器 + 内容创意能力"两层；自由对话取有界口径（选项甲）；主动引导为 A7
  首要产品目标；interaction_mode 分层修正；§八 编号残留修正（F→FE）。
- 配套文件：[UX-04R 前端产品化增量与工程边界执行包](UX-04R-前端产品化增量与工程边界执行包.md)。
- 立项依据：founder 2026-08-06 会话裁决，以及其后对品牌知识无感、用户冷启动无头绪、
  “参谋先于生成器”、标准制作交付包与前端产品化缺口的连续审查结论。
- 前置证据：2026-08-06 四路只读核查（生成合同 / 选题机会 / 前端工程 / 验收与规模文档），
  证据等级 `static_verified`；执行任一工作项前必须按 E7 纪律以 live git 与当前运行环境复核。
- 收费与额度原则：付费试点可以通过线下合同、报价单、发票、转账或其他人工方式收取费用；
  **本里程碑不建设计费系统、套餐系统、额度系统、积分/点数、在线支付、自动开票或用量自动停机**。
  具体金额、付款周期与试点范围由商务文件另行约定，不成为本包的软件交付项。
- 继续有效的上位裁决：
  [ADR-027](架构决策/ADR-027-内容表达空间目录与用户控制边界.md)、
  [ADR-014](架构决策/ADR-014-内容生成运行语义与评测分层.md)、
  [ADR-015](架构决策/ADR-015-首期平台媒体成品与跨平台重编译.md)、
  D-030 / D-032（首期交付文字型制作包，不生成图片、音频或视频文件）。

---

## 一、裁决记录（founder 2026-08-06，修订整合）

> 以下裁决在本包守护审查 PASS 后生效。审查 PASS 前，既有冻结与停止线继续按原文有效。

### D-COMM-01 · COMM-01 是 TENANT-01 之后的下一条主线

founder 批准 COMM-01 作为 TENANT-01 之后的商业化产品主线。TENANT-01 `REVIEW → CLOSED`
不由本草案自行执行；须在两份执行包同批审查通过后，由主控按 §十一单独落盘，历史证据、失败、
未证明项与权威证据根不得被改写。

### D-COMM-02 · 有界解除「不启动 UX-04」冻结

不批准目录整体重构、两大前端巨文件专项重写或全局设计系统推倒重建；仅解冻配套
UX-04R 所列的绞杀者式增量：新能力按新 feature 边界落地，旧代码只在被触碰时拆出，
旧路径保留兼容并逐步被替代。

### D-COMM-03 · 采用/批准不落为覆盖式状态机，改为追加式决策事件

既有“不新增审批状态机”边界继续有效。允许建立**单级人工决策事件**，但不得直接把
`draft / approved / exported / published` 做成互斥状态并覆盖内容版本。内容正文和版本仍不可变；
批准、撤回批准、导出、采用、放弃和人工标记发布全部追加为事件，服务端只派生只读状态投影。

允许事件：

```text
content.adopted
content.abandoned
content.approved
content.approval_revoked
content.exported
content.published_manual
content.publication_revoked
```

明确继续禁止：多级审批链、BPM、指定多人顺序审批、自动发布、生产 Reviewer、第二模型投票、
模型 fallback、通用规则引擎。

### D-COMM-04 · 不建 Brief 物理表，但建立第一等 `CreationProposalV1` 运行合同

继续遵守 M5-K：不新增 `content_briefs` 表或同义长期领域对象。但“不建表”不等于“不需要 Brief”。
本包允许建立瞬时、用户可见、可编辑、服务端签名的 `CreationProposalV1`：

```text
参谋讨论 / 机会卡
→ CreationProposalV1
→ 服务端签发 proposal_token
→ 用户确认
→ 服务端验证 token 与作用域
→ 原样冻结进 business_tasks.content_context_snapshot
→ 原子建立 task / run
```

`CreationProposalV1` 在确认前不建立 task、run、version，也不成为长期业务实体；刷新或会话丢失时
允许重新编译提案，不伪造已保存状态。

### D-COMM-05 · 最低可执行制作包前移为试点签约前门槛

“参谋是入口、确认提案是合同、制作包才是交付”成为本里程碑的产品主链。只有品牌依据与确认卡，
仍不足以证明产品已从文案生成器升级为品牌内容工作台。因此 C1、C3 与最小 C2 不再推迟到试点中；
最低结构化制作包必须在设计伙伴开始使用前上线。

高级景别、精确镜头秒数、逐镜音效、复杂转场与完整评论协作仍可在试点中按反馈迭代。

#### D-COMM-05a · R1 裁决（founder 2026-08-06）：选项 a——先建完、再启用试点，附时间盒与强制裁剪

- 不设"受监督首用"旁路：任何设计伙伴的真实使用均须等待 B 门放行；
- **时间盒**：B 组首个 Brief 立项时由 founder 设定 B 门目标日期（以周为单位）；超期未放行
  即触发范围复审，只允许两种出路——按 D-COMM-05b 清单进一步裁剪，或由 founder 重新裁决
  改走选项 b（受监督首用）。不允许无限期顺延。

#### D-COMM-05b · 最低裁剪清单（强制，防"最低包"回涨）

- `WriterOutputV4` 只承载 `script_blocks` 与 `subtitle_cues`；`audio_plan`、`editing_plan`、
  `duration_hint` 首版只能为 `compiler_derived` / `suggested_needs_review`，不进 Writer 合同；
- 景别、精确镜头秒数、音效点位、转场节奏等 C2 高级项不得混入 B3 最低包；
- B6 测试用户可来自候选设计伙伴在售前/入驻准备期的真实员工，或按目标角色招募的外部用户；
  FE-00 原型走查与 B6 可用性门**复用同一批用户**（两轮记录分别留存），不重复招募。

### D-COMM-06 · 付费试点收费与使用范围采用线下人工管理，不增加工程量

试点费用、试点周期、包含账号、服务范围和支持方式由线下合同/报价单约定；收款、开票和对账
在现有财务流程中完成。产品不新增：

```text
价格页
自助购买
订阅套餐
席位计费
生成额度
点数扣减
支付回调
自动续费
自动发票
用量超限自动停机
```

如客户使用明显超出约定范围，由客户成功人员人工沟通调整，不由系统实施硬性额度门。

### D-COMM-07 · 交互编排两层架构、自由对话有界口径与主动引导原则

founder 2026-08-06 裁决：

1. A7 重构为两层——**有界交互编排器 `BoundedInteractionOrchestratorV1`**（意图识别、模式
   政策、能力检查、路由、任务政策）+ **内容创意能力 `ContentAdvisorCapabilityV1`**（原参谋
   定义降格为可调用能力之一）。交互模式 / 意图 / 专业能力 / 业务承诺四层在合同层分离；
2. 自由对话取**有界口径（选项甲）**：限品牌与内容相邻话题（系统说明、品牌知识问答、
   想法讨论、头脑风暴、创作概念解释）；通用写作/学习类请求说明边界并指路，不静默受理；
3. **主动引导是 A7 的首要产品目标**：编排与路由是手段，目的是解决"用户面对系统不知道
   如何下手、不知道系统能为我做什么、对自媒体创作没有概念"这一最大使用门槛（详 A7.0）；
4. 瘦身边界：`CapabilityRegistry` 为代码内静态类型表；`CapabilityHandoff` 合同推迟至第二个
   真实专业能力立项；意图枚举首期 ≤7 且逐一满足消费者规则（与 R3 同理）。

---

## 二、产品定义、交付范围与停止线

### 2.1 一句话产品定义

> 笛语是一个以企业品牌知识为依据，先帮助用户想清楚“做什么、为什么这样做”，再把确认方案
> 编译为可执行内容制作包的品牌创作参谋与内容生产工作台。

### 2.2 唯一产品主链

```text
了解系统 / 获取建议
→ 有界交互编排（智能 / 自由对话 / 内容创意）
→ CreationProposalV1（用户确认）
→ ProductionPackageV1（标准制作交付）
→ 修改与版本
→ 采用 / 批准 / 导出 / 人工发布
→ 品牌依据反馈
→ 管理员处理候选
```

### 2.3 三个阶段

```text
阶段 A  品牌价值可见 + 冷启动 + 有界参谋（正式商业演示门）
阶段 B  确认提案 + 最低制作包 + 决策事件 + 人类可用性（试点启用门）
阶段 C  付费设计伙伴运营 + 高级制作迭代（真实试点期）
```

### 2.4 本里程碑交付

- 品牌依据在创作前、制作中和成品后持续可见；
- 用户能够了解系统、获取选题、评估想法、比较方案并形成确认提案；
- 用户确认前不建立正式任务；确认后任务精确绑定同一份提案；
- 新成品以结构化制作包呈现，不再依赖字符串正则猜测；
- 视频至少具备平台、主题、内容形式、封面、制作步骤、台词、字幕、声音角色、素材清单、
  制作提示、发布配文和品牌依据；
- 图文至少具备平台、主题、页序、每页职责、页面文案、视觉/排版建议、素材、发布配文和品牌依据；
- 品牌资料问题进入租户管理员队列，系统能力缺口继续进入笛语运维队列；
- 采用、批准、导出、放弃和人工发布形成追加式事件；
- 付费试点具备入驻、支持、复盘、成功标准和退出/扩大规则，但不建设计费产品。

### 2.5 明确不交付

- 不做微服务拆分、Kubernetes、消息队列平台或通用 Agent 平台；
- 不自建图片/视频/音频生成，不自动发布；
- 不增加第二模型投票、生产 Reviewer 或模型 fallback；
- 不建 `CreativeBriefV1` 物理表；
- 不做九种以上内容形式，首期只做三种；
- 不做多级审批、评论线程、指定审阅人链和 BPM；
- 不做计费、套餐、额度、点数、支付或开票系统；
- 不把“系统建议”伪装成品牌事实，不把“参考过”伪装成逐句因果；
- 不承诺平台流量、排名、爆款、GMV 或自动提高销售。

---

## 三、事实基线（`static_verified`，执行前须 live 复核）

| # | 当前事实 | 证据锚点 |
|---|---|---|
| 1 | 冷启动机会与轻量计划已有后端服务、落库、端点、OpenAPI 和测试，当前前端未消费 | `src/brain/content_control_service.py:465-570`、`src/gateway/api/app.py:2786-2798` |
| 2 | 机会/计划前端曾存在后被 UI-04 重写删除，属于回归而非从未实现 | git `c0f2873 → 6710072 → 78183ec`、`frontend/test/fixtures.json` |
| 3 | 品牌上下文选择阶段保留 segment 级信息，最终用户投影只剩类别、布尔和计数 | `src/shared/content_snapshot.py:39-95`、`src/brain/content_service.py:2158-2178` |
| 4 | 当前流式阶段只有 received / compiling_context / generating / validating / finalizing，无 `context_selected` | `src/brain/content_service.py` 阶段 emit 路径 |
| 5 | Writer 最新合同只有 title / natural_guide / creative_body / publication_caption 四字段 | `src/shared/writer_request.py:51-57,245-252` |
| 6 | 现有 V5 的分镜、字幕和观看链主要由同一 full_body 模板投影，尚不是逐镜可执行制作包 | `src/shared/delivery_compiler.py:599-607,751` |
| 7 | `VideoProductionBundle` / `GraphicProductionBundle` 与逐字段 provenance 已存在于内存，但不落库、不进 API | `src/shared/types.py:233-262`、`delivery_compiler.py:538-680` |
| 8 | 协作 Prompt 明文“不追问题材、观点、受众或结构”，“没想好发什么”可直接 ready | `src/tool/llm_gateway/deepseek.py:4243-4273` |
| 9 | `ContentControlService.opportunities()` 已可基于账号画像、受众、商品、素材和个人偏好给出机会卡 | `src/brain/content_control_service.py` opportunities 路径 |
| 10 | 现有 unmet capability 通道面向笛语运维，不适合直接承接租户品牌事实纠错 | `src/gateway/api/app.py` unmet endpoints、`frontend/src/app/OpsApp.tsx` |
| 11 | 普通用户帮助页暴露 FT、SHA、Schema 与“58 项正式支持面” | `frontend/src/components/CapabilityGuide.tsx`、`ProductShells.tsx` |
| 12 | 导出当前仅前端 toast；`content_versions` 无采用/审批状态列 | `frontend/src/app/CreatorApp.tsx`、初始 content_versions migration |
| 13 | 管理端已有内容尝试、成功、失败、修改、系列和 Token 等统计，`provider_usage` 明确不是完整计费总额 | `src/infrastructure/workbench_repository.py:1172-1219` |
| 14 | 前端手工路由、整页刷新、巨型组件、正则成品解析、重复 CSS 根变量等问题已被核实 | 详见配套 UX-04R §三 |
| 15 | 当前 fresh acceptance `23/26` 恰好达到下限，任何协作/Writer/制作合同变更均不得沿用旧结论 | `MILESTONE.md:34-37` |

---

## 四、阶段 A：品牌价值可见、冷启动与有界创作参谋（A1—A7）

> 放行定位：A 组全部通过后，才允许把系统作为“品牌创作参谋”进行正式商业演示。
> A1/A3/A6/A7 为中—重项；A2/A4/A5 为轻—中项。

### A1 · `context_selected` 与安全条目级品牌依据（中）

- 服务端完成任务相关上下文选择后，新增结构化流式事件 `context_selected`；同一投影进入
  `ContentVersion.context_basis.items[]`。
- 每条公开依据字段严格白名单化：

```text
basis_ref            服务端生成的无语义公开引用；不等于 segment id 或 digest
kind                 brand_fact / product_fact / expression_constraint / creative_method / account_identity
usage_mode            direct_fact / product_fact / expression_guard / creative_reference / account_identity
title                 用户可理解标题
summary               本次可读摘要
source_label          来源名称
source_version        来源版本
impact                本次起到的作用
content_locations[]   仅 direct_fact / product_fact 可有
```

- `basis_ref` 必须：
  - 先与 tenant、account、request/proposal 和本次公开投影作用域绑定；
  - 内容完成后，同一 `basis_ref` 原样冻结进 task/version 快照；
  - 不可反推出底层 segment、digest 或原始路径；
  - 只用于反馈与界面引用，不授予读取底层来源原文的权限。
- 诚实边界：
  - `direct_fact` / `product_fact` 才能绑定具体成品位置；
  - `expression_guard` 只说明“本次受该边界约束”；
  - `creative_reference` 只说明“本次参考”；
  - `account_identity` 只说明观察位置与受众关系。
- 不增加第二次模型调用；公开投影从已有选择结果确定性生成。
- 验收：流式事件与成品投影逐项一致；载荷白名单测试；grep 无 segment/digest/sha/prompt；
  旧成品无 items 时兼容现有类别摘要。

### A2 · 品牌依据常驻展示（轻）

- 创作前显示“当前品牌上下文”与“本次锁定依据”；
- 确认提案中显示将使用的依据和不会使用的事项；
- 制作包中常驻显示每条依据、作用、来源版本、缺口与反馈入口；
- 不再把核心品牌价值默认藏在 `<details>` 中。
- 移动端允许在“参谋 / 提案 / 制作包”任一阶段一键打开，不得只在成品页深层可达。

### A3 · 今日工作台、机会卡与轻量计划（中）

- `/user` 成为唯一“今天”工作台，首屏提供：

```text
了解笛语
帮我找选题
评估一个想法
直接制作
```

- 消费现有 opportunities/plan 能力，展示 2—5 张动态机会卡。每卡包括：
  - 选题；
  - 受众回报；
  - 推荐原因；
  - 推荐平台/形式（建议，不强制）；
  - 可用品牌依据；
  - 可用商品/素材；
  - 当前缺口；
  - 制作难度；
  - “讨论这个方向”与“形成提案”。
- 浏览、刷新机会、保存/调整计划均不建立 task/run/version。
- 未选择发布账号时，不显示虚构机会；先提供账号选择和“了解系统”入口。

### A4 · 帮助与技术诊断分流（轻）

- 普通用户帮助只回答四件事：能做什么、本次会用什么、当前缺什么、下一步怎么做；
- FT、SHA、Schema、能力矩阵和运行证据移至租户管理员“技术诊断”二级入口；
- 普通用户任何首屏和主任务页不得出现内部里程碑术语。

### A5 · 商业演示脚本（轻，doc-only）

形成五场景固定演示：

1. 系统知道当前品牌什么、不知道什么；
2. “我不知道发什么”时返回差异化方案，而非直接成稿；
3. 同一输入下，品牌依据如何改变方向与表达；
4. 明确商品事实边界，缺资料时不猜；
5. 从 CreationProposalV1 到标准制作包，再形成 V2。

通用 AI 对比只存在于受控演示脚本，不在产品内提供关闭品牌约束的开关。

### A6 · 品牌依据反馈与责任分流（中：schema / API）

不得继续把品牌资料问题全部塞入 `unmet_capability_requests`。

#### A6.1 租户品牌资料反馈

新增 append-only `brand_basis_feedbacks`（或同等有界对象），字段至少包含：

```text
feedback_id
 tenant_id / brand_id / account_id
 task_id / content_version_id
 basis_ref
 feedback_type     incorrect / outdated / irrelevant / missing
 user_note
 created_by / created_at
 handling_status   received / reviewing / resolved / rejected
 handled_by / handled_at / resolution_note
```

- 普通内容用户可提交；
- 租户管理员在“品牌反馈”队列处理；
- 处理动作不能直接修改正式知识，只能：
  - 标记无需处理；
  - 建立资料补充任务；
  - 进入既有品牌发布候选流程；
- 历史任务依据永不追溯改写。

#### A6.2 系统能力缺口

“系统现在做不到某类媒体、内容形式或工具动作”继续进入现有 `unmet_capability_requests` 与 Ops。
平台运维不得代替租户管理员裁决品牌事实。

### A7 · 有界交互编排器与内容创意能力（中—重：新运行合同；依据 D-COMM-07）

> **首要产品目标**：解决真实用户最大的使用门槛——"面对系统不知道如何下手、不知道系统
> 能为我做什么、对自媒体创作没有概念"。编排与路由是手段，主动引导是目的。

不另建通用 Agent 平台。A7 拆为两层：**有界交互编排器 `BoundedInteractionOrchestratorV1`**
（判断用户此刻想做什么、可以调用什么、走哪条路径）与**内容创意能力
`ContentAdvisorCapabilityV1`**（编排器可调用的一项专业能力，见 A7.5）。四层概念不得混淆：
交互模式（政策）≠ 意图（这句话想做什么）≠ 专业能力（谁来处理）≠ 业务承诺（是否建任务）。

#### A7.0 主动引导原则（guidance-first，产品级硬要求）

- **任何模式的任何回复不得是死胡同**：均以 `suggested_actions[]` 给出下一步入口；
- **边界拒答必须指路**：自由对话中收到通用写作/学习类请求时，说明边界并给出系统能做的
  最近替代入口（如"可以切换到内容创意，我先帮你形成方案"），不静默受理、不生硬拒绝；
- **"能做什么"必须有据**：对"系统能为我做什么 / 我现在能做什么 / 怎么开始"类输入，
  回答必须由**租户真实资料状态**确定性投影生成（账号画像、已确认商品事实数、素材数、
  发布投影条目数、当前缺口——数据源为既有 readiness 与 opportunities 输入），并用大白话
  表达（首现概念如"口播 / 图文页序 / 选题"须配一句解释），不得使用通用宣传文案或虚构能力。

**引导知识基座（系统凭什么给建议，founder 2026-08-06 补充裁决）——六层，逐层标注现状：**

| 层 | 内容 | 首期来源与现状 |
|---|---|---|
| 1 行业通用知识 | 自媒体内容运营专家方法论：选题方法、平台特性与节奏、内容形式与结构、表达技巧 | 首期由 Advisor prompt 合同与五轴表达目录承载；**GKB（行业领域通用知识库）只读接入属跨仓依赖，另立工作项单独裁决，不在本包隐式接入** |
| 2 租户品牌知识 | 发布投影（事实 / 边界 / 方法）、账号画像、商品事实、素材 | 已在仓（A1 同源投影） |
| 3 表达能力目录 | 五轴（题材 / 讲法 / 风格 / 形式 / 连续）：系统自身会哪些创作打法 | 已在仓（catalog-v1） |
| 4 能力与权限 | 当前用户资格、已启用能力、平台目标 | 已在仓（auth_grants + A7.3 注册表） |
| 5 运行状态 | 进行中任务、最近内容、系列前情、资料缺口 | 已在仓（readiness / tasks / opportunities 输入） |
| 6 用户个人 | 私人创作偏好、历史采用行为 | 已在仓（preferences；采用事件由 A5 补齐） |

**能力自评估（回答"能做什么"前必须先算）**：基于六层现状，把内容方向如实分为三类呈现——
**可做**（资料足以支撑）／**可做但受限**（说明缺什么、给补充入口）／**当前做不了**
（缺资格、资料或能力，指明去向）。用户输入落在哪一层就由哪一层回答：行业方法问题 ≠
品牌事实问题 ≠ 系统能力问题，不得混层作答。

**分层引用诚实性（硬边界）**：行业通用方法论建议必须标注"行业通用参考"；品牌事实必须
带来源版本；**不得把行业通用知识冒充品牌确认事实**；hard / performance 类主张不得引用
专家合成来源（沿用 GKB source policy 既有红线）。

#### A7.1 `InteractionModeV1`（用户可选交互模式）

```text
auto              智能（默认）：自动识别意图并路由到允许的只读/参谋型能力
free_chat         自由对话：有界口径（选项甲，founder 2026-08-06 裁决）——限品牌与内容
                  相邻话题（系统说明、品牌知识问答、想法讨论、头脑风暴、创作概念解释）；
                  通用写作/学习类请求按 A7.0 指路；本轮不自动形成提案
content_creative  内容创意：优先路由内容创意能力，保持自然对话，不变成强制表单
```

- 模式是**交互政策**，不是业务承诺；任何模式下建立正式任务都只经 A7.6 承诺门；
- 分层修正：现有 `interaction_mode: auto/conversation/generate` 把交互政策与业务承诺混在
  同一枚举（`src/gateway/api/contracts.py:64-65`、`app.py:2974-2975`）。本项将其分离——
  `generate` 的承诺语义由既有 `CreationIntentGate` 与 B1 提案确认承接，旧字段保留兼容
  映射、不破坏既有调用方。

#### A7.2 `IntentProjectionV1`（意图投影，首期 ≤7 个）

```text
general_conversation / understand_system / query_brand_knowledge /
get_recommendations / evaluate_or_compare / prepare_proposal / active_revision_followup
```

- 每个意图必须有真实路由差异（与 R3 消费者规则同理）：无差异的枚举删除；
- 确定性信号优先（沿用 `CreationIntentGate` 确定性判定先例），必要时才由模型做有界分类；
- 模型置信度只用于内部诊断，**永不**授权权限判断、task 创建、提案确认或资料使用。

#### A7.3 `CapabilityRegistryV1`（代码内静态类型表，非平台）

首发五项：`general_conversation / system_guide / brand_knowledge_answer /
content_advisor / proposal_compiler`；每项声明
`capability_id / version / accepted_intents / required_permissions / allowed_modes / task_policy`；
`task_policy ∈ {no_task, proposal_only, requires_proposal_confirmation, active_task_revision}`。
不做数据库注册表、插件市场或动态 Agent 平台；`CapabilityHandoff` 合同**推迟**——首发
"能力未启用"只需一句有界说明（不静默降级为普通文案），待第二个真实专业能力立项时再补合同。

#### A7.4 `RouteDecisionV1` 与路由优先级（冻结）

响应携带 `requested_mode / resolved_mode / intent / capability_id / task_policy /
reason_code / suggested_actions[]`。优先级冻结为：

```text
可信身份与权限 → 用户显式模式 → 显式意图 → 确定性信号 → 有界模型分类
→ 能力启用与资料检查 → RouteDecision → 调用能力 → 独立承诺门（A7.6）
```

用户显式选择"自由对话"后，识别到创作意图也不得静默形成提案或任务；智能模式的路由结果
必须以轻量方式对用户可见（如"智能分流 · 已使用内容创意能力"，可一键保持 / 切换）。

#### A7.5 内容创意能力 `ContentAdvisorCapabilityV1`

原"有界创作参谋"定义整体降格为编排器可调用的一项专业能力，其意图、响应与边界如下。

##### A7.5.1 支持的四类用户意图

```text
understand_system       了解系统与当前品牌能力
get_recommendations     获取选题/风格/平台/形式建议
evaluate_or_compare     评估一个想法或比较两个方案
prepare_proposal        形成 CreationProposalV1
```

##### A7.5.2 允许的结构化响应

```text
advisor_message
recommendations[]       2—5 个差异化方案
comparison              比较维度、建议结论、取舍
strategy_question       至多一个，可跳过
knowledge_answer        系统知道什么、依据是什么、缺什么
gaps[]                  当前阻断或非阻断缺口
proposal_candidate      可以进入 B1 的提案候选
suggested_actions[]     继续聊 / 换一批 / 比较 / 形成提案
```

##### A7.5.3 能力硬边界

- Advisor 请求不建立 task、run、version；
- 不输出完整发布正文或伪装成最终制作包；
- 不直接写品牌知识、商品事实、账号画像或用户偏好；
- 不执行自动发布、素材上传或权限变更；
- 最多一个策略问题，且必须可“采用系统建议”跳过；
- 硬性事实问题仍只限现有不可替代事实边界；
- 所有推荐说明“为什么适合当前账号”并绑定公开 `basis_ref`，但不声称逐句因果。

##### A7.5.4 能力级验收

- 输入“我不知道今天发什么”不建三表，返回至少两个实质不同方案；
- 输入“这个想法适合抖音还是小红书”返回比较，不直接成稿；
- 输入“系统知道我们的品牌什么”返回可核对的品牌知识摘要和缺口；
- 输入“先聊聊，不生成”不得弹出制作任务；
- Advisor 失败不留下半任务，用户原输入可继续使用。

#### A7.6 任务承诺分离（不可让渡）

沿用既有 `CreationIntentGate`（确定性、用户可观察）与 B1 提案确认：无论模式与路由结果
如何，task / run / version 只在用户确认"按此方案制作"后建立；意图识别器与编排器**无权**
授权任何业务动作（建任务、存版本、改资料、上传素材、改权限、发布）。

#### A7.7 编排级验收矩阵（节选，完整矩阵进执行 Brief）

| 模式 | 输入 | 必须结果 |
|---|---|---|
| 任意 | "这系统能干嘛 / 我不会用 / 怎么开始" | 返回基于当前租户真实资料的可做清单与起步动作，不建任务 |
| 智能 | "我不知道今天发什么" | 路由内容创意，≥2 个实质不同方案，不建任务 |
| 智能 | "系统知道我们品牌什么" | 路由品牌知识回答，内容可与管理端资料核对 |
| 自由对话 | "帮我生成完整内容" | 提供"切换内容创意"动作，不静默建任务 |
| 自由对话 | 通用写作/学习请求 | 说明边界 + 最近替代入口，不静默受理、不生硬拒绝 |
| 内容创意 | "采用第 2 个方向" | 形成提案候选，不建 task |
| 智能 | 请求未启用能力 | 有界说明，不静默降级为普通文案 |
| 任意 | 意图无法可靠判断 | 保持自由交流或问一个可跳过的问题 |

---

## 五、阶段 B：确认提案、最低制作包、人工决策与可用性门（B1—B6）

> 放行定位：B1—B6 全部通过，且阶段 C 的试点运营材料就绪后，才允许真实设计伙伴开始使用。
> B1/B2/B3/B4 为重活，须独立 Brief、founder 显式授权与守护三关。

### B1 · `CreationProposalV1`：第一等生成前确认合同（重）

#### B1.1 数据合同

`CreationProposalV1` 至少包含：

```text
proposal_version
proposal_token
expires_at
user_goal
topic
topic_origin
audience_need
content_objective
core_message
selected_angle
platform_target
media_format
content_form
speaker_plan
tone_ids
mechanism_id
duration_target
production_level
brand_basis_refs[]
product_basis_refs[]
material_refs[]
must_include[]
must_avoid[]
known_gaps[]
accepted_assumptions[]
strategy_question? / system_recommendation?
```

**字段消费者规则（R3，founder 2026-08-06）**：提案中每个字段必须有至少一个真实下游消费者
（`ProductionPlanV1` / `WriterOutputV4` / `DeliveryCompilerV6` / 前端 Proposal 或 Package
界面之一确实读取并影响产出）。无消费者的字段必须删出合同，不得为"显得周全"保留；
`tone_ids` / `mechanism_id` 必须绑定既有五轴表达目录的 stable_id，不另立第二套词表。
B1 交付物包含**逐字段消费者映射表**，并对 `duration_target`、`content_form`、`must_avoid`
等关键字段做"修改 → 下游产出可观察变化"的抽样验证。

#### B1.2 签名与防漂移

- 服务端按 canonical JSON 计算 proposal digest 并签发 `proposal_token`；
- 客户端确认时提交 proposal 文档与 token；
- 服务端验证：签名、用户/租户/账号/平台作用域、过期时间、品牌发布版本、账号画像版本、
  素材和商品版本；
- 任一真源版本已变化，确认失败并要求重新生成提案；
- 验证通过后，同一 proposal 文档原样写入 `content_context_snapshot`，并在同一事务中建立 task/run；
- 不允许确认后服务端再次静默换题、换平台、换形式或换依据。

#### B1.3 用户交互

- 用户可逐项修改提案；每次修改由服务端重新校验并签发新 token；
- “直接制作”也先生成一张系统默认提案，熟练用户一键确认；
- 主动作唯一为“按此方案制作”；
- 次动作：继续讨论、修改方案、采用系统建议、放弃；
- 确认前 task/run/version 计数必须保持不变。

#### B1.4 验收

- 提案所见内容与任务快照字节级/规范化摘要一致；
- 篡改 proposal 字段或跨账号重放 token 均失败关闭；
- 提案过期或依赖版本变化不会建立半任务；
- V2 修订沿用冻结提案，不重新读取今日设置改写历史；
- 受影响冻结验收子集必须 fresh rerun，不得沿用 `23/26`。

### B2 · 内容形式合同 `content_form-v1`（中）

首期只支持：

```text
single_narration        单人口播（默认）
structured_explanation  结构化解释
graphic_sequence        图文页序
```

- 默认单人口播采用“陈述 → 张力 → 依据 → 行动 → 收束”；
- 禁止用连续“你有没有发现 / 为什么 / 其实 / 那怎么办 / 答案是”构成默认骨架；
- Q&A、访谈、双人对话、小剧场不在首期正式制作合同中；用户明确请求时由 Advisor 说明当前边界，
  不得暗中生成伪问答；
- 扩展枚举必须另立工作项并补真实制作资源与验收。

### B3 · 最低可执行 `ProductionPackageV1`（重：Writer/Planner/Compiler/API/持久化）

#### B3.1 运行链

```text
CreationProposalV1
→ ProductionPlanV1（同一模型、独立结构合同；不是第二模型或 Agent 平台）
→ WriterOutputV4（脚本块与字幕提示）
→ DeliveryCompilerV6
→ ProductionPackageV1
→ 原子保存 ContentVersion + 结构化投影
```

**历史回归警戒（R2，founder 2026-08-06）**：本仓 v3 时期曾让 Writer 直接撰写媒体结构字段
（media_opening / subtitle_strategy 等），因产出为"形似分镜的段落散文"不可执行，才在
v4/v5 主动收窄为四字段。B3 重新引入 Writer 结构化输出是对该架构撤退的部分逆转，执行
Brief 必须显式对照该失败模式设计回归口径，至少包含：`script_blocks` 不得等价于把
`creative_body` 切段改名（逐块 purpose / linked_step_ids 必须有独立信息量）；
`subtitle_cues` 不得等于台词整块复制（须体现断句与屏幕长度约束）。

#### B3.2 来源状态

制作包中每一条制作信息必须带来源状态：

```text
confirmed_source        来自已确认事实、登记资源或用户明确输入
compiler_derived        服务端依据平台/形式/顺序确定性编译
suggested_needs_review  系统创意建议，需人工判断，不是品牌事实
unavailable             当前资料或能力不足，不能成立
```

这解决“无品牌真源就完全不做”和“把建议伪装成事实”两个极端。

#### B3.3 视频最低制作包

```text
overview
  platform / topic / audience_value / core_message
  content_form / speaker_plan / duration_target / production_level
cover
  title / first_frame / on_screen_text / source_status
production_steps[]
  step_id / order / purpose / duration_hint?
  visual_plan / action / script_block_refs[] / on_screen_text_refs[]
  resource_refs[] / audio_role / edit_note / source_status
script_blocks[]
  block_id / speaker / purpose / text / linked_step_ids[]
subtitle_cues[]
  cue_id / order / text / emphasis / linked_script_block_id
resource_checklist[]
  existing / needs_capture / optional / prohibited
 audio_plan[]
  voice / silence / music_role / effect_role / source_status
editing_plan[]
  pacing / transition suggestion / source_status
publishing_support
  release_caption / interaction / cover_title_options / AIGC reminder
brand_basis[] / gaps[]
```

- `duration_hint`、音乐角色、音效与转场在没有正式资源时必须标为 `suggested_needs_review`；
- 不得虚构演员、场地、商品、道具、音乐文件或环境声已存在；
- 不能再只写“镜头位置 N 承载原句”；每个 step 必须有明确目的、对应台词/字幕和资源条件。

#### B3.4 图文最低制作包

```text
overview
cover_page
pages[]
  page_no / purpose / heading / body / visual_plan / resource_refs[] / layout_note / source_status
full_caption
resource_checklist[]
layout_and_production
publishing_support
brand_basis[] / gaps[]
```

#### B3.5 DM01 结构化文字执行包

保持“不生成空间效果图”的边界，但输出结构化执行行：

```text
area / rail / product / quantity / facing / spacing / focus / substitute / execution_order
```

#### B3.6 持久化与兼容

- 结构化投影以 append-only jsonb 随 ContentVersion 首次插入；不得后补覆盖旧版本；
- 旧成品继续按 body 兼容读取；
- 新成品 API 返回 `production_package`；
- `outline/body` 继续保留作为人类可读导出与兼容路径；
- `visible_provenance` 扩展覆盖制作包全部字段并可重算。

#### B3.7 验收

- 新成品前端零正则猜标题；
- 视频制作包必须能找到平台、主题、形式、封面、步骤、逐块台词、字幕、声音角色、素材、剪辑、
  发布配文和品牌依据；
- 人工抽样确认制作步骤可执行且没有虚构资源；
- `suggested_needs_review` 不得渲染为“已确认”；
- v3 失败模式回归口径通过：切段改名 / 台词整块复制检测为 FAIL（机器可判 + 人工抽样双口径）；
- 受影响冻结验收子集 fresh rerun。

### B4 · 追加式内容决策事件与只读状态投影（重：schema）

新增 `content_version_decision_events`：

```text
event_id
 tenant_id / version_id / task_id
 event_type
 actor_id / actor_role
 metadata jsonb
 created_at
```

权限：

- 内容用户可：`adopted / abandoned / exported`；
- 首期 `approved / approval_revoked / published_manual / publication_revoked` 只允许租户管理员；
- 后续若需账号负责团队批准权限，另立最小授权工作项，不在本包隐式扩展。

服务端派生：

```text
adoption_state       none / adopted / abandoned
approval_state       none / approved
export_count
last_exported_at
publication_state    none / published_manual
publication_url?
last_decision_at
```

- 导出可以多次；
- 批准撤回不产生内容 V2；只有正文或制作包变化才产生新版本；
- 事件 append-only，内容版本行保持不可变；
- 无自动发布入口。

### B5 · 北极星、参谋漏斗与运营指标（中）

北极星：

> 每个活跃团队每周批准或实际采用的品牌依据内容数。

首期支撑指标：

1. 机会卡/参谋启动率；
2. 参谋到 CreationProposal 转化率；
3. 提案修改率；
4. 提案确认率；
5. V1 直接采用率；
6. 批准或采用率；
7. 放弃率；
8. 品牌依据反馈率；
9. 从首次登录到首份批准/采用制作包的时间。

内部诊断可继续展示 Provider Usage 估算消耗，但必须明确：

> 这是基于已记录 provider usage 的估算，不是完整计费总额，也不用于自动收费。

不建设新埋点平台；优先从 Advisor/Proposal/Decision 事件与既有 activity 汇总推导。

### B6 · 真实用户可用性门（硬放行条件）

至少 5 名非项目开发者、符合目标角色的用户，在无培训条件下完成任务：

- ≥80% 能在 `/user` 首屏找到“了解系统 / 找选题 / 评估想法 / 直接制作”；
- ≥80% 能从“我不知道发什么”进入两个以上差异化方案；
- ≥80% 能解释系统为何推荐其中一个方向；
- ≥80% 能从模糊想法形成并确认 CreationProposal；
- ≥80% 能在制作包中找到台词、字幕、素材、制作步骤、发布配文和品牌依据；
- ≥80% 能提交一条品牌资料反馈；
- 记录首次形成可制作方案耗时、误操作、放弃原因和“系统是否帮助我想清楚了”的主观评分。

自动化全绿不能替代此门。测试用户来源与 FE-00 走查的同批复用规则见 D-COMM-05b。

---

## 六、阶段 C：付费设计伙伴运营与高级制作迭代（C1—C3）

### C1 · 付费设计伙伴运营包 `PilotOpsV1`（doc/process-only）

> 本项不要求新增产品收费、套餐或额度工程。

#### C1.1 试点对象与角色

- 客户侧：品牌负责人、内容负责人、品牌管理员、2—5 名真实内容用户；
- 笛语侧：试点负责人、产品负责人、技术支持责任人；
- 每个试点只指定一个客户决策人和一个日常联系人，避免多头反馈。

#### C1.2 服务辅助入驻

```text
1. 冻结试点目标、账号与用户范围
2. 收集并登记品牌资料
3. 管理员确认发布投影与账号画像
4. 验证商品事实与素材缺口
5. 运行三条测试提案与制作包
6. 邀请真实成员
7. 完成首次价值会话
```

首次价值定义：真实用户在一次引导内，完成一份能清楚体现本品牌依据、可继续修改或交付制作的
ProductionPackageV1。

#### C1.3 收费与合同（线下执行）

- 费用金额、付款节点、税务和发票由线下合同/报价单确定；
- 可采用一次性试点服务费、分阶段服务费或其他人工约定方式；
- 付款通过现有公司收款与财务流程完成；
- 系统内不显示价格、不扣额度、不自动续费；
- 合同只需写清：试点周期、品牌/账号范围、用户范围、支持边界、数据责任、退出条件。

#### C1.4 支持与复盘

- 建立一个明确支持渠道（企业微信/群/邮箱等线下渠道）；
- 工作日问题分为：阻断故障、资料问题、使用问题、产品建议；
- 每周一次 30—45 分钟复盘：
  - 本周真实使用；
  - 提案确认与放弃；
  - 制作包采用；
  - 品牌依据反馈；
  - 需要补资料；
  - 下一周实验。
- 任何产品建议进入有来源、责任人和结论的试点反馈台账，不直接变成开发承诺。

#### C1.5 退出与扩大

停止条件：

- 连续两个周期无非创始人真实使用；
- 客户无法提供最低品牌资料或真实操作者；
- 制作包采用率持续为零且原因不属于可修复产品问题；
- 安全、权限或事实边界出现不可接受缺陷。

扩大条件：

- 北极星连续至少 3 个周期 > 0；
- 非创始人团队产生真实采用/批准；
- 新租户入驻无需开发者手改数据库；
- 支持成本和模型估算消耗可被人工核算；
- 至少一个客户愿意继续付费或扩大范围。

### C2 · 高级制作建议（真实反馈后启动）

仅在最低制作包真实使用后，根据反馈有界扩展：

- 景别建议；
- 更精细的步骤时长；
- 音效点与音乐角色；
- 转场与剪辑节奏；
- 分节修改；
- 简单评论/退回原因（如确有需求，另立工作项）。

全部建议继续使用 `suggested_needs_review`，不得伪装为已有资源、品牌事实或平台硬规则。

### C3 · 试点反馈收敛与 successor 门

试点结束形成：

- 产品采用证据；
- 参谋与制作包漏斗；
- 品牌反馈分类；
- 入驻人工成本；
- 支持负担；
- 模型估算消耗；
- 继续、收缩或停止建议。

只有主控基于该证据批准后，才能建立下一商业化 successor；不得以一次演示成功直接宣布规模化 SaaS。

---

## 七、前端工程贯穿项（FE-00—FE-04，编号与 UX-04R 完全一致）

详细规范以配套 UX-04R 为准。

| 项 | 内容 | 验收 |
|---|---|---|
| FE-00（先行门） | 目标体验蓝图、高保真原型与 5 名用户走查（与 B6 复用同批用户） | 未通过不得开工 FE-05—FE-13 |
| FE-01 | 正式路由、懒加载、应用内账号/平台切换，删除整页刷新救草稿路径 | 草稿不丢、旧 URL 兼容、首包不增 |
| FE-02 | 新合同 OpenAPI codegen + 流事件运行时校验 | 新代码零手写 API 类型，非法事件 fail-closed |
| FE-03 | 触碰路径 feature 化与死样式清理 | 无删测保绿，无隐式 CSS 依赖 |
| FE-04 | 9,311 行测试资产硬保护与迁移对账 | 每 PR CI 全绿 |

不做前端目录一次性整体重写；`CreatorApp` / `TenantAdminApp` 只在本包触碰的功能边界顺势拆出。

---

## 八、执行纪律与风险分级

| 工作项 | 风险级 | 流程 |
|---|---|---|
| A2 / A4 / A5 / FE-02 / FE-03 | 轻 | 侦察通过后合并执行，delta-only 验证 |
| A1 / A3 / A6 / A7 / B2 / B5 / FE-00 / FE-01 | 中 | 单项 Brief + 守护审查，可合并相邻步骤 |
| B1 / B3 / B4 | 重 | 独立 Brief + founder 显式授权 + 守护三关 + fresh acceptance |
| B6 / C1 | 人类/运营门 | 有记录的真实执行，不以代码测试替代 |
| C2 | 反馈驱动重活 | 只有真实试点反馈成立后另行授权 |

所有提交必须使用断言门控：

```text
python3 <assert> && git add <files> && git commit
```

任何协作、Proposal、Writer、Planner、Compiler 或制作包合同变更，均不得沿用 TENANT-01 的
`23/26` 结果，须按影响面生成 fresh acceptance。

---

## 九、阶段门

| 阶段门 | 必须条件 |
|---|---|
| A 放行：可做正式商业演示 | A1—A7 全部通过；五场景演练完成；普通用户无工程自证术语 |
| B 放行：产品具备试点启用条件 | B1—B5 上线并 fresh 验收；B6 人类可用性门通过；最低制作包可执行 |
| 试点启动门 | C1 运营材料、线下合同/报价与支持责任人就绪；无需计费或额度系统 |
| 试点扩大门 | 北极星连续 ≥3 周期 > 0；非创始人真实采用；入驻与支持成本可核算；无安全硬缺陷 |
| successor 门 | C3 完整复盘经主控批准；不得自行创建下一商业化里程碑 |

---

## 十、风险与回退

| 风险 | 缓解 / 回退 |
|---|---|
| A7 变成通用聊天 Agent | 响应类型白名单、无工具写入、无任务创建、最多一个策略问题 |
| A1 泄漏内部来源 | `basis_ref` 公开引用与底层 ID 分离；载荷白名单与 grep 门 |
| B1 提案确认前后漂移 | canonical JSON + 服务端签名 token + 依赖版本校验 + 原子冻结 |
| B3 制作包“结构漂亮但不可执行” | 每个步骤绑定台词/字幕/资源条件；人工抽样；来源状态强制显示 |
| B3 虚构景别/音效/资源 | `suggested_needs_review` / `unavailable` 明示；禁止渲染为已确认 |
| B4 决策覆盖内容版本 | 只用 append-only 事件，版本正文零更新 |
| A6 品牌问题错误交给 Ops | 独立租户品牌反馈队列；能力缺口才进入 Ops |
| 试点范围导致计费过度工程化 | D-COMM-06：全部线下收费，无产品计费/额度实现 |
| 前端范围回涨 | UX-04R 明确不做清单；新增范围另立裁决 |
| 旧测试阻碍正确产品调整 | 允许迁移但必须逐条对账，禁止删除测试掩盖回归 |

---

## 十一、状态变更与治理流程（两包审查 PASS 后）

1. 主控按 `MILESTONE.md` 纪律将 TENANT-01 置 `CLOSED`，完整保留其未证明项和权威证据根；
2. `MILESTONE.md` 当前主线更新为 `COMM-01 · IN-PROGRESS`；
3. TENANT-01 的“不新增审批状态机”处增加 D-COMM-03 的追加式决策事件修订说明；
4. UX-03 与总体基线的“不启动 UX-04”处增加 D-COMM-02 有界解冻说明；
5. M5-K 的 Brief 裁决处增加 D-COMM-04 无物理表、允许瞬时签名提案的无冲突说明；
6. 两份草案同批改为审查结论状态，不允许只批准后端或只批准前端；
7. 若审查 FAIL，两份草案原样保留失败原因，既有冻结继续有效。

---

## 十二、未证明项

本包完成仍不证明：

- 真实客户愿意以何种价格长期付费；
- 真实员工长期采用；
- 制作包一定被实际拍摄或发布；
- 平台流量、排名、爆款、GMV 或销售提升；
- 多租户规模化入驻成本；
- 企业 SLA、专属部署或跨区域合规能力。

试点收费通过线下方式收取，只能证明客户愿意参与有偿试验；不能自动等同于可规模复制的产品市场匹配。

---

## 十三、守护审查请求

1. `BoundedAdvisorV1` 是否足够形成真实参谋，而未膨胀为通用 Agent？
2. `CreationProposalV1 + proposal_token + snapshot` 是否遵守“不建 Brief 物理表”且能防确认漂移？
3. 最低 `ProductionPackageV1` 是否已在试点启用前提供真正可执行交付，而非只把 body 重新排版？
4. `confirmed_source / compiler_derived / suggested_needs_review / unavailable` 是否足以防止制作建议冒充事实？
5. 决策事件模型是否完整保留内容版本不可变性，并正确处理多次导出、批准撤回和人工发布撤回？
6. 品牌反馈与系统能力反馈的责任分流是否清晰、权限是否最小？
7. 真实用户可用性门是否能够证明“用户不再无从下手”？
8. D-COMM-06 是否已明确排除计费、套餐、额度和支付工程，而不妨碍线下有偿试点？
9. 本包与 UX-04R 的路线、依赖、阶段门和不做清单是否逐项一致？
10. B3 的 v3 失败模式回归口径（切段改名 / 台词整块复制检测）是否机器可判、fail-closed？
11. `CreationProposalV1` 逐字段消费者映射是否完整，有无"无人读取"的摆设字段？
12. D-COMM-05a 时间盒与范围复审机制是否可执行，不会退化为无限顺延？
13. A7 分层（模式 / 意图 / 能力 / 承诺）是否在合同层真实分离；`interaction_mode` 混层是否
    被修正而非换名搬家，旧调用方兼容映射是否完整？
14. 主动引导原则是否落进验收——边界拒答必须指路、"能做什么"回答必须由租户真实资料
    确定性投影生成且可与管理端核对？
15. 自由对话有界口径（选项甲）的文案、路由与验收是否一致；通用请求既不被静默受理、
    也不被生硬拒绝？
16. 六层引导知识基座是否只消费"已在仓"来源；GKB 接入是否确实未被隐式纳入；
    分层引用诚实性（行业通用参考 ≠ 品牌确认事实）是否落进验收与渲染？
