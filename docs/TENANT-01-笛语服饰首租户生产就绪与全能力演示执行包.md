# TENANT-01 · 笛语服饰首租户生产就绪与全能力演示执行包

## 当前状态

- 里程碑：`TENANT-01`
- 状态：`REVIEW`（execution-control 已从 `DEPLOY_READY` 正式转移；不得自行 `CLOSED`）
- 唯一写入执行端：当前 WSL Codex
- Git 启动基线：`94fa541f4b5a8f9c3fab5de6d826473440b6dd30`
- UX-03：`CLOSED / PASS`
- 最终运行锚点：运行实现 `748190c552c6b9610aa951bd346fe8903ef51121`，镜像
  `sha256:edc8dfc45f9cea82fd29ac656aa660c86ac3b50c1fb4c02df3b4d64f2cd617a4`，schema
  `20260813_40`；公网／回环 ready、live、status 均为 200
- 工作树保护：`docs/项目记忆.md` 用户未提交内容全部保留，不暂存、不提交；最终 diff SHA-256
  `96862202b06fd7821797d984215163069e8598a8641209ebae629ca2df0baaf7`
- 私有资料：仅从用户指定 Windows 目录只读；原文不得进入 Git、CI、公开日志或公开证据

### 2026-08-03 用户现实表达合同纠偏

- `80ed1437e8797829f6eb323adf0d5a04205756cc` 在旧“用户现实字面独占”合同下正确失败；旧
  raw、artifact、ledger、失败 run、checksum 与清理证据原样保留，不回写成当时没有失败。
- 主控已裁决旧合同属于产品误杀。当前唯一政策为
  `user-actuality-natural-expression-v2`：Writer 可在标题、导读、正文和配文中自然引用、复述、
  调整语序，并补充低风险即时反应、感受、比喻和文学性承接；这些文字始终是未验证
  `creative_expression`，不能取得 `fact_ref`、回写可信事实或获得权限与媒体资源。
- 确定性硬门只负责服务端事实原文／引用／所有权、租户与权限、资源、版本、digest、AIGC 和
  失败原子性。不得再因 Writer 文字包含 `user_actuality` 字面，或包含用户未逐字提供的低风险
  自然叙事补全而判硬失败；商品／品牌 canonical fact、价格、库存、性能、功效和内部商品计划
  边界没有放宽。

### 2026-08-03 历史正式验收失败结论（已被上述产品裁决取代）

- 最终运行候选：`80ed1437e8797829f6eb323adf0d5a04205756cc`。该 SHA 的
  `git diff --check`、Ruff、mypy、Golden／OpenAPI `785 passed, 2 skipped`、前端 lint／
  typecheck／interaction／build 与显式 Chrome Gate A—D 全部通过；受保护项目记忆 diff
  SHA-256 始终为 `96862202b06fd7821797d984215163069e8598a8641209ebae629ca2df0baaf7`，
  未暂存、未提交。
- 唯一正式 acceptance run 为 `tenant01-final-20260803-80ed143`。首张 `coffee` 已收到
  `deepseek-v4-flash` 的 intake 与 Writer 两个有效响应（request count 2）；Writer 在
  creative body 中再次写入冻结事实“居然是甜的”，并添加“入口的瞬间却愣了一下”等当前用户
  现实细节。确定性事实所有权校验因此返回“Writer 不得复制或改写服务端事实块”。
- 数据库结果为 task 1、failed run 1、version 0、artifact 0；没有半版本或永久 running。
  旧程序把该结果分类为硬边界失败并进入 `FAILED_SAFE`；这一历史分类与当时执行结果继续保留，
  但已被本次主控产品裁决取代，不再阻止新 candidate-scoped acceptance run。没有发生 push、
  CI、备份、部署或生产变更。
- 完整私有失败包位于
  `/home/faye/.local/share/diyu-tenant01-evidence/80ed1437e8797829f6eb323adf0d5a04205756cc/acceptance-26-v1/`，
  含 checkpoint、两阶段 raw、失败摘要、清理结果和可复算 `SHA256SUMS`。本轮 task 1、run 1、
  series 2、activity event 3、仍存在的临时 session 2 已按 UUID 清理；另外 2 个旧 session
  已不存在；相关对象和永久 running 均为 0，失败证据保留。
- 只读生产现场保持运行实现 `f77a2e852758b9157425633041aea59d9f2b24da`、镜像
  `sha256:f869aa605f3bc81a429a56a4081b1c4eabaa351587245f5b8aa73fb19f7bb683`、schema
  `20260813_40`，公网／回环 readiness、liveness 与 `/status` 为 200。本轮没有触发生产写入。
- 历史共享根因是把“creative expression 中出现用户现实字面”等同于“Writer 改写可信事实”。
  当前修复改以结构化 `fact_kind`、unit owner、fact refs 与 provenance 判断事实所有权，不增加
  Reviewer、语义词表、固定成稿或 coffee 专属分支。

## 唯一结果

笛语服饰作为首个正式租户，生产已具备管理员配置组织、账号画像和成员的能力；当前管理员已
激活，存在 1 个逻辑发布账号，但账号画像为 0，尚未创建正式内容成员，内容能力为
`ready_after_admin_action`。管理员完成画像和成员配置后才能开始正式内容生产。21 份授权资料
以源文档和稳定语义 segment 原子入库，14 个候选商品以 V/P/C/R 字段证据边界入库并由正式内容
上下文按任务相关性消费。P4、P5、DM01 的正式资料缺口继续分别诚实显示；软件功能真值与租户
资料就绪度分开。最终候选须完成本地门、两份有界审查、权威 CI、备份恢复、生产部署、隔离
恢复库黄金套件、旧镜像往返回退和精确清理，随后进入 `REVIEW`，不得自行 `CLOSED`。

