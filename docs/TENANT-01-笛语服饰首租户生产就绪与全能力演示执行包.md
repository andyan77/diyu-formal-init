# TENANT-01 · 笛语服饰首租户生产就绪与全能力演示执行包

## 当前状态

- 里程碑：`TENANT-01`
- 状态：`REVIEW / 等待主控独立终审`
- 唯一写入执行端：当前 WSL Codex
- Git 启动基线：`94fa541f4b5a8f9c3fab5de6d826473440b6dd30`
- UX-03：`CLOSED / PASS`
- 生产启动锚点：运行实现 `1f6aafee584fa5e2832be20c12534d9493691bda`，schema
  `20260810_37`；部署前以现场事实复核
- 工作树保护：`docs/项目记忆.md` 实测 93 行用户未提交内容全部保留，不暂存、不提交
- 私有资料：仅从用户指定 Windows 目录只读；原文不得进入 Git、CI、公开日志或公开证据

## 唯一结果

笛语服饰作为首个正式租户，在生产中具备干净且可维护的组织、逻辑发布账号、五段画像、四个
平台／形式目标、成员与具体资格；21 份授权 Markdown 以源文档和稳定语义 segment 原子入库，
14 个候选商品以 V/P/C/R 字段证据边界入库并由正式内容上下文按任务相关性消费。无真实图片时
P5 在建任务前自然提示且差分 `0/0/0`；软件功能真值与租户资料就绪度分开。最终候选须完成
本地门、两份有界审查、权威 CI、备份恢复、生产部署、隔离恢复库黄金套件、旧镜像往返回退和
精确清理，随后进入 `REVIEW`，不得自行 `CLOSED`。

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

只有全部 18 项用户完成门真实成立，才将 TENANT-01 置为 `REVIEW`。失败历史、生产前像、源批次
digest、正式运行 SHA、CI、镜像、schema、备份、隔离黄金证据和清理结果均在本文件后续追加；
不为内部阶段建立子状态机或平行台账。

## 本地正式候选证据

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

## 最终生产候选与数据结果

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

## 正式消费者、双真值与黄金验收

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

## 备份、回退、清理与两份有界审查

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

## 当前结论

TENANT-01 已满足 18 项完成门，进入 `REVIEW`，不自行 `CLOSED`，不启动下一里程碑。该结果不
证明真实员工长期采用、真实发布、流量、排名、爆款、GMV／销售、多真实租户市场差异、企业
SLA、`20/55/44` 全组合稳定支持、无真实图片时的笛语 P5 成品，或无真实门店／库存时的笛语
DM01 实际经营采用。唯一下一动作：主控独立终审 TENANT-01。
