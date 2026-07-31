# 当前里程碑

- 当前里程碑：`UX-03` 产品目标一致性与全链路修复。
- 状态：`REVIEW`；`Gate A · 正式入驻、身份、逻辑发布账号与多平台关系闭环` 为
  `COMPLETE` 且主控最终终审 `PASS`；`Gate B · 品牌资料、组织作用域、团队使用与能力诊断`
  为 `COMPLETE` 且主控最终终审 `PASS`；`Gate C · 创作控制、真实阶段、完整成品与系列前情`
  为 `COMPLETE` 且主控最终终审 `PASS`。FT-039、FT-040、FT-041、FT-045 均已通过；此前
  FT-041 的主控退回、失败套件和自报通过历史完整保留。UX-02 保持 `CLOSED`；Gate D 第二次
  主控终审发现的硬约束商品身份、请求级错误优先级和状态未知标题三个遗漏已由本地实现
  `28e19b0a93ec702062eb783fd08c76ff66d6bcea` 关闭，当前为
  `COMPLETE / 等待主控最终独立终审`；不创建 UX-04。
- 当前 Git 基线：`86f5df16b9e42fe4eee322694156361a007bdb88`；唯一写入执行端为
  当前 WSL Codex。
- Gate D 最终本地实现为 `28e19b0a93ec702062eb783fd08c76ff66d6bcea`；本地
  Golden/OpenAPI `529 passed, 2 skipped`，前端四门、显式 Gate D Chrome、三项 mutation
  和两份有界审查通过。未 push、未触发 CI、未部署、未连接生产或调用模型。
- Gate C 当前运行实现为 `ec3dbe45d485816c7a49f9c801cd2baa2fe58c04`；其后仅有测试 oracle
  前向提交 `6e3cb46b6c18d82f245a92f36c972ab65fa62bde`，没有运行代码变化。当前实现继续保留
  `faa4792538cbbcb54ff7b329dee7d03dd9488a24` 已关闭的总部素材作用域、正式 P5 消费者和
  证据 ID／摘要边界，并关闭 P2 自然商品取舍、P5 与 UUID／数据库顺序无关的冻结主辅角色及
  artifact 独立人工证据。此前所有失败候选与审计退回记录继续作为历史保留。
- Gate A 首次实现 `734dcee900bc67e23d058d4fd6f8ef15db8d9847` 与完成记录
  `11444a4d7920e5aa55979241691908120f25aca2` 保留；主控有界返工后的最终实现为
  `4899a068b7b2310cb45cecac4def4ff17e537f05`。Gate B 首次冻结实现
  `a67f44bdc4e73a2a8386cdfa311659220aefc0af` 与首次完成记录 `a961709…` 保留；主控终审
  判定 FT-031／FT-032 为 `FAIL` 后，本次有界返工实现为
  `4a49e0d912e17a10965e840e89c1ef7f03bca3f6`；其后 FT-031 最小返工实现为
  `0774ae685da3156e529a1b6fed5d502a920706a1`。本地 `main` 只在 `origin/main` 的 UX-02
  关闭基线上普通前向领先。Gate C 首次候选实现为
  `4d797d35614216c92a7e62ae7a62d7456165d70b`；主控已保留该候选及失败证据并退回
  FT-041。Gate A—C 均未 push、未触发远程 CI、未部署或连接生产。Gate C 最终套件只在
  本地 synthetic PostgreSQL、正式 API 与正式 React 消费者上调用受保护的
  `deepseek-v4-flash`；没有连接生产、Redis 或真实客户数据。
- FT-041 前向返工先后形成 `715838f0a093f12e1be77b4d76581f5db8814e6c`、
  `c18fcf5d0393c7bb7a4bffbd1a8a92f335703834` 与最终重试实现
  `ad398e60ea4b7544211190b99788c19ce7e293dc`。最后实现已通过 Ruff、mypy、
  Golden/OpenAPI `448 passed, 2 skipped`、前端四门和显式 Chrome；但按冻结纪律只运行
  一次的同 SHA 七卡套件在 P1 完成后，于 P2 的 `unit:media-opening` 检出 Writer 再次写入
  Compiler 所有的可见结构包装并失败关闭。root-only 失败证据及可复算校验位于
  `/var/lib/diyu-ux03-evidence/ad398e60ea4b7544211190b99788c19ce7e293dc/gate-c-final-suite/`；
  未生成最终 manifest 或人工 PASS。
- 主控随后批准服务端仅对图文 `media_opening` Writer 单元起始位置的规范字面
  `首图：` 去除一次，并对剩余全文重新执行既有可见结构与 Unicode 安全检查。实现
  `1f0dffcea106bff814925051ac3671bcb654f409` 已用保存的 P2 raw 完成无模型回放，三项
  mutation proof 均真实变红后恢复转绿，并通过 Ruff、mypy、Golden/OpenAPI
  `467 passed, 2 skipped`、前端四门和显式 Chrome。新同 SHA 七卡均只调用一次并成功
  生成，但人工阅读全文只确认 P5 完整通过；P1、P3、P4、series2、series3 的媒体单元引入
  未登记现实资源，P2 还把冻结的“两面完整外观”扩写成正反面及未冻结视觉细节，多张图文
  继续重复低饱和静物／居中排字结构。因此精确去包装缺口已关闭，FT-041 的事实／资源闭世界
  和媒体责任缺口仍未关闭，不得以工程门绿色代替产品通过。新 raw 与成品保留在
  `/var/lib/diyu-ux03-evidence/1f0dffcea106bff814925051ac3671bcb654f409/gate-c-final-suite/`；
  该目录的 `SHA256SUMS`、`normalization-replay.json`、`human-review-failure.json`、
  `bounded-reviews.json` 和 `suite-failure.json` 已复算校验；未生成成功 manifest。
- 主控其后冻结“确定镜头／可选补拍建议／抽象编排”三层媒体责任。实现
  `fc45c11a5beb021d8c4ff69aee61a19f035eba77` 引入
  `media-capability-envelope-v1`、封闭 `media-program-v1` 与
  `delivery-compiler-v4`：Writer 只填写标题、自然导读、正文和发布配文；服务端在调用前
  冻结能力、资源、程序和单元绑定；Compiler 确定性生成首图／首帧、图序／观看链、字幕、
  声音和制作提示。只有正式登记、启用、作用域合法、本次明确选择且版本冻结的资源才能形成
  确定制作指令；无登记资源时成品以文字、排版、色块、线条、符号和留白独立成立。可选补拍
  建议由 Compiler 以条件语态单独生成，不进入 required resource refs，不成为成品成立条件，
  但进入 provenance 与 artifact digest。
- 首轮最终套件又暴露 P2／P5 Writer 仍能从原题材和账号领地推导商品语义。最终实现
  `0c4f0d48f2d89daf0082c063c22c4f14aa6ea7e5` 将商品类 Writer brief 收敛为去对象化的
  判断顺序：冻结商品事实仍由服务端逐字插入，Writer 不再看到可推导商品属性、用途和体验的
  原始商品题材。恢复 raw product topic 的 mutation 会使 P2／P5 合同测试同时变红。
  该实现通过 `git diff --check`、Ruff、mypy、Golden/OpenAPI `475 passed, 2 skipped`、
  前端四门与显式 Gate C Chrome；产品／内容审查和工程／安全／兼容审查均无阻断。
- 在同一 `0c4f0d4…`、`deepseek-v4-flash`、temperature 0、max_retries 0 下，
  P1—P5、series2、series3 各执行一次；无数据库、Redis 或业务持久化，不择优、不拼接
  不同 SHA。七卡逐篇阅读全文均通过，使用七种不同 MediaProgram；P2 三条冻结事实各逐字
  一次且无新增属性／用途／效果，P3 咖啡原句逐字且账号观察路径自然，P5 的 required
  resource refs 精确等于本次冻结的两个登记商品资源，series2／3 按冻结前情连续推进。
  root-only 正式证据位于隔离执行主机
  `/var/lib/diyu-ux03-evidence/0c4f0d48f2d89daf0082c063c22c4f14aa6ea7e5/gate-c-final-suite/`，
  含七份 raw、artifact、配置、`manifest.json`、`human-review.json` 与
  `SHA256SUMS`；file SHA、raw SHA、正式 `visible_digest` 和人工审阅引用可复算一致。
- 当前任务包：
  [`docs/UX-03-产品目标一致性与全链路修复执行包.md`](docs/UX-03-产品目标一致性与全链路修复执行包.md)。
- Gate A 已在本地完成正式 React/API/PostgreSQL 的新租户入驻、品牌基线、自然人资格、
  逻辑发布账号、五段画像、多平台目标及最小生命周期闭环。全新 synthetic tenant 纵向和
  1440×900／768px／390×844 正式浏览器旅程通过并已精确清理；Golden/OpenAPI 为
  `421 passed, 1 skipped`，Ruff、mypy、前端四门和两份有界审查均无阻断。
- 最终有界返工进一步封闭：跨组织账号使用不再推导画像维护权；停用账号的既有成员授权可
  原样保留或显式移除、但不能新增；有维护资格的内容用户可在身份抽屉查看完整五段画像并保存
  Vn+1，同一逻辑账号跨平台／形式继续读取同一版本；synthetic 清理后对租户、身份、凭据、
  会话、授权、账号、画像、事件和运维对象逐项断言为 0。显式命令
  `DIYU_RUN_UX03_BROWSER=1 .venv/bin/pytest -q tests/test_ux03_gate_a.py` 退出码 0。
- Gate B 已以 schema `20260808_35` 在本地完成品牌文字资料、商品事实和组织官方素材的
  V1→V2、停用／恢复、历史读取和确定性运行消费；品牌全员／总部专用／指定区域以逻辑发布
  账号控制组织裁定，兄弟区域、其他品牌和其他租户失败关闭。任务快照冻结实际消费的资料、
  商品和明确选择的素材，后续版本与停用不污染原任务修订。
- Gate B 首次终审确认 FT-027—FT-030 主体成立，但发现系列首篇被误计为续写，六类诊断会
  把不同账号或组织的独立数量拼成 `available`，指定区域 API 还接受门店级组织；当时真值
  诚实退回 `48/10/0/6/0`。最终返工后，系列续写只统计 `series_position > 1`、
  `parent_version_id IS NULL`、具有 succeeded run 且实际提交完整 V1 的任务，并以 V1
  提交时间独立适用 7/30 日窗口；六类诊断仍由同一 tenant／brand 内完整且内部一致的账号、
  组织、资料路径决定，evidence 返回真实对象、版本、范围和更新时间；指定区域仍只接受
  明确登记的 region，历史非 region 数据仅兼容读取。Golden/OpenAPI 为
  `422 passed, 1 skipped`，FT-031 有界复核无阻断。
- Gate C 已关闭 FT-039、FT-040 和 FT-045：五轴可选方向及开放原话冻结到任务并
  随修订重放；NDJSON 只在实际节点发出阶段，`completed` 位于原子提交、digest 校验和正式
  回读之后；系列前情以同租户／品牌／逻辑账号／系列边界冻结并进入 Writer 输入。FT-041
  的 MediaCapabilityEnvelope 与封闭 MediaProgram 已能消费登记资源，但此前 P5 由证据
  Runner 手工构造两个 `registered_product_display`，没有经过正式管理 API、正式 React、
  正式资源 resolver 或 PostgreSQL，因此不能证明真实用户可获得该能力。首次同 SHA
  P1—P5 与三篇系列失败证据完整保留在
  `/var/lib/diyu-ux03-evidence/4d797d35614216c92a7e62ae7a62d7456165d70b/gate-c-final-suite/`。
  `git diff --check`、Ruff、mypy、Golden/OpenAPI `440 passed, 2 skipped`、前端四门、
  显式三视口 Chrome 和两份有界审查是该首次候选的历史工程证据，不替代本次 FT-041
  返工完成门。
- FT-041 最终正式消费者实现以 schema `20260809_36` 增加最小
  `product_media_bindings`：管理员可将同租户／品牌、作用域合法的组织官方图片或视频明确
  关联到已确认商品；内容用户本次明确选择两份素材后，正式 resolver 同时校验逻辑账号控制
  组织、商品／素材／绑定启用状态、当前版本与 checksum，只有两个不同
  product／asset／binding 才生成 `registered_product_display`。ProductFact、
  production condition、个人素材、未选择素材及客户端伪造 ID 均不授予媒体能力；预检失败
  为 task/run/version `0/0/0`，修订重放冻结 Envelope V2 和绑定版本。
- 最终实现 `faa4792538cbbcb54ff7b329dee7d03dd9488a24` 让内容素材列表与正式 resolver 复用同一
  账号控制组织边界：`headquarters` 素材归属组织必须精确等于当前逻辑发布账号控制组织，
  区域／门店素材的标题、文件名、checksum、说明及商品绑定元数据均不返回。P2 以冻结、
  可追踪的商品价值合同向 Writer 提供受控语义，服务端确定性插入商品专属理解、相伴取舍和
  成立条件；P5 只有在两份正式绑定素材和冻结事实能够形成具体色彩或轮廓主次时才进入，
  否则在 task/run/version 前自然失败。完整门为 Ruff、mypy、Golden/OpenAPI
  `491 passed, 2 skipped`、前端四门及显式 Gate C Chrome；产品／体验与工程／安全两份
  有界审查均无阻断。
- 同一 `faa4792…`、同一 `deepseek-v4-flash`、temperature 0、max_retries 0 下，
  P1—P5、series2、series3 各执行一次，正式 API/PostgreSQL task/run/version 为
  `7/7/7`、全部 run succeeded、永久 running 为 0、传输重试为 0。P2 三项价值证据逐字
  绑定可见成品与冻结合同；P5 使用 `graphic_registered_product_relation_v1`，其具体
  “一主一辅”视觉命题绑定两个不同登记商品 resource refs。七卡逐篇 8 项人工全文审阅通过。
  私有完整证据位于
  `/home/faye/.local/share/diyu-ux03-evidence/faa4792538cbbcb54ff7b329dee7d03dd9488a24/gate-c-final-suite/`；
  无凭据、可自校验的本地主机索引位于
  `var/tmp/ux03-gate-c-final-evidence-faa4792/`。私有 19 项与索引 3 项 checksum 均复算通过；
  synthetic 租户、运维身份及全部断言关联对象为 0，临时凭据／会话目录和一次性脚本已清理。
- 最终实现 `ec3dbe45d485816c7a49f9c801cd2baa2fe58c04` 在同一 SHA、同一
  `deepseek-v4-flash`、temperature 0、max_retries 0 下完成 P1—P5、series2、series3
  各一次正式 API/PostgreSQL 生成；7 task／7 succeeded run／7 version 均有真实 UUID，
  永久 running 与传输重试为 0。P2 的“双面完整外观”形成自然的选择、取舍和成立条件，
  不出现验收标签或未冻结商品语义；P5 的主辅来自本次冻结素材顺序而非 UUID／数据库返回
  顺序，并由首图、图序和制作提示共同实现。七卡逐篇八项人工全文审阅均通过。
- 私有完整证据位于
  `/home/faye/.local/share/diyu-ux03-evidence/ec3dbe45d485816c7a49f9c801cd2baa2fe58c04/gate-c-final-suite/`；
  本地主机可读的诚实索引位于 `var/tmp/ux03-gate-c-final-evidence-ec3dbe4/`。两处
  `SHA256SUMS` 均复算通过，manifest 绑定真实 task/run/version、raw/artifact SHA、正式
  `visible_digest` 与引用 artifact 原文的结构化人工审阅。synthetic tenant、任务、运行、
  版本、会话、商品、素材、绑定及临时 token／runner 已精确清零。
- 完整门最终为 Ruff、mypy、Golden/OpenAPI `495 passed, 2 skipped`、前端
  lint/typecheck/interaction/build 和显式 Gate C Chrome；产品／内容与工程／安全／兼容
  两份有界审查均无阻断。首次 Golden 暴露一个历史测试仍要求 Writer 自由带出未选重量事实，
  测试 oracle 已改为校验服务端实际冻结的“双面完整外观”，定向与全量回归转绿。
- Gate D 首次本地候选 `f2b5e266da44bc8a43aef65d92760076fa7e2987` 与文档候选
  `cda7b72318c1934d0f01fd7c235d188e48444091` 的完成记录保留。主控终审随后确定四个接缝：
  正式商品与 DM01 SKU 合同分裂、finalize 不在完整异常边界内、请求级 4xx 污染供应商全局
  状态，以及核心不可用时公共状态仍可能显示内容可用。Gate D 因此原地返回
  `ACTIVE / REWORK`；本次前向实现 `06669c8cc46e412227ca188cc85745d4040c0c03` 一次关闭
  四项后重新进入 `COMPLETE / 等待主控独立终审`，历史自报完成不作删除或改写。
- 当前 Gate D 本地实现继续使用 schema `20260810_37`。新 React/API 以稳定商品版本 ID 与
  正整数数量提交，服务端从正式当前版本和执行组织作用域解析并保留数据库 SKU 原值；
  `abc-123`、`ABC123`、`123456`、`款号一` 与 `GD-UP-01` 均已通过正式
  React/API/PostgreSQL 纵向。legacy `inventory_text` 保持兼容但不扩大授权；伪造、重复、
  停用、旧版本或越界选择均在建任务前失败为 `0/0/0`。
- 新 DM01 任务仍冻结商品摘要、门店档案与完整 `DM01RuleBundleV1`；V1 实际消费 11 条生成
  资产，修订资格冻结 13 条完整资产且 V2 不重读当前商品、门店或激活状态。finalize 现在把
  生成、校验、正文、版本保存、当前版本更新及正式回读放在同一异常边界和数据库事务内；
  V1／V2 插入、指针更新或提交失败均无新版本、run=failed、永久 running=0，数据库连接中断
  遗留的超租约 display run 只在后续安全同作用域访问时回收。用户只看到纯文字方案失败提示。
- `/health/live` 只证明进程存活，`/health/ready` 只证明数据库／对象存储等核心依赖；`/status`
  的 HTML fallback、React 与 API 共用 `public-service-status-v1`。核心不可用时三类能力均不可用；
  核心可用时 DM01 可用，内容生成按 900 秒内 observation 映射 available／degraded／unavailable，
  缺失、未来或过期 observation 为 unknown。请求级 content_filter、长度、参数或格式 4xx 不改写
  observation；429 为 degraded，5xx／传输／认证／权限／模型不存在为 unavailable。两类状态
  响应均 `Cache-Control: no-store`，访问和重新检查不调用模型。
- 完整门为 `git diff --check`、Ruff、mypy、Golden/OpenAPI `517 passed, 2 skipped`、前端
  lint/typecheck/interaction/build 和显式 Gate D Chrome；四项 mutation 分别恢复 SKU
  大写／旧正则、把 finalize 移出保护边界、让请求级 4xx 写 unavailable、删除 core 对内容状态
  的约束，均真实变红并在恢复后转绿。产品／用户体验与工程／安全／兼容两份有界审查无阻断；
  synthetic tenant、任务、运行、版本、会话、token、运维身份和浏览器目录均由正式测试精确
  清零。此前 `f2b5e266…` 的脱敏证据保持为历史，不拼接为本候选的新证据。
- 当前 64 项功能真值为 `58/0/0/6/0`；没有继续标为有缺陷、占位或尚无法证明的正式项。
  运行资产保持 `41/243/25/119`，激活增量 0。
- 第二次主控终审发现的三个消费者遗漏由最终实现
  `28e19b0a93ec702062eb783fd08c76ff66d6bcea` 关闭：硬约束与修订目标共用冻结商品 SKU 原值／
  完整名称的唯一匹配；稳定 request-scoped code/type 先于 400／403／404；状态 API error
  只显示无法确认，明确 core unavailable 才显示无法接单。三项 mutation 真实红→绿，最终
  Golden/OpenAPI `529 passed, 2 skipped`，前端四门与显式 Gate D Chrome 保持通过。
- UX-03 本地候选不证明生产新能力、真实员工／品牌采用、真实发布、平台流量、排名、爆款、GMV／销售、多真实
  租户市场差异、企业 SLA 或 `20/55/44` 全组合稳定支持。