## 主控终审退回与本次有界返工

- 历史 `96dcb74…` 十一卡、4.13 平均分和生产证据完整保留，但正式消费者审计已经退回：原始
  segment 仍可直接进入 Writer，单卡自然语言 3 分会被平均值掩盖，且当前没有正式 tenant_user
  时租户就绪度仍错误显示 `ready`。
- 本次只关闭三项共享根因：建立已确认、版本化的品牌发布投影作为新任务唯一品牌资料消费者；
  将产品审阅改为十一卡逐卡、逐维度均不低于 4 的二元门并绑定最终全文引用；让租户资料就绪度
  取决于同一条启用用户、账号、画像、平台及商品路径。
- 返工完成前，旧十一卡不得继续作为当前通过结论，TENANT-01 保持 `ACTIVE / BOUNDED_REWORK`。
- 共享责任纠偏的直接失败基线为 `0fa063645d8ee6f3b68b93af1ae071dbb2c7c234`：该 SHA 的
  十一卡人工初审为 4 PASS／7 FAIL；对应 raw、artifact 与逐卡结论永久作为失败候选保留，
  不删除、不改写，也不拼接进后续候选。

### 2026-08-03 最终裁决：机器硬门与首稿产品质量分轨

本段是当前最高优先级验收合同，取代下方历史 WIP 中“十一卡逐维度全部不低于 4”“等待是否
开放 Writer”以及“任意自由中文语义可由服务端确定性证明”的停止口径；历史候选、失败原因、
raw、artifact、ledger 和审阅输入均继续保留，不改写成从未发生。

1. 服务端确定性保证可信事实、来源、字节等值、引用、权限、资源、tenant／brand／organization／
   private 隔离、版本、摘要和失败原子性。这些机器硬门在 26 个冻结样本中必须 `26/26` 通过。
2. Writer 输出的标题、导读、正文和配文全部属于未验证 `creative_expression`，永远不得升级为
   ProductFact、BrandFact、真人事实或其他 trusted fact。系统要求 Writer 不生成未支持商品
   效果或健康诊断，但不声称能确定性理解并排除任意中文中的所有隐含语义。
3. 成品字段完整性和平台结构必须 `26/26` 通过。自然度、观点力度、品牌关系和首稿采用价值属于
   产品质量门，以冻结样本首稿可用率至少 `23/26` 验收，不再要求每张首稿一次完美，也不得用
   平均分掩盖机器硬边界或结构失败。
4. 冻结样本的人工语义安全审阅只证明该批样本，不证明未来任意输出。质量失败可由用户一次自然
   反馈形成追加式 V2；事实、权限、资源、隔离、版本或摘要硬失败不能通过 V2 洗白。
5. `config/tenant01/semantic-holdout-v1.json` 是已经公开且冻结的历史文件名；其内容、Git blob 和
   SHA-256 不再修改，正式身份改称“冻结泛化回归集”，不得冒充真正盲测。最终实现 SHA 冻结后，
   由主控使用未公开小样本进行一次独立抽检，执行端不得预先读取或据此补 Prompt、规则、fixture
   或 oracle。
6. 不新增生产 Reviewer、第二模型、模型投票、fallback、语义词表、规则引擎、服务端固定成稿
   或审批状态机；系统仍不自动发布，用户在采用或发布前自然阅读全文。

验收与证据实现 `8055dfbd0d861b73aa1fa4d6f14d910566072813` 已将 11 张既有回归卡和
15 张冻结泛化卡绑定为唯一 26 样本口径：`machine_hard_gate=26/26`、
`structure_gate=26/26`、`first_draft_usable>=23/26`。finalizer 逐文件复算 raw／artifact／
result SHA、visible digest、task／run／version 和人工引用；人工 `product_usable=FAIL` 可被诚实
记录，任何硬门失败、结构失败、预填 PASS、配置漂移或证据缺失均失败关闭。该提交没有修改
Writer、Prompt、Compiler 或业务语义，当前仍是本地 WIP，不构成 CI、部署或 REVIEW 结论。

### 2026-08-02 最终共享语义编译返工：责任矩阵与冻结保留集

本段是当前施工真值，取代下方历史 WIP 的“只保留 publication-contract-v2”结论；历史失败、
raw、artifact、ledger 和人审输入继续原样保留。`ba95a1f…` 只作为诊断候选，不得用其中预填
PASS 生成最终 manifest。新任务只允许沿一条链路执行：输入角色解析 → 任务相关上下文选择 →
`PublicationContractV3` → `WriterRequestV3` → `CreativeKernelV5` →
`DeliveryCompilerV5` → 确定性硬边界 → 原子保存 → 独立产品审阅。

