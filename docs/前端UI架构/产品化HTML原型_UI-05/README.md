# UI-05 Gate A 产品语义返工原型

本目录用于创始人在正式工程实现前复核 UI-05 的产品语义。它是离线静态演示，不连接正式
接口、不保存数据，也不证明系统已经理解任意自然语言或生产页面已经更新。

## 连续评审

双击打开 [`review/index.html`](review/index.html)。评审首页先选择一条彼此独立的身份旅程；
评审壳是创始人评审工具，不是产品导航。

### 租户管理员旅程

1. [`管理概览`](product/admin-overview.html)
2. [`团队使用`](product/team-usage.html)
3. [`成员与互斥入口资格`](product/members.html)
4. [`发布账号与五段画像`](product/publishing-account.html)
5. [`品牌资料库三级范围`](product/brand-library.html)
6. [`当前可用与待补`](product/readiness.html)
7. [`管理员访问创作端被拒绝`](product/access-admin-creator.html)

### 租户用户创作旅程

1. [`选择账号、平台与自然交流`](product/creator-empty.html?account=store&platform=xiaohongshu&format=graphic)
2. [`“婆媳”人物关系开放输入`](product/creator-relationship.html?account=store&platform=xiaohongshu&format=graphic)
3. [`生成过程、V1/V2 与历史`](product/creator-generating.html?account=store&platform=xiaohongshu&format=graphic)
4. [`生成失败与恢复`](product/creator-failure.html?account=store&platform=xiaohongshu&format=graphic)
5. [`租户用户访问管理端被拒绝`](product/access-user-admin.html)

## 本轮冻结的产品合同

- 租户管理员只进入品牌管理；租户用户按资格进入内容创作和／或陈列搭配。首期同一登录账号
  不同时拥有两类入口。
- 发布账号是逻辑表达身份，平台和内容形式是该身份下的任务目标。总部账号演示抖音、小红书、
  微信视频号三个平台和四个内容目标；柯桥门店人物只显示自己获准的平台。
- 一份五段账号画像归逻辑发布账号并跨平台共享；切换平台不会换画像，也不要求重新登录。
- 普通交流只产生自然回复；内容想法不完整时只问一个最有价值的问题；第二轮要求足够后直接
  进入生成。该分支是有界代表脚本，只证明产品合同和连续旅程，不证明任意自然语言理解。
- 创作方向是可选快捷控制，恢复题材、讲法、风格、形式、系列与互动五轴；每轴可不选、可展开
  更多或搜索，也可保留自然语言自定义。人物关系不进入封闭风格枚举。
- 生成失败保留整段对话和原始输入，不伪造成品；用户只需继续补充或再试一次。
- 品牌资料库只管理品牌资料，不包含发布账号画像；可用范围统一为“品牌全员”“总部专用”
  “指定区域”，指定区域必须选择具体区域。
- 管理概览、团队使用、成员资格、账号画像、资料缺口互相衔接，但管理员不能从产品页面进入
  创作，也不能看到私人素材、私人偏好或普通用户内容正文。

## 可重放验证

在仓库根目录执行：

```bash
node docs/前端UI架构/产品化HTML原型_UI-05/review/verify-ui05-gate-a.mjs
```

结果写入 [`review/verification.json`](review/verification.json)。验证覆盖 13 份本地 HTML、
两条独立旅程、互斥入口、两个发布账号、三个平台／四个目标、普通交流与一次澄清、五轴、
“婆媳”原话、失败恢复、三级资料范围，以及 `1440×900` / `390×844` 共 24 个页面视口组合。
五个内存单点变异用于证明关键断言会在错误实现下失败。

所有资料均为演示信息，不含密码、令牌、真实私人素材或生产密钥。本轮未修改正式 React、
API、OpenAPI、数据库、认证、权限、生产配置、生产数据或资产激活状态。
