# BRAND-MATRIX-01 · Gate D 媒体解锁后正式套件失败安全报告

状态：**`GATE-D FAILED_SAFE · FORMAL_SUITE_BOUNDARY_REJECTED`**。

本报告是执行侧证据，不是监理独立复验或 founder 逐篇终审。Gate D 未达到
`IMPLEMENTED`；正式套件已按唯一候选、单次运行和失败安全纪律停止，未重跑。

## 1. 完成门逐项结果

1. V2 projection 的 React/API 创建、确认、读取和任务消费纵向：**PASS**。
2. 10 逻辑根账号、20 carrier、30 矩阵账号行、40 平台/形式目标及旧 9 账号归档：
   **PASS**。
3. 31 条资料去向及真实组织任务消费：**PASS**；RK-EC-08 新任务消费为 0。
4. J、authorization、qualification 与反馈观察正式消费者：**PASS**。
5. 26 份技术母版、checksum 及十项门裁决：**PASS**。
6. P5 前置：**PASS**。6 份 PASS 母版绑定 4 个不同已导入正式商品；P5 卡取得
   一次正式响应并成功落版本。
7. 八剧本 8/8 + 八异常 8/8：**FAIL**。套件在第 6 卡 `S04-S04-P2` 触发既有事实边界
   后失败安全停止，未得到 8/8 + 8/8。
8. provider 账本、预算与唯一 SHA：**PASS（失败证据口径）**。请求 `6`，重试 `0`，重跑 `0`，
   全部绑定唯一候选 `997e6b55c1c40dacd44a46ff6617b28766011958`。
9. 全量工程门、Chrome 与 CI：**PASS**。本地 `1005 passed / 2 skipped`；CI run
   `31292553896` 四查全绿。
10. 生产接触、密钥泄漏、二进制入 Git：**PASS**，均为 0。

Gate D 因第 7 门未达成，不得报 `IMPLEMENTED`。

## 2. D0 纵向与导入证据

- D0 纵向：React/API 预览→服务端派生治理字段→候选保存→管理员确认→新任务冻结
  projection item ID/版本/组织作用域/source refs 成立；客户端越权治理字段被拒绝。
- headless Chrome：preview `2`、candidate `1`、confirm `1`，正式 V2 回读 PASS。
- 两轮 import batch digest：
  `f15d0efe63173b1b6c72b5b4cf4681673cf29e4536fe600e3d92066e52781750`。
- 两轮对象指纹：
  `e48dc6542db65593bb3830eda9cebad425d54b756d34a1ce469b88931eef6b88`。
- 帐号/载体/作用域回读：`10/20/30/40`；6 个合同组织、31 条区域/门店资料、
  34 个 V2 projection item、28 个区域/门店 projection item、4 个 J、2 个授权、
  30 个 qualification 均可回读。

## 3. 媒体解锁、P5 与 digest

- 授权：`ATT-MEDIA-20260808-01`，作用域
  `internal_demo_and_demo_tenant_operation`。
- 十项门终态：PASS(scope) `26` / FAIL `0` / QUARANTINED `0`。四道权利门引用
  attestation，其余六道保持原实测结果。
- 媒体 manifest digest：
  - 解锁前：`ab81e01fba2a83880c6d5ce38907cab849b60420a1f8fac2b181ddc34ca71a52`
  - 解锁后：`587d821315d896c414b382a1f277a07e1f7290f95cb8e0d829334cc53efc335b`
- 隔离库媒体回读 digest：
  `bcd3b3ac435e8e319b4b77e4597fded39c108085cfee125cfb7235c677cd37a0`；asset `26`，正式绑定 `6`。
- P5 资格：原片 `0`，母版 `6`，覆盖 `DIYU-CSPU-001/006/008/013` 四个正式商品。
  “26 份母版存储”不等于“26 份商品绑定”。

## 4. 唯一候选、CI 和冻结项

- runtime candidate SHA：`997e6b55c1c40dacd44a46ff6617b28766011958`。
- 候选登记 digest：`a69c5c4736114cd96c0c330dd42063c36c63b86fbee562c700d253b1bef59b16`。
- Gate A manifest：`14fed12141dc3b277c09c878a2a30ef71b445ce8ea31457c0122b403aeb48a06`。
- publication projection digest：
  `cb6b2cf509c31e9864ea632449e41ff06d553e7f2ed93cf758fce7c77e978962`。