| 问题 | 违反的不变量 | 当前错误作者 | 正确责任作者 | 共享修复 | 同时关闭的历史失败 | 承重回归 |
| --- | --- | --- | --- | --- | --- | --- |
| 创作命令混入现实事实 | 现实事实只能是服务端冻结的连续原文 span | intake 结果被整段输入兜底 | `InputRoleResolver` | 两个内容 API 共用同一 span 验证与生成授权；模型只能选择已有 span | daily、P1 事实复述 | 三种不同命令字面的 offset／byte 等值和 `0/0/0` mutation |
| 原始品牌资料或不相关资料进入 Writer | Writer 只能消费本题确认发布投影 | repository 丢弃 `weak_seed/products` 后按位置和预算截取 | `BrandContextSelectorV3` | 按作用域、内容产品、题材、明确商品／资料、账号和平台确定性选择；无 raw fallback | coffee、family、zero-topic 的品牌脚手架与画像复读 | held-out 表格／目录／采集／流程不进入，确认公开项正常进入 |
| “存在／冻结”冒充“实际使用” | UI 只能声明本题真实消费与展示 | context packet 与 UI 投影 | V3 消费记录＋presentation | 分开记录 `available/frozen/consumed/displayed`，UI 只投影后两者 | 所有“资料已入库但正文无关”的假绿 | API／React 同一 snapshot 投影与 displayed refs 反证 |
| 多套语义合同竞争 | Writer 只能接收一个最小业务合同 | Plan、Lens、claim、unit responsibility、repair 同时约束 | `PublicationContractV3` | 固定事实／用户控制／系列／产品责任／账号／平台优先级，仅保留六条负向边界 | P1、coffee、family、zero-topic 模板化 | 正向自然表达 mutation 不被句式门拒绝；恢复旧层变红 |
| 商品内部验收文本进入正文 | 商品机器计划不拥有可见文案 | `ProductValueContract.visible_text`／Compiler | `ProductDecisionBasisV2`＋Writer | 机器字段仅冻结理解、取舍、条件和 fact refs；规范事实由服务端逐字插入 | P2 合同语言、通用安全说明 | visible_text 直出 mutation 变红；canonical fact 字节等值 |
| Writer／Compiler 争夺观点与收束 | Writer 独占非事实成稿；Compiler 只编译结构 | kernel purpose、Compiler 固定媒体文案与收束 | Writer＋`CreativeKernelV5`／`DeliveryCompilerV5` | Kernel 只存 unit 所有权和 refs；Compiler 只绑定槽位、事实、披露、来源 | P1 固定骨架、P4 含混收束、跨卡观看链复读 | 恢复固定观点 mutation 变红；跨题材媒体职责比较 |
| 系列只换词不推进 | 每篇必须有冻结的新任务和新判断 | 通用 series context／Writer | `SeriesEpisodeContract` | 冻结前文事实、判断、本篇任务、必需新增判断、位置和 topic origin | series2／series3 | V1→V2→V1、topic origin、两次新增判断反证 |
| 确定性校验冒充自然语言 Reviewer | 软件硬门只证明可计算边界 | post validator／repair／evidence oracle | 确定性 checker＋独立人审 V2 | checker 只验所有权、字节事实、refs、资源、结构、AIGC、digest、RLS 和原子性 | 4/7、平均分及预填 PASS 假绿 | Human Review V2 字段、原文引用、逐卡二元门和 finalizer mutation |

直接消费者清单冻结如下；施工完成前不得只修主 Writer 入口：

| 合同 | 生产者 | 全部直接消费者 | 用户可见 | 当前处理 |
| --- | --- | --- | --- | --- |
| 输入 span／角色 | 服务端 candidate＋受控 intake 选择 | direct API、stream API、NarrativeFrame、PublicationContract、snapshot、revision replay、evidence | 只有 actuality 事实块可见 | 合并到统一 resolver |
| 品牌投影／消费状态 | confirmed publication projection＋selector | ContentService、WriterRequest、snapshot、context_basis、React、finalizer | consumed/displayed 类别可见 | 新增 V3 状态投影 |
| 商品 canonical fact／DecisionBasis | ProductResolver＋confirmed V 字段 | PublicationContract、WriterRequest、Compiler、snapshot、revision、evidence | canonical fact 与 Writer 自然解释可见 | 机器计划与文案分离 |
| PublicationContract | ContentService | WriterRequest、Kernel builder、snapshot、revision、evidence | 字段名和安全条款不可见 | 新任务仅 V3，旧版只读 |
| WriterRequest | PublicationContract 投影器 | DeepSeek writer、raw request digest | Writer 输出可见 | 只允许四类自然成稿字段 |
| CreativeKernel | Writer response＋服务端 unit owner | Compiler、snapshot、revision、evidence | 单元文字经 Compiler 可见 | V5 去除句式／claim 责任 |
| MediaProgram／Envelope | 服务端 | WriterRequest 的槽位提示、Compiler、snapshot、revision、evidence | 最终媒体结构与条件式建议可见 | Writer 前冻结，不反向授权 |
| DeliveryCompiler | 冻结事实＋Kernel＋MediaProgram | artifact、presentation、snapshot patch、digest、evidence | 最终成品 | V5 不写观点／收束 |
| Human Review V2 | 一次真实全文人工审阅 | finalizer、manifest、私有证据 | 不进入成品 | 不默认 PASS、不用平均分 |

冻结泛化回归集的历史文件名为 `config/tenant01/semantic-holdout-v1.json`，含 15 个与既有十一卡
不共享原句模板的合成场景，覆盖新生活／家庭／零题材、P1—P5、商品事实充分与不足、有／无
登记资源、明确风格修订、系列、跨平台、健康／商品效果诱导及跨品牌差异。文件首次落盘后以
Git blob 与 SHA-256 共同冻结；SHA-256 为
`e773158aef2a22e3d4344f20c80bdf90b5bd9d19c0d3012b4f5fd0b00d1dcda7`，首次 Git blob 为
`89fef8e9201501548e32cb5e7d8684808be57dad`。当前只将其称为“冻结泛化回归集”，不称盲测；
后续不得为通过输出修改题目、期望或人工门。

### 本轮共享责任合同与直接消费者清单

当前落盘候选只保留 `publication-contract-v2` 这一份新任务负向安全合同；它不是句式 DSL，
也不替代既有事实轨、资源包或版本合同。字段生产与消费关系如下：

