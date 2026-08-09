# Provider 端点统一裁决 · AUTH-PROVIDER-ENDPOINT-20260809-01

- 裁决日期：2026-08-09
- 裁决人：founder／用户
- 状态：`USER_CONFIRMED`
- 消费里程碑：BRAND-MATRIX-01 Gate D 续行与后续 provider 运行约束

## 用户原话

> 授权使用deep seek官方端点，同时将这个裁决作为后续统一裁决，遇到类似问题不再打架

## 统一裁决

1. 笛语项目当前正式 DeepSeek provider 端点统一为官方主机
   `api.deepseek.com`。
2. `f783c37` 与 `UNLOCK-D-RERUN-07` 中将当前端点限定为 `*.aliyuncs.com` 的
   端点识别，就“当前应连哪个 provider 主机”而言，被本裁决追加式取代。
   历史失败证据和当时结论保留，不回改。
3. 后续不得仅因旧文档记载了其他主机，与已授权的
   `api.deepseek.com` 配置互相否定或再次触发同类端点冲突。
4. provider 连接仍必须经由 `src/tool/llm_gateway/`，从授权环境的精确键取值；
   密钥不回显、不入证据、不入 Git。
5. 官方端点仍执行 `trust_env=False`、套件前 TCP/TLS 零请求握手、
   内容重试 0、传输重试最多 2 次且逐次入账。本裁决不放宽密钥、
   预算、择优、冻结 SHA 或生产隔离纪律。
6. 未来若要从 `api.deepseek.com` 切换到新 provider 或新主机，因涉及外部
   供应商、费用和运行边界，仍需新的明确授权；不得静默切换。

## 实现状态

本文只完成裁决落盘，不等于 Gate D 已续跑。现有候选 `f00e5d4…`
的握手主机白名单仍需按本裁决调整；该调整会产生新运行候选，必须重跑
确定性门、推送、CI 四查和冻结登记后，才可恢复正式套件。