- 当前状态为 UX-03 `REVIEW`、Gate D `COMPLETE / 等待主控最终独立终审`。唯一下一动作：
  主控最终独立终审 UX-03；不启动 UX-04。

## UX-02 关闭记录（历史保留）

- UX-02 状态：`CLOSED`。主控最终独立终审结论为 `PASS`；UX-01 保持 `CLOSED`。UX-02 原
  `REVIEW` 证据和两轮主控有界返工裁决完整保留。“两次输入密码、停用成员二次确认、复制
  一次性链接可感知反馈”三项管理员旅程缺口，以及其后发现的“复制反馈位于抽屉遮罩后、取消
  停用聚焦已卸载按钮”两个界面假绿，均已完成正式实现、精确反证、最终 CI、同 SHA 部署和
  生产定向验收，不创建 UX-03。UX-02 已从
  `75ed5283e2616ffa91b2ea20dd0b86e7d64449e3` 启动，并完成正式
  React/API/PostgreSQL 工程化、唯一承重 CI、生产默认前端替换、验收清理与不降级回退。
  UX-02 关闭提交当时没有自动启动后继里程碑；UX-03 是用户随后独立启动的新里程碑。
- UX-01 第一次执行侧以页面可打开和状态存在
  为主的 `15/15` 验证自报
  `3/3 Gate / REVIEW`，主控第一次独立终审判定 `FAIL_WITH_BOUNDED_REWORK`：错入口、
  不可操作资格、死按钮、版本时序和不可见焦点仍能假绿。该历史保留；UX-01 随后恢复
  `ACTIVE` 并完成有界返工，最终经主控实际重放 `30/30`、37 个状态、退出码 0 后关闭。
- UX-01 已完成 64 项正式可见交互真值盘点、四类角色与信息架构冻结，以及公共与认证、
  租户管理员、租户用户创作、纯文字 DM01 四条连续高保真旅程。原型现有 37 个连续状态；
  新验证器执行 30 项检查，包含裸产品真实点击、状态变化、键盘与焦点反证，而不是仅逐页打开。
- `CLOSED` 只证明功能真值盘点、角色职责与信息架构、连续高保真目标原型成立，并为 UX-02
  提供明确工程输入；不证明正式 React、完整 HTTPS 激活／重设链接、API、数据库或生产前端
  已改变，也不证明真实采用、发布、流量、排名、GMV 或销售效果。
- UX-01 关闭时只新增产品定义、功能真值台账、产品语言和静态 HTML 原型；没有修改正式
  React、API、OpenAPI、数据库或生产。UX-02 已按正式消费者重新核验 64 项：真实可用
  `58`、有缺陷 `0`、纯占位 `0`、重复或应删除 `6`、尚无法证明 `0`；正式生产消费者与
  清理后的同 SHA 证据均已成立。
- 唯一写入执行端：当前 WSL Codex；UX-02 启动基线：
  `75ed5283e2616ffa91b2ea20dd0b86e7d64449e3`。
- 当前任务包：
  [`docs/UX-02-正式前端工程化与生产替换执行包.md`](docs/UX-02-正式前端工程化与生产替换执行包.md)。
- 最终应用实现 `d5f4609288f284e083d2b1f090222cca50c03c1d` 完成管理员创建、完整
  HTTPS 激活、登录与停用；“发送”不建版本；低种子完成 V1→V2→V1→当前版复制/导出；
  DM01 完成纯文字 V1/V2/历史且库存守恒。最终运行 SHA
  `9c6b81779dced53b8c1f216cd5ba45e043ae7d24` 只在该应用语义之上前向修复部署/回退
  checkout 的继承 umask，二者差分仅为两个部署脚本和直接测试。Ruff、mypy、
  Golden/OpenAPI `419 passed`、前端 lint/typecheck/interaction/build 与
  `git diff --check` 全绿。
- 两份有界审查结论：产品与体验无阻断，三空间职责、移动双工作面、真实状态与错误恢复
  保持；工程与安全无阻断，可信公开域名、互斥资格、请求幂等、租户/品牌/账号/自然人作用域
  及 expand-first schema 33 均失败关闭。
- 最终承重 CI `30523024236` 对应运行 SHA `9c6b81779dced53b8c1f216cd5ba45e043ae7d24`
  且为 `success`。生产部署仓与镜像均为该 SHA，schema `20260806_33`，公网／回环
  readiness 与 `/status` 均为 `200`，备份 timer active。新鲜备份
  `/var/backups/diyu-m5-4/20260730T070654Z-ux02-final-predeploy` 的 `0700/0600`、
  checksum、隔离恢复、RLS、应用 readiness 与对象恢复均通过。
- 生产 synthetic 旅程完成管理员开通与停用、低种子 V1→V2→V1、纯文字 DM01
  V1→V2→V1、移动和响应式验收；全文人工审阅无阻断。验收后通过新鲜备份原子恢复，
  合成凭据、活动会话、未用 token、运行残留及临时数据库均为 0，正式计数恢复为已启用
  用户 `19`、授权 `21`、内容版本 `307`。旧健康镜像
  `9c5b2436f3594b08c5df9c5b758293fd5b4cf177` 已在 schema 33 上成功启动并恢复公网，
  随后切回最终候选；最终回退脚本在继承 `umask 077` 下真实通过。
- 生产业务证据位于
  `/var/lib/diyu-ux02-evidence/d5f4609288f284e083d2b1f090222cca50c03c1d/final-production/`，
  最终部署、回退与清理锚点位于
  `/var/lib/diyu-ux02-evidence/9c6b81779dced53b8c1f216cd5ba45e043ae7d24/final-production/`；
  两处均为 root-only `0700/0600` 且 SHA256SUMS 全绿。
- 主控终审有界返工的最终运行实现为
  `1abd0dbc9088ae8ac3127986cd7fcd0d347ef821`：激活／重设均要求两次输入至少 12 位密码，
  不一致时前后端都在消费 token 前失败；停用首击只打开带明确后果的二次确认，取消无写入，
  确认防重复且只调用一次；激活／重设共用 Clipboard Promise 处理，成功和拒绝均进入
  `aria-live`，不把“复制”写成“已发送”。三项临时 mutation 均真实使直接测试变红，恢复
  后转绿；Golden/OpenAPI `419 passed`，前端 lint/typecheck/interaction/build 和
  `git diff --check` 全绿，两份有界审查无阻断。
- 最终承重 CI `30528280841` 精确对应 `1abd0db…` 且为 `success`。生产部署仓和镜像均为
  该 SHA，schema 保持 `20260806_33`，公网／回环 readiness 与 `/status` 为 200。
  定向正式浏览器 4/4 通过，证明激活／重设不一致不消耗同一 token、修正后可成功，复制成功／
  失败反馈可见，停用首击和取消不撤销会话、确认后会话与登录资格失效；没有调用模型、创建
  内容任务或运行 DM01。
- 最终清洁备份
  `/var/backups/diyu-m5-4/20260730T090009Z-ux02-final-clean` 的 `0700/0600`、
  checksum、隔离数据库恢复、RLS、应用 readiness 与对象恢复均通过。上一健康镜像
  `9c6b81779dced53b8c1f216cd5ba45e043ae7d24` 已在 schema 33 上恢复公网和回环，随后切回
  最终候选。两个 synthetic 用户、会话、token、凭据文件及临时密码环境均精确清理；证据位于
  `/var/lib/diyu-ux02-evidence/1abd0dbc9088ae8ac3127986cd7fcd0d347ef821/bounded-admin-rework/`，
  权限 `0700/0600` 且 SHA256SUMS 全绿。
- 最后一轮运行实现
  `3dfe648571b679f74e7dbb4d7c9927de77f03000` 把激活／重设复制反馈直接放在当前
  `.tenant-drawer` 的一次性链接区内，并在新建链接、切换成员或关闭抽屉时清除旧反馈；
  停用确认取消或 Escape 后通过真实按钮 ref 和挂载后 effect 精确恢复焦点。测试不再用
  `body.textContent` 或 activeElement 文本冒充可见性／焦点，而是核验抽屉归属、视口、
  遮挡、`activeElement === trigger` 和 `trigger.isConnected`。
- 两项临时 mutation 均真实变红：反馈移回抽屉外时，390×844 Chrome 得到
  `inside=false / inViewport=false / uncovered=false`；恢复旧 `event.currentTarget`
  聚焦时，精确测试得到 `activeElement=body`。恢复正确实现后，1440×900 与 390×844
  Chrome、前端完整门和 Golden/OpenAPI `419 passed` 全绿；产品体验及工程防假绿两份
  有界审查无阻断。
- 唯一承重 CI `30537611606` 精确对应 `3dfe648…` 且为 `success`。生产部署仓与镜像均为
  该 SHA，schema 保持 `20260806_33`，公网／回环 readiness 与 `/status` 均为 200。
  生产 390×844 定向浏览器证明激活／重设反馈位于抽屉内且真实可见，取消与 Escape 都精确
  返回已连接的停用按钮。上一健康镜像 `1abd0db…` 已完成不降级回退并切回最终候选；
  predeploy 备份 `/var/backups/diyu-m5-4/20260730T111509Z-predeploy` 为 `0700/0600`
  且 checksum 通过。
- 本轮 synthetic 管理员、成员、会话、token 和临时凭据均已精确清理。root-only 证据位于
  `/var/lib/diyu-ux02-evidence/3dfe648571b679f74e7dbb4d7c9927de77f03000/final-targeted/`，
  权限 `0700/0600` 且 SHA256SUMS 全绿。64 项正式真值保持 `58/0/0/6/0`，资产保持
  `41/243/25/119`、激活增量 0。
- UX-02 `CLOSED` 只证明正式前端工程化、生产默认前端替换、三条用户旅程、64 项功能真值、
  响应式与可访问性，以及最后两项界面防假绿在既定范围内成立。它不证明真实员工／品牌采用、
  真实发布、平台流量、排名、爆款、GMV／销售、多真实租户市场差异、企业 SLA 或
  20/55/44 全组合稳定支持。
- UX-02 关闭时的下一动作原为停止执行、等待用户决定新里程碑；该历史动作已被用户随后正式
  启动 UX-03 的裁决取代，不改写 UX-02 关闭事实。

## UI-12 关闭结论（历史保留）

- UI-12 状态：`CLOSED`。主控第三次、也是最终一次独立终审结论为 `PASS`。主控对 schema 31
  候选的第二次独立终审给出 `FAIL_WITH_BOUNDED_REWORK` 后，UI-12 已在原里程碑内完成
  两项确定性收口：
  schema `20260805_32` 撤销 `diyu_app` 对 `content_versions` 的 UPDATE/DELETE，
  trigger 同时拒绝 UPDATE/DELETE，只允许迁移角色在事务局部、精确 tenant/version 和
  synthetic fixture 三重边界下清理；legacy 投影恢复历史“只识别全角冒号”合同，Writer
  新链路则继续识别全／半角 heading，并按 Unicode Default_Ignorable 统一防伪。最终运行
  SHA `9c5b2436f3594b08c5df9c5b758293fd5b4cf177` 的唯一 CI `30500580180`
  绿色，生产部署、兼容冒烟、备份恢复和旧镜像在 schema 32 上的不降级回退均成立。
  UI-07—UI-12 仍是一条自然创作真实性探索链，不创建 UI-13。此前
  occurrence、开放 evidence、商品事实职责、Reviewer-only 模型、oracle drift、parser
  与一次 repair 的失败及前向订正均完整保留。
- UI-12 `CLOSED` 证明自然创作后端主链、可信事实与创作表达责任边界、版本不可变保护、
  legacy/audit 兼容、失败原子性以及同 SHA 生产闭环在既定范围内成立。它不证明前端用户
  体验已经完成产品化，也不证明真实员工／品牌采用、真实发布、流量、排名、爆款、
  GMV／销售、多真实租户市场差异、企业 SLA 或 20/55/44 全组合稳定支持。
- 主控已正式取代“单一概率 Reviewer 承担零漏判生产授权”路线，采用服务端预分配的
  `trusted_fact + creative_expression` 双轨合同。Reviewer 退出新任务生产放行；历史
  DeepSeek／千问 raw、人工否决和 `BLOCKED` 事件继续保留。当前归档引用
  `archive/ui12-blocked-before-dual-track-20260729` 固定指向
  `8f5b3e52ff7f83494555b80ad511790514d21c45`。
- 历史 Reviewer 路线已完成否决：`deepseek-v4-pro` 与千问候选都在清楚负例上产生
  安全关键假阴性，OpenAI 又不满足中国境内生产运行边界。它们的 raw、人工否决与
  `BLOCKED` 记录完整保留，但新任务生产主链不再调用 Reviewer；千问适配器、配置、资格
  runner 与无正式消费者的测试已由普通前向提交移除。
- 当前实现由服务端在 Writer 前冻结 `creative-kernel-v2`：每个最终可见单元只有
  `trusted_fact` 或 `creative_expression` 一条轨道，后者只允许
  `general_observation`、`recommendation`、`hypothesis`、
  `disclosed_dramatization`。Writer 只能填写既定可写 unit；`delivery-compiler-v2`
  原样插入事实、添加自然可见范围并验证所有出口、来源与制作资源。
- G7 的新合同已经落地：整体 Frame 仍为 `actuality_reflection`，V1 真人事实及原反思
  冻结不变；用户明确要求荒诞／小情景时，服务端可新增一个局部、完整披露的
  `disclosed_dramatization`，且不能反向污染现实事实或资源。
- `UI-11` 为 `SUPERSEDED → UI-12`；只表示 UI-11 的粗粒度
  “abstract 里任一 action/cause/result 即现实事件”裁决被单一 clause 权限链取代，不表示
  UI-11 成功。UI-11 的 `BLOCKED`、G3 初稿和唯一修复失败、Reviewer evidence、G4/D1
  未运行及未 push/CI/部署证据完整保留。
- 上一轮运行、CI 与部署代码 SHA 为
  `b6180b093c1af5198edd396937e4b2d7700546d5`；实现历史已普通前向推送，
  `origin/main` 曾精确核对为该 SHA。主控终审指出事实冻结、修订不可变性、否定语义和
  披露防伪仍有直接代码缺口，该 SHA 不再作为最终生产候选。`docs/项目记忆.md` 的用户既有修改
  已单独保存在 `9bb9872…`，没有被覆盖或混入运行实现。UI-07—UI-12 历史禁止 reset、
  rebase、squash、删除或改写。
- 生产已先行回退到已验证安全镜像
  `diyu-saas:845f63291ba5060e60f87d1afa5cfc1cdb057e3b`，不 downgrade 数据库；
  schema 保持 expand-only `20260803_30`，回环／公网 readiness 为 `200/200`，应用角色
  可读取 32 条既有非空版本记录。本次回退只退出尚未封死的 UI-12 新自然创作路径，不改写
  上一轮 CI、备份、验收或回退证据，也不删除 `c0dfb94…` 镜像及 root-only 证据。
- 本轮只做两项高风险有界返工：以 forward、expand-first 迁移把 `content_versions`
  收敛为数据库追加式记录，并让所有新审计版本读取统一重算最终可见成品摘要；建立唯一
  保留可见结构定义，关闭 Writer 对范围标签、正式 heading、零宽与双向控制字符的伪造，
  且 `delivery-compiler-v2` 成品不再经过 legacy 自由文本重解析。完成前不 push、不触发
  CI、不部署新候选。
- 本轮最终运行实现 `15a6f1fd57dd46d16baadd0730cc255da9c6d5e2` 已形成并部署：
  schema head `20260804_31` 使
  `content_versions` 的任意 UPDATE 由 trigger 失败关闭，并撤销 `diyu_app` 的 UPDATE
  权限；`content-version-audit-v2` 绑定 compiler-v2 最终可见 outline/body，所有正文
  返回、历史、复制、导出、修订父版与平台改编源均消费同一摘要校验器。Writer 标题及全部
  可写单元使用共享保留结构定义进行 NFKC／零宽防伪并拒绝双向控制字符，原始正常中文与
  emoji 不被改写。旧 raw 反证、数据库 UPDATE、摘要不一致和两项 mutation proof 均已
  转绿；本地 PostgreSQL 纵向与 Golden/OpenAPI `406 passed`、Ruff、mypy、前端
  lint/typecheck/interaction/build 全绿。唯一承重 CI `30478106189` 对应该 SHA 且
  全绿；生产部署仓和镜像均为该 SHA，schema 31，公网／回环 readiness 为 `200/200`。
- 生产同一运行 SHA 的 G1—G7/H1/D1 已连续执行一次：G1/G6 为 `0/0/0`，其余卡片形成
  完整 V1 或 G7 V2，Reviewer 调用为 0；人工阅读全文确认正式 heading 各仅一处且没有
  零宽／双向字符逃逸。G2 只使用三个 ImmutableFactBlock；G4 原话逐字保持；G7 的
  V1/V2 各有独立 audit-v2 摘要，冻结 Frame、Plan、事实、来源、商品事实包和 compiler
  不变，V1→V2→V1 可读。失败原子性为 task +1、failed run +1、version +0、running +0。
  验收数据、两个会话及一次限流事件已精确清理，计数恢复 `78/80/32`。
- 新鲜备份
  `/var/backups/diyu-m5-4/20260729T181029Z-ui12-rework-predeploy` 创建时目录／文件为
  `0700/0600`，checksum、隔离恢复、RLS、应用 readiness 与对象恢复均通过。旧安全镜像
  `845f632…` 已在 schema 31 上读取 legacy 版本、AIGC 字段且错误租户为 0 行，随后切回
  最终候选；首次回退因执行 shell 的 `umask 077` 泄漏到 Git checkout 而短暂 502，保留
  原始失败证据，改用代码构建 `umask 022` 后同一路径通过。
- 部署后只读普查覆盖 2 个租户作用域：legacy 307、审计版本 0、部分审计 0、摘要不一致
  0；没有改写历史正文。`diyu_app` 的版本 UPDATE 权限为 false，append-only trigger
  恰好 1 个，运行资产 41，候选／目录真源继续为 `243/25/119`，激活增量 0。生产证据位于
  `/var/lib/diyu-ui12-evidence/15a6f1fd57dd46d16baadd0730cc255da9c6d5e2/`。
- 第二次终审返工的最终实现
  `9c5b2436f3594b08c5df9c5b758293fd5b4cf177` 以前向 schema
  `20260805_32` 关闭 DELETE：应用角色权限为 SELECT/INSERT true、
  UPDATE/DELETE false；数据库 trigger 覆盖 `BEFORE UPDATE OR DELETE`。迁移角色的
  maintenance gate 只能在同一事务、精确 tenant/version 且目标账号明确为
  `synthetic_business_fixture` 时删除一行，事务结束后自动失效。legacy 投影恢复为只按
  全角冒号解析，ASCII `限制:`／`标题:`／`完整发布正文:` 不再隐藏或重排历史文字；
  Writer 安全匹配仍覆盖全／半角 heading，并按 Default_Ignorable 处理 U+2061、
  U+2063、U+034F、soft hyphen、variation selectors 与 bidi controls，不改写正常中文
  或 emoji。
- 同一实现的 Ruff、mypy、Golden/OpenAPI `417 passed`、前端
  lint/typecheck/interaction/build 及两份有界审查均通过；唯一承重 CI
  `30500580180` 为 `success`。生产部署仓与镜像均为该 SHA，schema
  `20260805_32`，公网／回环 readiness 和 `/status` 为 `200/200`。生产只读 legacy
  普查为 307 行，旧全角算法差异 0、ASCII 误解析受影响 0、audit-v1 摘要异常 0，未改写
  任何正文。synthetic audit-v1/v2 冒烟验证了读取、历史、复制／导出同源、平台改编、
  系列、AIGC 和错误租户 0 行，随后通过精确 maintenance gate 清理，遗留 0。
