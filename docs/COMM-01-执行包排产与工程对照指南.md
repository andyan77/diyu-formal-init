# COMM-01 / UX-04R 执行包排产与工程对照指南（V2）

> V2（2026-08-06）：终审 `PASS_WITH_BOUNDED_CORRECTIONS` 十二项有界修正已同步进
> 两份 REVISION-6 执行包与本指南（选择服务前移、OpportunityV2、反馈两表、A5a/A5b、
> 交互 API 版本化与流式诚实、B1 防重放幂等、B3 所有权与完整 26 卡、B4 管理员入口与
> 语义冻结、B5 口径冻结、术语/编号残留清理）。转 `APPROVED_FOR_EXECUTION` 待守护确认。

- 性质：**非规范性工程参考**。规范真源是
  [COMM-01 执行包](COMM-01-品牌价值可见创作参谋确认提案与付费试点最小闭环执行包.md)（REVISION-5）与
  [UX-04R 执行包](UX-04R-前端产品化增量与工程边界执行包.md)（REVISION-5）；两者与本指南冲突时以执行包为准。
- 用途：各执行包立项 Brief 的工程对照；每包开工前按 E7 纪律以 live git 复核本指南全部代码锚点
  （行号会漂移，事实不允许靠快照假定）。
- 依据：2026-08-06 四路只读核查（`static_verified`，file:line 证据）+ 两包 REVISION-5 全文。

---

## 一、排产总览（12 包，顺序即依赖序）

| # | 执行包 | 承接工作项 | 风险级 | 阶段门 |
|---|---|---|---|---|
| EXE-01 | 前端地基与体验蓝图 | FE-00—FE-04 | 中 | 先行门 |
| EXE-01R | EXE-01 有界返工（founder 2026-08-07 追加裁决，EXE-02 前置） | 五项：作用域事务化 / task 深链补实现 / 流校验补强 / 证据矩阵重做 / 远端集成证明 | 中 | 先行门 |
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