| 合同内容 | 唯一生产者 | 直接消费者 | 用户可见 | 保留方式 |
| --- | --- | --- | --- | --- |
| 精确输入跨度及现实／创作／风格角色 | `CreationIntentGate` 结果经 `ContentService` 绑定原始 offset | `NarrativeFrame`、任务快照、Writer brief、证据 finalizer | 现实原句仅由 Compiler 逐字插入；角色标签不可见 | 新任务冻结；修订重放 |
| `topic`、中心任务、受众回报和一般建议范围 | `ContentService` 按内容产品与已确认上下文构造 | Writer、证据 finalizer | 只显示 Writer 的自然成品，不显示字段名 | 新任务冻结 |
| 六条负向安全边界 | `publication_contract` 单一常量 | Writer、快照校验、证据 finalizer | 不可见 | 新任务冻结 |
| 账号观察身份、受众、关注顺序和回应边界 | 已确认五段画像／当前发布投影，经 `ContentService` 投影 | Writer、任务快照、证据 finalizer | 只通过自然视角体现，不得照抄画像 | 版本和 digest 冻结 |
| `ProductValueContract` 内部计划 digest | 已确认 ProductFact 的确定性投影 | Writer 的选择目标、Compiler／finalizer 绑定 | 内部字段和防越界说明不可见；事实块仍逐字插入 | 新任务冻结 |
| MediaProgram、槽位和资源引用 | 服务端在 Writer 前确定 | Writer 只知内容职责；Compiler 绑定槽位；finalizer 复算 | 只显示最终媒体编排 | Envelope／Program／资源版本冻结 |
| Writer 四类自然表达单元 | Writer | Compiler、快照、证据 finalizer | 标题、导读、正文、发布配文 | 追加式版本冻结 |

已删除或停止供新任务消费的重复层包括：固定 P1 正文骨架与发布配文、AccountEditorialLens
V4／V5 的逐单元句式职责、全句 `claim allowlist`、`sentence_shape`／`text_shape`、强制问句、
强制二选一、强制“下次观察”收束，以及 Compiler 固定创意观点。历史 V1—V3 Lens 与既有
artifact 继续只读；失败候选中的 WIP 合同只保留在 Git／证据历史，不建设新的生产兼容层。
新发布路径检测到冻结事实复述、账号资料整句复制或机械整段重复时直接失败关闭，不进入旧的
语义 repair；finalizer 只接受 `intake → writer` 两次模型调用证据。

### 共享责任收敛与三卡停止结果（2026-08-02）

- 失败基线 `0fa0636…` 至当前确定性收口实现 `1614f6b…` 只做普通前向提交。新任务已删除固定
  P1 正文骨架／发布配文及整个 287 行 `server_bearing_expression.py`；
  `account_editorial_lens.py` 从 260 行降至 200 行，`deepseek.py` 从 4,920 行降至 4,694 行。
  新增的 `publication_contract.py` 为 409 行单一负向安全合同及其版本／digest 绑定，不再并存
  sentence shape、全句 claim allowlist、unit 唯一句型或 repair 语义限制。
- 停止消费的重复约束层：固定 P1 成稿、固定 P1 配文、Lens V4／V5 逐单元句式责任、强制问句、
  强制二选一、强制“下次观察”、Writer 全句 claim 分类、Compiler 固定创意收束。保留的唯一
  负向边界只有事实不可改写、商品效果必须有 ProductFact、品牌方法不得升级为事实、资源闭世界、
  一般建议保持条件身份及不得新增健康／法律／交易高风险现实结论。
- 定向确定性套件、Ruff、mypy 与 `git diff --check` 在真实三卡调用前均为绿色；恢复整段输入为
  事实、恢复固定 P1 成稿／配文以及恢复 P2 防越界说明冒充用户取舍的 mutation 均真实变红后
  恢复。`1614f6b…` 另关闭 P2 证据重编译接缝：完整冻结 ProductFact 注册表用于责任校验，只有
  本次选择的事实块进入可见正文；保存的正式 P2 快照已无模型重编译通过。
- `0286749…`、`48d8249…`、`49ee04a…` 的 raw、artifact 和失败事实分别保存在本机 0700／0600
  私有证据目录，不删除、不改写、不跨 SHA 拼接。最新 `49ee04a…` 三卡在同一 SHA、同一模型、
  temperature 0、max_retries 0 下各执行一次并已全文阅读：P1 给出轻外套／针织开衫、厚薄取舍
  和出门前体感／风感检查，达到可用选择帮助；P2 在冻结颜色事实外新增抢眼、内敛、耐看、百搭
  等未确认商品语义，`FAIL`；daily 在用户仅说事情接连发生、回家忘记喝水的事实外新增身体需求
  ／信号、专注占用、身体生活被调成静音及照顾自己的健康、心理和因果解释，`FAIL`。
- 三卡二元门因此未通过。按照冻结顺序，没有运行完整工程门、最终十一卡、CI、备份或部署，也
  没有把工程证据回放修复冒充内容通过。继续只能新增语义 Reviewer／规则层、恢复服务端固定
  成稿，或放宽事实安全边界，均会改变本轮冻结责任合同；状态保持 `ACTIVE / BOUNDED_REWORK`，
  等待主控对这一项产品责任作出明确裁决。

### 条件式开放 Writer 的两轮有界复验（2026-08-02）

- 用户裁决后，执行端没有恢复固定成稿、全句 claim allowlist、Reviewer、词表或后置语义清洗；
  `c0fa1bf…` 先收敛单一负向安全合同，`714558a…` 修正短事实复述边界并让 WIP runner 在单卡失败
  时继续完成其余卡，`9da7432…` 进一步把现实片段中的当前人物排除出 Writer 的推断主体。定向
  受影响测试、全仓 Ruff、mypy（131 个源文件）和 `git diff --check` 均通过。
- 第一轮完整三卡 `714558a…`：P2 形成商品专属颜色选择、取舍和成立条件，`PASS`；P1 仍把冻结
  条件改写为当前用户经历，并新增服装类别的便携、温度和收纳效果，`FAIL`；daily 新增身体信号、
  精力分配、节奏需要松动和呼吸结果，`FAIL`。
