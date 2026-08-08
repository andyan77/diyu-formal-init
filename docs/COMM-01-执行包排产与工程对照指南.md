# COMM-01 / UX-04R 执行包排产与工程对照指南（V3）

> V2（2026-08-06）：终审 `PASS_WITH_BOUNDED_CORRECTIONS` 十二项有界修正已同步进
> 两份 REVISION-6 执行包与本指南（选择服务前移、OpportunityV2、反馈两表、A5a/A5b、
> 交互 API 版本化与流式诚实、B1 防重放幂等、B3 所有权与完整 26 卡、B4 管理员入口与
> 语义冻结、B5 口径冻结、术语/编号残留清理）。转 `APPROVED_FOR_EXECUTION` 待守护确认。
>
> V3（2026-08-07）：D-COMM-09 落盘（MILESTONE / COMM-01 REVISION-7 / UX-04R 交叉注记 /
> AGENTS §9 例外同轮更新）——两部分合一、EXE-V0/V1 入列（14 包 / 13 接缝）；守护审查
> 修正吸收：SEAM-13 溯源正交化、TaskValueAssemblyV1 独立版本化对象（不原地扩写 V3 合同）、
> V0 可产路径收窄、降级 path=null、安全构造模板、安装顺序补 npm ci、函数预算改棘轮口径。

- 性质：**非规范性工程参考**。规范真源是
  [COMM-01 执行包](COMM-01-品牌价值可见创作参谋确认提案与付费试点最小闭环执行包.md)（REVISION-5）与
  [UX-04R 执行包](UX-04R-前端产品化增量与工程边界执行包.md)（REVISION-5）；两者与本指南冲突时以执行包为准。
- 用途：各执行包立项 Brief 的工程对照；每包开工前按 E7 纪律以 live git 复核本指南全部代码锚点
  （行号会漂移，事实不允许靠快照假定）。
- 依据：2026-08-06 四路只读核查（`static_verified`，file:line 证据）+ 两包 REVISION-5 全文。

---

## 一、排产总览（两部分合一方案 · founder 2026-08-07 裁决注入价值先行目标）

> **同一份方案、同一条主线 COMM-01，分两部分先后实现，不另立里程碑：**
> **第一部分 · 价值引擎先行与陪跑交付** = EXE-01R 收口 + EXE-V0 + EXE-V1——先把
> "内容应该是什么"的发动机装上并部署 ECS，由 founder 向陪跑种子客户**有陪同**交付与辅导；
> **第二部分 · 全量产品化** = EXE-02—EXE-12 按原序落盘，吸收价值方案增量
> （P1→EXE-02、P2-P4→EXE-06、P5→EXE-07 后、部署 runbook→EXE-10）。
> 无陪同自助与可用性阈值验收仍属 B6 人类门（EXE-09），不因先行交付提前放开。

| # | 执行包 | 承接工作项 | 风险级 | 阶段门 |
|---|---|---|---|---|
| EXE-01 | 前端地基与体验蓝图 | FE-00—FE-04 | 中 | 先行门 |
| EXE-01R | EXE-01 有界返工（founder 2026-08-07 追加裁决，EXE-02 前置） | 五项：作用域事务化 / task 深链补实现 / 流校验补强 / 证据矩阵重做 / 远端集成证明 | 中 | 先行门 |
| EXE-V0 | 价值引擎先行包（founder 注入意图目标，第一部分核心） | P0 生产只读核查分叉 + 服务端确定性组装 payoff + payoff_source + 路径观测 + 结构硬门 | **重（改生成语义）** | 先行价值门 |
| EXE-V1 | 最小生产晋级与陪跑交付包（第一部分收口） | 部署 runbook + ECS 晋级 + 生产冒烟 + 陪跑交付材料 + 反馈台账 + L0 生产观察 | 中（运维+doc；生产动作逐项单独裁决） | 陪跑交付门 |
| EXE-02 | 品牌依据可见闭环 | A1 + A2 + FE-07 | 中 | A |
| EXE-03 | 今日工作台与帮助分流 | A3 + A4 + A5 + FE-05/08/13 | 中 | A |
| EXE-04 | 品牌反馈队列 | A6 + FE-12 | 中 | A |
| EXE-05 | 交互编排路由与内容创意能力 | A7 + FE-06 | 中—重 | A |
| EXE-06 | 确认提案合同 | B1 + FE-09 | **重** | B |
| EXE-07 | 最低制作包链 | B2 + B3 + FE-10 | **重（最大单包）** | B |
| EXE-08 | 决策事件与指标 | B4 + B5 + FE-11 | **重** | B |
| EXE-09 | 可用性门与 B 组收口 | B6 | 人类门 | B |
| EXE-10 | 试点运营包 | C1 | 轻（doc/process） | 试点启动门 |
| EXE-11 | 高级制作迭代 | C2 | 条件触发 | 试点期 |
| EXE-12 | 试点复盘与收口 | C3 + 状态迁移 | 收口 | successor 门 |

执行纪律映射见 COMM-01 §八；EXE-06/07/08 须独立 Brief + founder 显式授权 + 守护三关 +
受影响冻结验收子集 fresh rerun（不得沿用 `23/26`）。B 门时间盒在 EXE-06 立项时由 founder
设定（D-COMM-05a）。

---

## 二、接缝裁定（SEAM-01—08，执行前已消歧）

> 这些是两包正文未写透、指南层面裁定的集成口径；各包 Brief 引用编号即可。

| # | 接缝 | 裁定口径 |
|---|---|---|
| SEAM-01 | A5 采用事件（activity_events）与 B4 决策事件（新表）双源 | A5 是 B4 前置最小版：EXE-08 上线后 `content_version_decision_events` 为**唯一真源**，A5 三事件停写（或仅保留为观测冗余、不入指标）；B5 全部指标切换单源，切换点在 EXE-08 验收中显式断言 |
| SEAM-02 | B2 `content_form-v1` 与五轴目录 form 轴 | 三枚举**绑定既有目录 form 轴 stable_id**（`config/content_expression/catalog-v1.json`），不另立第二套词表（与 R3 / tone_ids 同理） |
| SEAM-03 | A1 事件时序 vs B1 提案 | A 阶段 `context_selected` 在流内 `compiling_context` 完成后发出；EXE-06 上线后同一投影前移进提案卡展示（FE-07"本次将使用"），流内事件保留不删，两处同源同 digest |
| SEAM-04 | A7 编排器与既有 collaborate 通道 | 不建第二条模型通道：编排器复用 `collaborate()`（`deepseek.py:675-678`）扩展结构化响应 schema；`natural_entry` 高置信短路保留为确定性第一层；`creation_intent_gate` 承诺判定原样保留 |
| SEAM-05 | B1 proposal_token 密钥 | HMAC 服务端签名，密钥经环境变量注入（`load_env` 惯例），禁止硬编码；token 绑定 tenant/account/scope/过期与依赖版本 |
| SEAM-06 | FE-01 SPA 路由与服务端入口 | `src/gateway/api/html.py` 的 bootstrap 注入（identity/application）需适配新路由集合（SPA fallback 或逐路径注册），旧 URL 对照表是验收交付物 |
| SEAM-07 | V5→V6 编译复算 | `_assert_compiled_delivery_v5`（字节级重编译比对）扩展覆盖 V6 结构化投影；旧内容永走 V5 读路径，不迁移 |
| SEAM-08 | 北极星"品牌依据内容"精确定义 | = 被批准或采用、且 `context_basis.items` 含 ≥1 条**非** `model_parametric` 条目的内容版本（D-COMM-08 第 3 条排除项落进指标口径）；tenant/organization + 自然周 + 唯一版本去重，adopted 与 approved 不双计 |
| SEAM-09 | A 门演示与未实现能力 | A5 拆 A5a（场景 1—4 真实演练 + 场景 5 冻结合同，随 EXE-03）与 A5b（五场景全链，随 EXE-07，为 B 门条件） |
| SEAM-10 | 反馈表"append-only + 可变状态"自相矛盾 | 两表事件化：`brand_basis_feedbacks`（不可变提交）+ `brand_basis_feedback_events`（处理事件），服务端派生 current_status |
| SEAM-11 | 上下文选择多点漂移 | `BrandContextSelectionService` 前移为纯服务（EXE-02 交付），OpportunityV2 / Advisor / Proposal / context_selected / 快照 / 制作包六点同源消费；提案确认只重验证不重选 |
| SEAM-12 | 制作包存储所有权 | 内容侧 `ContentProductionPackageV1` 随 content_versions；DM01 `DisplayExecutionPackageV1` 随 display version——不塞入 ContentVersion |
| SEAM-13 | payoff 溯源与确认态正交化（V3 修订，取代单字段 payoff_source 草案） | 快照记四个正交字段：`payoff_origin ∈ {server_assembled, static_fallback, user_edited(EXE-06 起)}`、`payoff_confirmation_state ∈ {unavailable_pre_proposal, pending, user_confirmed}`、`payoff_degraded`、`payoff_degradation_reason ∈ {missing_profile_signal, invalid_assembly, unsupported_relevance_path, safety_gate_rejected}`。EXE-V0 只产 origin ∈ {server_assembled, static_fallback} 且 confirmation_state=unavailable_pre_proposal；EXE-06 只推进确认态/产生 user_edited，不得抹除原始溯源；历史快照零改写；降级必须可见，不得静默冒充成功 |

---

## 三、逐包工程对照

### EXE-01 · 前端地基与体验蓝图（FE-00—FE-04）

- **需求**：FE-00 页面状态图 + 1440×900/390×844 高保真原型 + 12 组件视觉交互合同 + 5 用户走查；
  FE-01 正式路由/懒加载/应用内账号平台切换；FE-02 新合同 codegen + 流事件运行时校验；
  FE-03 feature 目录 + 死样式清理；FE-04 测试资产保护机制。
- **上下游承接**：`frontend/src/app/Root.tsx:6-14,34,60-93`（手工路由，替换对象）；
  `CreatorApp.tsx:1047-1055`（navigateWithDraft 抢救机制，删除对象）；`frontend/src/styles.css`
  15 组零引用死样式；根目录 `openapi.json`（103 paths/60 schemas）+ `Makefile` openapi target +
  `scripts/golden.sh:6` 漂移检查（codegen 挂接点）；`frontend/test/` 9,311 行（保护对象）。
- **技术方案要点**：react-router（或 Brief 批准的等价轻量实现）+ route-level lazy；
  openapi-typescript 生成至 `frontend/src/shared/contracts/gen/`（仅新合同，存量 63 处手写不迁）；
  流事件轻量运行时校验（非法事件安全错误 + 保留输入）；草稿由页面 reducer 持有；SEAM-06。
- **新增目录**：`frontend/src/app/AppRouter.tsx`、`frontend/src/features/`（today/advisor/proposal/
  production/brand-basis/decisions/admin-brand-feedback）、`frontend/src/shared/contracts/`。
- **风险点**：路由改造破坏浏览器测试（FE-04 硬约束，迁移须逐条对账）；html.py 适配遗漏路径致 404；
  codegen 工具链进 CI 的 node 依赖。
- **验证标准**：旧 URL 对照表全通；切账号/平台不整页刷新、草稿不丢（浏览器断言）；首包体积不增；
  死样式删除附全 TSX grep 零引用证明 + 多视口截图回归；FE-00 未过不得开工 EXE-02+ 的界面项。
