# Gate A · 素材合同交付索引

- 状态：`GATE-A IMPLEMENTED · AWAITING_SUPERVISOR_REVERIFICATION`
- manifest SHA-256：`14fed12141dc3b277c09c878a2a30ef71b445ce8ea31457c0122b403aeb48a06`
- 合同性质：只冻结分类、结构化元数据、导入边界与后续选择规则；尚未导入数据库，尚未接通
  Gate B/C 运行时消费者，尚未制作媒体母版，尚未获得 Gate A founder 最终签署。
- 权威机器合同：`import-contract.json`；确定性产物：`import-manifest.json` 与
  `import-manifest.sha256`。

## A-1—A-8

1. `01-消费通道分类表.md`：25/25 文档主通道与 30 个原子消费项的边界。
2. `02-确定性导入合同.md`：九组精确计数、无静默截断合同与 V/P/C/R 边界。
3. `03-四组J判断合同.md`：四组 J 的真实业务所有者、founder 批准位与有效条件。
4. `04-账号过渡计划.md`：现存 9 个账号的隔离库盘点槽位、十新账号和历史兼容路线。
5. `05-26条视频逐条处理表.md`：26/26 Gate D 待办；本 Gate 没有原始或母版 SHA。
6. `06-媒体授权裁决-v2.md`：对旧“四项待确认”的追加式 supersession。
7. `07-D-07关闭记录.md`：柯桥店不进矩阵、不跨店复用、不进演示导入。
8. `08-founder素材定稿签署页.md`：绑定唯一 manifest digest 的空白签署页。

## 诚实边界

- Windows 21 份原文、仓库四份参考和 `素材草案-v0` 均未修改或复制进本目录。
- 本目录没有原始视频、媒体二进制、完整私有导入 payload、凭据或个人敏感信息。
- Gate A 只定义原子选择合同。`selected_item_ids`、`excluded_item_ids` 与 `overflow_reason`
  要由 Gate B/C 每次运行实际填写；当前空数组不代表运行时已消费。
- `CI_SCOPE=existing_regression_only`：远程 CI 只能证明既有工程回归门未退化，不执行
  `scripts/gatea/**`。