- 新鲜备份
  `/var/backups/diyu-m5-4/20260729T234943Z-ui12-final-predeploy` 创建时目录／文件为
  `0700/0600`，checksum、隔离数据库恢复、RLS、应用 readiness 与对象恢复均通过；
  deploy.sh 依既有行为另建
  `/var/backups/diyu-m5-4/20260729T235012Z-predeploy`，同样通过权限与 checksum。
  旧镜像 `845f632…` 已在 schema 32 上成功启动、读取 legacy 且错误租户为 0，随后切回
  最终候选。首次回退因证据 shell 的 `umask 077` 泄漏到 Git checkout，使旧镜像源码为
  0600 并短暂 502；候选立即恢复，改用构建 `umask 022` 后同路径通过，原始失败证据保留。
  当前 root-only 证据位于
  `/var/lib/diyu-ui12-evidence/9c5b2436f3594b08c5df9c5b758293fd5b4cf177/second-bounded-rework/`，
  目录／文件为 `0700/0600` 且 SHA256SUMS 全绿。
- 定向返工运行代码
  `c0dfb9459f9cffcb0958348d3f43c55f55f3bb26` 收敛：服务端只向 intake 暴露带稳定
  `source_id` 的完整用户事实句，模型无法返回任意事实子串；首人称／指代式真实经历请求在
  没有完整事实句时由服务端合并追问一次。仓储只接受封闭 completion patch，并在
  expand-only schema `20260803_30` 为每个版本写入不可变 artifact digest 与独立审计
  快照。否定式“不要荒诞”不再启用局部演绎，Writer 伪造服务端范围标签会失败关闭，可见
  范围已改为自然且明确的创作表达说明。
- 同一 SHA 已在 ECS 隔离临时 PostgreSQL、无生产业务连接的环境中完成一次
  G1—G7/H1/D1：G1/G6 为 `0/0/0`，G2/G3/G4/G5/H1/D1 为完整 V1，G7 为 V2 且
  V1→V2→V1 一致；DeepSeek Flash 调用 15 次、`max_retries=0`、Reviewer 调用为 0。
  G7 的 Frame、Plan、真人事实、来源、ProductFactPacket、事实块、renderer、资源和
  compiler 均在两个独立版本审计快照中保持不变，kernel 实质变化。root-only 证据位于
  `/var/lib/diyu-ui12-evidence/c0dfb9459f9cffcb0958348d3f43c55f55f3bb26/final-business-cards/`，
  权限为 `0700/0600`。
- 人工逐篇阅读全文确认：G2 只使用三个服务端 ImmutableFactBlock，G3/G5/H1/D1 的
  假设／演绎范围完整；G4 真人原话逐字保留，其余文字明确标为创作性观察、不补充现实
  细节；G7 小剧场在标题、概要、正文和发布配文均未脱标。最终本地门为 Ruff、mypy、
  Golden/OpenAPI `393 passed` 及前端 lint/typecheck/interaction/build 全绿。
- 最终候选 `c0dfb9459f9cffcb0958348d3f43c55f55f3bb26` 已普通前向推送；唯一承重 CI
  `30471874527` 对应该 SHA 且全部绿色。新鲜备份
  `/var/backups/diyu-m5-4/20260729T164439Z-predeploy` 在创建时满足目录 `0700`、文件
  `0600`，checksum、隔离数据库恢复、RLS、应用 readiness 与对象恢复均通过。生产已以
  同一 SHA 部署，schema expand-only 升至 `20260803_30`，公网／回环 readiness 与
  `/status`、公共／租户管理／运维入口均为 `200`；旧安全镜像 `845f632…` 保留。
- 同一生产 SHA 已连续完成一次 G1—G7/H1/D1：G1/G6 为 `0/0/0`，其余卡形成完整 V1
  或 G7 V2；人工逐篇阅读全文通过。G7 的两个版本各自保存不可变审计快照，Frame、Plan、
  真人事实、来源、ProductFactPacket、事实块、renderer、资源与 compiler 不变，
  kernel 实质变化且 V1→V2→V1 可读。生产验收的 6 个任务、7 个运行、7 个版本、
  6 个内容项和 14 条活动事件已精确清理，租户计数恢复 `78/80/32`，永久 running 为 0。
  失败原子性探针为 failed run、version 0、running 0，探针数据也已清理。
- 生产 root-only 证据位于
  `/var/lib/diyu-ui12-evidence/c0dfb9459f9cffcb0958348d3f43c55f55f3bb26/production-final-cards/`，
  权限为 `0700/0600` 且 SHA256SUMS 通过。RLS 无作用域读取拒绝、错误租户为 0 行；
  历史 V1/V2、系列、DM01、AIGC 与资产保持。旧镜像 `845f632…` 已在 schema 30 上完成
  不降级数据库的读取／readiness 回退检查，随后切回 `c0dfb94…` 并复核健康。
- 无持久化业务轮在运行合同 SHA
  `189e80cac2820e459aa444d75619c85bb7f643d2` 完成；G1/G6 为 `0/0/0`，
  G2/G3/G4/G5/G7/H1/D1 均形成完整成品，人工逐篇全文审阅通过。随后在最终代码 WIP
  `3518fda…` 的无网络容器中重新解析全部 kernel 并重跑 DeliveryCompiler，七个成品的
  标题、正文、语义合同、来源、资源与 digest 均无漂移；provider/Reviewer 调用为 0。
- 最终代码重放证据位于
  `/var/lib/diyu-ui12-evidence/3518fdacd21b37f9a0a76b8027bbec6ab659475a/final-runtime-replay/`，
  目录／文件权限为 `0700/0600`，summary SHA-256 为
  `4ca9feef0d20461d0063f3bbd9e7cf0ffc1e18e9fe09d12a2badb9d9af3acb5f`。
  凭据未进入证据或 Git，临时容器、源码投影与脚本已经删除。
- 最终本地工程门已通过：Ruff、mypy、Golden `379 passed`、OpenAPI，以及前端
  lint/typecheck/interaction/build 全部绿色；完整工程门之后的代码变化仅为产品事实职责
  注释订正。产品与内容语义、工程安全与兼容两份有界审查均为 `PASS`；最终
  候选 `dbcbef4…` 的 CI `30462824536` 已绿色并完成首次部署，schema 已 expand-only
  升至 `20260802_29`、readiness `200/200`。
- 首次部署的备份 `20260729T145342Z-predeploy` 暴露真实权限缺陷：dump／manifest 为
  `0600`、objects 目录为 `0700`，但 snapshot 父目录实际为 `0755`，对象镜像也继承容器
  默认权限。该快照已立即收紧至 `0700/0600` 并重新校验 checksum，但不冒充“创建时安全”
  的最终备份。备份脚本现同时显式创建 `0700` snapshot 父目录，并在 MinIO 镜像容器写入
  前执行 `umask 077`；定向反证、Ruff、mypy 与 Golden `379 passed` 已重新通过。
- 备份权限修复 SHA `b6180b0…` 的最终承重 CI `30463641265` 为 `success`；随后同 SHA
  部署完成。修复后的新鲜备份
  `/var/backups/diyu-m5-4/20260729T150217Z-predeploy` 在创建时即满足目录 `0700`、
  文件 `0600`，checksum 全通过；隔离恢复、RLS、应用 readiness 与对象恢复也全部通过。
  首次 `dbcbef4…` CI／部署只作为发现权限缺陷的前置候选保留，不冒充最终承重结果。
- 同一生产 SHA 已一次连续执行 G1—G7/H1/D1：G1/G6 为 `0/0/0`，其余卡形成完整
  V1/V2；Reviewer 调用为 0。人工阅读全文确认 G2 硬事实仅来自不可变事实块，G3/G5/H1/D1
  的假设／演绎范围完整，G4 原话逐字保留，G7 保持 Frame、Plan、事实和来源并新增局部已
  披露演绎。验收的 6 个任务、7 个运行、7 个版本、14 条活动事件和 2 个会话已精确清理，
  计数恢复且永久 running 为 0。
- 旧安全镜像 `845f632…` 已在 schema `20260802_29` 上往返回退：旧镜像 readiness
  `200/200` 且既有 V1/V2 可读，未 downgrade 数据库；随后切回 `b6180b0…` 并再次通过
  readiness、入口和状态检查。RLS 无作用域读取拒绝，跨账号历史读取失败关闭，系列、平台
  父子版本、DM01、AIGC 与资产 `41/243/25/119` 均保持。
- 唯一执行端：当前 WSL 执行端；同一时间只允许一个写入者。
- 当前任务包：
  [`docs/UI-12-来源语态主体绑定与服务端证据裁决闭环执行包.md`](docs/UI-12-来源语态主体绑定与服务端证据裁决闭环执行包.md)。
- 产品语义与工程安全两份有界审查均为 `PASS`；最终运行 SHA、唯一 CI、生产部署、备份、
  兼容冒烟、精确清理与回退证明均已成立。主控第三次、也是最终一次独立终审为 `PASS`，
  UI-12 正式 `CLOSED`。当前没有由本次自动启动的后继里程碑；唯一下一动作是停止执行，
  等待用户与主控另行启动“前端用户体验产品化”独立里程碑，本轮不提前命名、不施工、
  不部署。
- 承重裁决：[ADR-028](docs/架构决策/ADR-028-来源语态主体绑定与证据裁决矩阵.md)
  已由本次主控裁决置为 `ACCEPTED`。启动前已把 SDR-001—SDR-037 订正为 42 条无重复
  stable ID、单值 `unit_contract` 的 SDR-001—SDR-042，并通过 diff、唯一性、单合同与
  successor 未提前激活检查。
- 冻结能力：CreationIntentGate、CreativePlanV2、NarrativeFrame、CreativeKernelV1、
  ReviewEvidenceV1 legacy、服务端事实裁决、DeliveryCompilerV1、服务端逐字事实、最多一次
  affected-unit 修复、legacy 路径、RLS、DM01、AIGC 与资产 `41/243/25/119` 不得回退。
- 本地实现：功能 SHA
  `c3b3eadfb22ab21d528c42bbf58d1fd02c12456e` 已实现唯一 `ClauseContextV2`
  sidecar、occurrence-aware `ReviewEvidenceV2`、ContentRole 结构化 speaker kind、
  固定顺序四态裁决和 H1/D1 program 映射；该 SHA 只是未推送的本地实现，不是生产候选。
- 已通过门：16 个历史 raw bundle／20 份 raw response 均完成 hash 校验与按原版本离线
  解析；42 条 SDR 直接消费者、六项实际 mutation、`git diff --check`、lint、mypy、
  Golden `279 passed`、OpenAPI 以及前端 lint/typecheck/interaction/build 均通过。
- 阻断：同一 SHA、`deepseek-v4-flash`、temperature 0、零重试、thinking disabled、
  无 repository/database 的 Reviewer V2 首批真实资格调用返回 10 个 clause，但其中
  `q:c`、`q:recommend`、`q:hypothesis` 三项遗漏必填 `implicit_subject` 与
  `uncertain`，并把 `aspect` 错放到 clause 根级。响应因此不能解析为
  `ReviewEvidenceV2`；evidence 资格在服务端语义裁决前即失败关闭。
- 停止线执行：没有重跑 Reviewer，没有调用 Writer，没有执行 G3/G4/H1/D1、本地
  API/PostgreSQL、两份候选审查、push、CI、备份、部署或生产卡片。生产继续运行
  `845f632…`；本轮未写生产业务数据。root-only 原始响应保存在
  `/var/lib/diyu-ui12-evidence/c3b3eadfb22ab21d528c42bbf58d1fd02c12456e/`
  `reviewer-v2-qualification/`，目录／文件权限为 `0700/0600`。
- 主控恢复裁决：上述 `BLOCKED` 事件与 raw 证据原样保留，但根因订正为普通
  `response_format=json_object` 只约束 JSON 形态、不保证 ReviewEvidenceV2 Schema。
  UI-12 在原里程碑内恢复 `ACTIVE`，不创建 successor；唯一实现变化是 Reviewer V2
  改用同一 `deepseek-v4-flash` 的 `/beta` strict function transport，并把 Reviewer
  作用域收为 writer-owned clause。Writer、intake 与其他模型调用不切换 Beta。
- Strict transport 实现 SHA
  `b1deb3c98889f33902e765a1ab37ffb7614d0bd5` 已通过 schema、单一 tool call、
  writer-only 作用域、容量、旧 raw 拒绝及 SDR 不回退等确定性门；`make lint`、
  `make typecheck`、Golden `294 passed` 与 OpenAPI 同步。
- 第二次真实资格第一包只调用一次：API 接受 `/beta` strict schema，返回
  `finish_reason=tool_calls`、恰好一个正确 function，9/9 clause 且 arguments 可由严格
  parser 解析，故 transport 资格通过。但歧义句“婆婆尊重儿媳。”返回
  `uncertain=true`，重复 occurrence 的第二个“停了一下”返回错误 offset
  `9:13`（真实位置 `10:14`）；服务端分别保守为 `insufficient_evidence` 与
  `review_evidence_span`，整包 Reviewer evidence 资格失败。
- 停止线执行：第二包、Writer、G3/G4/H1/D1、正式 API/PostgreSQL、push、CI、备份、
  部署和生产验收均未执行；没有重跑、补默认值、清洗 offset、改 Prompt、fallback、
  换模型或启动 UI-13。生产保持 `845f632…`。
- 唯一下一动作：主控裁决“strict transport 已成立、但当前 Reviewer 不能稳定给出
  无 uncertain 且 occurrence 精确的 evidence”这一单一阻断；裁决前 UI-12 保持
  `BLOCKED`。
- 主控后续裁决已关闭该阻断：Reviewer 改为只返回“精确原文片段＋从 1 开始的 occurrence
  序号”，服务端在对应 clause 中枚举全部精确匹配并计算 Python Unicode offset；
  occurrence 越界、原文不匹配或无法唯一绑定继续失败关闭。歧义样本返回
  `uncertain=true` 是合格 evidence，最终由服务端裁为 `insufficient_evidence`，且不得
  送 Writer 修复。
- UI-12 在原里程碑内恢复 `ACTIVE`，不创建 UI-13。Strict function transport、
  ADR-028、服务端四态裁决矩阵与全部事实／主体／资源／租户边界不变；不换模型、不加
  fallback、不堆失败句 Prompt。
- 当前唯一下一动作：仅修正 Reviewer V2 span 传输合同、服务端 occurrence→offset
  解析和资格口径，完成确定性反证后执行一次新合同真实资格；本次裁决落盘不等于已经实现
  或通过资格。
- 首次新合同真实资格在实现 SHA `1da4811d059b8865f1ffc0673702a169d5f2d986`
  上完成一次调用：strict tool、6/6 clause、text+occurrence、重复片段第 1/2 次、
  服务端 offset `2:6/10:14` 及全部服务端 SDR 裁决均成立。唯一失败是资格脚本要求
  “婆婆尊重儿媳。”必须同时返回 `uncertain=true`；raw 实际完整提取主体、谓词及
  modality/aspect 缺席，服务端已正确得到 `insufficient_evidence`。
- 该失败归类为 oracle 把“证据关系歧义”和“合同证据不足”混同：裸建议／事实歧义由服务端
  单值 recommendation contract 与正向 grammatical evidence 裁决，不得要求 Reviewer
  重新判断 factuality。保留首次 raw；资格夹具改为真实存在指代关系歧义的 clause，
  不改 Reviewer Prompt、模型或服务端合同。
- 订正 oracle 后的新合同资格在文档 SHA
  `91be39cc5b8e993d790e9e59c59b0eb3e7d49d1c` 上一次通过：strict function、
  6/6 clause、真实指代歧义 `uncertain=true`、重复片段 occurrence `1/2`、服务端
  offset `2:6/10:14` 和全部冻结 SDR 裁决成立。raw SHA 为
  `03e9e1f2f3be1582f91468659c3e51987cca2a1ae3cc8c205d91a6d788cf82c5`，
  arguments SHA 为
  `4a646289d6b9a468e614daa5ff538f32eee9b73d1d2cd9b02fa4fc513d2d2b09`；
  重试为 0。由此证明 strict transport、小包 evidence 与服务端 occurrence→offset
  职责成立，但不冒充完整成品规模资格。
- 随后按最便宜纵向门执行冻结 G3。第一次调用已经到达 Reviewer 后的服务端失败关闭，但
  临时证据脚本只在成功末尾落 raw，未能保留失败响应；这是证据采集脚本缺陷，不作为产品
  结论。脚本改为每次响应立即 root-only 留存后，仅复验受影响 G3。
- G3 复验的 intake、Writer 与 strict Reviewer 各调用一次；Reviewer 返回
  `finish_reason=tool_calls`、唯一正确 function 和 16/16 clause，但 12 个 span 的
  occurrence 越界：对应 text 在各自 clause 只出现 1 次，却被返回 occurrence 2 或 3。
  服务端严格 parser 以 `review evidence occurrence cannot be resolved` 失败关闭，
  没有默认第一次、清洗、Writer 修复或 DeliveryCompiler/版本写入。Reviewer raw 封装
  SHA 为
  `598a879585a9f2837b7d22be7259417112b1d515bffd096ddf5e01681f0e9423`，
  诊断 SHA 为
  `c050013e3d7ba0453e78d715b84ba5533572b2f0f438873ab3465b828591af0e`，
  root-only 保存在
  `/var/lib/diyu-ui12-evidence/91be39cc5b8e993d790e9e59c59b0eb3e7d49d1c/g3-sentinel/`
  且权限为 `0700/0600 root:root`。
- 这已命中本轮明定停止线“Reviewer 在 text+occurrence 新合同下仍无法选择正确
  occurrence”。UI-12 置为 `BLOCKED`；G4/H1/D1、其余 G 卡、完整工程门、两审、push、
  CI、备份、部署和生产写入均未执行。生产继续运行 `845f632…` 安全版本。
- 停止后只读复核生产部署仓仍为 `845f632…`，镜像 ID 仍为
  `sha256:1171b153…`，schema `20260801_28`，回环／公网 readiness `200/200`，
  `diyu-m5-4-backup.timer` active。
- 当前唯一下一动作：主控审阅完整 G3 的 occurrence 失效证据并裁决当前 Reviewer 方案；
  不自动创建 UI-13，不在执行端继续重跑、换模型、加 fallback 或放宽事实边界。
- 主控后续裁决已完成：Reviewer 不再返回 `start/end/occurrence`，只返回所属 clause
  的 exact quote 与 evidence 类别；服务端负责 0/1/多次精确匹配、Unicode offset
  规范化和失败关闭。transport、schema、parser、binder、fixture、oracle 与必要 Prompt
  调整均属于 UI-12 内普通实现自由，运行时失败关闭不再等于开发立即停工。
- 当前执行纪律：先离线重放现存完整 16-clause G3 raw，再实现 quote-only binder 并尽早
  运行完整 G3；只有产品责任、安全隔离、供应商或历史兼容真实边界改变才停止。所有本地
  SHA 在完整 G1—G7/H1/D1 成立前均为 WIP，不是生产候选，不 push/CI/部署。
- quote-only 收口：Reviewer strict 输出已删除模型侧 `start/end/occurrence`，服务端只接受
  clause 内唯一 exact quote 并计算 Python Unicode offset；零匹配、多匹配和
  `uncertain` 均保守停止，且 `uncertain` 不进入 Writer 修复。定向 parser、binder、
  四态裁决和 legacy 回归通过；这些提交全部是未推送 WIP，不是生产候选。
- 完整 G3：实现 `440002d…` 的无 repository/database 纵向轮通过 strict evidence、
  服务端裁决、DeliveryCompiler 和人工全文审阅；成品采用“抽象观察＋服务端包裹的
  hypothesis”，未冒充用户、品牌或真实家庭经历。该证据证明 quote-only 绑定可在完整
  成品规模工作，但不单独证明 G4 真人事实边界。实际 Git SHA 为
  `440002d7151008f31163c3e610fff6d3accd3e6a`；证据目录的同前缀完整标签也存在脚本误写，
  原目录和 raw 均保留不改。
