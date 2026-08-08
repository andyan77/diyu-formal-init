# BRAND-MATRIX-01 · Gate D 执行证据与媒体阻断报告

状态：**`GATE-D EVIDENCE_BLOCKED · MEDIA_QUALIFICATION_INSUFFICIENT`**。

本报告是执行侧证据，不是监理独立复验或 founder 逐篇终审。Gate D 未达到 IMPLEMENTED。

## 1. 前置与隔离

- 当前分支为 `exe/brand-matrix-d`；与远端主线 merge-base 为
  `bd5a6bfac1c196f059242e5f42fe6c5efbec5b06`，`c913a1d38a522ecfed790b75ee822cb82f96fad8`
  是远端主线祖先。
- Prompt 5 rev3 冻结文件 SHA-256 为
  `e118e903b8cb9c00f133065ac6b381b48731697ec15dc2bc0f6334f926687178`。
- 原片 26/26、SHA256SUMS 26/26、文件名 stems 与 Gate A declared_identifier 集合一致；
  ffmpeg、ffprobe、本地 PG 与三个 DEEPSEEK 键存在性检查通过。
- 模型/provider request `0`，生产/SSH/ECS/生产数据库接触 `0`；未 source `.env`，密钥值未
  输出、记录或提交。

## 2. D0 正式纵向

- React/API 可预览、保存、确认并回读 `brand-publication-projection-v2`；客户端只提交来源、
  用途、可见范围、获准组织、时效和受控事实主题，tenant/brand/版本/权威/source digest 由
  服务端按当前上下文和来源派生。
- 正式仓储纵向完成：候选预览 → 保存 → 管理员确认 → 正式任务选择 → 任务快照冻结真实
  projection item ID、版本、digest、组织作用域和 source refs。
- headless Chrome 结果：preview `2`、candidate `1`、confirm `1`，回读当前版本 PASS。
- 反馈经正式 API/仓储进入 append-only 候选观察层；后续任务仍只读取确认投影，观察 ID 不
  进入正式 source refs。authorization/qualification 状态可经正式管理查询回读。

## 3. 两轮导入与正式消费者

- 两轮 batch digest 均为
  `f15d0efe63173b1b6c72b5b4cf4681673cf29e4536fe600e3d92066e52781750`。
- 两轮对象指纹均为
  `e48dc6542db65593bb3830eda9cebad425d54b756d34a1ce469b88931eef6b88`。
- 精确盘点：逻辑根账号 `10`、carrier `20`、矩阵账号行 `30`、平台/形式目标 `40`、旧账号
  归档隐藏 `9`、组织 `6`、区域/门店资料 `31`、深度商品 `4`、J `4`、系列 `2`、人物授权
  `2`、qualification `30`。
- V2 projection item `34`，其中区域/门店条目 `28`；31 条的其余不可发布项只存储并保留
  不消费理由。过期 RK-EC-08 已登记但新任务消费 `0`。
- H01、R01、R02、S01、S02、S03、S04 共 `7` 个零模型正式任务分别冻结实际 projection
  item；总部、华东、四川、杭州、湖州、成都正向成立，兄弟区域/门店泄漏 `0`。
- 四组 J 均被 P1 与 P2 决策依据实际引用。PS-S02-05、PS-S04-03 均实证失败释放、V1 一次
  核销、同谱系 V2 不二次核销、第二独立任务拒绝。

## 4. 媒体与 P5 硬停止

- 26/26 技术母版已生成，源 SHA、母版 SHA、ffprobe、标识位置和处理版本逐条登记；二进制
  只留在执行工作树 `var/`，未进入 Git。
- 媒体 manifest digest：
  `ab81e01fba2a83880c6d5ce38907cab849b60420a1f8fac2b181ddc34ca71a52`。
- 十项门结果：PASS `0`、FAIL `0`、QUARANTINED `26`。缺口是逐文件人物/儿童、第三方元素、
  平台权利和有效期等证据不完整；founder 一揽子裁决没有被错误当成第三方权利证据。
- 原片 P5 eligibility `0`；母版 P5 eligibility `0`。Gate A 仅有 `16` 行候选商品绑定声明，
  涉及 `14` 个候选商品；正式 PASS 母版商品绑定为 `0`。因此“26 个技术母版完成”不等于
  “26 个可发布母版”或“26 个商品绑定”。
- P5 task/run/version 为 `0/0/0`，P5 Writer/provider request 为 `0`。不足两份分别绑定不同
  正式商品的 PASS 母版，按补正条款必须停止。

## 5. 八剧本、八异常与四层口径

- 八剧本和八异常的机制级结果见 `scenario-anomaly-status.json`；确定性机制证据不能替代
  正式模型成品二元验收。
- 正式模型套件结果为 `NOT_RUN`，因此八剧本不是 `8/8 PASS`，八异常也不报正式 `8/8`。
- 已存储：10 根账号、20 carrier、31 条资料、4 商品、4 J、2 系列、2 授权、30 资格、26
  技术母版元数据。
- 已进入 projection：34 个 V2 条目；其中区域/门店 28 个，过期条目由生命周期阻断。
- 已被任务快照引用：7 个组织正向零模型任务，以及两条授权任务谱系；每项均冻结实际来源
  ID/版本/digest。
- 已进入最终成品：`0`。没有 provider 请求，没有把确定性 stub 版本冒充正式成品。

## 6. 证据索引与诚实边界

- `import-rehearsal-evidence.json`：两轮导入、对象指纹与正式管理回读。
- `formal-consumer-evidence.json`：组织任务快照、J 实际依据、两条授权状态机。
- `media-master-manifest.json`：26 个源/母版 checksum、ffprobe、十项门与 P5 资格。
- `d0-chrome-evidence.json`：正式 React V2 预览/保存/确认/回读。
- `scenario-anomaly-status.json`：机制结果与未运行的正式模型套件状态。

本 Gate 没有接触生产，没有部署，没有导入生产数据库，没有运行真实模型，没有完成 P5，
没有进行 founder 或监理独立终审。唯一下一动作是监理复核媒体证据缺口；在取得逐文件完整
权利证据并形成至少两份不同正式商品的 PASS 母版后，按新候选完整重跑确定性门、CI 与正式
模型套件，不得在当前证据上补写 IMPLEMENTED。
