BRAND-MATRIX-01 · Prompt 5 rev3 · Gate D：正式接线（D0）、隔离库完整预演与媒体母版完成
（rev3 取代 rev2 全文；经外部审查+监理逐条实测采纳后重签，主线 c913a1d 有案）

【0 · 身份与基线】
- 你是 BRAND-MATRIX-01 执行端，本轮只做 Gate D。规范真源：docs/BRAND-MATRIX-01/BRAND-MATRIX-01执行包.md §五 Prompt 5 段；状态真源：MILESTONE.md。
- 基线校验（与此前不同，注意）：继续使用既有分支 exe/brand-matrix-d；校验 `git merge-base exe/brand-matrix-d <主线>` == bd5a6bfac1c196f059242e5f42fe6c5efbec5b06 即可，不要求主线 HEAD 相等（主线新增的治理提交无需并入）。**现有未提交草稿保留，禁 reset、禁重建平行分支**。
- 隔离铁律：生产接触 0；alembic 冻结（基线 schema=20260818_45，确需新迁移→停+报）。
- Gate C 已勘正为「底层机制 PASS；正式写入与消费接线由本 Gate D0 承担」。
- 模型纪律（最硬约束）：在完成 D0 + 两轮导入 + 媒体资格预检 + 全量工程门 + CI 绿 + 唯一候选 SHA 冻结**之前，禁止任何 provider request**。目标 ≤80；推算 >120 → 停+报；D+E 合计绝对 300、累计 240 预警；逐笔 ledger；禁择优、禁逐卡补丁、禁跨 SHA 拼接。
- 密钥纪律（founder 授权 + 审查收窄）：**不得 source 整个 .env**。只允许以不回显值的精确解析方式，从 /home/faye/workspace/diyu-formal-init/.env 读取三个键：DEEPSEEK_API_BASE_URL / DEEPSEEK_API_KEY / DEEPSEEK_MODEL，注入进程环境。禁打印/禁日志留值/禁写证据/禁提交；ECS、生产数据库及其他一切变量不得载入或使用。
- 开工前置自检（任一不满足 → PRECONDITION_BLOCKED）：
  ① /home/faye/workspace/diyu-formal-init/var/media-staging/ 恰有 26 个视频（10 .mov + 16 .mp4）+ SHA256SUMS；独立 `sha256sum -c` 26/26 OK；文件名去扩展名后与 Gate A manifest declared_identifier 集合完全相等；该目录只读；
  ② 精确解析后三个 DEEPSEEK_* 键均非空（只测存在性）；
  ③ ffmpeg / ffprobe 可执行；④ 本地 PG 可用。

【1 · accepted_facts（监理已亲核，delta-only；冲突→停+报）】
a. Gate A/B COMPLETE；Gate C = MECHANISM COMPLETE（schema 45 六新表 FORCE RLS/预留状态机/观察层 DDL 约束/条目级作用域读取链全部成立，全量 1002/2 绿）；正式管理路径缺口实测确认：contracts.py 条目请求仅旧四字段、workbench create_brand_publication_candidate V1 写法、TenantAdminApp 仅提交旧四字段、Gate C 测试裸 SQL 插 V2——这就是 D0 要补的面。
b. 导入真源 = docs/BRAND-MATRIX-01/GateA-素材合同/import-contract.json 与 import-manifest.json（只读冻结，digest 14fed12141dc3b277c09c878a2a30ef71b445ce8ea31457c0122b403aeb48a06）：账号 10（每账号 platforms=douyin/xiaohongshu/wechat_video + product_mix）/组织 6/深度 SKU 包 4/系列 2/区域门店条目 31（含过期 RK-EC-08）/媒体 26/J 4/AMD-2026-0808-01/异常锚点 8。
c. 原片监理已实测：26/26 齐、ffprobe 全过、SHA256SUMS 26 行、stems 与 declared_identifier 零差异；.mov/.mp4 并存为真实状态，登记保留真实扩展名。
d. 前置态 fixture 复刻演示租户等价形态（9 旧账号+代表性历史，synthetic 标记），不拷贝生产。
e. 八剧本/八异常定义冻结于执行包 §三；剧本 7 证据 = AMD v1/v2。
f. 母版规范锚定《笛语素材品牌标识统一任务表 V1》：DIYU-V-XXX-MASTER-v1、十项发布门、原片永不获 P5 资格。
g. 门禁命令同前；CI 四查 --ref exe/brand-matrix-d；二进制不入 git。

