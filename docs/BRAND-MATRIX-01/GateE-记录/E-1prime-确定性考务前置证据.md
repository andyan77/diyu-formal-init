# BRAND-MATRIX-01 · E-1' 确定性考务前置证据

状态：`PASS · AWAITING_SUPERVISOR_REVERIFICATION`

## Readiness dry-run

- 考务合同：`brand-matrix-exam-administration-v2`。
- B11：输入与 E-2 审计 JSON 逐字一致；操作员绑定 `DIYU-CSPU-008/DIYU-V-011` 与
  `DIYU-CSPU-001/DIYU-V-001`；两份母版均由冻结媒体台账复核为 `PASS` 且 P5 资格为真。
- B12、B16：输入逐字一致；均绑定 `DIYU-CSPU-008`。
- 三卡绑定解析：`3/3 PASS`；provider request：`0`。
- readiness 输出 SHA256：`002c67b01bf88e67f939e15a1ad59cf9da6f217051b9d98cac22cb1aea39b5ee`。

## 隔离库与负向套件

- 数据库性质：本地隔离库；schema `20260818_45`；生产接触 `0`。
- 导入 batch digest：`961e33d93b4b504318c5b9531064574a34ab5e6d2b5362f76c22ca19e3389088`。
- 对象指纹：`03c572b79ee0ef36e5852a2c9657abb484ff318dc11c38d492007b48fee1ec28`。
- 含品控扩展的确认投影 digest：`cba9c56bed7fb4f5eb5569a99ae3953f9f4daf4188f34d607383d4d98117a938`。
- `NEG-H04-P2-MISSING-QUALITY`：H04 品控使命题绑定测试专用、无品控记录的合成商品，正式服务在
  provider 前返回补料问句，且明确不自动退化为商品介绍。
- `NEG-P5-MISSING-BINDINGS`：P5 缺两商品/两母版绑定时在 provider 前返回补选问句。
- 两例合计 provider request：`0`；运行前后 task/run/version 均为 `1/1/1`，差分 `0/0/0`。
- 负向套件输出 SHA256：`5df573fbc90c6cc8a6d14958fc1c3dd86a89e252d6edcd47b4cb80149357f1f8`。

## 判定器边界

- 四门独立分账：`machine_hard`、`structure`、`high_risk_fact_boundary`、
  `first_draft_usable`。
- 前三门按冻结契约逐项判定；`first_draft_usable` 始终输出 `PENDING_HUMAN`，执行端不自评。
- 正向夹具证明三卡合同形证据 `3/3 PASS`；反向夹具证明把未确认的纯棉成分写成确定事实时，
  高风险事实边界为 `FAIL`。

本证据只证明考务绑定、确定性前置和 oracle 可执行，不证明三张真实模型成品已通过；真实成品只在
八对象冻结后各请求一次。