- **监理复验记录（2026-08-06，runtime_verified）**：执行分支 `exe-01-frontend-foundation`
  远端 HEAD `3043217`，监理独立 worktree 全量复跑——golden 913/2/0、前端 6 suite 全过、
  8 断言脚本全 PASS（路由断言在裸环境正确失败关闭、test.sh 环境下通过）、entry gzip
  −29.6%、批准表 P1—P6 全 DRAFT 零自批、依赖门合规（esbuild 为基线既有）、后端 2 skip
  均为基线既有环境门控。**判定：PARTIAL · BLOCKED_EXTERNAL_FE00_HUMAN_GATE，符合预期
  轨迹，无需补充执行 Prompt。**
- **EXE-01 上报遗留缺陷与去向**（执行侧发现、未越界顺手修，处置正确）：
  ① 裸 `/activate` 服务端从未注册（仅 `/activate/{token}`），旧 Root 分支为死代码 →
  EXE-03 触碰 `/user` 壳时一并裁决注册或删除；② `/materials` 未授权 303→/login 而
  `/user` 返回 401，处理器层既有不一致 → EXE-03 统一未授权行为口径；③ `--surface-soft`
  全仓未定义无回退，`.artifact-context-basis` 背景实际透明 → FE-00 设计评审时裁决补定义
  或删除；④ 生产模式 5 条路由仅 static_verified → EXE-10 生产晋级时随部署验收补运行时复核。
- **FE-00 人类走查门收口（2026-08-07）**：founder 裁决以 AI 专家代行评审替代真实用户走查
  （裁决原文、方法与诚实边界见执行分支
  `docs/前端UI架构/FE-00/走查记录-AI代行评审-2026-08-07.md`，commit `94cc40a`）。
  P1—P6 已置 `APPROVED`；缺陷 ③（`--surface-soft`）设计裁决为随 EXE-02 在 UserShell
  作用域局部定义 `#f6f4f0`；走查发现 F1—F4 作为实现约束路由至 EXE-02/03/06/07。
  **B6 可用性门（EXE-09）仍须真实用户，不受本替代影响。**
  EXE-01 据此从 `PARTIAL · BLOCKED_EXTERNAL_FE00_HUMAN_GATE` 收口为 **COMPLETE**；
  执行分支已合入主线（merge `588303a`），主线同时含监理记录与执行产物。

### EXE-01R · EXE-01 有界返工包（founder 2026-08-07 追加裁决，EXE-02 前置）

外部审查提出五项问题，监理以独立代码实证逐项复核（static_verified，file:line 证据存档于
监理会话），判定与去向：

| # | 指控 | 复核判定 | 关键证据 |
|---|---|---|---|
| 1 | 作用域未事务化 | **属实（P0）**：`useAdvisorScope` 的 AbortController 无任何消费方；流消费零 `isCurrent`/epoch 守卫，A 账号迟到 `completed` 会落进 B 账号；切号只重载 workspace，`messages/current/viewed/versions/selections/materialIds` 全不清（`materialIds` 还会带进 B 的请求载荷）；草稿键 `tenant` 用品牌展示名（后端 bootstrap 未投影稳定 id）；非法 target 被静默兜底不归一化，URL/草稿/API 三者口径不一致 | `useAdvisorScope.ts:74-125`、`CreatorApp.tsx:943-952/1131-1328/747-753/771-775`、`workbench_repository.py:73` |
| 2 | 深链假宣称 | **指控不成立、建议采纳**：全仓 grep 零处"业务全兼容"宣称，`legacy_routes.json` 诚实限定为路由级 303/query 保持；且**非回归**——重构前 SPA 同样从不消费 `?task/?version`（成品只进服务端 `<noscript>`）。但旧 URL 确实承载成品链接 → 按审查建议**补真实现**：`taskId` prop 现为死参数，而 `openSeriesTask`（`CreatorApp.tsx:1080-1101`）已具备全部加载能力，接线成本低 | `AppRouter.tsx:129-138`、`app.py:3570-3581`、`html.py:31` |
| 3 | 流校验非 fail-closed | **属实（P0/P1）**：字段校验仅"存在性"零类型（`version:"one"`、`body:123` 可通过）；UI 消费的 `outline`/`ai_generated` 不在必填清单；target 枚举不校验且直写 URL；守卫内两处 `as unknown as` 强转；**terminal 事件即到即提交**，after-terminal 违约时成品已上屏 + 失败横幅并存，"违约流不改工作区"不成立；5 类反证测试仅 1 类存在 | `contentStream.ts:92-121/157/167`、`CreatorApp.tsx:1222-1238` |
| 4 | 证据矩阵掺水 | **属实且比指控更重（假绿）**：36 张桌面 PNG 仅 12 个不同 sha256——200% zoom / reduced-motion 条件与基准逐字节相同（截图裁剪固定 `.fe00-frame` 1440×900，视口条件从未生效）；断言只查文件存在+非零字节，无 PNG 实际尺寸、无 `scrollWidth<=clientWidth`、无键盘探测、无原型源码 hash 绑定；移动端为一张 all-states 长图 ×3 | `fe00-evidence.mjs:24-34/127`、`assert_visual_evidence.py:51-56` |
| 5 | 远端集成缺失 | **部分属实**：CI 存在（`ci.yml` deterministic-quality-gate：frontend 四目标 + lint/typecheck/golden，push/PR@main + workflow_dispatch）但 8 个 `scripts/exe01/assert_*` 全不在任何 runner 里；8 个部署面浏览器脚本（均基线既有）EXE-01 一个都没跑、零运行产物；包内双基线不一致（回归对照用 `8c9f2ac`、scope 断言用 `af20ae5`）；分支落后监理记录——此项已由监理合并 `588303a` 解决 | `ci.yml:3-39`、`test_baseline.json:73-208`、`regression-summary.json` |

- **监理自报漏检**：2026-08-07 P6 批准时仅验"39 张存在 + axe 零违规"，未做跨条件哈希比对，
  漏过第 4 项假绿。P6 批准已加限定注记（见批准表），待 EXE-01R 重做证据后以 P6v2 行取代。
- **EXE-01R 边界**：只修上表五项，不做 CreatorApp 全量重构、不迁存量 63 处手写类型、
  不碰 TenantAdminApp；新增/改动函数 ≤60 行（AST 断言 + 存量超限冻结清单只减不增）；
  浏览器脚本一律打**本地**拉起的实例，不触生产/外部服务。验收细则以 EXE-01R 执行 Prompt 为准。
- **状态口径**：EXE-01 维持 COMPLETE（地基交付本身有效），EXE-01R 为独立有界返工包，
  **EXE-02 不得先于 EXE-01R 通过监理复验开工**。
- **Prompt v1.1 修订（2026-08-07，守护审查 PASS_AFTER_BOUNDED_CORRECTIONS，监理逐条实证后采纳）**：
  安装顺序（uv sync → npm ci → make 四目标 → golden）/ 独立 clean worktree 门（分支已存在即
  PRECONDITION_BLOCKED，禁 reset/clean/stash）/ scope 切换禁用会清草稿的
  `clearOneTimeControls`（首行 `setSeed("")`），抽不碰草稿的 `resetScopeBoundUiState` /
  后端只补 `tenant_id` 只增投影（`operator_id` 实已在 `workbench_repository.py:73`）/
  R2 放行 `app.py` 最小深链入口适配（版本不存在仍出 SPA shell）/ R3 终态原子提交语义
  （用户消息与暂态进度不算污染）/ R4 同帧跨条件哈希比对 + manifest 记物理尺寸与 CSS 视口 +
  执行端只登记 P6v2 DRAFT 不动 P6 / scope 门改双窗口（历史 af20ae5→3043217 + 当前
  202da6d→HEAD）+ 9 门自包含 runner / 函数预算五级优先（豁免棘轮按 202da6d 冻结）/
  CI run 须 headSha==最终远端 HEAD / 执行侧终态只能
  `IMPLEMENTED · AWAITING_SUPERVISOR_REVERIFICATION`。
  **双向事实纠错**：审查方"分隔符已为 U+0000"不实（`advisorDraft.ts:37` 为普通空格）；
  v1 的 `content_service.py:1960` 锚点系 `identity_summary` 误引，弃用。
  完整 v1.1 覆盖段以监理会话 2026-08-07 输出为准，与 v1 冲突处以 v1.1 为准。
- **执行轮次 1 交付与监理复验（2026-08-07，runtime_verified）**：分支
  `exe-01r-scope-stream-hardening` 远端 HEAD `caeb6ea`（`357d17c` + 4 commits，
  改动面全在 allowlist 内）。**R1/R2/R3 复验全部为真**：golden 920/2/0 +
  codegen up to date（913→920 = 新增 7 条后端测试）；前端 9 套件全过（新增断言
  流事务 10 / 跨账号 12 / 深链 13）；篡改反证抽查真咬人（禁用终态缓存 → runner
  断言崩溃，还原 → 全绿）；CreatorApp 2044→1968 行（AccountDrawer 311 行抽出）。
  **R4 = BLOCKED_BY_DESIGN_REAPPROVAL**：真实缩放溢出监理独立复现（桌面 200%
  文档 1440 > 视口 720；移动 1:1 即 410 > 390；两原型 animation/transition 计数
  全为 0），P2v2/P3v2/P6v2 已按纪律 DRAFT 登记、P6 未动，待 founder 裁决重排口径。
  **R5 未交付**（无 9 门 runner、无 CI run），待第二轮。执行侧自报 PARTIAL，诚实。
- **监理二次自纠（字节级教训）**：v1.1 中"分隔符为普通空格"的纠错**本身是错的**——
  xxd 复验得 `22 00 22`：分隔符自 EXE-01 `bbfe4e1` 起就是**裸 NUL 控制字节**
  （执行侧本意打空格却写入 \x00，git 从此视该文件为二进制；文本渲染里 NUL 不可见，
  致监理与实证代理两轮都读成"空格"）。远程审查该条为真。执行侧已改为源码可见的字面转义序列（反斜杠 u 0 0 0 0 七个字符）。**教训固化：字节级论断必须用 xxd/hexdump 字节级验证，不得凭文本渲染。**
- **本轮监理裁决（随第二轮 Prompt 生效）**：① `conversation.kind` 枚举须补
  `greeting`——服务端 5 处真实发射点（`content_service.py:213/222/229/312`、
  `app.py:2883`），严格 `chat|question` 会把合法问候拒为违约（审查方与 Brief 均
  只读了 TS 类型未查服务端真源）；② 深链缺 target 落默认平台 scope 属已知限界，
  修复需读任务拿 target（本包禁区），随 EXE-07 制作包页面收口；③ 仓根加
  `.python-version` 固定 3.10 纳入第二轮（uv 默认取 3.14 触发 asyncio 行为差异
  误报，CI 实用 3.10）。
- **R4 重排 founder 裁决（2026-08-07，AskUserQuestion 选项 A）**：**重排验收挂到
  真实产品页**——固定画布原型是一次性设计草图，不承担 200% 重排证明；200% 缩放
  `scrollWidth<=clientWidth` 断言（无障碍口径）成为**各前端实现包对真实页面的
  常设验收项**（范式 `ux02-responsive-browser.mjs`）。原型侧仅修 P3 移动端
  410>390 自溢出缺陷（P3v2 小修，监理代行评审后批准）；桌面原型不改版，P2v2
  登记行以"裁决 A 关闭"注记处理；P6v2 重采诚实证据（逐状态截图 / PNG 实际尺寸
  交叉校验 / 原型 sha256 绑定 / 同帧重复哈希检测 / 键盘可达 / axe），200% 条件对
  固定画布原型记 `N/A-by-design` 并援引本裁决，reduced-motion 维持 N/A（动效计数
  0 实测）。