- G4 停止线：实现 `72c1201…` 的 G4 曾机器通过，但人工阅读全文发现 Writer 增加“伴侣”
  身份、动机和示例对白，证明 Reviewer 假阴性。执行端在同一 evidence 合同内增加通用
  `relationship_role` 精确证据并收窄一次修复；最终实现
  `c4b89534cdbe393dc30dfda858595d5d80da0b88` 的初稿、唯一修复和完整复审仍失败关闭。
  修复稿可见文字仍增加“亲密关系”、期待／渴望等动机以及建议动作；对应 Reviewer raw
  对 10 个 clause 返回 32 项 evidence、`uncertain=0`，却没有返回任何
  `relationship_role`、`motive` 或 `dialogue` evidence。服务端抓住发布配文的两项问题
  并拒绝保存，但无法仅靠缺失 evidence 稳定识别其余人工可见违规。
- 这不是 quote binder、transport、schema、fixture 或服务端四态裁决错误；继续关闭该
  缺口只能依赖本轮禁止的失败句／人物词表、第二 Reviewer／模型处置，或降低 G4 “不扩写
  人物、动机、对白、原因和结果”的事实边界。故 UI-12 如实保持 `BLOCKED`。H1、D1、
  G1/G2/G5/G6/G7、最终完整业务轮、完整工程门、两审、push、CI、备份、部署和生产写入均
  未执行。
- root-only G4 证据保存在
  `/var/lib/diyu-ui12-evidence/c4b895362075309247895e49c4e29bc87d04fbc2/`
  `g4-preflight/`，目录／文件权限为 `0700/0600 root:root`；最终 Reviewer raw 与最终
  服务端 issues 的 SHA-256 分别为 `d9d921865080…`、`0512712ab2ab…`。原始 Prompt、
  凭据和完整敏感正文未进入 Git。该目录名及 `g4-failure.json.wip_sha` 是证据脚本误写的
  同前缀完整 SHA；真实 Git 实现 SHA 为 `c4b89534cdbe393dc30dfda858595d5d80da0b88`。
  原始证据不改名、不改写，以哈希和本条纠偏共同留痕。该偏差意味着本轮 WIP 模型证据没有
  完整 SHA 级的自动来源证明，不能冒充最终候选同 SHA 证据。停止后只读复核生产部署仓及镜像仍为 `845f632…`，
  schema `20260801_28`，回环／公网 readiness `200/200`，备份 timer active；本轮没有
  生产业务写入。本机及 ECS `/tmp` 下本轮 UI-12 源码归档、隔离源码和探针脚本已精确
  清理，`/var/lib/diyu-ui12-evidence/` 正式历史证据保留。
- 当前唯一下一动作：主控审阅并裁决“当前单一 Reviewer 无法稳定提取 G4 所需关系角色／
  动机 evidence”这一已经角色隔离的能力阻断；裁决前不换模型、不加第二 Reviewer、不降
  事实边界，也不创建 UI-13。
- 后续主控裁决：上述阻断不是单 Reviewer 能力结论，而是开放式 evidence 枚举无法证明
  “未返回的风险不存在”。UI-12 在原里程碑内恢复 `ACTIVE`，用服务端闭合问题集取代自由
  类别枚举；Reviewer 对每个 `question_id` 恰好回答 `present/absent/uncertain`，服务端
  验证全集与唯一 quote 后派生 Claim Inventory，再执行 ADR-028 唯一裁决。不得继续添加
  evidence 类别、失败句或人物词表。
- 当前 Git 现场：状态启动 `HEAD=0bed884d92e34fa7a63b01d5896cce33a1e44abf`，
  `origin/main=7aa87ab624cf3ff64f42e49f1755d66d496cac7a`，本地领先 54 个线性提交；工作树已有
  用户的项目记忆增量，已完整保护。生产只读复核仍为部署仓／镜像 `845f632…`、schema
  `20260801_28`、回环／公网 readiness `200/200`、备份 timer active。
- 当前执行纪律：先离线重放现存完整 G4 初稿、修复稿、Reviewer raw 与 service issues，
  直接形成当前 G4 消费的闭合问题夹具；确定性门通过后直接运行完整无持久化 G4。完整
  G1—G7/H1/D1 成立前均为 WIP，不 push、CI、备份、部署或写生产。
- 闭合合同首轮确定性结果：当前 G4 初稿 `13` 个 writer clause 被展开为 `130` 个固定
  问题，唯一修复稿 `10` 个 writer clause 被展开为 `100` 个固定问题；人工冻结回答经
  服务端派生 Claim Inventory 后，两稿均稳定拒绝。最终旧 raw 中
  relationship/motive/dialogue 全部漏提的事实被保留，闭合回答不再允许用“没有返回”
  冒充 absent。主链定向回归、strict transport、legacy SDR 与相邻 UI-09—UI-12 消费者
  已通过；这些仍是未调用新模型的 WIP 证据，不表示 G4 成立。
- 首次闭合合同真实 G4：本机供应商连接在任何响应前超时，确认是 WSL 出网不可达；随后
  用固定 SHA 在无数据库临时容器执行。探针首次把历史稳定的无句末标点 fact span 与 P4
  错当成 P3/带标点而拒绝，归为 oracle 缺陷并复用已哈希 intake raw。有效链完成初稿、
  两批审查、唯一修复和完整复审；Reviewer 已逐题提取关系、动机、对白与当前用户绑定，
  服务端正确拒绝初稿。修复稿唯一剩余 issue 是把“仅向受众征询观点”的互动问句误标为
  recommendation；明确“建议须指示行动，纯受众问句为 generic observation”后，原 raw
  离线裁决转绿。该项是 statement-mode 合同歧义，不是失败句、人物词表或事实边界放宽；
  新实现 SHA 尚待一次完整 G4。
- 闭合合同真实 G4 已在 WIP `0eca737fc7d8da76a47f57f9596ae2becc57540c`
  重新完成：Gate 与 intake 合法，服务端逐字事实保持，初稿经一次允许的 affected-unit
  修复后完整复审通过，reviewed digest 为
  `cce8ce…`，visible SHA 为 `3525eb…`。人工阅读全文确认未补丈夫身份、具体对白、
  谁洗、动机、结果或现场重演，制作只使用文字卡与排版。root-only 证据位于
  `/var/lib/diyu-ui12-evidence/0eca737fc7d8da76a47f57f9596ae2becc57540c/`
  `g4-closed-preflight/`。该 SHA 是 WIP，不冒充最终同 SHA 业务轮。
- 随后 G2 在 WIP `0eca737…`、`914b1d7…`、`a10e600…` 与最终
  `d4d2818d23b453d6798ab7a60709d2df28610113` 逐层排除了 answer operand、
  issue 分类与事实暴露接缝。最终轮已不向 Writer 暴露商品 frozen fact，Writer 仍把
  `ZX-C218` 猜成电子产品并补造电源、接口、驱动、兼容性、规格、性能和适用性；Reviewer
  闭合回答与服务端 Claim Inventory 将其全部判为 `unsupported_product_claim`，唯一
  修复后仍失败。调用链共 6 次 provider 调用，未编译、未保存版本，证据目录为
  `/var/lib/diyu-ui12-evidence/d4d2818d23b453d6798ab7a60709d2df28610113/`
  `g2-preflight/`，失败摘要 SHA-256 为
  `ed913c70f2cc69c3f7913adbfd31f39d5f21484c199ac289d68e96bd7b63dee5`。
- 该结果证明闭合 Reviewer／服务端裁决按设计失败关闭，也证明当前冻结职责无法同时做到
  “Writer 不读取商品事实”“Compiler 不新增语义”与“只凭 SKU 交付有商品价值的完整
  V1”。继续补 Prompt、问题类别或失败句不能解决；固定成稿、模型替换与扩大 Compiler／
  Writer 商品事实权限均未获本轮授权。G1 仅在 WIP `0eca737…` 验证为 `0/0/0`；
  最终同 SHA 的 G1—G7/H1/D1、完整工程门、两审、push、CI、备份和部署均未执行。
  生产继续运行 `845f632…`。
- 当前唯一下一动作：主控裁决商品成品中“由谁把服务端冻结商品事实编译成可审创作文字”
  这一单一职责边界；在不降低事实边界的前提下，选择服务端确定性商品表达编译，或授权
  Writer 只读消费精确商品事实的最小新合同。UI-12 在裁决前保持 `BLOCKED`。
- 主控现已解除上述阻断并恢复 UI-12 `ACTIVE`：采用单一职责模型
  `ProductFactPacket → ImmutableFactBlock → Writer 引用＋创意文字 → Closed Reviewer／
  服务端裁决 → DeliveryCompiler`。服务端拥有商品事实真值并原样渲染硬事实；Writer
  只读理解精确商品、可选择既有事实块 ID 与顺序，但不得创建、改写或复述硬事实；
  `claim_refs` 只作追溯线索，不自动授权。Reviewer 审查创意文字新增的商品属性、性能、
  结果、动机、价格、库存、比较与实际体验，服务端继续唯一裁决。历史 `BLOCKED` 与 G2
  原始证据完整保留；恢复施工不表示 G2 或 UI-12 已通过，不创建 UI-13。
- 当前 Git 基线为状态提交 `cd444856e1ab8642b3f4f5b4b4d2ed77884d1e96`，
  代码 WIP `d4d2818d23b453d6798ab7a60709d2df28610113`，
  `origin/main=7aa87ab624cf3ff64f42e49f1755d66d496cac7a`，本地领先 64 个线性
  提交且工作树干净。当前唯一下一动作是实现上述最小事实包／事实块纵向链，先用历史
  G2 raw 反证，再运行一次新实现真实 G2；完整业务轮成立前不 push、CI、备份或部署。

- 商品责任裁决后的本地 WIP 已继续收敛到
  `e213cc6c771960ee0896a277599dfcf3fc30f3da`，并执行同一 SHA 的无持久化
  G4→G7 纵向轮。机器链将 G4、G7 都判为通过，Frame／Plan／program／事实／来源／
  compiler version 不变量也成立；但人工阅读全文否决该结果。G4 创意文字新增“这个家、
  两个人、被看见、拥抱”等未冻结关系／心理／动作，G7 又新增“两只碗、家庭矛盾”等
  现实细节。
- 最终 G4 Reviewer raw
  `12fec18004747ff20fd3f1f7bd8cf751985923be7c212a61801ebdad1505317d`
  与 G7 Reviewer raw
  `a23f3cc7b92706a4994659f242a189e4b4d1ff7008b3672f127eac9c1a7c19eb`
  证明同一发布配文、同一 question ID 的心理 evidence 在两轮分别为空与
  `desire/emotion`；G7 明确含“家庭矛盾”的 natural guide 对
  `relationship_claim` 仍返回空且 `uncertain=false`。闭合问题 Prompt 已明确家庭属于
  关系主张，问题全集也完整，因此 fixture、oracle、transport、quote binder 和服务端
  收答覆盖均已排除。
- 该假绿意味着最终同 SHA G1—G7/H1/D1 未成立；未形成生产候选，未 push、CI、备份、
  部署或写生产。只读复核生产部署仓／镜像仍为 `845f632…`，镜像 ID
  `sha256:1171b153…`，schema `20260801_28`，回环／公网 readiness `200/200`，
  `diyu-m5-4-backup.timer` active。
- 当前唯一下一动作：主控只裁决 Reviewer 单角色能力边界；在不降低真人事实边界的前提
  下决定是否授权更换 Reviewer 模型或增加独立语义审查能力。执行端不通过失败句、
  人物词表、默认放行或随机重跑继续。
- 主控已正式选择 Reviewer-only 单角色替换并解除该阻断：intake 与 Writer 继续使用
  `deepseek-v4-flash`，唯一 Reviewer 候选使用 `deepseek-v4-pro`；不增加第二 Reviewer、
  双审、投票、fallback 或事实边界放宽。UI-12 在保留 G4/G7 人工假绿与此前全部
  `BLOCKED` 证据的前提下恢复 `ACTIVE`，不创建 UI-13。
- 当前唯一下一动作：先冻结与 Prompt 分离的 Reviewer 资格集，完成 Writer／Reviewer
  独立模型配置和留痕，再对 `deepseek-v4-pro` 执行无仓储、零重试的 Reviewer-only
  资格门。资格通过前不调用 Writer、不 push、CI、备份或部署。
- Reviewer-only 资格集随后在实现 `2a41fde69db6f615cd9728d5e4439434b5b5b815`
  上通过：strict function transport、问题全集、合法近邻、硬正例、真实歧义与跨 bundle
  一致性均成立；旧 `e213cc6…` G4/G7 假绿也在不调用 Writer 的情况下被 pro 正确拒绝。
- 同一实现的新鲜无持久化 G4 随后命中本次明确停止线。Reviewer 对包含“两个人”的
  writer clause 将 `relationship_claim` 回答为 `absent` 且非 uncertain，形成清楚的
  语义假阴性；唯一 affected-unit 修复又生成“一对伴侣”，最终 Reviewer 正确提取后由
  服务端失败关闭。未进入 DeliveryCompiler，未生成版本或业务写入。
- 该结果不是配置、transport、Schema、parser、quote binder、fixture、oracle 或服务端
  覆盖缺陷。继续只能依赖失败句 Prompt／中文关系词表、第二 Reviewer、投票、fallback、
  更换单一 Reviewer 能力方案或降低事实边界；前四项被禁止，后两项需要新的主控裁决。
  UI-12 因此重新置为 `BLOCKED`，不创建 UI-13。G7、最终同 SHA G1—G7/H1/D1、完整工程
  门、push、CI、备份和部署均未执行；生产继续运行 `845f632…`。
- 当前唯一下一动作：主控裁决是否授权新的单一 Reviewer 语义能力方案；不得在当前
  `deepseek-v4-pro` 候选上随机重跑或回退 flash。
- 主控已用前向裁决订正上述最新停止线：正式 `relationship_claim` 只包含亲属、伴侣、
  家庭、同住、同事、员工、顾客或明确其他社会关系；“两个人／人与人／一些人”等泛指
  人数本身不是关系主张，也不新增 people_count 维度。因此 pro 对“两个疲惫的人”的
  relationship absent 与正式合同一致，先前把它当硬正例属于 qualification oracle drift，
  不是 Reviewer 假阴性。旧 `BLOCKED`、raw 与责任隔离摘要均保留，不回写。
- UI-12 在同一里程碑内恢复 `ACTIVE`，pro 继续为唯一 Reviewer，flash 继续承担 intake／
  Writer。服务端将从既有 ClauseContext、unit contract 与 Claim Inventory 派生最小
  `ClauseLicenseV1` 正向许可；真正的 G4 失败重新归因于唯一 affected-unit repair 仍生成
  未经授权的具体关系身份。不得新增第三模型、第二 Reviewer、投票、fallback、中文关系
  词表或固定成稿。
- 当前唯一下一动作：订正成对 oracle 与旧 raw 离线回放，证明具体关系／current-user
  绑定仍拒绝、泛指心理与建议仍允许，再修复共享 affected-unit repair 合同。

## UI-10 被 UI-11 取代结论（2026-07-28，历史完整保留）

- UI-10 状态：`SUPERSEDED → UI-11`，此前 `BLOCKED` 事实保持。
- UI-10 已证明 Reviewer 新路径只提逐 clause exact evidence，服务端独立裁决
  protected subject、institutional assertion、situated event 和 frozen fact；真实
  Reviewer A/B/C pipeline 为 `3/3`。
- UI-10 同 SHA G3 初稿和唯一 body 修复均在 abstract-only 合同下产生具体家庭情境；
  Reviewer 两轮均完整覆盖 `25/25` clause、跨度精确且无 uncertain，服务端正确拒绝。
  G4、D1、完整验收、push、CI、备份和部署均未执行。
- 历史实现 `ada98ff47e5655fea9e23d6e3d3fc06b00e4f566`、收口
  `9cc96ab8e756f16add2179e0add9e51d3447445a` 及 root-only 证据不改写、不删除。

## UI-07 被 UI-08 取代结论（2026-07-28，历史完整保留）

- 里程碑：`UI-07` 自然创作提交门与叙事真实性闭环。
- 状态：`SUPERSEDED → UI-08`。此前 `BLOCKED` 事实保持。`UI-06` 已在 UI-07 启动时置为
  `SUPERSEDED → UI-07`；这只表示旧的“模型 `ready` 直接授权创建任务”路径由前置
  `CreationIntentGate` 替代，不表示 UI-07 已成功。UI-06 的真实 G1 失败、唯一生产候选、
  CI、备份、部署、回退、清理与 `BLOCKED` 证据全部原样保留。
- 当前 Git 基线：本地 `main` 的 `HEAD`，由阻断实现与证据提交
  `03b710a2420397ac31d8d890a4ebc762f677232b` 及其后的纯状态文档提交组成；`origin/main`
  仍为启动基线
  `7aa87ab624cf3ff64f42e49f1755d66d496cac7a`。该本地提交不是生产候选，没有 push、
  CI 或部署。
- 启动现场：2026-07-28（UTC）核实本地 `main`、`origin/main` 与 `HEAD` 均为
  `7aa87ab624cf3ff64f42e49f1755d66d496cac7a`，工作树干净；相对
  `845f63291ba5060e60f87d1afa5cfc1cdb057e3b` 只有权威文档差异，运行代码树等价。
  生产部署仓库只读核实为 `845f632…` 且干净，运行镜像
  `diyu-saas:845f632…`、摘要
  `sha256:1171b153cbc709a760caf4a5db1fb14fe00e0bca3ef9c7b79c85f737a3a6bdb9`，
  schema `20260801_28`，回环与公网 readiness 均为 `ready`，备份 timer 正常；被拒
  UI-06 镜像 `sha256:a7059106…` 仍保留。
- 已完成范围：已以纯应用层、无副作用、版本化的 `CreationIntentGate` 在任何 repository
  写入及 Writer／Reviewer 调用前冻结 `CreationCommitment`；只有明确文本、用户主动点击
  “直接生成”或服务端可信修改上下文可以授权。门后以前向实现重新引入
  `NarrativeFrame`、四类 `NarrativeBlock`、独立 Reviewer、服务端闭世界对账和最多一次
  完整块级修复；不新增迁移，不整体更换 DeepSeek。确定性恶意 intake seam 已证明 G1 即使
  自报 ready 仍为 task/run/version `0/0/0`，Writer/Reviewer `0/0`；统一 exact-span claims
  和完整目标跨度反证后的当前有界回归为 `170 passed`，ruff、mypy 与前端
  lint/typecheck/interaction 均通过，
  前端普通交流无虚假进度且“直接生成”保留原输入。由于真实模型预检失败，未运行或冒充
  最终候选 `make golden` 与前端 build 门。
- 唯一执行端：当前 WSL 执行端；同一时间只允许一个写入者。
- 当前任务包：`docs/UI-07-自然创作提交门与叙事真实性闭环执行包.md`
- 阻断证据：受保护 DeepSeek 无业务持久化预检中，G1 为 `not_committed/chat`，G2—G5
  均为合法 ready，G6 为一次 question，H1 为 hypothesis，D1 为 dramatization；但 G3
  Writer 仍在最终可见候选中补造未提供的婆媳微事件，并新增“品牌相信”等现实主张。独立
  Reviewer 的 exact-span claims 同时把“换位思考／彼此尊重”等抽象概念误报为事件；唯一
  块级修复后仍失败。该预检没有连接业务仓储、没有创建 task/run/version。按停止线未形成
  生产候选，未 push、未触发 CI、未部署、未创建本轮生产备份，也未执行生产卡片轮次。
- 阻断后生产复核：部署仓库仍为干净的 `845f632…`，镜像摘要仍为 `sha256:1171b153…`，
  schema `20260801_28`，回环 readiness 为 `ready`、公网为 `200`，备份 timer 为 `active`，
  最新既有备份目录／文件当前分别为 `0700/0600`，远端没有残留 `ui07-preflight.*`。生产
  `845f632…` 的备份脚本本身尚无创建前 `umask 077`；该保证只在本地阻断实现中完成并经
  定向测试覆盖，因未形成候选而没有部署。