- 第二轮完整三卡 `9da7432…`：P2 完成正式版本；P1 Writer 再次逐字复述冻结现实且同时新增十度
  阈值、服装收纳和温度效果，被服务端硬门失败关闭、没有版本；daily 虽完成正式版本，但仍新增
  身体需求、意志力、大脑占用、疲惫、干渴和身体提醒等健康／心理／因果解释，人工判定 `FAIL`。
- 两轮均为同一现有 DeepSeek 配置、temperature 0、max_retries 0，三卡成组执行，不择优、不跨
  SHA 拼接；私有 raw／artifact 继续保存在对应 SHA 的 0700／0600 本机证据目录。按照用户冻结的
  最多两轮治理，执行端没有继续补第三轮 Prompt 规则，也没有运行最终十一卡、完整门、CI 或部署。
  这证明确定性事实／资源／版本边界仍有效，但单 Writer 的自然语义没有达到本次产品门。
- 本段记录的是当时的停止事实；2026-08-03 主控已经采用机器硬门与统计产品门分轨的最终裁决，
  不再等待 Writer 责任决定。本段的 `ACTIVE / BOUNDED_REWORK` 仅是历史检查点；当前状态以
  文末“最终 REVIEW 交付”为准，不得创建 TENANT-02。

## 冻结业务与安全边界

1. 公开品牌规范名称为“笛语”，“笛语服饰”只作为管理显示名和检索别名。
2. `diyu-fashion-admin` 只拥有租户管理员职责；管理员和租户用户入口互斥。
3. 自然人、工作资格、逻辑发布账号、ContentRole、五段画像和平台／形式继续分离；一个逻辑
   账号共享一份画像并拥有四个目标。
4. synthetic／legacy 从普通服务端查询源头排除，但不可变历史不删除；折线之间 tenant 不处理。
5. ProductFact 只消费明确获准的 V 类字段；P/C/R、价格、库存、功效、体验和设计动机不得绕道
   升级为事实。
6. 品牌源文档保留原始状态与 provenance；本轮授权只表示允许按语义类型使用，不把候选、建议、
   推断或模板升级为客观事实。
7. 品牌上下文按任务相关 segment 形成版本化冻结包；修订、系列续写和平台改编重放冻结上下文。
8. 无正式登记并明确选择的媒体时，不产生商品媒体能力或 P5；DM01 继续纯文字、零模型、库存守恒。
9. 租户／品牌／组织／私人 RLS、追加式版本、AIGC、失败原子性和资源闭世界不得回退。
10. 不新增模型供应商、Reviewer、DIFY、向量库、知识图谱、消息队列或第二套真值平台。

## 执行路径与完成门

执行顺序固定为：生产前像与源文件冻结 → 正式纵向失败矩阵 → expand-only 合同与 RLS → 正式
API／React 消费者 → 原子幂等 dry-run／导入 → BrandContextPacket 与双真值 → 本地纵向、反证、
完整门和两审 → 运行候选／CI → predata/predeploy 备份恢复 → 部署与原子激活 → post-import
隔离恢复库黄金套件 → 生产浏览器检查 → 旧镜像往返回退 → 精确清理 → 权威文档收口。

只有全部 18 项冻结工程交付门真实成立，才将 TENANT-01 置为 `REVIEW`。这组完成门不等于首租户
全部业务目标 100%。失败历史、生产前像、源批次 digest、正式运行 SHA、CI、镜像、schema、
备份、隔离黄金证据和清理结果均在本文件后续追加；
不为内部阶段建立子状态机或平行台账。

## 历史 `96dcb74…` 本地候选证据（已被取代）

- schema head 已由 Alembic 实测为 `20260812_39`；新源文档、版本、segment、字段证据、门店精确
  资格和门店档案版本表均启用并强制 RLS，新增复合 tenant／brand 外键均为已验证状态。
- 私有源批次本地 dry-run 冻结 21 个 source document、5,046 个稳定 segment、14 个候选商品和
  203 条字段证据（V 42／P 145／C 15／R 1），其中 26 个纯 V 字段获准进入 ProductFact；首轮
  原子导入和同批重跑 no-op 均在一次性隔离数据库成立，隔离数据库已销毁。
- 正式 React／API／PostgreSQL Gate A Chrome 纵向完成源资料／商品回读、零租户用户时创建逻辑
  账号与四个目标、画像、成员与具体门店资格，并证明无图片 P5 在持久化前自然提示；Gate B
  Chrome 纵向完成资料生命周期、组织范围、团队使用和双真值就绪度。覆盖 1440×900、768×900、
  390×844、200% 等效缩放、键盘／焦点、44px 触控、reduced-motion、无横向溢出、无控制台错误
  和无意外外部请求。
- 完整本地门通过：`git diff --check`、Ruff、mypy、Golden/OpenAPI `576 passed, 2 skipped`、
  前端 lint／typecheck／interaction／build。两个 skip 均为需显式环境开关的浏览器入口；对应正式
  Chrome 命令已独立执行并通过。
- 产品与内容／真实使用体验有界审查：`PASS`。工程、安全、RLS、兼容与防假绿有界审查：
  `PASS`。两审只对当前候选成立，不替代 CI、生产导入、隔离黄金套件、备份恢复和回退证据。

## 已处理偏差

- 审查发现 18 份与当前私有源一致的 Markdown 副本在 TENANT-01 启动基线之前已由历史提交
  `865c318` 纳入 Git。当前候选已从 tip 工作树删除这些副本并增加根目录忽略规则；常规 pytest／
  CI 只使用合成合同夹具，真实源目录只由显式本地或生产导入命令传入。外部 21 份原文件未修改。
- 受禁止改写历史与禁止强推约束影响，历史 Git 对象不会在本里程碑中重写；因此最终负向证明将
  精确表述为“当前候选树、staged diff、CI 输入与新提交不含品牌原文”，不得改写成仓库历史上
  从未出现过。