- **执行轮次 2 交付与监理复验（2026-08-07，runtime_verified）**：远端 HEAD `9ac5143`
  （监理批准提交后 `4854cf2`）。**R4 完成并全部验真**：golden 920/2/0 + codegen、
  前端 9 套件全过（greeting 反证 3 条在内）、证据矩阵 42 张实数且缩放截图物理
  2880×1800 vs 基准 1440×900（真缩放非复制）、原型 sha256 绑定当场篡改反证
  （改 1 字节→门报"自取证后已修改"，还原→绿）、reflow 门 mobile-base 修复后通过、
  200% 条件按裁决 A 记 N/A-by-design；`.python-version`=3.10 落地。
  **P3v2/P6v2 已批准（监理代行），P6 置 SUPERSEDED，P2v2 按裁决 A 关闭——R4 收口**。
  **R5 仍缺**：assert_function_budget 已建成且抓到真问题——9 处棘轮违约（R1 守卫
  代码推超豁免基线 + 3 个新组件超 60 行），执行侧**红着如实提交、拒接红门进 CI**，
  行为正确；双窗口 scope 门 / run_gates.sh / CI dispatch / 浏览器脚本 / 双基线
  说明未做。
- **监理排产检讨**：EXE-01R 实际体量 ≈ 3 个执行会话，首轮按单会话包排产是监理
  估算误差（停止组因：制度性停止点〔角色分离/门红不绕〕属设计如此，产能切分属
  排产责任）。第三轮范围收敛为最短收口路径：9 处棘轮修复 → 门链（双窗口 scope +
  runner + make 目标）→ ci.yml 接入与 dispatch 三件套 → 浏览器脚本 → 双基线说明。
- **执行轮次 3+4 交付、监理复验与串行合入（2026-08-07，runtime_verified）——EXE-01R
  收口 COMPLETE**：轮次 3（远端 `f4600ac`）九处棘轮全修回（只用抽取）、九门进 CI、
  quotePath 中文路径转义 bug 以 `-z` 修门不绕门、8 个浏览器脚本等待条件修法经监理裁定
  属本包合规（协议缺陷修工具，断言 549→646 只增）。轮次 4：实现终态 `13cfcb2`、冻结
  提交 `eb6bb5d`——scope 窗写死 357d17c..13cfcb2 + 祖先守卫（监理篡改反证：外来 SHA
  当场报"冻结点不是当前 HEAD 的祖先"）。残留归属查清：ux03-product-media 系**本包 R3
  回归**——`completed.result.target` 被当枚举校验，而服务端 `content_service.py:2186`
  成对发射（`target` 是人看的标签、`target_key` 才是枚举）；35 条自建断言全绿却拦不住，
  因夹具按同一错误理解编写，**自己验自己验不出来，真服务器一跑现形**→ 修三处（守卫
  target 改自由文本 / types.ts target 改 string / targetOf 删标签兜底）+ 5 条反证；
  ux03-gate-c 基线本就不过、修后反超基线；ux03-gate-d 归属 EXE-01 时期既有 → **监理
  路由 EXE-03**（陈列搭配导航面，若属 DM01 深层链路届时转独立小包）。浏览器脚本终态
  3 PASS / 1 FAIL(已归属) / 4 BLOCKED(缺私有语料/fixture 逐条在案)。监理复验：golden
  920/2/0 + 前端 9 套件 + CI 三件套（run 31186778559 headSha==`eb6bb5d`）+ 修复代码
  逐处核对全真。**串行集成第 1 步完成：merge `d484540` 入主线**，合并后主线 CI
  dispatch 复核（run 31188653125）。**教训固化：合同夹具必须取自服务端真源形状，
  不得照实现者的理解手写**——此为 EXE-V0 固定样本纪律的先例依据。

### EXE-V0 · 价值引擎先行包（founder 2026-08-07 注入，第一部分核心）

- **动机**：真实性防线（"不能是什么"）已工业级，但 `audience_payoff` 是产品类型级静态查表
  （`publication_contract.py:456`，6 题材共 3 句固定文案，签名只吃 primary_product +
  topic_origin），空话坐在 Writer prompt 最高权重位（`src/tool/llm_gateway/deepseek.py:2138`
  `给读者的回报：{contract.audience_payoff}`），校验只查非空永远绿——"应该是什么"没有发动机。
  模型+用户确认路径在 COMM-01 前物理不可行（`content_service.py:505` `_context_for_intake`
  刻意剥离画像；确认环节依赖 EXE-06 proposal_token + FE-09），故本包走**服务端确定性组装**。
- **需求**：① P0 生产只读核查（生效画像分叉：查询包由方案作者交付、监理守护审查、
  生产授权运维端执行、证据入私有根、仓库只落无敏感摘要；若生效"普通生活"版→先修画像
  [零代码 API 动作，单独裁决]再校准基线）；② 服务端确定性组装 `task_audience_payoff`
  （零 LLM：画像五段 + 题材 + primary_product + 冻结商品/系列引用 → 每篇不同的具体回报句）；
  ③ `payoff_source` 第一天进合同（SEAM-13）；④ `brand_relevance_path` 七枚举（ADR-013 §4）
  观测字段 + `assembly_trace` 进任务快照，只记录不拦截；⑤ 结构硬门子集：非空+长度边界、
  规范化后≠任何静态默认句、路径∈七枚举、`product_brief()` 产出语义收窄为
  `product_contract_job`（五类产品不变量，组装器与模型均不可改写）、路径与 primary_product
  不矛盾；⑥ 组装无法产出合法 payoff（如画像字段空）→ 静态 fallback 但
  `payoff_source=static_fallback` + `payoff_degraded=true` **可见记录**——V0 无追问出口的
  过渡策略，EXE-06 升级为"新任务不得带病放行"。
- **上下游承接**：手术点 `content_service.py:558` 在 `_new_publication_contract()`（:539）
  体内，与 EXE-06 承接点同函数——所有改动附 supersession 注记"EXE-06 上线后组装器降级
  fallback"；快照 jsonb expand-only（20260726_20 先例），V5 读路径与历史零改写；
  与 EXE-01R **并行**（纯后端 vs 前端+CI 零文件交叠），后合入者过合并后全部门；
  观测产出（路径分布/静态重合率/degraded 率）是 EXE-06 Brief 的设计输入。
- **风险点**：改生成语义 → 受影响冻结验收子集 **fresh rerun**（不得沿用 23/26）；真模型
  子集需 founder 显式启用（密钥预 export 进环境、脚本绝不读 `.env`——2026-06-20 先例）；
  模板化表达上限："每篇不同"≠"每篇都好"，交付材料须如实陈述此边界。
- **验证标准**：组装确定性（同输入同输出）单测；固定样本回归（前后对照归档供 founder 审）；
  6 题材 payoff 互不相同且各可指回画像字段（**样本验收目标，非运行时硬门**）；golden 全绿；
  硬门反证测试（静态默认句必拒、非法路径必拒、degraded 必可见）；payoff 零事实主张
  （不含商品属性/经历/效果断言）；新增函数 ≤60 行。

### EXE-V1 · 最小生产晋级与陪跑交付包（第一部分收口）

- **需求**：① 部署 runbook（版本 tag / 配置核对 / 回滚预案 / local→ECS 推送纪律）；
  ② ECS 部署 + 部署后运行时冒烟（固定样本生产实跑 + 顺带收 EXE-01 遗留④中后端相关
  路由的运行时复核）；③ 陪跑交付材料：founder 辅导脚本、种子客户选择标准（对齐
  D-COMM-05 付费设计伙伴口径）、**已知边界卡**（如实告知当前做不到什么：依据面板未常驻、
  payoff 为模板组装、无自助引导等）、结构化反馈台账（手工 plan-B 口径，含"改什么/不改及
  理由"处置列）、事故联系与回滚协议；④ L0 生产观察：≥20 条真实生成的路径分布直方图 +
  payoff 静态重合率 + 人工抽样质量台账。
- **边界（硬约束）**：只做**有陪同交付**（founder 在场辅导）；无陪同自助与七项 ≥80%
  可用性验收仍属 B6 人类门（EXE-09）；计费维持线下零工程（D-COMM-06）；每个生产动作
  （部署/画像修正/密钥启用）**逐项单独裁决**，不预支授权。
- **上下游承接**：种子客户与 B6 复用同批人（D-COMM-05b，陪跑轮记录单独留存）；反馈台账
  与 L0 数据直接喂 EXE-06 Brief；runbook 与冒烟资产被 EXE-10 复用扩展。
- **验证标准**：部署三件套（tag + 回滚预案 + 冒烟记录）齐备；≥1 次完整陪跑交付演练记录；
  台账处置列非空。
- **一站到底授权信封（founder 2026-08-07 裁决，替代逐段 GO）**：GO#1A/1B/2 三个
  人工停点由预授权 + 自动刹车替代——预授权边界：部署候选 SHA + 全冒烟（B 层真实
  生成 ≤3 条）；RLS 加固（须实测 row_security_active=t，先留回退语句）；内部生产
  验证运行仅限笛语服饰三逻辑账号、自驱生成 ≤30 条、模型调用 ≤60 次、禁发布/禁新增
  用户/禁改画像资料权限；顺序锁定 S3→1B→S4，1B 不达标不得进 S4（不启用"书面风险
  接受"通道）。**失败刹车不可豁免**（冒烟红→回滚停；跨租户可见/事实错误→立即停；
  两败→停）。founder 亲自走查演练改在首次真实陪跑时补记，本包以执行侧驱动的生产
  验证运行记录替代并如实标注。监理事后全量复验照旧，终态仍不得自宣 COMPLETE。

**第二部分增量注记（吸收价值方案，届时随各包 Brief 生效）**：EXE-02 快照观测字段升级为
basis_ref 关联；EXE-06 增 P2-P4——`CreationProposalV1` 扩 `task_audience_payoff` /
`brand_relevance_path` 两字段（不新建 TaskValueIntentV1，避免语义四源漂移并补 R3 消费闭环）
+ 用户确认 + 路径↔证据闭合表 + `organization_people` 窄门（情景演绎不授路径资格）+
fallback 升级为"新任务不得带病放行"，同时把 EXE-V0 组装器降级 fallback、B 门时间盒重设
（D-COMM-05a）；EXE-07 后补 P5（`_LENS_PRODUCTS` 扩五类）；EXE-10 复用 EXE-V1 runbook。