- 未证明边界：真实员工采用、真实品牌资料完整、真实发布、平台流量、排名、爆款、GMV、
  销售、企业采用、真实跨租户市场差异、企业 SLA 与 `20/55/44` 全组合稳定支持。
- 唯一下一动作：请主控裁决是否授权只对 **Writer** 一个角色做无持久化、有界模型对比；
  不整体替换 intake/Writer/Reviewer，不并行比较 Reviewer，不形成 fallback。Writer 是首要
  角色，因为其最终可见 G3 候选在脱离 Reviewer 结论时也已独立违反事实边界。

## UI-06 被 UI-07 取代结论（2026-07-28，历史完整保留）

- 里程碑：`UI-06` 自然创作与叙事真实性闭环。
- 状态：`SUPERSEDED → UI-07`。此前 `BLOCKED` 事实保持：`UI-05` 已在前向状态交接中置为
  `SUPERSEDED → UI-06`；这只表示被否决的自报事实标签／单元修复路径由 UI-06 的类型化叙事
  闭环替代，不表示 UI-06 已成功。UI-05 的 G3/G4/G7 失败、候选 A/B、回退与停止线证据
  全部原样保留；UI-06 的唯一生产候选也已被真实 G1 否决。
- 启动现场：本地启动提交
  `4b27f2f17d5ff50621bf156831ca4dd8fc82e40f`，启动时 `origin/main` 为
  `f0261e74421c5818afc337aefc42a5b2350dfdd9`，本地领先的
  `31cec3509216ba79b7de62bc2730306636aad87b` 与 `4b27f2f…` 均为纯文档提交；
  工作树干净。生产当时继续健康运行
  `845f63291ba5060e60f87d1afa5cfc1cdb057e3b`，不合格候选 B 不在生产。
- 第 0 步已完成：只把冻结的 17 条责任合同运行／测试路径以前向修改恢复到 `845f632…`
  的运行内容，没有第 18 条运行差异；没有 reset、rebase、squash、区间 revert、迁移、
  认证、配置或部署改动。恢复与状态交接提交为
  `dc86b9520001a91e6b3d37591baa068f8f8b05ea`，同 `31cec35…`、`4b27f2f…`
  一次推送；恢复基线 CI run `30325920857` 为 `success`，该等价恢复提交未部署。
- 唯一 UI-06 功能候选为
  `e77099f4c8b8d1c135cb4b78708663dcb8b4e403`。它只用 `NarrativeFrame`
  `narrative-frame-v1`、四类 `NarrativeBlock`、独立 `ReviewerObservation` 和最多一次
  完整块级修复；同一 DeepSeek 的 Writer 与 Reviewer 分请求，服务端不采信 Writer 自报
  标签，并做跨度、覆盖、事实、资源和审后摘要对账。没有迁移、第二模型／供应商、关键词
  黑名单、第二修复轮或新平台。
- 候选规模与本地门：`deepseek.py` 从安全基线约 1,905 行收为 1,565 行，适配器测试从约
  1,314 行收为 788 行，独立叙事合同 589 行；五项 mutation proof 均能使测试失败。
  唯一一次完整本地门全部通过：`git diff --check`、ruff、mypy（84 个源文件）、
  Golden `155 passed` 与 OpenAPI、前端 lint/typecheck/interaction/build。产品与内容、
  工程与安全两份开发期有界审查当时均无本地阻断；这些只允许进入生产候选，不是 DeepSeek
  生产语义证明。
- 候选只做一次功能推送，承重 CI run `30328125186`（quality job
  `90177639167`）为 `success`。实现部署前，生产仍为 `845f632…`、schema
  `20260801_28`、readiness 正常。新鲜备份
  `/var/backups/diyu-m5-4/20260728T041650Z-ui06-e77099f4` 通过 checksum，清单为
  41 个激活资产、2 租户、307 个全局历史成功内容版本，并通过隔离数据库恢复、RLS、
  应用 readiness 与对象恢复；正式部署又形成
  `/var/backups/diyu-m5-4/20260728T041731Z-predeploy`。
- 同 SHA 候选曾部署为镜像
  `sha256:a70591063d0ead5971260e5fe70ee9e3afb4d1bef079508fbc9ffb52bf22066b`，
  schema 保持 `20260801_28`，公网与回环均 `ready`。不可拼接真实轮次在第一张 G1
  “今天有点不知道从哪儿开始。”即终止：DeepSeek intake 把普通交流冻结为
  `general_observation` 并创建任务
  `fa45a92e-d3e8-46f4-9b4b-e16b24df74bf`、运行
  `c2924165-360b-4f65-b1ec-214b902a88af`；Writer 随后以“模型返回的类型化成品不完整”
  失败关闭。实际差分为任务／运行／版本 `+1/+1/+0`，而 G1 要求 `0/0/0`；永久 running
  为 0。
- 该失败约 13 秒返回，远短于生产 45 秒超时；API 未返回 429，任务中的模型为
  `deepseek-v4-flash`，因此不是允许重试的网络、429 或超时。G1 没有重跑；G2—G7、H1、
  D1 没有开始，不能拼接或写成通过，也没有可供人工全文审阅的成品。虽然它不是冻结停止线
  中列举的 G3/G4/G7 假绿形态，但普通聊天误建任务本身已违反阻断性 G1；本轮又只允许一个
  生产语义候选，因此同样必须停止，不能借“未列名”形成第二候选。
- 失败任务、失败运行、对应活动事件和已撤销短会话
  `b7e91953-1d52-4df4-a2d7-7391d6477cbb` 已按精确 ID 清理；租户计数从
  任务／运行／版本 `285/358/275` 回到 `284/357/275`，短会话 `1→0`，永久 running
  保持 0。凭据未输出、复制或提交，用户可见输入没有 marker。
- 生产已用既有 `rollback.sh` 在不 downgrade 数据库的前提下回到
  `845f63291ba5060e60f87d1afa5cfc1cdb057e3b`；当前重建镜像摘要为
  `sha256:1171b153cbc709a760caf4a5db1fb14fe00e0bca3ef9c7b79c85f737a3a6bdb9`，
  schema `20260801_28`，公网／回环均 `ready`。既有回退脚本重建了 845 标签，回退前记录
  的旧镜像摘要 `sha256:19ca263…` 已不再留存在本机；这是实际偏差，不把新摘要冒充旧摘要。
  被拒候选镜像 `sha256:a7059106…` 仍保留。
- 两份新备份最初继承既有脚本的 `0644` 转储权限；执行端发现后只将本轮两条精确快照递归
  收紧为 root-only `0700/0600` 并重新通过 checksum。没有借本轮修改部署脚本或其他历史
  快照；该既有默认权限缺口保留为工程审查事实。
- 被拒实现已由普通 forward revert 提交
  `93f824f` 恢复为 `dc86b95…` 的安全运行树；候选实现、CI 和生产失败历史完整保留，
  不 reset、rebase、squash 或删除。
- 唯一执行端：当前 WSL 执行端；同一时间只允许一个写入者。
- 前置与资产边界：UI-04 保持 `CLOSED`；UI-05 Gate A/B/C、首页动效、品牌管理员账户安全、
  三入口验证码、RLS、历史版本等既有能力不重开。激活增量仍为 `0`；运行激活保持 41 条
  （20 知识、21 方法），候选保持
  243 条，目录保持 25/119（21 项默认可见、4 项体型主动启用），既有缺口状态不变。
- 当前任务包：`docs/UI-06-自然创作与叙事真实性闭环执行包.md`
- 未证明边界保持：G2—G7、H1、D1、本候选的人工全文语义、真实员工采用、真实品牌资料完整、
  真实发布、平台流量、排名、爆款、GMV、销售、企业采用、真实跨租户市场差异、企业 SLA
  与 `20/55/44` 全组合稳定支持均未证明。
- 历史外部裁决 `UI06-D1`：**已被 UI-07 的前置 `CreationIntentGate` 裁决取代；历史原文
  保留。**原文为：是否授权用一个经过有界结构化输出实测的新模型／供应商，
  整体替换当前 DeepSeek 在 UI-06 intake、Writer、Reviewer 的单一运行角色后重开里程碑**。
  不允许并行 fallback、随机重跑或继续补 Prompt。仅增加人工成品审核不能修复 G1 在审核前
  已误建任务，故不推荐作为本次单独补丁；若不授权替换，UI-06 保持 `BLOCKED`、生产继续
  `845f632…`。
- 该历史下一动作已由 UI-07 启动裁决取代；不得继续 UI-06 代码施工或把 UI-07 写成 UI-06
  第二候选。

## UI-04 关闭结论（2026-07-27，历史完整保留）

- 里程碑：`UI-04` 全业务接入与生产替换
- 状态：`CLOSED`（关闭日期：2026-07-27（UTC）；主控独立终审 `PASS`）
- 前置：M7-3、UI-01R、UI-02、UI-03 已 `CLOSED`；UI-01 保持 `SUPERSEDED`。UI-01、
  UI-01R 与 UI-02 的历史原型完整保留，不改写为正式 React 复制模板。
- Git 基线：启动时本地与 `origin/main` 均为
  `52371c2c70d5487557b2cc0ec19d85e12f8846a0`，工作树干净。
- UI-03 关闭锚点：最终实现 `05fa32ec1bbcbe3f4e2d972234f226df5eb83279`，最终文档
  `52371c2c70d5487557b2cc0ec19d85e12f8846a0`，唯一远程 CI `30236466903` 为
  `success`。关闭只证明正式 React 产品骨架与内容主链成立，不证明生产默认 UI 已替换。
- 唯一执行端：当前 WSL 执行端；同一时间只允许一个写入者。
- 当前结果：UI-03 正式 React 产品骨架已接入纯文字 DM01、连续系列、素材管理、完整租户管理、
  笛语运维和公共状态页；生产默认 UI 已切换到最终承重实现，并完成有界备份、正式路径冒烟和
  安全回退锚定。
- 产品边界：总部、区域、代理商与门店继续共用 `/content`，差异只来自服务端可信组织、发布
  账号、表达身份和资格；`/tenant-admin` 与 `/ops` 维持独立产品空间和服务端资格边界。
- 能力边界：目录继续由服务端版本化接口提供，默认可见 21 项，4 项体型相关方向仅在本人主动
  启用后出现；实验、未支持、明确不做和三个来源缺口不进入普通选择面板。UI-03 不批量激活
  资产，不补齐 39 项缺口。
- 生产锚点：最终承重实现与运行标签
  `da5391bcd1c13e556bbd7f22da1c081741f2e8b9`；最终承重 CI `30247375239 success`；运行
  镜像摘要 `sha256:53c66e89f0e5d4686343ea82e3930b71be4ae2a48b5ecb49043524f15112da95`；
  schema `20260731_27`；部署前备份
  `/var/backups/diyu-m5-4/20260727T074956Z-predeploy` 校验通过；生产证据
  `/var/lib/diyu-m5-4/ui04-production-review-da5391b.json` 为 `0600 root:root`。
- 生产边界：公网与回环 readiness、`/status`、Nginx 配置和备份定时器均正常；前一可启动
  候选镜像 `diyu-saas:78183ecb58f6cde2bb55dd0456cfea836ca28a6d` 与 UI-04 前已验收
  的 `diyu-saas:af63a62c9169ba94907bf8316059109e9191ed66` 均保留，安全回退不执行
  数据库 downgrade。未修改历史 DIFY。
- 资产结论：激活增量 `0`，运行激活保持 41 条（20 知识、21 方法）；候选保持 243 条，目录
  保持 25/119（21 项默认可见、4 项体型主动启用），39 项缺口、6 项实验、1 项明确不做和
  3 个来源缺口均未改变。
- 当前任务包：`docs/UI-04-全业务接入与生产替换执行包.md`
- 工程收口：本地完整门通过，Golden 为 `164 passed`，前端 lint/typecheck/test/build
  全绿；UI-G03/UI-G04/UI-G07/OPS-G01、系列、素材和两种代表视口均形成正式接缝证据。
  初始候选 CI `30244446597` 虽为绿色，但随后被生产 FORCE RLS 直接失败证据作废；最小共享
  修复后，只有最终 CI `30247375239` 和上述同 SHA 部署作为当前承重证据。
- 审查结论：产品/UI 审查与工程/安全/生产审查各一份，最终均 `PASS`；生产发现的运维候选
  FORCE RLS 上下文缺口已由 schema `20260731_27` 修复，未放宽 RLS、角色或表权限。
- 关闭结论：UI-04 完成门和主控独立终审均已通过。全部既定第一阶段及 UI 产品化里程碑现在
  均为 `CLOSED`，或具有已关闭 successor 的 `SUPERSEDED`；当前没有 `ACTIVE`、`REVIEW`
  或 `BLOCKED` 的既定里程碑。
- 终态对账：M6-3 保持 `SUPERSEDED`，successor 为已关闭的 M7-2B；UI-01 保持
  `SUPERSEDED`，successor 为已关闭的 UI-01R。历史状态流转不改写。
- 未证明边界：不证明真实员工或门店采用、真实发布、平台流量、排名、爆款、GMV、销售、企业
  采用、真实跨租户市场差异、企业 SLA 或 `20/55/44` 全组合稳定支持。
- 唯一下一动作：停止执行，等待用户决定是否启动首期以后新的独立里程碑；F01—F10/F12 继续
  只按各自真实触发条件推进，不自动启动。

## UI-03 关闭结论（2026-07-26，历史完整保留）

- 里程碑：`UI-03` 正式 React 产品骨架与内容主链
- 状态：`CLOSED`（主控独立终审通过）
- 关闭范围：正式 React 公共首页与 A 动效、三入口隔离壳、统一创作端、服务端五轴目录和正式
  内容 V1→V2→V1、复制导出、可信默认目标、桌面与移动成立。
- 关闭限制：不证明生产默认 UI 已替换，也不证明完整 DM01、系列、素材管理、租户管理、运维、
  真实用户采用、真实发布、流量或销售已经完成；这些首期产品接缝由 UI-04 承接。
- 最终实现：`05fa32ec1bbcbe3f4e2d972234f226df5eb83279`；最终文档：
  `52371c2c70d5487557b2cc0ec19d85e12f8846a0`；唯一 CI：`30236466903 success`。

## UI-02 关闭结论（2026-07-26，历史完整保留）

- 里程碑：`UI-02` 角色任务架构、能力映射与全链路高保真 HTML 原型
- 状态：`CLOSED`（主控按有限范围裁决通过）
- 关闭范围：只证明三套隔离产品空间、四条连续静态旅程、纯文字 DM01、25 项精简 V1 能力
  消费者映射和 UI-G/CAP-G 产品合同成立；不证明正式 React、正式 API 接入、真实权限运行、
  生产默认 UI 替换或真实用户采用。
- 历史保留：全部离线 HTML、评审壳与验证记录继续作为产品合同证据，不是 UI-03 的逐页复制
  模板。
- 后继：UI-03 承接正式 React 骨架与内容主链但不切换生产默认 UI；UI-04 才接入纯文字 DM01、
  系列、素材管理、完整租户管理、运维和生产替换。

## UI-01R 关闭结论（2026-07-26，历史完整保留）

- 里程碑：`UI-01R` 产品叙事、资产能力总账与核心体验原型重构
- 状态：`CLOSED`（创始人已完成产品策略与方向裁决）
- 关闭范围：只表示产品策略探索、现有资产盘点和核心方向裁决完成；243/119 只读投影、三套
  动效候选、六张代表页与独立评审壳继续是产品讨论证据，不是正式 React 实现或逐页复制模板。
- 最终裁决：首页采用 A“种子找到声音”，B/C 保留为历史候选；正式 VI SVG 继续是唯一 Logo
  真源，首页文字仍是产品候选。
- 历史保留：UI-01 的 19 页 v0.1 与 UI-01R 的全部候选文件均原样保留。UI-01 继续为
  `SUPERSEDED`，不把其页面覆盖盘点改写为通过结论。
- 后继：UI-02 承接角色任务架构、能力映射和全链路高保真 HTML；UI-01R 不证明正式系统已改造、
  生产 UI 已替换或真实用户采用。

## UI-01 取代结论（2026-07-26，历史完整保留）

- 里程碑：`UI-01` 全站产品化 HTML 原型与首页品牌动效
- 状态：`SUPERSEDED`；successor 为 `UI-01R`。这不是关闭或通过。
- 历史交付：`docs/前端UI架构/产品化HTML原型_v0.1/` 的 19 张静态页面、评审导航、共享样式
  与约 `7.2s` 首页动效，继续只作为页面覆盖盘点与历史反例。
- 取代理由：创始人产品审查确认其首页缺少叙事，19 页按功能机械铺开，主页面仍有说明书化和
  内部过程暴露，产品模式与评审模式混用，不能直接作为 React 工程化输入。

## M7-3 关闭结论（2026-07-26，历史完整保留）

- 里程碑：`M7-3` 第一阶段整体验收与停止
- 状态：`CLOSED`（2026-07-26 主控已完成产品级独立终审并裁决 `PASS`）
- 前置：M7-1、M7-2A、M7-2B 均已 `CLOSED`；M6-3 保持 `SUPERSEDED`，不恢复候选、
  不重跑 Q1—Q8。
- Git 基线：启动时本地、`origin/main` 与生产部署仓库均为
  `1e4423519ec74e69d062f3eb6809c06901921590`，状态检查点为 `8f82864`；首轮整体验收承重实现、
  唯一 CI 与部署 SHA 为 `9f987e3a035563e9cf3eb8f676d27c55e0688e52`。
- 本轮返工基线：主控终审退回时本地与 `origin/main` 为
  `5d41b2c81bf083d2f8cc53a20d6f23a9a6b9786b`；本轮承重实现、唯一 CI 与部署 SHA 为
  `af63a62c9169ba94907bf8316059109e9191ed66`。
- 生产锚点：运行镜像摘要
  `sha256:3d9e2847f5c2ba482200be2a66658f859a60b4e58eefa1ac922ac8418837b7cb`，
  schema `20260730_24`，唯一 CI run `30200960337` 对应上述 SHA 且为 `success`；回环与公网
  readiness 均为 `ready`。部署前备份
  `/var/backups/diyu-m5-4/20260726T115643Z-predeploy` 的校验全部通过；上一运行镜像
  `9f987e3…` 及摘要 `sha256:a8fdc56d…` 保留为回退锚点，不执行 schema downgrade。
- 唯一执行端：当前 WSL 执行端；同一时间只允许一个写入者。
- 当前任务包：`docs/M7-3-第一阶段整体验收与停止执行包.md`
- 验收结果：内容生产与 DM01 两条关闭路径共同成立；三入口在服务端失败关闭。Chrome 148
  以 `1440×900` / `390×844` 完成 `131` 项生产浏览器断言，演示索引可读两个身份、六篇源
  成品和六份平台成品，账号历史版本、复制/导出同一投影、移动双工作面和跨入口恢复页均成立；
  三个短期会话全部撤销且存活数为 `0`。DM01 复用 M7-1 正式租户用户闭环证据并新鲜核对生产
  V1、`dm01-rule-compiler-v1`、`provider_usage=null`、任务/运行/版本 `1/1/1`；已退出的
  M7-1 验收身份未重启、未替建。
- 接缝修复：正式 `/content` / `/display` 以服务端 bootstrap 为权威，开发/测试壳才读取通用
  fallback；平台方向为后续新运行补齐来源、适用范围、时间、新鲜度、替代关系与维护责任并冻结
  到既有回执，历史 H3 只保留诚实的 `legacy_version_reference`；9 条 `unsupported` 去向由
  已关闭 M7-2B 改绑 F10，能力状态和可见性不变。无迁移、未重生成或改写 M7-2B 成品。
- 终审接缝：正式 `/content` bootstrap 显式返回服务端已解析的 `current_target`，前端以
  `current_target ?? targets[0] ?? "douyin_video"` 初始化；小红书身份、默认形式及直接提交
  目标一致，且目标列表首项仍为抖音。正式用户页面匿名访问按入口 `303`，错误入口资格返回
  带恢复动作的人话 HTML `403`，`/api/v1/*` 继续保持 JSON `401/403`。