【2 · D0：正式管理写入与消费接线（一切模型调用的硬前置）】
D0-1 定向解冻（仅限本闭环必需，禁无关重构）：src/gateway/api/contracts.py、对应 repository/service、frontend/src/app/TenantAdminApp.tsx、及配套 API/interaction/Chrome 测试。
D0-2 正式 React/API 能创建、预览、确认、读取 publication-contract-v2 条目，字段齐备：tenant/brand/organization_id/visibility_scope/version/effective_at/expired_at/authority level/semantic subject/claim key/source refs。
D0-3 客户端不得自行授予权威或作用域：前端只提交业务选择，服务端按当前管理员/品牌/组织/来源派生并校验最终合同字段。
D0-4 正式纵向证据：React/API 创建候选 → 服务端校验 → 管理员确认 → 新内容任务装配 → 任务快照出现真实 projection item ID/版本/组织作用域/source refs。
D0-5 反馈观察正式面：可经正式 API 登记反馈、管理端可读观察记录、明确不自动升格 F/J/G、下一任务不得把未确认反馈当正式来源。
D0-6 authorization 与 qualification：importer 可初次建库，但须经正式 repository/service 校验；管理端或正式诊断接口可读资格状态与不可用原因；禁止只靠测试 SQL 证明。

【3 · 导入器完成门（禁止按行数过门）】
3-1 账号：正式逻辑根账号严格 = H01—H04/R01—R02/S01—S04 共 10 个；按合同为每账号创建 douyin/xiaohongshu/wechat_video 平台载体；根账号列表只显示 10 个；逻辑账号/ContentRole/五段画像/组织/平台载体关系全部可回读。9 旧账号归档隐藏、历史按原 ID 可回读。
3-2 31 条区域/门店资料：每条登记明确去向；可发布项进入 V2 projection（组织/作用域/生命周期/权威/claim 字段齐备）；internal 项保留不进 Writer 理由；RK-EC-08 因过期不得进入新任务；至少用正式任务证明总部/华东/四川/杭州/湖州/成都的正向消费与反向隔离。「数据库存在 31 行」不是完成证据。
3-3 四组 J：在 P1/P2 相应任务中形成实际决策依据引用，不只证明存在。
3-4 两条人物授权（PS-S02-05、PS-S04-03）：建 authorization + 对应 qualification；一次成功后核销、第二次拒绝、失败释放预留。
3-5 导入全流程：dry-run → apply → 盘点 → 恢复隔离快照 → 再导入；两轮 batch digest 与对象指纹逐字节一致。

【4 · 八剧本必须走正式消费者】
剧本1 总部 F/J/G：管理端创建或导入，任务快照引用实际 F/J/G；
剧本2 华东资料：R01 消费；R02 与无权门店不消费；
剧本3 杭州资料：S01/S02 消费；S03/S04 不得读取；
剧本4 成都错误普通文件：可保存，不成正式事实，不污染成品；
剧本5 同一 SKU 四节点（总部/华东/杭州/成都）独立任务：ProductFact 核心一致，lens/brand_relevance_path/组织资料/成品表达真实差异；
剧本6 同一种子三账号（H01/S02/S04）：操作人/逻辑账号/ContentRole/组织作用域/成品视角不混同；
剧本7 AMD v1/v2：更新前任务冻结 v1，更新后任务用 v2，旧任务与 digest 不变；
剧本8 反馈观察：正式 API 登记、观察层可见、不升格、后续任务不消费该反馈。
八异常样本同样优先走正式 API/repository 路径；只有正式路径无法制造的数据库级破坏反证才允许受控 SQL fixture。