**EXE-V0 v1.1 修正（2026-08-07 守护审查采纳，与上文冲突处以本块为准）**：
① 动态价值以 **`TaskValueAssemblyV1` 独立版本化对象**随任务快照存储（含
contract_version / audience_payoff / 四个正交溯源字段 / brand_relevance_path? /
ruleset_version+digest / assembly_trace，单独带 digest）——**不原地扩写
publication-contract-v3 结构**（历史 digest 字节兼容红线）；
`PublicationContractV3.audience_payoff` 仍是 Writer 唯一消费值且必须与 assembly 值
相等（断言）；**`deepseek.py` 一行不改**并加"该行未修改"断言。
② V0 可产路径收窄：`V0_PRODUCIBLE = {product_expertise(仅 product_decision_basis 的
supporting_fact_refs 非空触发), existing_series(仅有效 series_delta 触发),
audience_relationship, brand_stance}`；`V0_RESERVED = {brand_visual, local_trust,
organization_people}` 一律不产。降级（static_fallback）时
`brand_relevance_path=null` + `degradation_reason` 必填，**不得为凑枚举伪造路径**。
③ 安全构造：payoff 只能由版本化审核模板 + 白名单语义片段组装；不拼接画像五段原文/
seed 原文/商品事实值；不出现人物/账号/门店名；显式用户题材不得被画像改写为商品/门店/
行业题材；assembly_trace 为精确类型合同（枚举字段名 + template_id + ruleset digest，
零原文零 PII）。
④ 历史与幂等三测试：pre-V0 快照 round-trip digest 不变；retry/幂等不重选模板不换
digest；V1→V2 修订沿用原任务冻结值不读新画像。`product_brief()` 旧 V2 调用路径
（`publication_contract.py:421`）行为与历史 digest 零变化。
⑤ 安装顺序：uv sync → **npm ci** → make 前后端目标 → golden；期望值只冻结
failed=0 + 新增 skip=0（不硬编码通过数）。函数预算 = EXE-01R 同款棘轮口径
（新函数 ≤60；基线超限冻结豁免只减不增），配 `scripts/exev0/` 双门
（assert_scope + assert_function_budget）。
⑥ 并行与集成：与 EXE-01R 并行实现、**串行集成**（EXE-01R 先合入且先把 scope 窗
从 HEAD 冻结为终态 SHA；EXE-V0 后 merge 主线重跑合并后全部门 + CI 三件套）。
并行期终态只能报 `IMPLEMENTED_ON_AUTHORIZED_BASE · AWAITING_SERIALIZED_INTEGRATION`。
⑦ P0 缺失不阻塞本地实现，但报告须标 `production_profile_calibration=UNVERIFIED`，
且不得进入 EXE-V1 部署与真实陪跑；P0 分类增加 `mixed_or_ambiguous` 第三态。

- **实现轮交付与监理复验（2026-08-07，runtime_verified）**：分支 `exe-v0-value-engine`
  远端 HEAD `cbdf0be`，恰建于治理基线 `c37ae78`；14 文件全在 allowlist（
  `publication_contract.py` 未触碰，比授权面更克制）；`deepseek.py` 与 `openapi.json`
  与基线**字节零漂移**（监理独立 diff 复核 = 0 行）。监理复跑：golden **951/2/0**
  （913+38 新增，skip 未增；监理环境首跑 exit 1 系缺 node_modules 的环境假象，
  补装后 codegen/openapi 双检查通过）；exev0 双门真实退出码绿（1697 函数 / 233 冻结
  豁免 / 新函数 ≤60，棘轮曾当场拦下三处越界并被重构回基线内）；**固定样本在监理
  环境逐字节复现**（160 行，digest `aa0b8844…c9672` 与交付一致——确定性成立）；
  **篡改反证外科级命中**：禁用 `is_static_default` → 全量 951 条中恰其专属反证
  `test_a_ruleset_that_reproduces_a_static_default_is_refused_at_the_hard_gate`
  单条转红（1 failed / 950 passed），还原后干净。执行侧诚实项（venv 3.10 对齐口径、
  TOTP 偶发 401 隔离复绿、P0 摘要不复制进分支待集成）全部核实相容。
  **监理裁决：`assembly_trace.used_profile_fields` 只记实际撑起路径的字段——批准**
  （把未参与决策的字段写成证据即伪造溯源；商品/系列路径行改指冻结依据的分列口径成立）。
  终态申报 `IMPLEMENTED_ON_AUTHORIZED_BASE · AWAITING_SERIALIZED_INTEGRATION` 合规。
  **已知集成风险预授权**：`scripts/exev0/assert_scope.py:67` 现用两点 diff
  `BASE..HEAD`，merge 主线后必误报——集成指令预授权改为对主线的三点 diff
  （merge-base 语义）或沿 EXE-01R 先例冻结实现终态 SHA，属最小修门。
- **串行集成轮交付与监理复验（2026-08-07，runtime_verified）**：merge `4e09cbf` 零冲突
  （两侧变更文件交集 ∅：主线 123 vs 本包 14；diff 8d909cf..16638f6 恰 14 文件，主线
  零丢失零改写；实现代码自 `cbdf0be` 起逐字节未变）。修门四处——G1 scope 窗主线 SHA
  钉死 `8d909cf` + 双祖先断言（预授权内）；G3 中文路径 `-z`（与 EXE-01R quotePath
  同类缺陷第二次实锤）；G4 未知参数退出码 2（监理 `--wrte` 探针实测）；
  **G2 越权自首，监理裁决：追认批准**——预算门同类窗口缺陷不修则组合门结构性必红，
  文件在其 allowlist 内，台账审计干净（233 条豁免零增零删，仅 EXE-01R 两处合法更新
  create_app 3416 / content_workbench 189，其自身三处冻结值 186/295/241 未动，监理
  逐值复核）。组合门监理独立复跑：golden **958/2/0** + codegen（真实退出码）、exev0
  三门绿、固定样本 digest `aa0b8844…` 第三次逐字节复现（远端 CI 未跑这三门，监理
  本地执行即唯一第三方执行）；CI 三件套精确（run 31192914148 / headSha==`16638f6` /
  success / dispatch）。棘轮探针首轮误设计被执行侧自报为非自证，防假绿意识到位。
  **遗留缺口上报正确并裁决**：ci.yml 不含 exev0 三门 → 授权微轮补 `make exev0-gates`
  并接入 ci.yml（Makefile 与 ci.yml 两文件解禁仅限此目的），微轮复验通过后由监理
  执行集成第 2 步（merge 入主线）。`.python-version` 落地使前轮 venv 变通作废，已确认。
- **微轮交付与监理复验（2026-08-07，runtime_verified）**：远端 HEAD `877566a`，
  diff 恰 3 文件；CI 三件套精确（run 31195442982 / headSha==`877566a` / success /
  dispatch）；runner 日志独立核验——`make exev0-gates` 步骤存在、三门首次远端执行
  （上一 run 日志 exev0 出现 0 次，本轮 9 次），且中文路径在 runner 正常识别
  （G3 `-z` 修复在其唯一发作环境实证）。**第三文件（assert_scope.py 自身）越权自首，
  裁决：追认批准**——门的 ALLOWED/FORBIDDEN 表是授权面的机器可读副本，监理移动授权面
  后副本必须跟动，否则门说假话；解禁仅两条精确路径（监理独立探针：提交
  `.github/CODEOWNERS` 当场被拒"越界（CI 定义禁改）"——目录未被打开；首次未提交
  探针无效系监理自误，diff 门看不见未提交文件，已按正确姿势重探）。
  **监理发现下一层结构问题并授权微轮 2（合入前最后一步）**：scope 门现比对
  `8d909cf..HEAD`，合入主线后会把主线侧后续提交（如 `e5038bf` 指南记录）误判越界 →
  沿 EXE-01R 冻结先例改为双钉死窗口 `8d909cf..877566a` + 双祖先断言，此后主线永续
  提交不再被本包门扫描。**附带裁决**：exev0 函数预算门自合入起成为**后端永续质量门**
  （对应 exe01 的前端棘轮）；后续包新增函数 ≤60 或在各自 Brief 授权下更新台账
  （G2 先例口径）。
- **微轮 2 交付、监理复验与集成第 2 步（2026-08-07，runtime_verified）——EXE-V0 收口
  COMPLETE**：远端 HEAD `4cf1802`（diff 恰 1 文件）；scope 窗双钉死
  `8d909cf..877566a` + 双祖先断言；执行侧三种伪造自证全拦 + 16 文件清单以**上一轮
  runner 日志**为基准逐字比对（非本地自我对照）；BYTE_IDENTICAL 主动收紧为双端冻结
  （保留"本包从未碰过"强主张）。监理独立复验：CI 三件套精确（run 31197511614 /
  headSha==`4cf1802`）；干净门 PASS（冻结口径字样）；篡改探针逐字命中失败文案
  （伪造终点 → "窗口终点…不是当前 HEAD 的祖先"）。**集成第 2 步：merge `d1a0308`
  入主线**；合并后主线 CI dispatch（run 31198555038）全绿——冻结窗设计经受"含主线
  永续提交的树"终极考验，exev0 三门在 runner 执行且通过。**EXE-V0 = COMPLETE**。
  第一部分剩余：founder 画像评审（P0 裁决 3 前置，三段 content_territories 原文
  待提供）→ 画像更新（单独授权）→ EXE-V1（部署 + 有界陪跑，生产动作逐项授权）。
  【2026-08-07 后续修正：画像评审已按 `c1b929c` 关闭——founder 确认画像维持现状、
  **无需画像更新**，校准挪 EXE-V1 冒烟；本行历史规划句保留不改写。】

### EXE-02 · 品牌依据可见闭环（A1 + A2 + FE-07）

- **需求**：`context_selected` 流式事件；条目级 `context_basis.items[]`（`BrandBasisItemV1` 白名单
  字段 + `basis_ref` 无语义公开引用）；`usage_mode` 五分类；依据面板常驻化；`model_parametric`
  徽标渲染规则（D-COMM-08）。
- **上下游承接**：`src/brain/content_service.py:883,2036,2069,2097`（阶段 emit 点）、
  `:2158-2178`（快照投影）；`src/shared/content_snapshot.py:71`（segment 信息被过滤后丢弃处——
  本包核心改动：留下并投影）；`src/gateway/api/app.py:2932`（emit 白名单）；
  `src/gateway/api/contracts.py:79-93` + `frontend/src/app/types.ts:134-141`（合同扩展）；
  `CreatorApp.tsx:1915-1924 / 762-783`（两处折叠块，改常驻）。
- **技术方案要点**：**抽出 `BrandContextSelectionService` 纯服务（SEAM-11，本包核心交付，
  六个下游消费点同源）**；选择结果 → 确定性白名单投影（不加模型调用）；`basis_ref`
  服务端生成、绑定 tenant/account/请求作用域、不可反推 segment/digest；content_locations
  用稳定语义指针不用字符偏移；items 原样冻结进任务快照；旧版本无 items 前端回退；SEAM-03。
- **风险点**：泄漏内部 ID（验收含全载荷 grep 断言，fail-closed）；V5 防漂移复算
  （`delivery_compiler.py:649-680`）不受影响；历史版本零改写。
- **验证标准**：流事件与成品投影逐项一致；载荷 grep 无 segment/digest/sha/prompt；
  不展开任何折叠即可见依据；A7.7 矩阵知识来源各行；`model_parametric` 不入面板品牌依据列表。

### EXE-03 · 今日工作台与帮助分流（A3 + A4 + A5 + FE-05/08/13）

- **需求**：`/user` 今日工作台（四起始入口 + 2—5 张机会卡 + 继续进行 + 品牌上下文摘要）；
  帮助三级分流；五场景演示脚本（doc）；首页动效非阻断化。
- **上下游承接**：opportunities/plan 后端六层全在——`src/gateway/api/app.py:2786/2794/2798`、
  `src/brain/content_control_service.py:465-570`（uuid5 确定性）、
  `tests/test_m7_2a_content_control_surface.py:556`（不建任务反证测试）；被删前端可考古
  git `78183ec`（OpportunityPanel/PlanPanel）；`ProductShells.tsx:72-78`（CapabilityGuide 摘除点）、
  `TenantAdminApp.tsx:5553-5554`（诊断保留点）；`PublicHome.tsx:18`（7200ms 常量）+
  `styles/product.css:275-294`；数据实证引导数据源：`src/brain/formal_readiness.py:315` 一带。