## 历史 `96dcb74…` 生产候选与数据结果（已被取代）

- 最终运行实现为 `96dcb74d4538f8f929193292b119333a64ee9558`；唯一权威 CI
  `30712642287` 为 `success`。本地完整门为 `582 passed, 2 skipped`，并通过 Ruff、mypy、
  OpenAPI、前端 lint／typecheck／interaction／build 和显式正式 Chrome 纵向。
- 生产 schema 为 `20260812_39`，当前镜像 digest 为
  `sha256:6e9aa9140bd2e66a56df398c00daa0ce596c8ee07dfdd2f3db3e6e1c2d8a5d0c`；公网／回环
  readiness、liveness 与 `/status` 均为 200，backup timer 为 active，内容与 DM01 永久
  running 均为 0。
- 正式活跃视图保留 1 个 tenant、1 个 brand、1 个管理组织、`diyu-fashion-admin`、1 个逻辑
  发布账号、4 个平台／形式目标、1 个 ContentRole 与追加式五段画像历史。生产资料为 21 个
  source document、21 个不可变 source version、5,046 个 segment、14 个品牌授权候选商品、
  203 条字段证据和 26 个 ProductFact 字段；正式商品媒体、媒体绑定与 display store 均为 0。
- 生命周期前像共 316 个 UUID 级对象：111 个明确 synthetic 对象及历史被归档，200 个来源不明
  legacy 对象及历史默认隐藏，5 个正式根对象保留；其中 290 个历史任务与 281 个内容版本、
  1 个 DM01 版本继续只读保留。折线之间 tenant 未修改，普通 API、团队使用和能力诊断均从
  查询源头排除 synthetic／legacy。
- 导入批次 digest 为
  `869424242c1512e66fc51d408df6024dc4ff0b87f6d8193d987c4ac70f406882`，dry-run manifest
  digest 为 `fd929ca372bd110732ef26bef2c7ea26ad4031f17e10638191c6c3e10fe8f23e`。segment 类型为
  brand_fact 530、expression_constraint 1,404、creative_method 744、
  candidate_product_guidance 985、template_only 1,349、source_catalog_only 34；19 份授权文档
  与 2 份模板保持原始语义等级，不把 P／C／R、价格、库存或推断升级为硬事实。

## 历史 `96dcb74…` 正式消费者、双真值与黄金验收（已被取代）

- `BrandContextPacketV1` 按 tenant／brand／账号控制组织、ContentRole、画像版本、平台形式、
  内容产品、明确 SKU／资料选择和自然输入确定性选取相关 segment；任务快照冻结 packet、
  segment、画像、商品 FactPacket 与媒体 Envelope 的版本和 digest。Writer 不能读取整库或
  自选来源，V2、系列和平台改编重放冻结上下文。
- 软件功能真值保持 `58/0/0/6/0`。笛语服饰资料就绪度独立记录：非商品内容、P3、系列、
  平台形式和新成员首次创作为 `ready`；候选商品承重 P1／P2 按 V 字段为 `ready` 或
  `ready_after_admin_action`；P4 在没有真实门店事实时为 `data_missing`；P5 因正式商品媒体为
  0 而 `data_missing`，预检差分 `0/0/0`；DM01 因正式门店和库存为空而 `data_missing`。
- 同一实现、镜像、schema、`deepseek-v4-flash`、temperature 0、无择优条件下，咖啡、零题材、
  婆媳、生活抱怨、P1、P2、P4、同输入小红书／抖音、series2、series3 共 11 份成品各运行一次；
  P5 无图预检不调用 Writer，DM01 仅在隔离恢复库以规则编译器完成 V1→V2→V1且模型调用为 0。
  11 份人工全文审阅平均 4.13，品牌关联／账号声纹／平台适配最低 4，完整度最低 5，事实、真人、
  媒体和跨租户硬边界违规为 0。P2、生活抱怨和 series3 的自然语言评分为 3，作为真实质量观察
  保留，不冒充长期品牌采用或市场效果。
- 不可变证据位于
  `/var/lib/diyu-tenant01-evidence/96dcb74d4538f8f929193292b119333a64ee9558/golden-v1/`，目录／
  文件为 0700／0600，`SHA256SUMS` 通过；manifest 绑定 11 份 raw／artifact、task／run／version
  UUID、正式 visible digest、模型配置与人工审阅。证据不包含凭据、请求头或品牌源文档原文。

## 历史 `96dcb74…` 备份、回退、清理与两份有界审查（已被取代）

- 部署前备份 `/var/backups/diyu-m5-4/20260801T183351Z-predeploy` 以 0700／0600 保存并通过
  checksum、隔离数据库恢复、FORCE RLS、关键对象、恢复库 readiness 与对象恢复验证。上一健康
  `e30ecab…` 镜像在 schema `20260812_39` 上完成 readiness 与正式历史读取，随后切回最终镜像；
  回退过程未 downgrade 数据库，最终 evidence 已重新绑定当前镜像 digest。
- 产品、内容与真实使用体验有界审查为 `PASS`：账号／平台关系、品牌上下文、P5 无图、DM01
  局部缺口及 11 份最终成品均符合冻结合同；自然语言 3 分项已诚实记录。工程、安全、RLS、兼容
  与防假绿有界审查为 `PASS`：expand-only schema、FORCE RLS、跨 tenant／brand／organization／
  private 反证、追加式历史、失败原子性、AIGC、证据绑定和旧镜像读取均无阻断。未开启第三份审查。
- 隔离黄金数据库、临时用户、会话、token、任务／run／version、staging、runner、浏览器目录和
  root-only 凭据投影均已精确清理；生产未遗留黄金任务或版本，永久 running 为 0。备份、生产
  正式数据和不可变验收证据保留。