- 隔离库冻结输入指纹：
  `e3862fb84b388eb27d7df9c738fd2235705691862ef860bd3ec40d05fbe6bba2`。
- 模型 `deepseek-v4-flash`，temperature `0`，max_retries `0`。
- CI run `31292553896`：event=`workflow_dispatch`；headSha=`997e6b55…`，与远程候选一致；
  conclusion=`success`；非成功步骤=`0`。
- CI 承重既有工程回归门；Gate D 专属 scope/semantics/privacy 脚本由本地退出码承重。

## 5. 正式套件和 ledger

- 正式请求数 `6`，成功落版本的卡 `5`，失败卡 `1`，transport retry `0`，重跑 `0`。
- 第 6 卡 `S04-S04-P2` 已收到唯一 provider 响应，但触发既有硬边界：
  `WRITER_FACT_BLOCK_RESTATEMENT_REJECTED`。对应 run 为 `failed`，版本为 `null`，没有把越界
  文字当成成品提交。
- 私有证据位于
  `~/diyu-evidence-brand-matrix-gated-997e6b55c1c40dacd44a46ff6617b28766011958/`；目录权限
  `0700`，文件权限 `0600`，`SHA256SUMS` digest 为
  `146366d3a88abe168f67eae3499683aa055c2ec9252b09f733580af5eed05d58`。
- Git 仅保留脱敏证据索引、请求/响应 digest、task/run/version ID 与二元结论；raw
  response、完整 artifact、任务快照和未脱敏品牌引用未进入 Git。

## 6. 八剧本与八异常二元结果

剧本结果：

1. 总部 F/J/G：`INCOMPLETE_SUITE_ABORTED`（P1/P2/P5 三卡成功落版本，全局断言未到达）。
2. 华东资料：`INCOMPLETE_SUITE_ABORTED`（R01 P4 卡成功落版本，全局断言未到达）。
3. 杭州资料：`INCOMPLETE_SUITE_ABORTED`（S01 P4 卡成功落版本，全局断言未到达）。
4. 成都错误普通文件：`FAILED_SAFE`（事实块复述边界拒绝）。
5. 同一 SKU 四节点：`NOT_RUN_SUITE_ABORTED`。
6. 同一种子三账号：`NOT_RUN_SUITE_ABORTED`。
7. AMD v1/v2：`NOT_RUN_SUITE_ABORTED`。
8. 反馈观察：`NOT_RUN_SUITE_ABORTED`。

异常结果：

1. 过期成分口径版本对：`INCOMPLETE_SUITE_ABORTED`（旧快照冻结成立，当前任务比较未完成）。
2. 门店错误成分文件：`PASS_ZERO_PROVIDER`。
3. 同字段正式事实冲突：`PASS_ZERO_PROVIDER`。
4. 过期区域活动：`PASS_ZERO_PROVIDER`。
5. 跨门店读取：`PASS_ZERO_PROVIDER`。
6. 两名用户操作同一逻辑账号：`PASS_ZERO_PROVIDER`。
7. 私人经历单次授权：`NOT_RUN_SUITE_ABORTED`。
8. 知识更新前后两版任务：`INCOMPLETE_SUITE_ABORTED`。

## 7. 四层口径

- **已存储**：10 根账号、20 carrier、31 条资料、4 商品、4 J、2 系列、2 授权、
  30 资格、26 技术母版元数据；本次正式套件新建 6 个任务/run。
- **已进入 projection**：34 个 V2 条目，其中 28 个区域/门店条目；过期 RK-EC-08
  被生命周期阻断。
- **已被任务快照引用**：原有 7 个零模型组织任务；本次 6 个正式套件任务冻结
  同一候选合同，其中 5 个提交版本、1 个失败且无版本。
- **已进入最终成品**：5 个卡级成品版本存在；第 6 卡成品为 0；整套验收成品
  **未完成**，不能用前 5 卡代替 8/8 剧本交付。

## 8. 诚实边界与下一动作

本轮未接触生产，未 SSH/ECS，未改 alembic，未提交视频/母版二进制，未泄漏
密钥，未完成 founder 或监理独立终审。媒体资格阻断已解除；当前阻断是唯一
模型套件在既有商品事实保护边界上被拒绝。

唯一下一动作：监理独立复核私有失败证据和脱敏 ledger，然后由主控决定是否签发
新的“失败后共享根因修复 + 新候选整套重跑”指令。在新指令前不修代码、不重跑 provider、
不签发 Gate E。