- **技术方案要点**：`features/today/` 新结构；机会卡"用这条开始"只回填输入区与方向；
  空态保留四入口不造假数据；**后端增量：`OpportunityV2` 兼容投影**（现有 V1 仅
  title/seed/selections/why/materials，不足以承载 basis/gaps/difficulty/建议平台形式——
  由后端消费 EXE-02 的选择服务组合投影，**前端不得自行拼装伪依据**；故本包依赖 EXE-02）；
  A5 按 SEAM-09 只交付 A5a。
- **风险点**：未选账号降级路径；机会为空的体验；动效改造的减动效兼容。
- **验证标准**：浏览/刷新/保存计划前后三表计数不变（前端 e2e 复证）；`/user` 渲染 grep 无
  `FT-`/`SHA`/`Schema`/"58 项"；首页首帧 CTA 可见可交互断言；演示脚本 + 一次完整演练记录。

### EXE-04 · 品牌反馈队列（A6 + FE-12）

- **需求**：append-only `brand_basis_feedbacks`（四类反馈 + 四态处理）+ 提交/处理 API +
  租户管理端 `section=brand-feedback` 队列页；与 Ops 能力缺口通道分流。
- **上下游承接**：`basis_ref` 依赖 EXE-02；通道先例 `app.py:2804-2820`（用户提交）/
  `:1219-1238`（运维回告）/ `OpsApp.tsx:249-310`；迁移与租户 RLS（FORCE RLS）先例沿用既有
  alembic 模式；管理端 section 导航 `TenantAdminApp.tsx:508-514`。
- **技术方案要点**：处理动作只能"无需处理 / 建资料补充任务 / 进既有发布候选流程"，
  不提供直改正式知识入口；历史任务依据永不追溯改写。
- **风险点**：权限最小化（内容用户提交、管理员处理，Ops 不可见品牌反馈）；与 unmet 通道误混。
- **验证标准**：append-only 断言；全部测试中正式投影表零写入；权限矩阵测试；
  参谋质量反馈**不**走本表（进 B5#10 台账，见 EXE-08/10）。

### EXE-05 · 交互编排路由与内容创意能力（A7 + FE-06）

- **需求**：`BoundedInteractionOrchestratorV1`（InteractionModeV1 三模式 / IntentProjectionV1 ≤7 /
  CapabilityRegistryV1 静态表 / RouteDecisionV1 + 冻结优先级）+ `ContentAdvisorCapabilityV1`
  （四意图结构化响应）+ A7.0 主动引导（六层栈 + 三分法自评估）+ ChatGPT 体感基准 +
  FE-06 工作区（模式分段控制器 + 路由指示 + 七类结构化卡片）。
- **上下游承接**：`deepseek.py:675-678`（collaborate 通道，SEAM-04 复用）、`:4183-4273`
  （协作 prompt——本包只**新增** advisor 响应 schema，"不追问"条款修订属 EXE-06 范围）；
  `src/brain/natural_entry.py`（高置信短路保留）；`src/brain/creation_intent_gate.py`
  （承诺门原样）；`contracts.py:64-65`（interaction_mode 兼容映射）；
  `src/brain/platform_directions.py` + `config/content_expression/catalog-v1.json`（建议数据源）；
  readiness + opportunities 输入（A7.0"能做什么"确定性投影）。
- **技术方案要点**：新增 `src/brain/interaction_orchestrator.py` + registry dataclass 表
  （六能力含 content_revision，意图→能力唯一映射，required_data_predicates）；新端点
  `/api/v1/interactions/stream`（旧 stream 保留兼容）；意图判定＝确定性信号 → 有界模型
  分类（同一模型、扩展 schema）；自然文本 `message_delta` 增量流为目标、卡片校验后整发
  （降级须改文案，不虚称流式）；`AdvisorDraftV1` 显式草稿合同；`model_parametric` 标注
  贯穿；GKB 零调用（D-COMM-08 工程断言）。
- **风险点**：**与冻结验收的边界**——本包不触碰 create_content 生成路径则无需 fresh rerun，
  但若共享 prompt 段被改动须与守护对齐子集重跑（Brief 中显式裁定）；膨胀为通用 Agent
  （响应白名单 + 审查 13 条防守）；A7.7 矩阵含边界拒答指路行。
- **验证标准**：A7.7 全矩阵；任何路由不建三表；路由结果可见可切换；GKB adapter/endpoint/
  vector 调用为 0；"能做什么"回答与管理端资料可核对。

### EXE-06 · 确认提案合同（B1 + FE-09）【重】

- **需求**：`CreationProposalV1`（字段清单 + 逐字段消费者映射表交付）+ canonical JSON digest +
  HMAC `proposal_token`（SEAM-05）+ 依赖版本钉住 + 原子冻结建任务；协作 prompt
  `deepseek.py:4245` "不追问"条款修订（至多一个可跳过策略问题）；FE-09 提案确认页。
- **上下游承接**：`business_tasks.content_context_snapshot`（expand-only 冻结先例，M7-2A §四）；
  `content_service.py:552-556`（V3 强制点，建任务路径）；`creation_intent_gate`（显式承诺来源）；
  投影 id/digest/画像版本已有快照字段先例（MILESTONE.md TENANT-01 段）。
- **技术方案要点**：确认时服务端验签 + 作用域 + 过期 + nonce + contract_version +
  品牌投影/画像/素材/商品版本一致性；`confirmation_request_id` 幂等（DB 唯一约束，重复
  request_id 回读同一任务、异 request_id 重放同 token 拒绝）；任一真源版本变化 → 确认
  失败要求重新编译提案；确认只重验证不重选（SEAM-11）；同事务建 task/run；"直接制作"=
  系统默认提案一键确认（摩擦增量一次点击）。
- **风险点**：**改运行语义 → 冻结验收子集 fresh rerun**（范围：协作/意图门相关卡 + 抽样生成卡，
  Brief 与守护圈定）；token 重放/跨账号/篡改（验收含攻击用例）；模型通用建议只入
  `system_recommendation`/`accepted_assumptions`（D-COMM-08 第 3 条）。
- **验证标准**：B1.4 全项；R3 抽样（改 `duration_target`/`must_avoid` → 下游产出可观察变化）；
  确认前三表计数不变；提案所见与任务快照 digest 一致。

### EXE-07 · 最低制作包链（B2 + B3 + FE-10）【重·最大单包】

- **需求**：`content_form-v1`（三枚举，SEAM-02 绑定目录 form 轴）；`ProductionPlanV1`（同模型
  独立结构合同）；`WriterOutputV4`（仅 script_blocks + subtitle_cues，D-COMM-05b）；
  `DeliveryCompilerV6`；`source_status` 四态；结构化投影 jsonb 持久化；FE-10 三类制作包页
  （视频步骤表 / 图文页序 / DM01 执行行）+ `LegacyArtifactView`。
- **上下游承接**：`src/shared/writer_request.py:51-57,245-252`（V3 精确集合校验，扩展模式沿用）；
  `src/shared/delivery_compiler.py:471,599-607,649-680`（V5 编译与复算，V6 扩展基座，SEAM-07）；
  `src/shared/types.py:233-262`（既有 Bundle 结构起点）；`content_service.py:2098-2110`
  （持久化点，加 nullable jsonb 列）；`visible_provenance`（`delivery_compiler.py:538-563`，
  扩展覆盖制作包全字段）；退役对象 `CreatorApp.tsx:157-174` / `DisplayApp.tsx:41-56`。
- **技术方案要点**：所有权边界——Planner 只在服务端冻结的 skeleton/slot/资源 allowlist
  内填建议，WriterV4 只回 writer-owned script/subtitle 单元、不返回事实 refs/资源权限/
  服务端 slot；v3 反模式机器判定（subtitle cue 必须是对应 script block **连续原文片段**，
  长度/顺序/覆盖服务端校验 + 逐块 purpose/linked_step 独立信息量）+ 人工抽样双口径；
  存储所有权 SEAM-12（内容/DM01 分表）；`suggested_needs_review` 渲染永不映射确认绿；
  无声音素材时 audio/editing 仅 compiler_derived/suggested；A5b 五场景全链演示随本包交付。
- **风险点**：单包体量——Brief 阶段可评估拆为"后端链 / 前端渲染"两步（守护定，不改总数上限
  精神）；fresh rerun；结构化投影与 body 双源漂移（同一确定性编译产出 + 复算覆盖）。
- **验证标准**：B3.7 全项（含 v3 回归口径 FAIL 判定）；新成品零正则渲染；旧成品兼容回退；
  人工抽样无虚构资源；**完整 26 张冻结集重跑**（hard 26/26、structure 26/26、
  first-draft usable ≥23/26——B3 改全部输出合同，不适用子集口径）。

### EXE-08 · 决策事件与指标（B4 + B5 + FE-11）【重】

- **需求**：`content_version_decision_events`（append-only + RLS）+ 服务端派生只读投影 +
  权限分级（用户：adopted/abandoned/exported；管理员：approved/published_manual 及撤回）+
  FE-11 操作区；B5 北极星 + 10 支撑指标（含 #10 参谋质量反馈率人工台账口径）。
- **上下游承接**：`activity_events` 先例（`postgres_repository.py:1423` content.saved）；
  `workbench_repository.py:1172-1219`（汇总扩展点，`provider_usage.is_complete_billing_total=False`
  口径不变）；SEAM-01（A5 → B4 单源切换）；SEAM-08（北极星口径）；alembic RLS 模式沿用。
- **技术方案要点**：撤回批准不产生内容 V2；导出可多次计数（定义=服务端完成导出准备）；
  `published_manual` 须先 approved；事件 metadata 按类型 Pydantic union + update/delete
  触发器；管理端 `content-review` 二级入口（可审列表 + 只读制作包视图）+
  `PilotMetricsPanel`（并入 FE-11）；派生状态服务端算、前端只读；无自动发布入口。
- **风险点**：schema 变更（nullable/新表可回滚）；双源切换断言（SEAM-01）；权限扩展
  （账号负责团队批准权）明确不在本包隐式做。
- **验证标准**：B4 全项；事件 append-only + 版本行零更新断言；派生投影回读一致；
  北极星按 SEAM-08 可计算且排除 `model_parametric`；RLS 回归全绿。

### EXE-09 · 可用性门与 B 组收口（B6）

- **需求**：≥5 名非开发者目标用户无培训测试（七项 ≥80% 阈值 + 主观评分记录）；B 门对账
  checklist（B1—B5 验收凭据逐项核对）。
- **承接**：用户来源与 FE-00 同批复用（D-COMM-05b）；记录格式与 EXE-10 台账衔接。
- **风险点**：招募与执行是运营工作，不得以自动化测试替代（明文）；不达标 → 回改不放行。
- **验证标准**：留档的测试记录（任务、耗时、误操作、放弃原因、评分）；七项阈值全达标；
  B 门 reconciliation 文档。

### EXE-10 · 试点运营包（C1，doc/process-only）

- **需求**：试点合同要点模板（周期/范围/支持边界/数据责任/退出条件）、线下收费流程说明
  （D-COMM-06：产品零计费工程）、支持渠道与分级、周复盘模板、试点反馈台账
  （含 B5#10 参谋质量分子记录规范）、退出/扩大条件核对表、首次价值会话定义。
- **承接**：B5 指标消费台账（SEAM 无代码接缝，纯运营衔接）；`docs/` 下新增运营子目录。
- **验证标准**：材料齐备 + 首个设计伙伴入驻按 §C1.2 七步走完且无需开发者手改数据库。

### EXE-11 · 高级制作迭代（C2，条件触发）