【5 · 媒体母版与 P5 资格分离】
5-1 26/26 生成带「笛语/DIYU」标识母版，逐条登记 source SHA（与监理 SHA256SUMS 交叉一致）/master SHA/ffprobe 信息/标识位置/处理版本；母版二进制留执行工作树 var/（untracked）。
5-2 每条母版独立评十项发布门，结果只能 PASS 或 FAIL/QUARANTINED；未知授权不得按 PASS。
5-3 人物/儿童/第三方元素/平台权利/有效期/商品绑定证据不足：母版保留、不激活、不获 P5 资格；原片 P5 资格恒 0。
5-4 「26 个母版导入」≠「26 个商品绑定」，报告分开列。
5-5 P5 正式预演前置：至少两份十项门 PASS 的母版，分别绑定两个不同正式商品，当前启用、作用域合法、版本与 checksum 冻结；不满足则在调用 Writer 前停止 P5、差分 0/0/0、如实报告媒体证据缺口。

【6 · 唯一候选冻结顺序（硬顺序）】
A 完成 D0+导入器+媒体处理器+全部确定性测试 → B 两轮导入与账号/载体/作用域/授权/媒体资格预检 → C 全量 pytest+Ruff+mypy+前端四门+显式 Chrome → D 提交、push、CI 四查 success → 冻结唯一候选 SHA → E 登记候选 SHA/代码配置/数据 manifest/媒体 manifest/Prompt 合同/模型/temperature/max_retries → F 冻结后才运行一次正式模型验收（八剧本+八异常）。
首次 provider request 后：禁改代码/Prompt/oracle/数据/媒体，禁单卡补丁、禁择优重跑、禁跨 SHA 拼接；**允许 docs-only 的 ledger/审阅包/治理记录提交**（监理裁定，不构成拼接）。发现共享根因只允许一次共享实现修复：保留失败证据 → 新 SHA → 从确定性工程门完整重跑。