- 生产反证：两个演示账号各自的 declared 控制组织、ContentRole、五段画像 V1、两条三篇系列
  与冻结前情 `0/1/2` 均正确；H3 三平台父链精确；六张承重表保持 `ENABLE + FORCE RLS`，
  错误租户读取为 `0`，失败运行关联版本和遗留 running 均为 `0`。唯一一条明确标记的
  synthetic 未满足需求经正式用户 API → 运维受控函数分类回告 → 本人回读；其他自然人不可读，
  目录文件、知识、方法激活、画像、私人偏好、系列、商品及内容任务/运行/版本保护快照前后不变。
- 关闭范围：M7-3 `CLOSED` 只证明第一阶段软件闭环、生产部署、两条业务路径、入口恢复、
  隔离边界和有界产品验收成立；不证明真实员工采用、真实商品采用、真实门店现场执行、真实
  发布、平台流量、排名、爆款、GMV、销售、企业采用、真实跨租户市场差异、企业 SLA 或
  `20/55/44` 全组合稳定支持。
- 唯一下一动作：与主控讨论“用户界面产品化重构”；当前只进入专项讨论，不启动 UI 施工，
  不预设新里程碑。

## M7-2B 关闭结论（2026-07-26，历史完整保留）

- 状态：`CLOSED`。主控已独立完成产品级终验并裁决通过；执行侧不再返工或重跑六篇内容。
- 关闭范围：正式生产路径下的连续内容、自然修改、历史版本、系列前情、多平台重编译及安全
  入口成立。
- 限制：不证明真实员工采用、真实商品采用、真实发布、平台流量、排名、爆款、GMV、销售、
  多个真实租户的市场差异或企业 SLA。
- M7-2B 启动基线：本地、`origin/main` 与生产镜像均为
  `e1579783af31ca1beb05d3eef4ecec054087383b`，生产 schema 为 `20260730_24`；上一轮
  `REVIEW` 的六篇、旧版本、H2/H3、用户可见投影、RLS、DeepSeek 与一次性链接事务失效证据
  全部保留。本轮不回退生产、不重建六篇、不删除旧版本。
- 唯一执行端：当前 WSL 执行端；同一时间只允许一个写入者。
- 任务包：`docs/M7-2B-真实品牌内容协作试点执行包.md`
- 业务裁决：旧“等待真实人物、真实商品和真实画像”前置已被取代。M7-2B 使用明确标记的
  `synthetic_business_fixture / 等深模拟业务资料`，通过正式生产代码、部署、PostgreSQL、
  FORCE RLS、认证、API 与真实 DeepSeek 验收软件能力；真实资料入驻是软件可用后的独立动作。
- 关闭交付：两个实质不同的演示表达身份及五段画像 V1；两个连续系列各三篇。H1 当前 V3、
  H2 当前 V13、H3 当前 V6，S1 当前 V2、S2 当前 V4、S3 当前 V7；全部旧版本继续可读。
  H2/S2 冻结一篇前情，H3/S3 冻结两篇；S2/H2/H3 分别通过 P1/P2/P5；H3 的
  “幽默玩梗→克制冷幽默”透明转译、`多图合集` 与三张静态画面一致。总部与门店各有抖音、
  小红书、微信视频号当前版，共六份，均由 `deepseek-v4-flash` 生成或重编译；总部当前三平台
  以 H3 V6 为唯一源：抖音为 H3 V6，小红书
  `滑完四张图，看中心与侧边怎么改变颜色主次` V2，微信视频号
  `亮黄短袖站中间，白色连衣裙在旁边｜先看这一组` V2。两个子任务的
  `parent_version_id` 均精确指向 H3 V6，旧平台任务和版本继续保留。
- 用户入口：`https://diyuai.cc/tenant-admin?section=demo`。未登录先进入租户管理员登录并在成功
  后返回该索引；页面从正式对象实时只读投影两个身份、画像、六篇全部版本、系列前情数量和六份
  平台当前版。管理员可为演示操作者生成一次性安全进入链接；无共享密码、认证旁路或平台连接。
- 点名审查：H2 V13 既有通过结论未重做。S2 V4 保留 P1 条件判断，手机先固定，创作者逐件
  持衣各录一段并按本次目标回看；台词不再承诺画面没有完成的“两件商品同框换位”，也没有
  顾客、家庭演员、桌子或纸笔。S3 V7 只用一名创作者、一部固定且全程不移动的手机、空墙、
  呼吸和自然停顿，并以假设语气从柯桥门店人物位置观察“对方尚未表示需要时的浏览节奏”；
  没有真实关店事件、顾客、商品、励志化或品牌宣言。H3 V6 及刷新后的三平台均让两件完整商品
  在同平面同距离下以等权、居中、侧边形成主次；小红书是一套四图滑读链，视频号以结果先行
  的连续视频组织，标题、开头、结构和媒体组织与抖音实质不同。审查 A/B 仍各一份，本轮只
  更新这三组受影响结论。
- 用户可见投影：新生成、当前版、历史版和演示验收页均通过同一服务端投影移除
  `账号观察/受众获得/账号关系/演示商品锚点/可见造型命题/画面成立条件` 等编译脚手架；
  页面展示自然概要、标题、完整正文/口播、制作说明、发布辅助和 AIGC 提醒。复制与导出只消费
  同一投影，并追加同一 AIGC 披露，不建第二编译器或第二张内容表。
- 一次性链接：正式与 maintenance 配置的四个 `/activate/` location 均位置级关闭
  access/error token 日志并返回 `Referrer-Policy: no-referrer`；正式 HTTP 激活入口固定
  `303` 到 HTTPS 首页，不再携带 `$request_uri`。Uvicorn 访问日志关闭，应用请求日志只记录
  `/activate/:token`；新链接在同事务失效同一用户旧链接，成功使用在同事务失效其余链接并
  撤销旧会话。生产 A/B 反证继续成立；本轮明显测试夹具假 token 的 access/error/app 三类
  日志原文命中数为 `0/0/0`，HTTP 与 HTTPS 均返回 `no-referrer`，且没有读取或输出真实 token。
  历史访问日志不删除，既存未使用链接已全部失效。
- 工程证据：定向测试通过；最终一次完整本地门为 `git diff --check`、Ruff、mypy、Golden、
  后端 `155 passed`、前端 lint/typecheck/build/interaction test 全绿。承重代码 SHA 为
  `ca4f85c454217720ebc3328789a4c8d470ed9c44`；包含全部承重代码与收口证据的唯一远程 CI
  提交为 `7f920d491d198b2f9a4ef7d9565f9c7af686d300`，run `30194854609`，
  `deterministic-quality-gate / quality` 在 `1m17s` 内完成且结论 `success`。此后的最终
  状态同步只改权威文档并以 `[skip ci]` 提交，不触发第二次 CI。
- 生产证据：schema 为 `20260730_24`；承重代码 SHA
  `ca4f85c454217720ebc3328789a4c8d470ed9c44` 已通过正式生产对象、正式 API、
  PostgreSQL/FORCE RLS 与真实 `deepseek-v4-flash` 运行，镜像摘要为
  `sha256:64c0ec711e9daaa9d5d585578849ae64dc903f4afe0bb40de6034147d283b266`。
  唯一 CI 与最终生产运行标签均为
  `7f920d491d198b2f9a4ef7d9565f9c7af686d300`；该提交在承重代码之上只增加权威证据文档，
  运行镜像复用同一不可变摘要，未重建、未迁移。
  唯一本轮部署前备份为
  `/var/backups/diyu-m5-4/20260726T081419Z-predeploy`，schema `20260730_24`、成功内容版本
  `275`、完整链 `247`、对象 `1`，`SHA256SUMS` 全部通过；前一健康镜像 `e157978…` 保留，
  回退不做 schema downgrade。回环与公网 readiness 均为 `ready`，`nginx -t` 通过，历史
  DIFY 未改动。
- 生产数据反证：演示根账号/画像/商品为 `2/2/3`；两个系列各三篇，前情计数均为 `0/1/2`；
  六篇源成品和六份平台当前版保留。S2 V4、S3 V7、H3 V6 与总部小红书/视频号 V2 的对应
  GenerationRun 均为 `succeeded / deepseek-v4-flash`；本轮小红书失败修订 `1` 个、关联版本
  `0`。演示索引由正式租户管理 API 返回 `ready`，H3 V6 源/父关系精确可读。内容、画像、
  商品、系列、私人偏好六张承重表仍为 `ENABLE + FORCE RLS`，DM01 任务/运行/版本为 `1/1/1`；
  无自动回写和既有人话投影只做必要不回退核对。
- 未证明：真实员工使用、真实商品采用、真实门店经营事实、真实发布、平台流量/排名、爆款、
  GMV/销售、企业采用、多个真实租户之间的市场差异化、企业 SLA 与 20/55/44 全组合稳定支持。
- 关闭时剩余验收：无。本轮四项产品与安全缺口、唯一 CI、备份、同代码镜像的最终状态 SHA
  标签、生产 readiness 与稳定验收证据均已收口；最终状态 SHA 的不可变值记录在生产
  `/var/lib/diyu-m5-4/m7-2b-review-final.json`（`0600`）。
- 主控终验结果：`PASS`；M7-2B 已由本次状态承接正式关闭，后继为 M7-3。

## M7-2A 关闭结论（2026-07-25，历史完整保留）

- 里程碑：`M7-2A` 内容表达目录、账号表达画像与用户控制面
- 状态：`CLOSED`（主控 2026-07-25 终审关闭。本里程碑期间曾两次由 `REVIEW` 恢复为 `ACTIVE`：
  一次单一有界修复、一次主控终审极小返工，两次均已收口。全程未启动 M7-2B）
- **`CLOSED` 只证明 M7-2A 的软件控制面成立**：版本化五轴目录、账号五段表达画像与控制组织判权、
  私人创作偏好、可选创作方向与透明转译、本次素材选择、冷启动机会与轻量计划、未满足需求候选，
  以及任务冻结与重放。**它不证明**真实 DeepSeek 下的内容质量、真实账号画像已由有权主体确认、
  真实发布、平台流量、企业采用或销售效果——这些全部转入 M7-2B 及其后。
- 起点：M7-1 已 `CLOSED`；施工基线 `07fd4b8a54c1ad96fc237b97f18cff0cdb101847`。
- 唯一执行端：当前 WSL 执行端；同一时间只允许一个写入者
- 当前任务包：`docs/M7-2A-内容表达目录账号画像与用户控制面执行包.md`
- 边界：本里程碑只交付最小内容控制面（版本化五轴目录、实际启用发布账号的五段人话画像、
  私人创作偏好、可选创作方向面板与透明品牌转译、本次合法素材选择、冷启动内容机会与轻量
  计划、未满足需求候选）。未启动 M7-2B，未做真实连续系列、真实商品 P1/P2/P5、三平台重
  编译验证、平台流量或内容市场结果。
- Git 基线：首轮实现提交 `c0f28732fe85e35ff28e35911d09144fb97b94a5`（CI run `30159843299`），
  单一有界修复轮实现提交 `6710072b7d3a610c263977cb3ecaf8fd385e349a`（CI run `30162932954`），
  主控终审极小返工实现提交 `436ac8923e45263a687ee8d2ce0b758371b1fb08`（CI run `30165283424`）。
  三轮各只触发一次 CI，均绿。历史提交全部保留，未 reset、rebase、squash 或改写 M6-3/M7-1 历史。
- 当前生产：运行镜像 `diyu-saas:436ac8923e45263a687ee8d2ce0b758371b1fb08`，数据库 schema
  仍为 `20260727_21`（终审返工**未新增迁移**）；本机与公网 readiness 均 `200`，公网首页 `303`。
  指定上一回退目标为 `6710072b7d3a610c263977cb3ecaf8fd385e349a`（上一在产版本，schema 相同，
  回退无需 downgrade）。
- **日期口径（唯一，不并存）**：M7-2A 三轮（首轮实现、单一有界修复、主控终审极小返工）与 M7-1
  关闭均发生在 **2026-07-25**（以执行端与生产主机 `date -u` 为准，时区 **UTC**）。文档中若还
  出现别的日期即为笔误。`20260726_20` / `20260727_21` 是**迁移标识符不是日期**：它们已在生产
  落库、不可改名，沿用"次日编号"的既有惯例，不代表任何一轮发生在 7-26 或 7-27。
- 迁移 `20260726_20`（expand-only，生产 migrator 既非 superuser 也无 `BYPASSRLS`）：新增
  `account_expression_profile_versions`、`user_creation_preferences`、`content_plans`、
  `unmet_capability_requests` 四表（全部 `ENABLE + FORCE` 行级安全，私人偏好额外要求可信
  `app.user_id`），以及 `content_accounts.control_organization_id` /
  `current_expression_profile_id`、`auth_grants.can_maintain_expression_profile`、
  `material_assets.reference_note`、`business_tasks.content_context_snapshot` 五列。两处回填
  均逐租户 `set_config('app.tenant_id')`：控制组织只在**唯一证据**（恰好一条
  `publishing_account.created` 事件且操作者组织唯一）成立时回填，其余保持 `NULL`；历史任务由
  既有 `generation_runs.input_receipt` 无损回填 legacy 快照。生产实测：`271/271` 条历史任务
  全部有快照、`0` 条为空、`0` 条冒充画像版本；真实品牌账号回填为
  `笛语服饰品牌官方账号 → 笛语服饰管理组织`。**该回填已在 `20260727_21` 中降级为 `inferred`
  并因此不再授予任何维护资格**（见下）。
- 迁移 `20260727_21`（expand-only，单一有界修复轮）：新增
  `content_accounts.control_organization_source`（`unset / inferred / declared`，逐租户
  `set_config` 把既有非空控制组织标为 `inferred`）；新增
  `account_expression_profile_versions UNIQUE (tenant_id, account_id, id)` 与
  `content_accounts (tenant_id, id, current_expression_profile_id)` 复合外键，使"当前画像指针
  指向别的账号的画像"在数据库层存不进去；新增 `ops_unmet_capability_requests()` 与
  `ops_classify_unmet_capability_request()` 两个 `SECURITY DEFINER` 受控函数（与既有
  `ops_runtime_summary` 同一跨租户边界，`REVOKE ALL FROM PUBLIC` 后只授 `diyu_app`）。
- 归属纪律（本轮硬化）：**由创建事件推断出的控制组织不是证据，不授予画像维护资格。**
  只有新建账号时明确指定，或该租户有权主体经
  `POST /api/v1/tenant-management/publishing-accounts/{id}/control-organization` 一次声明，
  才成立；声明留痕复用既有 `activity_events`（`publishing_account.control_organization_declared`），
  不新增审批流。新建账号不再默认取创建者所属组织。生产核对：真实
  `笛语服饰品牌官方账号` 现为 `inferred`，因此**当前没有任何真实主体可以维护它的画像**，
  等待该租户有权主体明确声明；演示租户四个账号由 seed 明确声明为 `declared`。
- 目录来源诚实对账（真源 `config/content_expression/capability-inventory-v1.jsonl`）：
  风格 `20/20`、题材 `55/55`、**体裁 `41/44`**，合计有定义 `116`、声明目标 `119`、缺 `3`。
  缺口登记为 `CAT-SOURCE-GAP-GENRE-001/002/003`（`gap_type=source_gap`，去向 F10），不进入
  前端。**不得**宣称“119 项全部登记、全部支持或全部验证”。运行时精简 V1 共 `25` 条，全部为
  `verified/composable`；默认可见 `21` 条，`4` 条体型相关项只有本人主动启用后才出现。
- 有界审查：两份独立审查（产品语义/UI；权限/迁移/隔离）。前者初判 `FAIL`（修订自然提示会
  让前端崩溃、保存默认会清空本人偏好说明、已保存默认静默生效等），后者 `PASS_WITH_NOTES`
  且未找到任何可利用的越权路径，但指出 `control_organization_id` 当时没有生产写入面。全部
  实质问题已在同一实现提交内修复并复验，逐条记录在 M7-2A 执行包 §八。
- F11 有界清理（部署前）：按保护清单（当前运行 SHA、指定回退目标、`MILESTONE.md` 明确保留的
  `3828073` / `58a52f1` / `3bcae817`）删除 102 个历史 `diyu-saas` 镜像并回收未使用构建缓存，
  镜像标签 `107 → 5`，根分区 `89%`（剩 `4.2G`）→ `76%`（剩 `9.2G`）。19 个容器全部照常运行，
  历史 DIFY 与其他应用未触碰，备份目录仍为 `4.1M`；未执行无界 `docker system prune -a`。
- 有界回退检查：`rollback.sh 1241cbd…` 后本机/公网 readiness `200`、公网首页 `303`、匿名 API
  `401`，**schema 保持 `20260726_20`，未执行 downgrade、未重跑旧迁移**；用该回退版本自身代码
  路径读出生产已有内容（`version=1`、`1459` 字符），最终版本读同一条内容结果一致并额外带出
  透明转译。随后切回 `c0f2873…`，内容 `271/271/185`、陈列 `1/1/1` 计数不变。
- 验证证据（首轮）：本地 Ruff、mypy、OpenAPI/Golden、后端 `119 passed`、前端
  lint/typecheck/build 全绿；生产六个新端点匿名访问全部 `401`，四张新表 RLS 均 `true/true`，
  系统激活资产恒 `41`，M7-1 陈列侧 `1/1/1` 且无空快照。
- 单一有界修复轮（2026-07-25，详见执行包 §十）一次关闭五组缺口：画像权限与归属（推断不授权、
  一次声明、同事务判权与写入、当前画像三重匹配 + 数据库约束、同名幂等含控制组织）；任务冻结
  （快照冻结 ContentRole 名称与表达边界，V2 重放冻结角色而非当前角色）；私人偏好
  （`collaboration_note` 入模型不入租户记录、真正的临时无偏好会话请求头、每轴三态且空选择不
  清空已保存默认）；用户闭环（计划「用这条开始」、缺说明原件不可勾选并就地补写、身份抽屉进入
  既有画像卡、笛语运维最小分类与回告入口）；自然语言透明转译（六条声明别名精确命中时复用
  `restrained_variant`，无法映射的原样保留，硬冲突只给一句自然建议）。
- 验证证据（修复轮）：`git diff --check`、`make lint`、`make typecheck`、`make golden`、
  `make test`（`132 passed`）、前端 `lint / typecheck / build / test` 全绿，OpenAPI 由实际
  路由重新生成；新增 **最小前端交互验证**（`frontend/test/interaction.test.tsx`，jsdom 中真实
  挂载工作台并逐步点击 8 项行为），只增加 `esbuild` / `jsdom` / `@types/node` 三个开发依赖，
  不建设测试平台。生产复核：schema `20260727_21`、readiness `200/200`、首页 `303`、新端点匿名
  `401`、四张表 RLS 仍 `true/true`、内容 `271/271/185`、陈列 `1/1/1`、空快照 `0/271`、
  系统激活资产 `41`；部署前由 `deploy.sh` 执行既有有界备份。
- 主控终审极小返工（2026-07-25，详见执行包 §十一）只关闭五处具体缺口，**未新增迁移、未改数据库
  结构**：① 同一轴优先级写死为 **本次明确选择 > 本次自然语言中未被否定的精确标签/别名 > 已保存
  默认**，保存默认不得压过本次自然要求；② 为已声明标签/别名增加最小否定语义（`不要 / 不想 /
  别 / 不用 / 取消` 五个精确词，仅限紧邻 4 字符且不跨句读；正向应用仍只限带 `restrained_variant`
  或体型相关的条目，拒绝可作用于任何已声明条目但只会拿掉、不会引入），被拒绝的条目若正是该轴
  默认则本次不生效且**不修改已保存默认**；③ 修改接口读取 `X-Diyu-Preference-Session`，同目标
  修改继续只重放快照，跨目标改编显式传 `use_personal_preferences=false`，不变式落为常量
  `_REVISION_MAY_READ_PREFERENCE=False`；④ 私人协作说明只控制协作与表达取舍，成品中不得引用、
  复述或解释其原文（写进既有适配器边界的两处指令，不新增审查层/重试层/第二模型）；⑤ 修复
  `frontend/test/run.mjs` 在 Node 20 与 Node 22 的 `navigator` 安装兼容（改用
  `Object.defineProperty`；Node 22/24 的 `navigator` 是只读取值器，直接赋值会抛 `TypeError`），
  并订正 `contracts.py` 中 `control_organization_id` 的过期注释。