- 仅在最低制作包获真实试点反馈后另行授权立项；范围见 COMM-01 C2；
  全部高级建议维持 `suggested_needs_review`。未触发即不存在。

### EXE-12 · 试点复盘与 COMM-01 收口（C3）

- **需求**：C3 复盘六件套（采用证据/漏斗/反馈分类/入驻成本/支持负担/模型消耗）+ 继续/收缩/
  停止建议；MILESTONE.md 收口与 successor 门流程（两包 §十一）。
- **验证标准**：主控批准的复盘文档；未经批准不建下一商业化里程碑。

---

## 四、原始问题 → 方案覆盖对照（追溯矩阵）

| 原始问题（三份外部评估 + 四路核查确认） | 承接 | 状态 |
|---|---|---|
| 品牌依据折叠 / 只有类目名计数 | EXE-02 | 补全 |
| 无 context_selected 事件 | EXE-02 | 补全 |
| 成品无条目级回溯（snapshot 丢弃 segment 信息） | EXE-02 | 补全 |
| 登录后空白海报 / 冷启动无从下手 | EXE-03 + EXE-05（A7.0） | 补全增强 |
| opportunities 有 API 无 UI（78183ec 回归） | EXE-03 | 补全 |
| 帮助页暴露 FT/SHA/Schema/"58 项" | EXE-03 | 补全 |
| "不追问直接生成"（prompt 明文） | EXE-05 + EXE-06 | 补全 |
| 发送/生成双按钮心智混乱 + interaction_mode 混层 | EXE-05 | 补全 |
| 无 Brief 层（模糊输入直达成品） | EXE-06 | 补全 |
| 假分镜（"镜头位置 N 承载原句"、台词=字幕） | EXE-07 | 补全 |
| 自问自答默认骨架 | EXE-07（content_form） | 补全 |
| 无采用/批准/发布留痕（主动裁决所致） | EXE-08（D-COMM-03 修订后） | 补全（收窄版） |
| 无价值指标 / 北极星 | EXE-08 | 补全 |
| 知识纠错闭环缺失 | EXE-04 | 补全 |
| 演示路径不成立 | EXE-03（A5 脚本） | 补全 |
| 手工路由 / 整页刷新丢草稿 | EXE-01 | 补全 |
| 巨文件 / 正则猜标题 / 双 CSS / 死样式 / 手写类型 | EXE-01 + EXE-07（触碰时拆） | 补全（绞杀者式） |
| 首页 7.2s 阻断动效 | EXE-03（FE-13） | 补全 |
| 移动端隐藏侧栏 / 小字号 / 双面局限 | EXE-01/03/07（§八 旅程） | 补全 |
| 单位经济 / 计费 | EXE-08 指标 + D-COMM-06 线下 | 补全（零计费工程） |
| 产品化入驻向导 | EXE-10 服务辅助人工版 | **有意推迟**（试点反馈后产品化） |
| 品牌测试实验室 | 人工 checklist | **有意推迟** |
| 管理端全量 IA 重排 | EXE-04 反馈队列 + 诊断分流 | **有意收窄** |

---

## 五、指南维护规则

- 本指南随各包 Brief 立项时更新"实际拆分/实际锚点"，追加式修订、不改写历史；
- 任何包发现锚点与 live 仓库不符 → 以 live 为准并回写本指南（E7）；
- 新增执行包或改变阶段门归属，须先修订 COMM-01/UX-04R 并过守护审查，本指南只跟随。

---

## 六、BRAND-MATRIX-01 · 立项与 founder 一揽子裁决记录（2026-08-07）

- **立项**：新主线 `BRAND-MATRIX-01 · 十账号品牌知识与八剧本全能力演示闭环`（单一里程碑，
  内部结构 S0 + Gate A—E + 主控终审，共六条 Prompt；方案真源为本日主控窗口实施方案 +
  监理六项增强补充）。COMM-01 第二部分（EXE-02—EXE-12）按 D10 暂停，其直接消费者收编入
  本主线；EXE-V0/EXE-V1 交付保留（EXE-V1 终局监理复验并入 S0）。COMM-01 执行包正文的
  supersession 注记待 S0 基线统一时一并追加，本节先行作为裁决登记。
- **founder 一揽子裁决**（原话「全部授权」）：D01—D12 全部按推荐值放行（十账号中文名冻结、
  H02/S02/S04 为明确标识演示角色、画像约束式进入内容且禁原文照抄、P1 必须实现商品依据、
  权威顺序为总部正式事实＞区域/门店普通资料且同级冲突失败关闭、到期资料不进新任务、
  价格本轮不进 ProductFact、私人经历默认单次、反馈首期手工/API 登记不宣称自动接入、
  COMM-01 关系按 D10、Gate A—D 不部署生产且最终唯一候选一次部署、硬边界由系统证明+
  账号差异与可用性逐篇人工裁决）；D13 媒体四项授权（商业使用/二次剪辑/AI 再创作/真人授权）
  一并放行；D14 深度 SKU 由素材侧从 DIYU-CSPU-001—014 提名并预授权，founder 保留替换权。
- **唯一附加条款（媒体标识硬前置）**：26 条云盘视频的品牌标识必须全部统一为「笛语」或
  「DIYU」标识后方可进入正式媒体绑定与 P5 消费。执行口径锚定真源
  《笛语素材品牌标识统一任务表 V1》（DIYU-ASSET-BRAND-UNIFICATION-001）：原始哈希名
  文件只作技术底稿、不进入内容生成；正式使用版本为 `DIYU-V-XXX-MASTER-v1` 命名的笛语
  标识母版（水印/片头片尾/字幕/封面按该表处理）；正式发布另受该表 §六 十项门禁约束。
- **素材路线修正**（founder 两条即时指令）：①素材必须满足十账号×八剧本且**结合现有素材
  不重复输出**；②真实商品视频已有、**款号在现有知识库已有不另造**。据此：首轮 AI 代行
  生成的 13 份虚构素材（虚构 DY-xxxx 款号/虚构主理人/虚构成分工艺）已全部废弃、从未提交；
  改为「真源缺口填补包」——canon 为 Windows 目录《笛语品牌数据库知识数据》21 份文档
  （即生产库 21 份源文档 / 5,046 segment / 14 个 DIYU-CSPU 候选商品 / 26 条 DIYU-V
  视频目录之源）+ 仓库 `docs/品牌入驻候选/笛语服饰/` 4 份重述。缺口填补草案由 Opus
  子 agent 代行草拟（确认人字段一律「AI代行草拟·待founder定稿」），监理复核后另行提交。
- **S0 悬账清单（施工前必须一次收口）**：三线归一（`origin/main` 停在 `bce9747`；监理线
  `95fa010`；执行线 `d7f90df` 载 EXE-V1 部署与交付记录，未合入主线）；EXE-V1 交付报告
  终局监理复验；P0-D1 改判裁定（执行侧提议改为「观测·测量口径错误」）；E1/E2 越权自首
  裁决与 17 个遗留镜像（约 4.9G）处置。
- **待核小旗**：Drive 文件夹当前可见 25 个文件 vs 视频目录登记 26 条（DIYU-V-001—026），
  差 1 条在 Gate A 媒体台账逐条核对时定位。
  【2026-08-07 复核闭旗：Drive 实测 26 个文件与素材草案 `08` 台账文件名逐字 diff
  26/26 完全一致；「差 1 条」系监理计数错误，小旗撤销。】
- **命名 v2 定稿与一致性修复（founder 2026-08-08，supersede D01 原中文名单）**：十账号
  对外命名定稿——H01 笛语服饰（官方母号无后缀）/ H02 笛语主理人·取舍笔记 / H03 笛语·把衣服
  讲清楚 / H04 笛语·出厂之前 / R01 笛语华东·江浙穿衣日历 / R02 笛语四川·巴适穿衣 /
  S01 笛语杭州西湖店 / S02 笛语西湖店·试衣间问答 / S03 笛语湖州吴兴店·街坊衣事 /
  S04 阿野在笛语·成都金牛店（阿野＝演示虚构人名，D02 口径）。组织节点同步：西南区域→
  **四川区域代理**、三门店具体化（杭州西湖／湖州吴兴／成都金牛）；华东保持"总部直属内容
  服务中心"形态，与四川"区域代理"构成联邦模型两形态对照（监理推断，founder 可否决）。
  素材草案一致性修复完成（72 处更名零残留、四川区域知识改写为 7 条盆地特定、S04 原句挂名
  并补口播版），顺带修复一处红线问题（`PS-S04-03` 虚构顾客原话移除，触内容红线 §6.3）。
  **新增开放裁决 D-08**：R02「方言人格」与 canon《DIYU-BRAND-BASELINE-001》§3.5
  「区域和门店账号可以使用本地生活语境，不模仿方言人设」逐字冲突——关闭前 R02 账号名
  保留、正文按 canon 走本地生活语境不建方言人格（安全默认，不阻塞）；若放行方言人格须
  同步修订该 canon 条款。详见素材草案 MANIFEST §6。
- **D-08 关闭（founder 2026-08-08 亲裁）**：最新裁决逐字"区域和门店账号可以使用本地
  生活语境，**可以模仿方言人设**"，supersede 上述 canon 条款。方言人格对全部区域/门店
  账号放行（事实边界与其余红线不变）。对齐范围：素材草案 `01` 注记改关闭记录、`09` 新增
  §4 修订单（`AMD-2026-0808-01`）、MANIFEST §6.4 更新。**Windows V1 原件保持只读未改**
  （版本诚实：V1 内容静默变更会与生产已导入的 5,046 段及既有 digest 失配）；条款正式落库
  随定稿签署经 Gate A 品牌库版本化升级（发布投影 expression_constraint 更新），同时充当
  剧本 7 知识版本更新的真实活案例。**开放裁决项仅余 D-07（柯桥店关系）。**
- **方案 v4 采纳与执行包落盘（founder 2026-08-08）**：BRAND-MATRIX-01 实施方案 v4
  （监理 8 项增强全部内嵌）经 founder 确认对齐并授权串行开工，落盘为规范真源
  `docs/BRAND-MATRIX-01/BRAND-MATRIX-01执行包.md`（REVISION-1）。结构定稿：Prompt 1＝S0，
  Prompt 2—6＝Gate A—E，主控终审为控制动作；Gate A—D 不碰生产。随方案一并受理的裁决：
  ①**旧账号退役授权**（有引用归档隐藏／无引用 synthetic 可精确删除／自然人与历史不删／
  最终激活列表仅十新账号）；②**D-07 关闭**：柯桥店不属于本次十账号，不复用其门店资料，
  不进入 DM01；③媒体授权文字冲突以**追加式裁决版本**修复，不静默改旧文档；④31 条区域/
  门店知识计数以 8+7+6+5+5 为准，MANIFEST"30 条"待 Gate A 纠正；⑤停止条件收敛为四类
  （业务目标变／降隔离安全／超 300 次模型调用／无法安全回退），其余问题执行侧在当前 Gate
  内自主修复。**Prompt 1（S0·基线归一与历史悬账清零）已由监理签发**，基线钉本提交。