【7 · 写面与禁区】
- 允许写：src/**、frontend/src/app/TenantAdminApp.tsx 及 D0-1 列明配套（禁无关 UI 重构）、tests/**、scripts/gated/**、docs/BRAND-MATRIX-01/GateD-记录/**、执行工作树 var/**、治理日志与 MILESTONE（只追加）。
- 只读：var/media-staging/（原片+SHA256SUMS）；GateA-素材合同/**；素材草案-v0/**；Windows 真源；docs/品牌入驻候选/**。
- 禁止：alembic/、scripts/{exev0,exev1,exe01,s0,gatea,gateb,gatec}/**、生产/SSH/ECS、密钥值任何形式留存、主线、其他 worktree、用户未提交修改、二进制入 git。
- 提交纪律：断言与 git add/commit 同一条 && 链。

【8 · 完成门（10 项全部成立才可报 IMPLEMENTED）】
1 V2 projection 的正式 React/API 创建/确认/读取/任务消费纵向成立；
2 10 逻辑根账号 + 全部目标平台载体成立，旧 9 账号归档；
3 31 条资料均有明确消费通道，组织资料有真实任务消费证据；
4 四组 J、authorization、qualification、反馈观察均有正式消费者；
5 26 母版全部完成 checksum 与诚实十项门三态裁决；
6 P5 仅在两份不同商品的合格母版成立后执行（否则如实停止并报缺口）；
7 八剧本 8/8 + 八异常 8/8 按书面判据通过；
8 全部 provider request 齐账、未超预算、全程唯一 SHA；
9 全量工程门+Chrome+CI 全绿；
10 生产接触 0、密钥泄漏 0、二进制入 git 0。
报告必须分层列明：数据「已存储」/「已进入 projection」/「已被任务快照引用」/「已进入最终成品」——不得以一层替代另一层。
终态只允许：GATE-D IMPLEMENTED · AWAITING_SUPERVISOR_REVERIFICATION。

【9 · 停止条件】
仅四类：业务目标改变／需降低隔离或安全／模型调用超限（推算 >120 即停；240 预警；300 绝对）／无法安全回退。另：前置自检失败、merge-base 不匹配、确需新迁移、accepted_facts 冲突 → PRECONDITION_BLOCKED。

【10 · 报告格式】
完成门逐项；D0 纵向证据锚点；导入两轮 digest；账号/载体/作用域回读证据；母版台账摘要（PASS/FAIL/QUARANTINED 计数）；P5 前置判定结果；八剧本/八异常逐条二元结果+审阅包路径；ledger 汇总；冻结候选 SHA 与登记项；git 提交链与远端 HEAD；CI run 号与四查值；四层分层口径（存储/投影/快照引用/成品）；诚实边界；下一动作 = 监理复验 + founder 逐篇审阅。
【Prompt 5 rev3 · 独立审查补正条款】

本条款是 rev3 的组成部分；与 rev3 其他文字发生冲突时，以本条款为准。

一、基线与草稿保护

1. 开工必须执行：
   git fetch origin
   当前分支必须为 exe/brand-matrix-d。
   c913a1d38a522ecfed790b75ee822cb82f96fad8 必须是
   origin/claude/brand-knowledge-pilot-review-8a3105 的祖先。
   merge-base(HEAD, origin/claude/brand-knowledge-pilot-review-8a3105)
   必须等于 bd5a6bfac1c196f059242e5f42fe6c5efbec5b06。

2. 先记录现有未提交文件清单及 SHA256。
   禁止 reset 或覆盖式 checkout。
   “保留草稿”不表示必须保留草稿中的错误实现：
   审计存证后，可以在 Gate D 范围内修改、拆分或删除错误草稿代码。

3. 开工第一笔提交必须把本 rev3 全文及本补正条款逐字保存为：
   docs/BRAND-MATRIX-01/GateD-记录/Prompt-5-rev3.md
   并登记文件 SHA256，避免只靠聊天窗口作为执行真源。

二、D0 字段所有权

1. 正式持久化及响应字段使用 schema 45 的真实命名：
   - projection.contract_version
   - item.visibility_scope
   - item.scope_organization_ids
   - item.effective_at
   - item.expires_at
   - item.authority_class
   - item.semantic_subject_type
   - item.semantic_subject_id
   - item.claim_key
   - item.scope_contract_version
   - source_ref/source_version/source_digest

2. tenant_id、brand_id、contract_version、scope_contract_version、
   authority_class、source_ref、source_version、source_digest
   必须由当前登录上下文和服务端来源记录派生，客户端不得提交或覆盖。

3. 前端只呈现业务可理解的输入：
   - 来源选择；
   - 发布用途和适用内容；
   - 可见范围；
   - 获准组织；
   - 生效与失效时间；
   - 必要的事实主题分类。

4. semantic subject 与 claim key 如需管理员选择，只能从服务端根据
   当前来源生成的受控候选中选择，禁止任意自由文本自行获得正式事实资格。
   服务端必须复核来源、组织和 publication_role 的一致性。

5. React/API 纵向测试必须同时证明：
   请求不能越权提交治理字段；
   响应和数据库中完整 V2 字段成立；
   新任务快照消费的是正式确认后的 V2 item。

三、账号和平台载体精确计数

1. 创建10个逻辑根账号：
   H01—H04、R01—R02、S01—S04。

2. 每个根账号按现行正式模型：
   - 根账号自身承载抖音；
   - 创建一个小红书 carrier；
   - 创建一个微信视频号 carrier。

3. 最终精确断言：
   - logical roots = 10；
   - carrier rows = 20；
   - 矩阵相关 content_accounts = 30；
   - platform/format targets = 40：
     10 抖音视频、
     10 小红书图文、
     10 小红书视频、
     10 微信视频号视频。

4. 管理页面逻辑账号列表只能显示10个根账号；
   carrier 只能作为根账号的平台目标显示，不得显示成20个额外独立账号。

四、媒体三态和 P5 终态

1. 十项媒体门定义：
   - PASS：十项均有可验证证据；
   - FAIL：已有证据证明不符合；
   - QUARANTINED：证据未知、不完整或待确认。

2. QUARANTINED 不得按 PASS 使用，也不得绑定为正式商品媒体。

3. 26/26 母版完成只证明技术母版生成完成，不证明：
   - 26/26 可发布；
   - 26/26 获得商品绑定；
   - 26/26 获得 P5 资格。

4. P5 前置不足两份不同商品的合格母版时：
   - P5 task/run/version = 0/0/0；
   - Writer/provider request = 0；
   - 保存媒体资格缺口证据；
   - Gate D 终态为
     GATE-D EVIDENCE_BLOCKED · MEDIA_QUALIFICATION_INSUFFICIENT；
   - 不得报 IMPLEMENTED，不得要求模型绕开媒体合同。

5. 只有至少两份分别绑定不同正式商品的 PASS 母版成立，
   P5 剧本才可进入正式模型验收。

五、唯一运行候选与冻结面

1. 工程和 CI 冻结时登记 runtime_candidate_sha。
   所有正式模型响应必须绑定该 SHA。

2. 同时冻结并计算 digest：
   - Prompt 合同；
   - 模型名；
   - temperature=0；
   - max_retries=0；
   - Gate A manifest；
   - 导入 batch；
   - 账号和平台关系；
   - publication projection；
   - 媒体台账和母版 SHA；
   - 八剧本与八异常输入；
   - 本地隔离数据库基础指纹。

3. 冻结后禁止管理员资料、账号、投影、媒体和 Prompt 发生修改。
   模型运行只允许新增验收 task/run/version/evidence。

4. 运行后允许 docs-only 提交，但必须：
   - 另记 documentation_sha；
   - frozen runtime_candidate_sha 不变；
   - runtime_candidate_sha 到 documentation_sha 的 diff
     只能落在 GateD 证据索引、治理日志和 MILESTONE；
   - src、frontend、tests、scripts、配置和数据 manifest 差异必须为0；
   - docs-only 提交不得冒充新的运行候选或触发第二套承重 CI。

六、模型调用纪律

1. 正式参数固定：
   temperature=0，max_retries=0。

2. 每个需要内容生成的剧本只接受一次有效模型响应。
   响应到达后禁止因质量不理想再次调用。

3. 能由权限、作用域、生命周期、冲突或媒体资格确定失败的异常样本，
   必须在 provider 调用前失败，provider request=0。

4. readiness 如实际访问 provider，必须：
   - 位于候选冻结之后；
   - 计入 ledger；
   - 不得生成或替代正式内容响应。

5. 读取 .env 时禁止 shell source、eval 或命令替换。
   必须使用进程内解析器只读取三个精确键，拒绝重复键、畸形行和多行值；
   直接把三键注入验收子进程，不打印中间值。

七、证据隐私

1. raw response、完整 artifact、任务快照和未脱敏品牌引用保存到：
   ~/diyu-evidence-brand-matrix-gated-<runtime_sha>/
   目录权限0700，文件权限0600，并生成 SHA256SUMS。

2. Git 只允许提交：
   - 脱敏 evidence index；
   - 文件 SHA；
   - task/run/version UUID；
   - 二元结论；
   - 必要的短摘录；
   - 私有证据路径。

3. 禁止把21份真源全文、完整模型 raw、原始视频、媒体母版、
   密钥或数据库导出提交 Git。

八、验收归属

1. 执行侧可以完成：
   - machine hard boundary；
   - structure；
   - 执行侧逐篇初审；
   - 八剧本和八异常的初步二元结论。

2. 执行侧不得自称完成 founder 或监理的独立人工终审。

3. GATE-D IMPLEMENTED 只表示10项工程完成门均成立，
   终态仍须为：
   GATE-D IMPLEMENTED · AWAITING_SUPERVISOR_REVERIFICATION。

4. 若出现媒体资格不足、硬边界失败或唯一候选模型套件失败，
   必须使用对应的 FAILED_SAFE/EVIDENCE_BLOCKED 状态，
   不得用“正确阻断”替代8/8交付。