- 验证证据（终审返工轮）：`git diff --check`、`make lint`、`make typecheck`、`make golden`、
  `make test`（`136 passed`）、前端 `lint / typecheck / build / test` 全绿；前端交互验证在
  **Node 20 与 Node 22 上分别实跑**通过（修复前 Node 22 崩溃）。两条关键反证（默认不得压过本次
  自然要求、跨目标改编不得重读私人偏好）均当场把代码改回旧行为验证过**会失败**，不是自审假绿。
  生产复核（部署 `436ac89…` 后）：schema 仍 `20260727_21`、本机/公网 readiness `200`、首页
  `303`、`/api/v1/tasks/{id}/revisions` 与租户管理端点匿名 `401`；四张表 RLS 仍 `true/true`；
  内容任务/运行/版本 `271/271/185`、内容空快照 `0/271`；陈列任务/运行/版本 `1/1/1`、
  运行成功/失败 `1/0`、空快照 `0`；系统激活资产 `41`、缺口候选 `0`；
  部署前由 `deploy.sh` 执行既有有界备份（`20260725T161837Z-predeploy`，备份共 7 份），
  镜像 8 个、容器 19 个、根分区 `78%`（剩 `8.3G`）。**真实账号权限复核：
  `笛语服饰品牌官方账号` 仍为 `inferred`，未因本轮获得任何扩大权限。**
- **未证明项（硬约束，不得被后续文档改写）**：
  1. **有界 DeepSeek 真实内容冒烟未执行**。它需要一个正式登录会话：真实品牌管理员口令属
     founder 本人、按协作基线不由执行侧代持；而为合成演示租户临时开通一次性登录的动作被
     执行环境权限闸拦下。执行侧**未绕过**该拦截，也未创建任何生产登录身份——`ops-run` 目录
     为空、`m7-2a*` 用户名凭据数 `0`、有效激活令牌 `0`。因此真实模型路径在生产上未验证。
  2. 真实笛语服饰账号的五段画像**仍未由有权主体保存**；执行侧未代用户激活，两轮均未向该租户
     写入任何内容。这是 M7-2B 的启动前条件，不构成 M7-2A 软件能力阻断。修复轮之后它还多了
     一个前置：该账号的控制组织必须先由租户有权主体**明确声明**（当前是 `inferred`）。
  3. 内容质量、真实发布、平台流量、企业采用与销售结果均未证明。
  4. 修复轮**未调用真实 DeepSeek**、未创建临时生产验收身份、未重跑 M6-3 Q1—Q8；真实模型调用
     正式转入 M7-2B 首个真实账号任务。
- 关闭方式：主控终审通过后只做了一次**纯文档最终收口**（统一陈列计数口径、明确私人协作说明
  在真实模型下属提示级约束、为已被取代的旧控制组织口径加"已被后续修复轮取代"标注、统一日期
  口径、置为 `CLOSED`）。该收口**未修改代码、数据库、OpenAPI、部署配置或生产环境，未触发 CI**，
  因此在产 SHA 与 schema 仍是 `436ac89…` / `20260727_21`。
- 唯一下一动作：由主控开启 `M7-2B` 真实品牌内容协作试点。本轮不启动。

## M7-1 关闭结论（2026-07-25，历史完整保留）

- 里程碑：`M7-1` 真实门店 DM01 最小闭环
- 状态：`CLOSED`（主控 2026-07-25 终审关闭；最终安全收尾完成后置入）
- 起点：M6-3 未通过，已由主控置为 `SUPERSEDED`；其 successor 为
  `M7-2B`“真实品牌内容协作试点”。M7-1 与内容生产解耦后开始。
- 执行端：当时 WSL 执行端
- 任务包：`docs/M7-1-真实门店DM01最小闭环执行包.md`
- Git 基线：M7-1 原运行实现提交为
  `3828073977bff935dfb96f8ba58a1dad2350577f`；语义纠偏为 `3bf07d3`，假操作者与快照收口为
  `b85a8e6`+`1241cbd`，历史任务失败关闭为 `ac6e03c3b3a7e8fd8a768884746d0cb8a1d0cd59`
  （本轮唯一实现提交，也是当前生产运行 SHA）。历史提交全部保留，未重置、未删除、未改写；
  本轮唯一的数据删除是主控明确要求清理的旧错误验收任务子树。提交链完整保留 BLOCKED 状态提交
  `8086a20120d637c91a438e70becfbbc59f633c3f`、失败候选实现
  `3bcae817750abb01a04e9d5410fd4334c91933cf`，已由
  `d9fcb770aab8f3dc73b10ae54745940e385f11c1` 普通回退；不得 reset、rebase、squash
  或改写这段历史。
- 当前生产：运行镜像为
  `diyu-saas:ac6e03c3b3a7e8fd8a768884746d0cb8a1d0cd59`，数据库 schema `20260725_19`；
  本机与公网 readiness 均 `200`，公网首页 `303`。原 `3828073`、`58a52f1` 镜像和既有回退路径
  继续保留。本部署只承载 M7-1，不恢复任何 M6-3 候选。
- **撤销**此前“`e0a7efd225fcd48d6af357f3889c504a2f537337` 是合格业务回退桥接”的表述：该
  提交是 docs-only（相对 `3bf07d3` 的 `src/`、`alembic/`、compose、config、frontend 差异
  为空），其运行代码仍是第一轮语义纠偏版本，带有假操作者与未冻结任务快照两项已被裁决取代
  的缺陷，不构成合格的业务回退目标。
- 指定回退目标：`1241cbd04aee8d3e28637d13323ae17d657c7082`（上一在产版本）。已在 schema
  `20260725_19` 上完成应用回退演练：`rollback.sh` 切换后本机与公网 readiness 均 `200`，
  生产新 V1 经该版本自身代码路径读出（`version=1`、`1363` 字符、`30=18+12` 守恒为真），
  schema 未变、未重跑旧迁移、未恢复旧错误任务；随后 `deploy.sh` 切回最终 SHA 并再次全绿。
- 前一轮关于“当前执行环境没有 SSH 私钥、无法登录 ECS”的记载**不成立**：该判断来自被沙箱
  拒绝读取的 `~/.ssh` 目录列表，实际 `/home/faye/.ssh/diyu-hk.pem` 一直存在。本轮已按既有
  授权部署路径完成生产部署与验收。
- 正式产品入口：`https://diyuai.cc`
- 产品语义裁决（2026-07-25，取代原确认流程）：系统只根据租户、品牌、账号、用户输入和
  可用知识交付**参考建议**，不自动执行陈列，也不承担监管责任。不需要用户授权系统
  “给建议”，不需要确认人、确认日期、系统代录人和复核人，不设“业务指定／系统建议”
  二选一，也不要求用户实际执行后回复才承认 V1 成立。账号与数据访问权限是一次性的系统
  资格，不是每次生成任务的授权流程；后台自动记录真实登录操作者、作用域、输入、版本和
  时间，但不展示成用户任务负担。
- 已撤销的无来源表述：`阿丹已现场确认`、`现场差异为无`、`商品当前在店且可售`、
  `2026-07-25 为现场确认日期`、`007+006 与 005 已被确认为业务指定`，以及
  `confirmed_by` / `confirmed_at` / `system_submitted_by` 等业务确认语义。它们没有可靠
  用户来源，已按本次裁决取代，不得再作为真实事实、授权证明或验收依据。
- 当前输入真值：笛语服饰租户和品牌存在；柯桥店资料统一定义为“用户提供的本次任务快照，
  用于生成参考方案；其中现场条件和库存仍未证明为真实现场事实”。`007+006` 是系统形成的
  右侧主焦点建议，`005` 是较弱回应建议；只有用户在自然输入中写明“必须、固定、不可
  改变”时才在该次任务内成为硬要求。该快照不是 ERP 核验、长期商品主档或门店已经执行的
  证明。
- 当前代码真值：施工起点的 `dm01-rule-compiler-v1` 曾硬编码六个 `ZX-*` 合成商品、
  A/B/C 固定布局和唯一马甲反馈。本轮保持确定性执行器与结构合同，改为读取门店可复用结构、
  本次任务输入和商品轻量陈列属性；真实品牌路径不读取 `ZX-*`，且本次商品不写入内容侧
  长期商品主档。未建设通用陈列优化器或 LLM 陈列路径。
- 语义纠偏实现（第一轮，`3bf07d3`）：迁移 `20260725_18` 为 `display_stores` 增加
  `current_task_input`；`confirmed_dm01.py`→`dm01_task_input.py`、
  `config/confirmed_inputs/`→`config/task_inputs/`；取消 `enforce_exact` 旧快照比对与
  “已有版本即短路”；焦点建议不可用时由确定性规则重新选择主焦点；
  `parse_hard_requirements` 只从本次自然输入识别“必须/务必/固定/不可改变”类硬要求；
  可见正文改为“{门店}墙面挂杆参考执行方案”，间距口径改为“侧挂保持正常可抽取间距，
  主正挂两侧各留约一个衣架宽的视觉边界”。
- 假操作者与快照收口（第二轮，`b85a8e6`+`1241cbd`）：
  - 用户可见方案删除“本次操作人 X”；真实登录操作者只落在后台 `input_receipt.operator`。
  - 维护命令不再按姓名挑选租户管理员、不再伪造 `DisplayScope`、不再代生成任务与 V1；
    `dm01_task_input.py`→`dm01_store_seed.py`、`activate_dm01_task_input.py`→
    `seed_dm01_store.py`、compose 服务 `activate-dm01`→`dm01-store-seed`。它现在只是幂等的
    “门店结构与下一次任务默认种子”配置，生产两次运行输出一致且 `tasks_created=0`。
  - 迁移 `20260725_19` 为 `display_tasks` 增加 `context_snapshot`：创建 V1 时冻结本次表达、
    商品轻量属性、挂杆结构与版本；V2 只读本任务快照，不再重读门店当前值（本地反证测试
    `test_a_revision_replays_its_own_task_snapshot_not_the_current_store_seed`）。
  - 可见文案收口：“已确认的舒适容量”→“当前舒适容量”、“业务指定主焦点”→“主焦点”、
    “本次已确认商品或数量”→“本次清单商品或数量”，并新增失败路径断言，覆盖 API `422`、
    页面、追问与成品四类界面上的九个禁用词。
  - 迁移改为 expand-only：`20260725_18` 不再原地删除旧 `confirmation` /
    `inventory_snapshot`，只新增并回填；且因生产 migrator 既非 superuser 也无 `BYPASSRLS`，
    回填改为逐租户 `set_config('app.tenant_id')` 后再更新（已在
    `rolsuper=false, rolbypassrls=false` 的角色上实测）。本轮不执行任何不可恢复删除，也未对
    生产数据库执行 `downgrade`。
  - **事实更正**：迁移 `20260725_18` 本身确为 expand-only（只新增、只回填、不删除）；但旧
    `rail_profile.confirmation` / `inventory_snapshot` 随后被幂等门店种子的规范化结构整体
    覆盖，当前生产 live 行已不含这两个键（实测两店均为 `f`），它们只存在于部署前备份中。
    此前“旧字段仍作为回退窗口内的兼容数据留在生产表里”的写法不成立，已更正。
- 历史任务失败关闭（第三轮，`ac6e03c`）：
  - `DisplayService.revise()` 删除 `load_task_context(...) or load_context(...)` 静默回退。
    任务没有保留上下文快照时只返回一句自然提示“这份历史方案没有保留完整的任务条件，请按
    当前库存新建一份方案。”，不创建运行、不创建版本、不读取门店当前种子；作用域之外的任务
    由仓储直接失败关闭，缺快照不再兼作越权读取的掩护。
  - 本地反证 `test_a_task_without_a_frozen_snapshot_can_no_longer_be_revised`：把某任务快照
    置空并改动门店种子后，修订被拒、任务/运行/版本计数不变、V1 仍可读；同一测试内新任务
    V1→V2 快照重放继续成立。
  - 生产反证：对空快照任务 `3408983d…` 发起修订只得到同一句自然提示，前后
    `display_tasks / runs / versions` 均为 `2/2/2`。
- 已确认规划：D-033 已形成 ADR-027。三条长期核心目标是品牌一致性下的表达广度、不同
  租户的实质差异化与反串味、自媒体内容市场竞争力与持续进化；它们是规划，不是实现、
  验证或市场效果证明。M7-2A 承接内容表达目录、只面向实际启用发布账号的可版本化五段
  人话画像、控制组织与个人权限分离、私人偏好、任务文字素材、轻量内容计划和未满足需求；
  M7-2B 承接总部/门店真实连续系列、经确认商品的P1/P2/P5、三平台重编译、平台/在地
  上下文、内容协作和 R/O 表现；
  M7-3 承接首期整体验收。未进入上述里程碑的已确认事项统一见
  `docs/待落盘推进事项清单.md`。
- 旧错误验收成品已退出普通产品面（第三轮）：任务
  `3408983d-a39c-4854-b813-03f8aa1cb60d`、版本 `0b35af60-2ca6-4a4e-9208-7f62aa153f3a`、
  artifact `191b8710-df30-46e9-9e91-d3bc948052d3`、run `9490e644-a3b9-4209-9664-fc15517bb4af`
  于 `2026-07-25 08:32:04 UTC` 由被伪造陈列作用域的租户管理员代生成，`context_snapshot` 为空，
  正文仍带已被裁决取代的确认人、代录与业务指定语义。已在紧邻备份
  `20260725T112246Z-m7-1-pre-task-cleanup` 后，用**单事务**按
  `versions → artifacts → runs → task` 精确清理（事务内断言各删 `1` 行、其他任务/门店/品牌
  商品/陈列政策/用户计数不变、清理后不存在空快照任务）。首次执行因守卫写死门店计数而整体
  回滚、未删除任何行，修正守卫后一次通过。清理后：任务列表不含该 ID、直接读版本 `422`、
  版本列表 `404`、修订 `422`，新 V1 仍 `200`。证据 ID、历史结论与备份位置保留在本文件与
  M7-1 执行包；未建设归档状态机。
- 一次性账号资格及其退出：生产原本没有任何具备陈列执行资格的账号（唯一自然人属管理组织）。
  已按既有租户管理员账号管理流程创建并激活 `M7-1验收用陈列操作账号`
  （`diyu-kq-display-acceptance`，用户 `32d97a9c-2afa-4deb-95b8-31acc046c279`，归属浙江
  分公司，无发布账号、无租户管理授权）。这是一次性账号资格配置，不是逐任务授权，也不冒充
  阿丹或任何真实门店人员。该身份已于第三轮**退出生产**：`enabled=false`、5 个 tenant-user
  会话全部撤销、口令文件 `/etc/diyu/ops-run/m7-1-display-acceptance.secret` 已删除且目录已空，
  并写入一条 `operator_id` 为空的 `tenant_user.retired_by_maintenance` ops 审计记录。实测：
  退出前该会话读新 V1 `200`；退出后旧 Cookie 读接口与页面均 `401`，用原口令再次登录 `401`、
  随后读取 `401`。用户行与任务外键证据保留，未创建替代验收账号，因此当前生产不存在可用的
  陈列登录身份。
- 密钥处置偏差（如实记录）：该账号口令由服务端随机生成、写入 root-only 文件，从未写入仓库
  或提交；但第三轮为确认文件格式曾用 `awk` 打印其字段名，而该文件正文只有口令本身，导致
  口令回显到执行端会话输出，违反“不得输出密钥”的约束。此后所有登录改用
  `curl --data-urlencode password@<文件>` 直读，不再经变量或命令行。安全收尾已在带租户
  作用域与审计的单一事务中把该账号的 `user_credentials.password_hash` 置为 `NULL`、
  `password_changed_at` 更新为当时时间：**数据库密码哈希已清空，凭据完成不可恢复失效**
  （`password_hash_null=true`、`user_enabled=false`、`live_sessions=0`、`enabled_grants=0`、
  `live_tokens=0`）。同一事务写入一条 `operator_id` 为空的运维审计
  `tenant_user.credential_irrecoverably_invalidated:验收账号因口令曾进入执行输出，凭据已不可
  恢复失效。`，未创建任何新口令、账号、会话或激活链接。
- 生产参考方案 V1（最终 SHA，由正式认证的陈列用户经正式 API 发起）：任务
  `108b03f4-c95a-49ac-ae70-b996cf3dd83a`、版本
  `8dfa179f-98f4-4249-9a4d-b8a3ce7e784e`。执行器 `dm01-rule-compiler-v1`、
  `provider_usage=null`、未调用 DeepSeek；30 件任务库存逐项守恒（18 上墙 / 12 不上墙）；
  `context_snapshot` 已冻结结构版本 `KQ-WALL-01-structure-v1` 与 11 项商品；
  `input_receipt.operator` 为该验收账号且不含 `field_executor` / `submitted_by`；正文对
  九个禁用词与两个操作者姓名的匹配数为 `0`。
- 生产验收：匿名写入与读取均 `401`；正式会话可读新 V1（`200`，正文含
  “本次任务库存共 30 件；建议 18 件上墙，12 件不上墙。”，九个禁用词与“本次操作人”匹配数
  为 `0`）；不存在/非本作用域任务 `422`；`/display` 页面 `200`、任务列表可读。空快照任务的
  修订只返回一句自然提示，前后 `display_tasks / runs / versions` 均 `2/2/2`，没有半版本，
  也没有新增品牌长期商品或陈列政策。清理旧错误任务后，生产只剩一个陈列任务（新 V1），
  且不存在 `context_snapshot` 为空的陈列任务。
- 验证证据：本地 Ruff、mypy、OpenAPI/Golden、后端 `98 passed`、前端 lint/typecheck/build
  绿色；本轮唯一远程 CI 为 run `30155757920`，对应已部署实现提交
  `ac6e03c3b3a7e8fd8a768884746d0cb8a1d0cd59` 并绿色。第三轮部署前完成新鲜备份
  `20260725T111527Z-m7-1-round3-fresh`；清理旧任务前完成紧邻备份
  `20260725T112246Z-m7-1-pre-task-cleanup`。上一轮的隔离恢复检查
  （`20260725T102137Z-m7-1-predeploy-2`：数据库还原、RLS 反证、应用 readiness、对象恢复
  全部通过）继续有效，本轮未再重复执行。
- 状态流转记录：主控终审第一次将 M7-1 由 `REVIEW` 退回 `ACTIVE`（假操作者语义、任务快照
  未冻结、可见文案残留、破坏性迁移四项缺口），修复部署后重回 `REVIEW`；第二次再退回
  `ACTIVE`（历史任务未失败关闭、旧错误验收成品仍在产品面、验收身份未退出，以及回退与迁移
  表述失真），修复、部署、清理并验收后重新进入 `REVIEW`；主控终审据此将 M7-1 置为
  `CLOSED`，并要求先完成验收凭据的不可恢复失效作为最终安全收尾（已完成，见上）。全部历史
  提交保留，未 reset、rebase 或 squash。`CLOSED` 只表示本里程碑的软件闭环与安全收尾成立，
  不表示真实现场执行、门店采用、陈列效果或销售已经证明。
- 未证明项：真实现场执行、门店实际采用、陈列效果和销售结果**尚未证明**。按用户裁决，
  这些不构成 M7-1 软件验收阻断。生产 V1 由验收用陈列账号发起，不代表真实门店人员已采用。
- 未清理项（按 expand/contract 规则留待回退窗口结束后处理）：`display_policies` 中
  笛语服饰 `V1.0-confirmed-2026-07-25` 一行属早期把本次焦点写成长期品牌政策的残留，当前
  已与门店结构版本脱钩、不再被读取，本轮按主控裁决保留、不阻塞收口。柯桥店 `rail_profile`
  的旧结构只存在于部署前备份中。两者都不在本轮执行不可恢复删除。