- 当前候选树与源文件 basename 交集为 0，当前 HEAD tree 与 21 份源文件 blob 交集为 0，暂存区
  为空；权威 CI 只消费当前候选树。历史提交中已存在的 18 个 source blob 按禁止重写历史约束
  保留并作为已知偏差披露，不能将此事实改写为“仓库历史从未包含私有资料”。
- 实际执行中还发生并关闭：初始人审发现 series2 整段重复；随后跨平台账号关联的空格展示被
  误判；回退脚本重建最终 tag 使镜像 digest 改变，最终 manifest 已重新绑定当前 digest；隔离
  restore readiness 存在启动竞态，部署等待逻辑已以前向实现收敛。上述历史均不改写为从未发生。

## 历史 `96dcb74…` REVIEW 结论（已被主控退回）

该候选当时记录为满足 18 项完成门并进入 `REVIEW`，随后已被本包顶部的主控终审返工裁决取代，
不再是当前结论。该历史结果不
证明真实员工长期采用、真实发布、流量、排名、爆款、GMV／销售、多真实租户市场差异、企业
SLA、`20/55/44` 全组合稳定支持、无真实图片时的笛语 P5 成品，或无真实门店／库存时的笛语
DM01 实际经营采用。当前状态和唯一下一动作以文末“最终 REVIEW 交付”为准。

## 2026-08-04 最终 REVIEW 交付（当前唯一权威结论）

TENANT-01 已完成工程、验收、CI、生产部署、恢复、回退和清理的唯一纵向结果。正式管理员现在
可以登录生产，读取笛语服饰现有资料与商品边界；生产已具备管理员配置账号画像和成员的能力，
正式历史读取和 legacy 投影保持兼容。当前正式管理员已激活且启用，存在 1 个逻辑发布账号，
账号画像为 0，尚未创建正式内容成员，因此内容能力诚实显示 `ready_after_admin_action`。管理员
完成画像和成员配置后才能开始正式内容生产，不能把“软件能力存在”写成“笛语已经完成内容团队
配置”。

### 冻结工程交付门 18 项

| # | 完成门 | 最终结果 |
| --- | --- | --- |
| 1 | F 构建卷与 PostgreSQL 恢复 | `PASS`；外部双备份、只读检查和 ext4 修复完成 |
| 2 | execution-control 中断恢复接缝 | `PASS`；历史 ledger／checkpoint／event chain 保留 |
| 3 | 受影响定向后端门 | `PASS` |
| 4 | 完整后端／OpenAPI 确定性门 | `PASS` |
| 5 | 前端 lint／typecheck／test／build | `PASS` |
| 6 | Chrome Gate A—D | `PASS`；桌面、窄屏、移动、200%、键盘／焦点／触控覆盖 |
| 7 | 唯一候选冻结 | `PASS`；`748190c552c6b9610aa951bd346fe8903ef51121` |
| 8 | build once／digest 绑定 | `PASS`；构建次数 1，部署未重建 |
| 9 | 11 张正式黄金卡 | `PASS`；同一 SHA／run／模型配置 |
| 10 | 15 张冻结泛化回归卡 | `PASS`；冻结配置 SHA-256 未变 |
| 11 | 26 张逐篇审阅与防假绿 finalization | `PASS`；硬边界、结构和高风险边界 `26/26`，首稿可用 `23/26`，保留 3 项质量 FAIL |
| 12 | 产品与体验有界审查 | `PASS` |
| 13 | 工程、安全与兼容有界审查 | `PASS` |
| 14 | 唯一权威 CI | `PASS`；run `30889298662` |
| 15 | predeploy 备份与隔离恢复 | `PASS` |
| 16 | 按绑定 digest 部署与生产产品检查 | `PASS` |
| 17 | 上一健康镜像往返回退 | `PASS`；无数据库 downgrade |
| 18 | 精确 synthetic／临时材料清理与状态收口 | `PASS`；execution-control=`REVIEW` |

冻结工程交付门完成比例为 `18/18（100%）`。这只表示本执行包的工程交付门成立，不表示
“首租户全部业务目标 100%”，也不把下文“尚未证明事项”升级为生产事实。

### 11＋15 卡最终结果

- 运行 SHA：`748190c552c6b9610aa951bd346fe8903ef51121`
- acceptance run：`tenant01-final-20260804-748190c`
- 模型：`deepseek-v4-flash`，temperature `0`，max retries `0`
- machine hard：`26/26 PASS`
- human high-risk boundary：`26/26 PASS`
- structure：`26/26 PASS`
- first-draft product usable：`23/26 PASS`，达到冻结下限
- hard-boundary violations：`0`

全部 26 卡均在隔离 synthetic tenant 和冻结品牌投影上完成，证明共享架构、作用域和内容合同，
不冒充正式管理员租户已经完成真实内容生产。执行侧由单一执行端逐篇审阅，当前主控完成独立
复核；不宣称两名独立真人盲审，也不把重复的 `comparison` 派生字段作为跨卡差异的单独证明。

三个质量 FAIL 全文、摘录和残余风险均保留，没有中断套件、重跑样本、择优或改写成硬失败：

1. `new_couple_housework`：正文用“也许他只是没看见”替一方猜测动机，并使用单边性别指代，
   与题目要求不一致；需自然改写后才适合采用。
2. `new_style_revision`：V2 与 V1 的 visible digest 和可见全文完全相同，没有落实“更简洁、带
   一点冷幽默”的局部修订。
3. `new_series_progression`：三篇重复同一核心标题，第二、三篇继续复用雨天、客户和旧书店主线，
   没有形成三次新的中心判断。

