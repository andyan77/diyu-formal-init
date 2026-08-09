# BRAND-MATRIX-01 · Gate E R-1 内容领地契约修复实施证据

- 执行基线：`a1c4b8cf87ac16b1a371be418aae86a45b2f5400`
- 执行分支：`exe/brand-matrix-e-fix`
- 性质：部署前确定性契约修复；不冻结候选，不使用 SEALED-SET-01。
- 隔离：provider request `0`；生产、SSH、ECS `0`；未读取 `.env`。

## R1 · 人设契约

- `src/tool/llm_gateway/deepseek.py::_writer_truth_and_persona_instruction` 已允许账号第一人称经历基于账号画像与任务上下文自由演绎，不再以获准原句作为创作前提。
- 获准原句仍可逐字使用，并继续通过 `used_persona_quote_ids` 审计；未使用时为空。
- 未授权真实人物姓名、肖像、声音仍禁止；演绎不得夹带、改写或补充商品性能与商品事实。
- 既有商品精确机器门（成分比例、价格、年龄段、精确工艺、保证/绝对化性能、商品改值）未放松。

## R2 · 披露转审计元数据

- 已从 `visible_structure.py`、`creative_kernel.py`、`delivery_compiler.py` 及 Writer 文案合同中移除面向消费者的“创作表达/情景演绎、不对应真实人物或经历”声明与标题前缀。
- `expression_mode=dramatization` 进入 Publication V3 完成快照；仓储白名单同步接受并严格校验该字段，名单外字段仍失败关闭。
- 确定性 stub 与真实 Writer 路径生成同形审计字段；旧快照没有新字段时仍按旧合同读取。

## R3 · 使命优先、缺料拦问与品牌压力拆除

- 新增 `src/shared/content_territory.py`。H04/P2 在没有与当前账号、当前 SKU 匹配的品控段时，在任务、资产和 provider 调用之前返回补料问句；不会退化成商品介绍。
- 正式读路径以 `logical_account_product_mission` 复合主题约束账号，并在仓储层继续约束所选 SKU，不能借用其他账号或其他商品的品控段。
- 新建 WriterRequest 不再携带 `brand_relevance`；该状态只留在任务冻结合同、快照和详情投影中用于审计与资格解释。

Writer 品牌压力侦察全目录：

1. `src/shared/writer_request.py`：原正式 Writer 输入携带 `brand_relevance`；现对新请求固定为 `None`。
2. `src/tool/llm_gateway/deepseek.py` Publication V2 兼容 Writer：原“品牌和账号关系自然体现”要求已改为“题材优先、无自然关联照常完成、不得品牌式收尾”。
3. 同文件 CreativeKernel 兼容 Writer：原“必须让受众读出账号为什么说”已改为仅约束观察和回应姿态，不要求证明账号/品牌关联。
4. `src/brain/content_service.py`、`src/shared/publication_contract.py`、`src/shared/task_value_assembly.py`、`src/shared/content_snapshot.py`：保留 `brand_relevance` 的确定性装配、冻结与脱敏读取，均不再进入新 WriterRequest。
5. `frontend/src/**`：只发现品牌资料/事实管理说明，没有要求成品硬关联品牌的 Writer 指令；产品代码字节差异为 `0`，无需修改。

回归断言同时禁止旧压力句重新出现，并要求正式与兼容 Writer 都明确“找不到自然关联时照常完成题材”。

## R4 · H04 品控供给

- 输入文档：`素材草案-v0/05-品控记录汇编-演示补充.md`；实测 SHA-256：
  `62b43ff4ba93f6856b50c95486574a7b2ec966669b4d828fc18b0c2894fb1d7a`。
- Gate A 合同只在 `amendments` 尾部追加 `AMD-CONTENT-TERRITORY-20260809-01`；既有字段、条目及首个 amendment 零修改。
- 导入器确定性抽取五条 DEMO 记录：四条已关闭记录进入 H04/P2 可见 V2 projection；一条未关闭记录只作 internal/source catalog 保留，进入 Writer 数量为 `0`。
- 每条可消费记录都带“仅演示，不得当作真实批次证据”语义、商品绑定、H04 账号使命复合主题、来源版本和 digest。
- 两轮隔离导入：batch digest 均为
  `961e33d93b4b504318c5b9531064574a34ab5e6d2b5362f76c22ca19e3389088`；对象指纹均为
  `03c572b79ee0ef36e5852a2c9657abb484ff318dc11c38d492007b48fee1ec28`。
- 两轮盘点均为 `quality_demo_segments=5`、`quality_demo_projection_items=4`；私有证据文件 SHA-256：
  `e55cf0dcc0a4aa4dd44090fa5560253d7ce71d428f5631a2c67a7c5c4b3496e4`。
- H04/P2 正式本地纵向以 `DIYU-CSPU-013` 消费 `DEMO-QC-013-2607-01`，版本 `1` 落版；其他 SKU 的品控记录没有混入。私有证据 SHA-256：
  `0050f340a2fe2a2f40acbe2400fb73976c3201ea0cf8840b17e7de1f89bd0e35`。
- 既有 tenant01 setup/run 正式纵向为 `PASS`：五案例、十六检查、V1→V2 当前投影升级、旧任务 packet/artifact 前后 digest 不变。私有上下文证据 SHA-256：
  `1060e564811ddbfe47ad130e690bc944e3944340c15b550f8bd75f64be56fdc3`。

## 确定性门

- 全量 pytest/Golden：`1061 passed / 2 skipped`。
- Ruff 全仓：PASS；mypy：`180 source files` PASS。
- EXE-V0：`3/3` PASS；EXE-01：`9/9` PASS。
- 前端 lint/typecheck/test/build：PASS；显式 Chrome：preview `2`、candidate `1`、confirm `1`，PASS。
- EXE-V1 与 S0 两套秘密扫描：PASS；`git diff --check`：PASS。
- workflow_dispatch CI 在提交推送后执行；run 号和四查值由本轮最终执行报告登记，不能由提交前文档预填。

## 剩余边界与风险

- 本轮没有调用模型，确定性 stub 只证明契约、前置门、数据消费和落版链路，不证明真实模型初稿质量。
- 五条品控记录都是 DEMO 资料，不得升级为真实生产批次或对外检验结论。
- 没有迁移、没有前端产品改动、没有生产导入或部署。
- SEALED-SET-01 已归档；重冻结与 SEALED-SET-02 属下一执行包，本轮未做。
- 下一动作：监理独立复验本轮；通过后另包重冻结并使用 SEALED-SET-02 重考。