- 收口时的下一动作（已发生）：等待主控开启下一里程碑。主控其后开启 `M7-2A`；M7-1 保持
  `CLOSED`，本轮不重开、不改写、不再请求用户或门店人员确认、授权或现场回复。

## M6-3 替代结论（2026-07-25，历史完整保留）

- 主控裁决：M6-3 未通过，不得写为 `CLOSED`；当前终态为 `SUPERSEDED`，successor 明确
  指向 M7-2B“真实品牌内容协作试点”。该状态只表示原验收方法和对 M7-1 的串行依赖被
  替代，不表示 M6-3 成功。
- 候选实现 `3bcae817750abb01a04e9d5410fd4334c91933cf` 只增加两个运行时共享不变量：
  R 从可见画面、动作、声音和制作提示独立提取资源能力，服务端对登记能力闭世界校验；
  O 从可见文字独立提取陈述性质，服务端再按可信来源判定品牌立场、条件性建议、确认状态、
  已发生事件和经营做法是否合法。缺字段、未知枚举、漏单元和观察不一致均失败关闭。
  writer 自报的 `basis / actuality / source_refs / resource_refs` 不作为 judge 的实际语义观察。
- 通用正反例和定向测试通过；候选本地 `make lint`、`make typecheck`、`make golden`、
  `make test` 及前端 lint/typecheck/build 全绿（Golden 与全量测试均为 `98 passed`）。
  预部署备份 `20260725T053916Z-predeploy` 校验和、`pg_restore --list` 和清单可读；
  候选镜像完整摘要为
  `sha256:d96e3c9279437c8ac6632e56a73233aec5c7aa30d10ca1e29d5585fb839164ff`。
- 同一候选 SHA 下严格按冻结输入各发起一次正常业务请求。Q1、Q3、Q5、Q6 成功，Q2、
  Q4、Q7 均在最多一次单元修复后以“内容边界无法在一次单元修复内满足”失败；因此
  Q1—Q7 只有 `4/7`，审查 A 不能通过。Q4、Q7 正是本轮 R/O 结构路径，证明本轮两项
  方法仍不足以在冻结合同下稳定形成完整成品，已命中用户规定的结构停止线。
- 成功证据分别为 Q1
  `task=2c300b0b-b040-459c-b04b-3e8997e61186 / version=02cb0fd2-981e-4532-ac8f-a08ffa61c851`
  （`05:44:45 UTC`）、Q3
  `84510a22-4018-45dc-8fd8-4c57f7114b41 / f187c909-d464-484e-abcb-f5263fa8b270`
  （`05:50:22 UTC`）、Q5
  `e7678642-fb8f-4b98-bacb-287fffe27638 / b8f5bfb3-400c-431a-8fbe-cc44d676bbf0`
  （`05:52:37 UTC`）、Q6
  `580a6f28-3a6c-4fe6-9510-020a049e11eb / 49ed8d30-2b99-49dc-82ce-a2650a905925`
  （`05:53:10 UTC`）。
- 失败证据分别为 Q2
  `task=fe1b7d07-4e4d-40a1-bc3e-de2613f80059 / run=8d6b81e6-7d1c-4c26-a70a-6d7ecf3956dd`、
  Q4 `7bb0cbf6-73d4-4733-8edc-556b332f73bc / c62fba1a-a5e7-4439-9771-38f56fab2d97`、
  Q7 `f63d325a-7794-4a08-bd0d-b04584b1cf0d / 6942ca56-bf0a-406e-a88f-74b2f1c1c356`；
  三个失败运行的版本数均为 `0`。Q8 返回最小商品资料追问，实时任务/运行/版本差分为
  `0/0/0`，完成 `1/1`。
- 审查 B `PASS`：匿名访问 `401`，错误租户、品牌和账号均失败关闭；成功卡商品引用为
  `0`；失败运行没有半版本，运行中记录为 `0`；品牌知识、系统激活资产 `41`、个人偏好、
  系列前情、跨租户学习和 DM01 均未改变；AIGC 阅读、复制和导出披露保持成立。
- 直接运行证据保存在生产数据库以及
  `/tmp/m6-3-final-evidence.ndjson`（SHA-256
  `cf8255bb526bfe539cddc5e8f7d9a3ec5d8fd0fe449e3a8738621b46d0438cff`）。
  失败候选镜像和新鲜预部署备份保留，未删除或改写失败任务。
- 已用既有回退入口恢复 `58a52f1ba81e8c8dae75a3277c44af65919da0c9`；当前运行镜像完整
  摘要为 `sha256:0332bf0c06a658135085e4170b49ec759e13128709c54feee2235591aa3b357a`，
  容器运行、本机和公网 readiness 均健康，生产仓库工作树干净且来源一致。
- 失败候选实现已在 Git 中以普通 revert 保留完整历史，没有破坏性重置。BLOCKED 阶段
  当时未创建 ADR-027、未推送、未触发成功路径 CI，也未启动 M7-1；这些当时事实继续保留。
- 后续主控已用本节首条裁决取代 `BLOCKED`：不形成第四个 R/O 候选，不恢复
  `3bcae817`，不重跑 Q1—Q8，也不以人工补写 V2 包装通过。R 制作资源转由 M7-2B 按
  可人工复核质量处理，优先省略、替代或降级；O 事实边界继续有效。ADR-027 已作为
  “已确认规划”落盘，M7-1 与内容生产解耦进入 `ACTIVE`。

## M6-3 最终结构收敛返工（2026-07-24，历史；已被上述停止结果取代）

- 主控重新完整审读 `58a52f1` 七份可见成品后否定审查 A：Q4 要求手机展示一张未提供的
  三人合影，违反资源能力闭世界；Q7 把品牌关系观点写成门店已经执行的服务做法或承诺，
  违反现实经营事实边界。旧七卡仍保留为历史证据，但不得继续作为当前通过证据，也不得在
  同一 SHA 随机重跑碰运气。
- 本轮只增加两个运行时共享不变量：R＝从可见画面、动作、声音和制作提示独立观察
  `required_capabilities`，再由服务端对允许能力集合做闭世界判定；O＝从可见文字独立观察
  陈述性质，再由服务端结合可信 `basis / actuality / source_refs` 判定品牌立场、条件性
  建议、现实状态、已发生事件和经营做法是否合法。writer 自报引用不作为观察依据。
- 当时唯一执行端为本 WSL Codex；剩余验收是形成一个新实现 SHA、同 SHA 连续完成
  Q1—Q8、审查 A/B、本地必要回归、规划同步和唯一 CI。只有新候选再次发生同类资源或
  经营做法硬失败时，才回退并置为 `BLOCKED`；否则达到 `REVIEW` 后立即停止，M7-1
  不启动。

## M6-3 收敛结构阻断

- 干净施工起点为 `1c6cce17c9c5c225b3bbfaa91bb60fb00605332a`；旧施工保存在
  `refs/archive/m6-3-pre-convergence`、`refs/archive/m6-3-churn-head`，未提交差异保存在
  `/tmp/m6-3-convergence-wip.patch`。
- 第一生产候选 `d322d71f4472339753f607feae3f4c669b47089a` 的 Q2—Q7 多次把话题
  人物写成演员或第一人称经历、安排未提供衣物/多人/门店资源，并把门店观点写成已执行事实。
  该候选保存在 `refs/archive/m6-3-first-candidate`。
- 唯一一次共享根因修复收紧了“边界未提供即不存在”、逐字段语义核对和最小资源组合，
  形成第二生产候选 `ebbea8187bafabdc36094a883778e3ffda87234d`。同 SHA 下 Q1—Q7
  均生成、Q8 为最小追问且任务/运行/版本在 Q8 前后保持 `196/196/160`；但人工审读仍发现
  Q3 冒充孩子照护者，Q4 安排一家三口和既有合照，Q5 编造品牌观察经历，Q7 宣称门店已执行
  服务。审查 A 因此失败，审查 B 的 Q8 原子性与知识/资产不变成立。
- 按用户硬停止线，不再增加具体提示句、角色/资源词表或测试卡特判，也不形成第三个生产 SHA。
  备份 `20260724T175040Z-m6-3-structural-blocker-precleanup` 后只删除两轮 14 个明确任务及其
  直属运行/版本/事件；其他真实内容未触碰。实现与状态均未推送，唯一 CI 未触发。

## M6-3 主控终审退回

- 七份保留候选确实都属于笛语服饰真实租户，商品引用为 0，跨租户读取失败关闭；Q8
  独立复测仍为最小追问，请求前后任务/运行/版本计数不变。Ruff、mypy、Golden、
  前端检查及远程 CI 均绿色。
- 但七份候选分别生成于 `12:12—12:43 UTC`，最终生产镜像
  `6a81791278a19660e8ec6e5be5710b73c03386a9` 在 `12:47 UTC` 后才部署；因此现有证据
  不能证明最终生产版本七卡 `7/7`。
- Q5、Q6、Q7 的完整口播分别约 `80/131/112` 个可读字符，却声明约
  `14/22/19 秒`，接近每秒 6 个汉字；这只能通过当前 `(字符数+5)//6` 的机械下限，
  不符合合同要求的自然口语与直接制作。Q5 的声音提示还包含正文/动作没有承接的脚步、
  衣柜门轴等声音，声画不闭合。
- 当前七卡内容只部分出现在适配器单元测试中，没有一份能证明同一最终生产 SHA 下七卡
  全部成立的真实验收记录。故执行侧写入的“七份均可执行”和审查 A `PASS` 被主控否定；
  审查 B 继续有效。
- 修复范围只限自然时长下限、声画/制作提示一致性，以及同一最终 SHA 的一次七卡真实
  复验。不得增加评测平台、第二模型、更多重试、SEO、AI味评分器或新知识层。

## M6-3 结构重构与最终收口证据（2026-07-25）

- 最终生产实现 SHA `58a52f1ba81e8c8dae75a3277c44af65919da0c9` 于 `04:07 UTC` 部署
  （运行镜像标签＝完整 SHA，readiness 通过；预部署备份 `20260725T040711Z-predeploy`）。
  Q1—Q7 七卡于 `04:09:13—04:12:58 UTC` 在该部署下连续生成 `7/7`（任务
  `a9a90377/900a3b11/75e717b5/261df576/888ad827/229f83ce/976a5a23`，均为 v1，
  P3 五条、P1 两条），Q8 同部署下返回一次最小商品追问且任务/运行/版本计数前后不变。
- founder 裁决（2026-07-25）：9c3c1b7 轮 Q2“我们被问过很多次”（制作提示引述）判同类
  经历漏出、Q5“我们内部讨论过很多次”判同样越界，该轮七卡证据作废；确立共享语义规则——
  凡声称现实品牌/账号/组织/人物曾经、反复或长期发生过询问、讨论、观察、经历、服务、
  执行或改变，必须有用户明确前提或已确认事实来源；品牌观点只承载当前立场、希望、主张
  和建议；无来源时保留观点、删除经历外壳或转为问题/假设/条件表达。该规则落地于写作/
  判定/修复三处共享提示词与边界一话题预设语义（basis+actuality+source_refs 结构不变，
  无 Q 卡特判、无关键词黑名单、无固定成稿），并新增通用正反例 E1/E2 入前置门。
- 最终 SHA 前置门：四反证（Q3/Q4/Q5/Q7）+ 四合法近邻 + E1（经历诱惑种子）/E2（当前
  立场正例）共 10 例单轮全部生成、禁词命中 0；E1 追踪证明写作被诱惑时判定器全抓、
  一次修复把预设转为问句后复检干净。
- 最终七卡：口播 3.52—3.69 字/秒（≤4 上限），串味词/内部编号/无源经历壳命中 0，
  声画引述与台词逐字一致，未承接声音提示 0，一人一手机成立；审查 A `PASS`
  （Q7“你的安静，我们收到了”为现在时修辞性回应，按共享规则字面不属“曾经/反复/长期”
  类，作为边缘项记录）；审查 B `PASS`：input_receipt 全部指向笛语服饰当前租户/
  发布账号/`ContentRole`“品牌官方 / 品牌定义者”/抖音/零商品引用；合成租户读真实任务
  `422` 失败关闭、匿名 `401`、合成租户列表无笛语内容；品牌知识八表计数不变、系统激活
  资产恒 `41`、八小时事件全部为生成域事件、失败运行零半版本、真实租户陈列任务 0。
- 验收探针在独立备份 `20260725T042035Z-m6-3-final-precleanup` 后按明确任务 ID 精确
  清理 `36` 个（断言门控：非 36 即回滚），只保留七份通过候选；真实租户计数收敛为
  `189/189/153`。有界遗漏扫描十项无阻断。本地 `90 passed`、Ruff、mypy、Golden、
  前端 lint/typecheck/build 全绿。
- 修复分级记录：编号简写（`创作者口播：c8、c9内容`/`口播内容：c9…`/`（口播c8内容）`）
  属协议表达缺陷，由服务端确定性还原为 claim 台词原文（混入散文或超出 claim_refs 的
  编号仍失败关闭）；无源历史主张属共享语义缺陷，由三处共享提示词承载；两类均无
  重试层新增，一次单元修复上限不变。

## M6-3 首轮验收证据（2026-07-24，主控终审已裁定其审查 A 无效，保留为历史记录）

- “笛语服饰品牌官方账号”以正式 DeepSeek 和服务端可信作用域完成 7 个非商品承重内容
  机会，其中 P3 五条、P1 两条；每条均有完整口播、画面动作、字幕、声音与制作提示，
  当前一人一手机条件成立。
- 七份保留候选的 `GenerationRun.input_receipt` 均只指向“笛语服饰”、当前发布账号、
  `ContentRole`“品牌官方 / 品牌定义者”、抖音视频和零商品引用；正文中“折线之间”、
  南城店、`ZX-C218`、双面外套、总部内容运营甲及内部品牌版本号命中 `0`。
- Q8 在真实生产 API 返回“请先指定一件已经确认资料的商品”；请求前后真实租户的任务、
  运行和版本计数均为 `67/67/41`，没有半任务或半版本。笛语服饰确认商品、素材仍分别
  为 `0/0`，系统激活资产仍为 `41`。
- 真实运行纠正了三类承重边界：话题中的妈妈、孩子、顾客不是账号操作者或可拍演员；
  品牌观点不能扩写为未发生的家庭/门店经历；通用颜色、品类和风格示例属于创作方法，
  不能被误判成当前品牌商品事实，也不能冒充已有拍摄道具。
- 生产验收产生的淘汰与失败探针在备份 `20260724T125119Z-m6-3-precleanup` 后按八条冻结
  种子精确清理 `59` 个任务，只保留七份通过候选；其他真实租户内容未触碰。
- 当前就绪范围是品牌官方账号的非商品 P1/P3；缺少确认商品只限制商品承重 P1/P2/P5，
  缺少真实门店事实只限制具体门店 P4 与 DM01。真人经历、真实评论、发布反馈、本地信号
  和平台表现继续等待 M7 真实使用，不自动写回知识。
- 本地 Ruff、mypy 与全量测试通过，后端 `144 passed`。既有 M6-2 取消路径测试补充接受
  底层等义 `CancelledError`，未改变生产逻辑。Golden、前端检查和唯一 CI 以最终状态
  提交为准。

## M6-2 关闭结论

- 主控独立复核确认 M6-2 合同全部成立，无需返工，正式裁决为 `CLOSED`。
- 5 租户/200 已启用账号隔离容量、模型限流七项、备份隔离恢复和版本回退往返均成立。
- 主控定向复跑 M6-2 测试 `3 passed`；状态提交 `702e97a` 的唯一远程 CI
  `30090327580` 绿色。
- 本次并发、恢复和回退时间只是当前 ECS 有界观察值，不构成企业 SLA、RTO、RPO 或
  200 并发证明。

## M6-1 关闭结论

- 主控独立复核确认 M6-1 合同全部成立，无需返工，正式裁决为 `CLOSED`。
- 真实租户、品牌、管理员、发布账号、独立 `ContentRole`、本人操作授权、品牌确认版本和真实非商品 P3 均为 `1/1`。
- M6-1 定向测试独立复跑 `2 passed`；状态提交 `09dfd68` 的唯一远程 CI 绿色。
- 未确认商品继续只限制商品承重 P1/P2/P5，未确认真实挂杆继续只限制 DM01。
- M6-1 不证明真实发布、平台流量、销售效果、企业采用、内容竞争结果或企业 SLA。

## M6-2 冻结边界

- 第一阶段容量验收包络是最多 5 个租户、全平台合计不超过 200 个已启用自然人账号；不是 200 并发，也不是业务代码硬上限。
- 保持单应用实例、单 Uvicorn worker和进程内模型限流；本轮不建设多副本、Redis、消息队列或分布式限流。
- 复用现有 DeepSeek、PostgreSQL/RLS、对象存储、每日备份和 SHA 回退底座，只关闭当前直接验收缺口。
- 200 账号容量夹具只进入隔离测试数据库，不向生产创建假租户或批量测试账号。
- M6-2 只记录当前环境的并发、重启、恢复和回退观察值，不虚构 SLA、RTO 或 RPO。
- 已知有结构性缺陷且与本仓错配的系统级审查测试验证 Skill 继续禁用；其缺陷不是项目阻断。

## M6-2 REVIEW 证据

- 隔离容量夹具通过正式开户、品牌确认、发布账号、`ContentRole`、自然人和授权边界创建 `5` 个租户、合计 `200` 个已启用自然人账号；跨租户、错误品牌、错误账号和未授权自然人反证各成立，测试资源已清理，生产新增容量账号 `0`。
- 正式 `/api/v1/content` 路径证明全局、租户、单用户两秒和租户分钟速率边界；超限快速 `429` 且不产生任务、运行或版本，成功、模型失败和取消均释放槽位。取消路径同时把运行落为失败，不再遗留 `running` 记录。
- 生产保持单应用实例、单 Uvicorn worker 及 `全局并发 4 / 单租户并发 2 / 单租户每分钟 12`。公网读取突发 `20/20`，约 `2.134 秒`；无敏感、无持久化的 DeepSeek 并发探针 `4/4`，约 `1.298 秒`。
- 真实 Uvicorn 进程被异常终止后约 `1.762 秒`自动恢复，随后现有真实 P3 读取 `1/1`。第一次用 `docker kill` 的控制面人工停止不属于进程崩溃，未自动恢复且曾短暂返回 `502`；该非合格探针已由执行端立即恢复，未冒充通过证据。
- 新备份 `20260724T112610Z-m6-2` 的清单只含 schema 与数量，记录 schema `20260724_17`、真实关系链 `1` 和无敏感测试对象 `1`，并纳入校验和。隔离恢复约 `7.978 秒`，清单一致、应用角色无 `BYPASSRLS`、未设租户上下文失败、应用 readiness、M6-1 关系链和对象复制/删除均成立；临时容器与线上测试对象已清理。
- 候选回到 M6-1 `f4697a8` 用时约 `7.587 秒`，再恢复候选用时约 `12.819 秒`；两次切换的 schema 与“确认品牌—账号—角色—授权—P3”计数均保持 `20260724_17|1|1|1|1|1`，未执行数据库 downgrade。
- 唯一必要回归全部通过：Ruff、mypy、Golden、全量测试和前端 lint/typecheck/build 绿色，Golden 与全量测试均为 `130 passed`。审查 A（容量、限流与租户隔离）和审查 B（备份、恢复与版本回退）均无阻断。
- `d2c6908` 首次 CI 因不存在的浮动 `astral-sh/setup-uv@v8` 标签在 job 初始化失败；按官方 v8.1.0 不可变提交修正后，`29adfe5` 的唯一 CI run `30090059899` 绿色。该历史失败保留为 CI 运行时证据。
- 上述时间均是本次 ECS 的有界观察值，不是企业 SLA、RTO 或 RPO；M6-2 不证明 200 并发、真实发布、平台流量、销售效果或企业采用。