- **Prompt 1 守护审查裁定与 rev2 签发（2026-08-08）**：远程守护审查
  `CONDITIONAL_PASS / REVISION_REQUIRED`，六项修正经监理逐条独立核验后**全部采纳**：
  ①S0 状态口径——执行侧只登记 `IMPLEMENTED · AWAITING_SUPERVISOR_REVERIFICATION`，
  四悬账由"预裁定核验成立"待监理复验终裁；②RLS 反证与显式谓词安全纪律拆分（反证
  查询不得带 tenant 条件，仅切 `app.tenant_id`，以 `diyu_app` 角色执行）；③"21 条
  任务"绑定私有证据冻结 task ID 批次逐 ID 对账，当前总量仅旁证；④复核判定改三态
  `VERIFIED / HISTORICAL_ONLY / CONTRADICTED`，现场前进不反证历史报告为假，完成门
  要求零未处置 CONTRADICTED；⑤镜像删除加不可变 dry-run allowlist、全量 digest 标识、
  含停止容器与证据引用检查、删后回验（当前/回退为逻辑类别可同像）；⑥断言与 CI 命令
  具体化——监理实证 `make exe01-gates`/`make exev0-gates`/`.github/workflows/ci.yml`
  真实存在，CI dispatch 必须 `--ref exe/brand-matrix-s0` 防默认分支假绿；并采信审查
  预侦察事实（试合并零冲突、仅 21 个 EXE-V1 文件、无 src 语义改动；`scripts/exev1/`
  连同 secrets 门在 d7f90df 上、合并后才可用，S0 新增文档需专用 secrets 扫描）。
  **Prompt 1 rev2 签发，基线钉本提交。**

<!-- BRAND-MATRIX-01-S0-CLOSEOUT-START -->

### S0 收口记录（执行侧核验稿，2026-08-08）

> 状态：**`S0 IMPLEMENTED · AWAITING_SUPERVISOR_REVERIFICATION`**。以下均为证据绑定的
> 执行侧核验记录，全部待监理复验确认；`COMPLETE / PASS` 只能由监理终裁落款。

#### 1. 基线归一与门控

- 远端权威主线 fetch 后为 `a65c4e2fe4b05bebb4c036fac5c81758d683d734`；执行线
  `d7f90dffaf6a79ec4a5144818fed5a4099c459a1` 零冲突合入。
- merge commit：`ad8d471fb0a042952f3d7fc5fd16317fcee75872`。净增量严格为 21 个
  EXE-V1 文件（15 文档、6 脚本），无 `src/`、前端、migration 或测试语义改动；冲突处置为无。
- 合并后全量本地门：`git diff --check` 通过；pytest 958 passed / 2 skipped；EXE-V0 3/3；
  EXE-01 9/9；前端 lint/typecheck/test/build；EXE-V1 secrets；Ruff；mypy 全部退出码 0。

#### 2. S0-2 三态明细

| 项 | 判定 | 核验摘要 | 私有证据锚点 |
|---|---|---|---|
| EXE-V1 原证据完整性 | `VERIFIED` | 34/34 checksum 全量复算成功 | `01_exev1_sha256_check.txt` |
| 生产运行面 | `VERIFIED` | 运行代码身份一致、容器 digest 与冻结 digest 一致，三端点 200，schema `20260817_44` | `03_runtime_readonly.txt`、`05_schema_readonly.txt` |
| 冻结 21 任务批次 | `VERIFIED` | 21/21 逐 ID 存在，抽样 3/3 为 `server_assembled`；当前任务总量 324 仅作旁证 | `07_frozen_batch_result.txt`、`11_current_tenant_task_count_result.txt` |
| RLS 反证 | `VERIFIED` | `diyu_app` 非超管、无 BYPASS、RLS 生效；无租户谓词同 SQL 只切上下文得到 9→0 | `08_rls_counterproof.sql`、`09_rls_counterproof_result.txt` |
| 历史 CI | `VERIFIED` | run `31207012048` 为 `workflow_dispatch`，head SHA 等于部署实现，success，19 步非成功数 0 | `12_historical_ci_run.json`、`13_historical_ci_jobs.json` |

汇总：`VERIFIED=5`、`HISTORICAL_ONLY / SUPERSEDED=0`、`CONTRADICTED=0`；无未处置矛盾。

#### 3. P0-D1 核验记录

**预裁定核验成立（附 S0-2d 证据锚点）· 待监理复验确认。** P0 的 `false` 来自数据库
超管视角；应用真实角色 `diyu_app` 实测 `rolsuper=false`、`rolbypassrls=false`、
`row_security_active=true`，无租户谓词反证为 9→0。执行侧支持改判为
**「观测 · 测量口径错误」**，最终改判由监理落款；原 P0 登记保持原文并已追加核验注记。

#### 4. E1/E2 核验记录

- **E1：事实核对无误 · 待监理复验确认。** 授权内 44 个无 binding `diyu-saas` 镜像
  回收支持【追认】；扩大到 `diyu-tenant01-wip` 的越授权尝试支持【驳回】。护栏已拦、已停手，
  影响面为零数据损失、扩权未遂、零运行容器影响。
- **E2：事实核对无误 · 待监理复验确认。** 658MB 纯构建缓存回收结果支持【追认】，同时
  登记一次「先做后报」程序违规；生产端任何清理动作继续执行先报、冻结范围、再做。

#### 5. 镜像处置摘要

- 删除前 55 个唯一镜像、20 个容器（含停止容器）；当前运行、回退锚、最终候选三逻辑类别齐备。
- 17 个 `diyu-tenant01-wip` 经不可变 dry-run allowlist 逐项证明容器、binding、部署/回退、
  systemd 与私有证据完整 digest 零引用。allowlist SHA-256 为
  `a4511397b1e046dec51e22ccc5b168ecdbc610823510eca15ff5359dcd570c1c`。
- 仅以完整 image ID 精确删除 allowlist 内 17 个镜像；删除后唯一镜像 38、WIP 剩余 0。
- 两个 `diyu-tenant01-final` 因 `final` 语义承重且不在已接受的 17 镜像悬账内，按存疑保留。
- 删除后当前与回退镜像 inspect 成功，运行容器 digest 未变，三端点 200；生产应用与数据库
  无写入，模型调用为 0。

#### 6. 执行侧状态

四笔悬账已形成 4/4 证据绑定核验记录；密封盲测托管规则与空登记表已就位。执行侧仅登记
`S0 IMPLEMENTED · AWAITING_SUPERVISOR_REVERIFICATION`，等待监理复验终裁。

<!-- BRAND-MATRIX-01-S0-CLOSEOUT-END -->

<!-- BRAND-MATRIX-01-S0-SUPERVISOR-VERDICT-START -->

### S0 监理复验终裁（2026-08-08）

> 状态：**`S0 COMPLETE · PASS`**（监理落款）。本记录只登记监理独立复验事实与终裁，
> 执行侧收口记录（上方 CLOSEOUT 块）原文保留。

#### 1. 监理独立复验（不依赖执行侧证据文件的重测）

| 面 | 独立手段 | 结果 |
|---|---|---|
| Git 面 | `git ls-remote` + 祖先/范围重算 | 执行分支 HEAD `7583239` 精确匹配；主线 `a65c4e2`、`main`、EXE-V1 分支均未被执行侧触碰；`a65c4e2..7583239` 恰为 EXE-V1 合并（`ad8d471`）+ 2 笔 S0 记录提交；范围 28 文件、修改类 3 文件全部 append-only（0 删行）；`素材草案-v0`、`alembic/`、`src/`、前端零改动 |
| 证据面 | 本机重算 | 私有证据根 0700，27/27 `sha256sum -c` 通过；`SHA256SUMS` 自身 digest 与报告逐字符一致 |
| CI 面 | `gh api` 直查 run `31251813432` | `workflow_dispatch`、head SHA == `7583239`、`success`、19 步非成功数 0（含 0 skipped） |
| 生产面 | SSH 只读重测 | 唯一镜像 38、WIP 0、2 个 `diyu-tenant01-final` 存疑保留在位；运行容器 image == 冻结 digest `9a1dea01…`；`DIYU_RUNTIME_SHA=95fa010`；`/health/live`、`/health/ready`、`/api/v1/status` 均 200 |
| RLS 面 | 独立 READ ONLY 会话重跑无谓词反证 | `diyu_app` `rolsuper=f`、`rolbypassrls=f`、`row_security_active=t`；仅 `set_config` 切换上下文 9→0，与执行侧结果完全复现 |
| 合并面 | `git diff --quiet` 树比对 | 主线合并结果树与 `7583239` 逐字节相同，CI 绿色结论对合并后主线直接成立；合并断言 `28/28` 范围、双 secrets 扫描通过后门控提交 |

#### 2. 四笔悬账终裁落款（4/4 关账）

- **P0-D1**：正式改判为**「观测 · 测量口径错误」**并关账。依据：执行侧 S0-2d 证据 +
  监理独立反证两次一致——超管路径的 `row_security_active=false` 只描述超管视角，应用
  真实角色 `diyu_app` 下 RLS 实际生效。原 P0 登记与执行侧注记均原文保留。
- **E1**：授权内 44 个无 release binding `diyu-saas` 镜像回收**【追认】**；扩大到
  `diyu-tenant01-wip` 的越授权尝试**【驳回】**（护栏已拦、未遂、零损害）。关账。
- **E2**：658MB 纯构建缓存回收**【追认】**；「先做后报」程序违规记录在案，规则维持
  「先报、冻结范围、再做」。关账。
- **EXE-V1 交付主张**：5/5 `VERIFIED`、0 `CONTRADICTED`，EXE-V1 里程碑**正式闭结**。

#### 3. 镜像处置审计结论

allowlist 17/17 精确删除、删后 WIP 归零、当前/回退锚 inspect 正常、运行容器 digest 未变、
三端点 200——**通过**。2 个 `diyu-tenant01-final` 按「存疑保留＝已处置」条款关闭，如需
回收须另立裁决。被删 WIP 不可本机恢复、仅可源码重建的事实已如实登记。

#### 4. 状态推进

- `S0 → COMPLETE`；模型调用累计 0（执行侧 0 + 监理 0），Gate D+E ≤300 配额未动。
- 下一动作：**Prompt 2（Gate A · 素材定稿、消费通道与导入合同）签发**。

<!-- BRAND-MATRIX-01-S0-SUPERVISOR-VERDICT-END -->

### Prompt 2（Gate A）签发记录（2026-08-08）

- 基线：`55b1a5ea7ef8101f1029f360e427de0a330554d7`（S0 关账后主线 HEAD）；执行分支
  `exe/brand-matrix-a`；模型调用配额 **0**；生产接触 **0**（本 Gate 不得 SSH）。
- 监理签发前亲核事实（写入 Prompt accepted_facts，执行侧不再重验）：
  区域/门店知识实数 **31 条**＝`RK-EC-01..08`(8，含过期样本 `RK-EC-08`)＋`RK-SW-01..07`(7)
  ＋`SK-HZ-01..06`(6)＋`SK-HuZ-01..05`(5)＋`SK-CD-01..05`(5)；`素材草案-v0/MANIFEST.md`
  的「全部 30 条」为漏计 `RK-EC-08` 的误计数，按 Gate A 合同追加式纠正、v0 冻结不改；
  「四组 J」锚定 `06-P1穿搭决策资料.md` 四款决策组；两条系列名（「各自站住」「同一件外套
  的四个位置」）为 `演示虚构·待founder定稿`，入 founder 签署页。
- 完成门含 founder 素材定稿签署；执行侧终态只允许
  `GATE-A IMPLEMENTED · AWAITING_SUPERVISOR_REVERIFICATION`。

> **基线勘正（2026-08-08，监理）**：上条记录中「基线 `55b1a5e`」为监理复验关账时点
> HEAD；Prompt 2 实际 `EXPECTED_BASE_SHA` 为**含本勘正在内的签发链最终主线提交**，
> 具体 SHA 以 chat 签发件载明值为准。执行侧以 chat 签发件为唯一基线真源。