正式 finalization 位于
`/mnt/diyu-build/evidence/TENANT-01/748190c552c6b9610aa951bd346fe8903ef51121/acceptance-v2/`，包含
`human-review.json`、`manifest.json`、`SHA256SUMS`、raw、artifact、result、真实 UUID、
visible digest 和逐篇引用。generation ledger 保持只读；普通私有证据保持 0600、目录 0700。

### P4、P5、DM01 与生产资料真值

- P4：笛语生产没有正式门店事实，能力保持 `data_missing`，不得用 synthetic 门店场景冒充正式
  近场经营输入。
- P5：笛语生产正式商品媒体绑定为 0，能力保持 `data_missing`。无本次明确选择的正式商品媒体
  时，系统在建任务前返回
  “缺少本次明确选择的正式商品媒体”的自然提示；task／run／version 差分 `0/0/0`、Writer
  调用 0，没有把 ProductFact 当成媒体资源，也没有导入用户排除的视频。
- DM01：生产正式门店和库存仍为空，能力与真实经营采用保持 `data_missing`。隔离 synthetic
  旅程已
  证明冻结商品版本与规则包的 V1→V2→V1、库存守恒、追加式版本和模型调用 0；旅程随后精确
  清理为 task／run／version `0/0/0`，不得把该证明冒充笛语真实门店执行。
- 当前生产笛语服饰有 21 个资料投影（19 份授权资料＋2 份模板）、5,046 个稳定 segment、14 个
  品牌候选商品、203 条字段证据和 26 个 ProductFact 字段；正式商品媒体、媒体绑定和正式门店
  均为 0。软件功能真值 `58/0/0/6/0`、资产 `41/243/25/119` 与租户资料就绪度继续分开。

### CI、镜像、备份、生产与回退

- 唯一权威 CI：GitHub Actions workflow `deterministic-quality-gate`，run `30889298662`、job
  `91927407713`，event `push`，结论 `success`；它精确对应运行 SHA。
- build-once／生产镜像 digest：
  `sha256:edc8dfc45f9cea82fd29ac656aa660c86ac3b50c1fb4c02df3b4d64f2cd617a4`。acceptance manifest、
  release evidence、部署和最终运行 digest 一致，构建次数为 1。
- schema：`20260813_40`；部署采用 expand-only migration，没有 downgrade 数据库。
- 新鲜备份：
  `/var/backups/diyu-m5-4/20260804T080232Z-tenant01-748190c552c6b9610aa951bd346fe8903ef51121-predeploy`。
  目录／文件权限为 0700／0600，checksum digest
  `533dc0ba50ceb8ca87b62e56af01ae50918c1784e6d10c21944cfb847b0ccaf9`；`pg_restore` 清单、隔离
  恢复、FORCE RLS 未设作用域读取拒绝、恢复库 readiness 和对象恢复往返均通过，临时恢复资源 0。
- 生产公网与回环 `/health/ready`、`/health/live`、`/status` 均为 200；内容和 display 永久
  running 均为 0。正式管理员 API、账号、资料作用域、资料缺口真值和 legacy 历史读取均已验证，
  临时生产会话清理为 0。
- 上一健康镜像
  `sha256:f869aa605f3bc81a429a56a4081b1c4eabaa351587245f5b8aa73fb19f7bb683`（SHA
  `f77a2e852758b9157425633041aea59d9f2b24da`）已在 schema `20260813_40` 上通过公网／回环三端点和
  正式历史读取；再切回最终候选后，数据库指纹、历史 API 响应和版本 UUID 完全一致，未创建新
  备份或执行数据库降级。

### 清理、保护与尚未证明事项

- F 盘主 synthetic 租户及 7,035 条关联行归零。固定演示租户只删除 1 条最终验收 synthetic
  内容链；其余 199,967 行正式演示数据清理前后指纹一致。DM01 synthetic 链、临时 session／
  token、两个 synthetic 素材及绑定、10 个素材对象文件、8 个 Chromium 临时目录、pytest 临时
  目录、SSH CONNECT proxy、29 个一次性脚本和永久 running 均为 0。ECS 遗留
  `diyu-tenant01-final-pg` 及其独占匿名 volume 已在只读证明生产不依赖后精确删除，55441
  监听归零；生产应用未重启或漂移，digest、schema、六个端点、备份 timer 与正式历史指纹均
  保持。独立证据为
  `/mnt/diyu-build/evidence/TENANT-01/748190c552c6b9610aa951bd346fe8903ef51121/production/ecs-temporary-database-cleanup.json`，
  SHA-256 `e17054205194de84aafa2d66500ac6d1adabb793d7328b90ca3005fe883ddd10`；原 acceptance
  `SHA256SUMS` 87/87 项复算通过。
- 正式 evidence、raw、artifact、manifest、checksum、生产正式数据、备份和不可变历史保留。
  `docs/项目记忆.md` 未覆盖、未清理、未暂存、未提交，最终 diff SHA-256 保持
  `96862202b06fd7821797d984215163069e8598a8641209ebae629ca2df0baaf7`。
- 21 份私有 Markdown 原文未进入当前候选树、CI 输入、公开日志或最终公开证据；历史 Git 对象中
  既有 18 份旧副本按禁止改写历史约束继续如实披露，不能写成“仓库历史从未包含”。
- 尚未证明：正式租户真实内容生产与真实发布、真实员工采用、平台流量／排名／爆款、GMV／
  销售、多真实租户市场差异、企业 SLA、`20/55/44` 全组合稳定支持、无正式门店事实时的 P4、
  无正式媒体时的 P5 成品，以及无正式门店／库存时的 DM01 真实经营采用。

当前状态：`TENANT-01 REVIEW`。本执行端不得自行置为 `CLOSED`。唯一下一动作：主控最终独立
复核并决定是否 `CLOSED`。