<!-- BRAND-MATRIX-01-GATEA-CLOSEOUT-START -->

### Gate A 收口记录（执行侧核验稿，2026-08-08）

> 状态：**`GATE-A IMPLEMENTED · AWAITING_SUPERVISOR_REVERIFICATION`**。以下结果均为执行侧
> 核验，**待监理复验确认**；本记录不代替 founder attestation，不把 Gate A 置为 COMPLETE。

#### 1. 合同结果

- 25/25 文档具有唯一主通道；30 个原子消费项零未分类，整篇 Markdown 进入 Writer 为 0，
  internal/template/not publishable 进入 Writer 为 0。
- import manifest 精确包含账号/组织/深度 SKU/系列/区域门店条目/媒体/J/修订单/异常样本
  `10/6/4/2/31/26/4/1/8`；十账号五段画像 `50/50`、ContentRole `10/10`、组织绑定 `10/10`。
- manifest SHA-256 为
  `14fed12141dc3b277c09c878a2a30ef71b445ce8ea31457c0122b403aeb48a06`；构建器两份独立
  临时输出逐字节一致，非仅比较摘要字符串。
- 四组 J 的 `judgment_owner` 均为商品负责人/H03；`approved_by=founder` 与业务所有权分离，
  `approved_at=null`。四个深度 SKU 保留 V/P/C/R，正式 ProductFact 只纳入 V 字段。
- 媒体 26/26 `source_sha256=null`、`sha_verification=pending_gate_d`、母版未完成、当前
  `P5 eligibility=false`；授权裁决、逐人物/儿童证据、第三方核验与母版状态分字段保存。
- D-07 已追加式关闭；媒体授权 v2 已追加式登记；空白签署页绑定唯一 digest，状态
  `AWAITING_FOUNDER_SIGNOFF`，签名与时间均为空。

#### 2. 冻结与隐私

- Windows 21 份真源、`素材草案-v0` 11 文件与仓库四份参考字节差异均为 0；21 份真源完整
  blob 与候选树交集为 0；Gate A 新写面秘密、凭据、私钥和私有绝对证据路径命中为 0。
- 未修改 `src/`、`alembic/`、`frontend/`、冻结脚本目录、`docs/项目记忆.md` 或主线；模型调用
  0、生产接触 0，未读 `.env`。

#### 3. 本地门

- Gate A：build、scope/manifest/privacy 断言在提交前最终候选上门控；manifest 与 privacy
  已通过，scope 在本追加记录完成后执行。
- 既有回归：`git diff --check`、`make lint`、`make typecheck`、`make golden`、
  `make exev0-gates`、`make exe01-gates`、前端 lint/typecheck/test/build、
  `bash scripts/test.sh` 全绿；Golden 与独立全量测试均为 `958 passed, 2 skipped`，EXE-V0
  3/3，EXE-01 9/9。
- `CI_SCOPE=existing_regression_only`：最终提交 push 后的 workflow_dispatch 四查由执行报告
  登记；现有 CI 不执行 `scripts/gatea/**`，不得用远程 CI 替代本地 Gate A 专属断言。

#### 4. 诚实边界与下一动作

本 Gate 未导入数据库、未创建/退役账号、未迁移授权、未接通运行时消费者、未取得原始视频、
未计算媒体 SHA、未制作母版、未接触生产、未获得 founder 最终签署。唯一下一动作：监理独立
复验；PASS 后由主控组织 founder 对上述 digest 作独立 attestation。

<!-- BRAND-MATRIX-01-GATEA-CLOSEOUT-END -->

<!-- BRAND-MATRIX-01-GATEA-SUPERVISOR-VERDICT-START -->

### Gate A 监理复验记录（2026-08-08）

> 状态：**`GATE-A VERIFIED_BY_SUPERVISOR · AWAITING_FOUNDER_SIGNOFF`**。监理复验通过，
> 但 Gate A 完成门含 founder 素材定稿签署，签署完成前不得置 `COMPLETE / PASS`。

#### 监理独立复验（重测，非采信执行侧证据）

- **Git 面**：执行分支 HEAD `15190da` 精确匹配；基线祖先关系成立；主线未被执行侧触碰；
  范围恰 18 文件，治理两文件 append-only（0 删行）；`素材草案-v0`、`docs/品牌入驻候选`、
  `src/`、`alembic/`、`frontend/`、冻结脚本目录零改动。
- **manifest 面**：监理独立双跑构建器，两次输出互相逐字节一致**且与已提交
  `import-manifest.json` 逐字节一致**；digest 精确等于
  `14fed12141dc3b277c09c878a2a30ef71b445ce8ea31457c0122b403aeb48a06`；计数
  `10/6/4/2/31/26/4/1/8`＋文档 25 全部实测吻合。
- **内容面**：31 条区域/门店条目前缀分布 8/7/6/5/5 与监理签发前亲数一致，`RK-EC-08`
  状态 `expired_demo_sample_not_current`；媒体 26/26 `source_sha256=null`、
  `sha_verification=pending_gate_d`、母版空、`p5_eligibility=false`、云盘文件名保留在
  `declared_identifier`（较签发件"SHA 列登记声明值"更严谨，予以采认）；J 4/4 六字段齐备、
  `judgment_owner`(H03/商品负责人) 与 `approved_by=founder` 分离、`approved_at=null`；
  异常锚点 8/8 指向真实对象 ID（含 `PS-S04-03` 经查证为合法单次授权条目）；25/25 分类表
  文件名互换处理正确、画像类 4 份改判画像通道、R 级守卫项零消费方。
- **隐私面**：Gate A privacy 断言 PASS；监理另行独立计算 21 份 Windows 真源 git blob，
  与候选树交集 **0**；EXE-V1 与 S0 secrets 断言复跑 PASS。
- **CI 面**：`gh api` 直查 run `31254885113`：`workflow_dispatch`、head SHA==`15190da`、
  `success`、19 步非成功 0。执行侧如实申报 `CI_SCOPE=existing_regression_only`
  （CI 不跑 `scripts/gatea/**`）——监理本地以 Ruff/mypy 补验 4 个脚本全绿，缺口关闭。
- **合并面**：合入主线树与 `15190da` 逐字节相同（CI 结论直接覆盖），断言门控提交。

#### 状态推进

- Gate A 推进至 `VERIFIED_BY_SUPERVISOR · AWAITING_FOUNDER_SIGNOFF`；模型调用累计 0。
- 下一动作：主控向 founder 提交 manifest digest 签署请求；签署记录落盘后 Gate A 置
  `COMPLETE`，随后签发 Prompt 3（Gate B）。

<!-- BRAND-MATRIX-01-GATEA-SUPERVISOR-VERDICT-END -->

### Gate A COMPLETE 落款（2026-08-08，监理）

- founder 已对 manifest digest `14fed121…aeb48a06` 完成签署（记录
  `ATT-GATEA-20260808-01`，原话「签署确认，digest 14fed121 开头那份」，主控会话文字确认）。
- 监理确认签署未改写冻结 manifest（digest 复算不变）。Gate A 完成门全部满足：
  **`GATE-A COMPLETE · PASS`**。
- 机制进化记录：`assert_gatea_manifest.py` 的「签名区必须空白」检查系交付态专用不变式，签署后按「协议缺陷改工具」原则进化为二态合法（空白待签／已签且登记绑定 digest），杜绝签署后门禁误报。
- 下一动作：签发 Prompt 3（Gate B · 账号语义正向消费与七族品牌关联）；基线为含本落款
  的主线最终提交，具体 SHA 以 chat 签发件为准。

### Prompt 3（Gate B）签发记录（2026-08-08）

- 基线：本签发记录提交自身（SHA 以 chat 签发件载明值为准，沿用基线勘正惯例）；执行分支
  `exe/brand-matrix-b`；模型调用配额 **0**；生产接触 **0**；本 Gate 允许本地 PG 跑测试。
- 监理签发前亲核代码锚点（写入 accepted_facts）：`account_editorial_lens.py`
  `_LENS_PRODUCTS` 现仅 `{brand_life_narrative, local_response}`（P3/P4）；
  `task_value_assembly.py` 七族枚举注释明言「V0 只装配前四族」；`content_service.py`
  商品依据仅对 P2/P5 装配；五类产品键以 ADR-013 表为准（P1 `dressing_decision`／
  P2 `product_truth`／P3 `brand_life_narrative`／P4 `local_response`／
  P5 `visual_styling_story`），P5 建简报前必须绑定真实商品（ADR-013 §5）。
- 范围：扩 lens 至 P1—P5、五道 AND 门显性化（禁静默 None）、P1 取得商品依据、七族全部
  可生产、degraded 可见、topic fidelity、旧快照旧解释；禁新增 Reviewer/第二模型/语义
  词表/服务端固定成稿；alembic 与 frontend 冻结（确需迁移→停+报）。
- 执行侧终态只允许 `GATE-B IMPLEMENTED · AWAITING_SUPERVISOR_REVERIFICATION`。

<!-- BRAND-MATRIX-01-GATEB-CLOSEOUT-START -->

### Gate B 收口记录（执行侧核验稿，2026-08-08）

> **待监理复验确认**。本记录只证明 Gate B 候选实现和本地门结果，不代替监理独立复验。

- 新任务账号 lens 升级为 V4，精确覆盖 P1—P5；V1—V3 冻结解析保留。唯一入口
  `resolve_account_editorial_context` 的同一解析结果进入 PublicationContract、任务快照、
  WriterRequest、DeepSeek adapter 与确定性 stub；修订和平台改编继续回放冻结合同。
- 五个显式降级码 5/5：`unsupported_content_product`、`account_profile_missing`、
  `account_profile_identity_incomplete`、`account_profile_not_confirmed`、
  `brand_context_incompatible`。快照和现有 context_basis 可读脱敏状态，静默 `None` 为 0；
  本 Gate 未新增前端页面。
- P1 三路径成立：合法选定商品冻结 V 级事实、J 判断条件和 digest 并送入 Writer；未选商品
  仍可走自然关联；明确索要商品但多选/依据不足时失败关闭。候选价格、效果、性能、精确工艺
  及 P/C/R 不升格。
- 七族 7/7 具备类型化、带来源和实际消费引用的合同；后三族缺媒体/组织/人物授权资格引用时
  失败关闭。没有自然路径时显式 degraded、`demonstration_eligible=false`，不硬插商品或品牌
  收尾，生活题材不改写成商品题材。
- 确定性测试覆盖 H01/H03/S02 同种子差异：事实、平台、central job 和资源不变，账号观察/
  判断/受众/立场至少两维变化，profile ID/digest 正确变化；P1—P5 均有正向消费断言；一条
  ContentService→PublicationContract→snapshot→WriterRequest→stub→context_basis 零模型纵向通过。
- 本地门：Gate B scope/semantics/privacy、`git diff --check`、Ruff、mypy、Golden、EXE-V0
  3/3、EXE-01 9/9、前端 lint/typecheck/test/build、独立 `scripts/test.sh` 与两套既有秘密
  断言全绿；Golden 和全量测试均为 `984 passed, 2 skipped`。CI 四查在最终推送提交上执行，
  结果待监理复验确认。
- 七族合同能力成立；后三族的正式组织、素材和人物资格由 Gate C 承重验证。模型调用 0、生产
  接触 0；未导入素材、未建十账号、未执行组织过滤/生命周期/授权、未制作母版。
- 下一动作：监理独立复验 Gate B；PASS 后才可签发 Gate C。

<!-- BRAND-MATRIX-01-GATEB-CLOSEOUT-END -->
