# P0-D1 RLS 加固执行记录（1B）

> **结论：无需加固——目标状态早已成立。P0-D1 是测量口径错误，不是生产缺陷。**
> 依据全部为 2026-08-07 生产实测（只读），下附可复现命令与反证。
> 本轮**未对生产做任何变更**：既然目标状态已满足，做变更只有风险没有收益。

---

## 一、P0-D1 原登记内容

> 生产容器连接角色 `diyu` 为 superuser 且 `rolbypassrls=t`，`row_security_active=f`——
> FORCE RLS 对其失效，租户隔离仅剩应用层单防线。
> 定级：**中危 · 生产加固缺口**。

## 二、实测：结论不成立

### 2.1 应用真实连接的是 `diyu_app`，不是 `diyu`

| 证据 | 实测值 |
|---|---|
| `/etc/diyu/app.env` 的 `DIYU_APP_DATABASE_URL` 角色段 | **`diyu_app`** |
| 运行容器实际加载的角色段 | **`diyu_app`** |
| `app.env` 最后修改时间 | **2026-08-05 05:29 UTC** |
| P0 核查时刻 | 2026-08-07 13:58 UTC |

`app.env` 在 P0 之前**两天**就已经是 `diyu_app`，其间无人改动。
所以这不是"P0 之后被修好了"，而是 **P0 当时就测错了对象**。

> 提取角色名用 `grep -oE '^DIYU_APP_DATABASE_URL=postgres(ql)?://[^:]+' | sed 's#.*://##'`，
> 正则在第一个 `:` 处截断，**口令永远不会被读出或打印**。

### 2.2 P0 测的是 PostgreSQL 容器的管理员，不是应用角色

P0 的连接路径是 `docker exec diyu-infra-postgres-1 psql -U "$POSTGRES_USER"`。
该容器的 `POSTGRES_USER` 恰好叫 `diyu`——**这是数据库管理员账号**，
与应用连接角色 `diyu_app` 同名前缀、实为两个角色。P0 把前者的属性写成了后者的。

### 2.3 同一次会话里的双视角对照（决定性证据）

```sql
-- 超管视角（P0 当时看到的）
SELECT current_user, row_security_active('content_accounts');
--  diyu     | f

SET ROLE diyu_app;
-- 应用真实角色视角
SELECT current_user, row_security_active('content_accounts');
--  diyu_app | t        ← RLS 对应用是生效的
```

### 2.4 隔离是真生效，不是"标志位好看"

以 `diyu_app` 身份，只改租户上下文、不加任何 `tenant_id` 谓词：

| 租户上下文 | `SELECT count(*) FROM content_accounts` |
|---|---|
| `258aa400…`（笛语服饰真实租户） | **9** |
| `00000000…`（伪造租户） | **0** |
| 超管视角全库对照 | **13** |

同一条 SQL、只换上下文 → 可见行数从 9 变 0，且都小于全库 13。
**这是隔离真正起作用的正面证据**，而不是只看一个布尔标志。

### 2.5 角色属性实测

| rolname | rolsuper | rolbypassrls | 用途 |
|---|---|---|---|
| `diyu` | t | t | **PostgreSQL 容器管理员**，非应用连接角色 |
| `diyu_app` | **f** | **f** | 应用连接角色 ✅ |
| `diyu_migrator` | f | f | 迁移 / seed 角色 |

52 张表 `relrowsecurity` 与 `relforcerowsecurity` **均为 52**（全部启用且强制）。

### 2.6 活体证据：B 层真实生成就是在这个状态下跑通的

本轮 B 层受控生成用 `--env-file /etc/diyu/app.env` 启动，即**以 `diyu_app` 身份**、
在 FORCE RLS 生效的前提下成功创建了 2 条真实内容任务。
这说明应用的 `set_config('app.tenant_id', …)` 上下文管线是正确的——
若 RLS 生效而上下文没设对，写入会直接失败而不是静默串租户。

---

## 三、对照 v1.1 与信封要求

| 要求 | 状态 |
|---|---|
| 迁移为非超管、无 BYPASSRLS 的应用角色 | **已成立**（`diyu_app`：`rolsuper=f` / `rolbypassrls=f`） |
| 执行前留存角色回退语句 | **不适用**——未做变更，无需回退 |
| 完成后必须实测 `row_security_active = t` | ✅ **实测为 `t`** |
| 不达标即回退并不得进 S4 | 达标，可进 S4 |

---

## 四、附带发现

| # | 事实 | 处置 |
|---|---|---|
| D1-a | `formal_capability_observations` 表 `diyu_app` 无 INSERT/UPDATE/DELETE 权限 | 属观测投影表，只读是设计意图；**不修**。已确认它不在内容主链写入路径上 |
| D1-b | 三个有画像的逻辑账号中，**只有 1 个**有启用的 `auth_grants` 授权 | 另两个账号有画像但当前无人可操作。非本包范围，登记给运营侧确认是否符合预期 |

---

## 五、这条记录证明不了什么

- ❌ **没有**证明应用层每一条查询都设对了租户上下文——只证明数据库层的强制隔离已生效，
  且本轮实际写入路径工作正常。逐条查询的上下文正确性属代码审查范围；
- ❌ **没有**做跨租户越权的主动渗透测试（例如伪造会话尝试读他人数据）；
  本轮只做了角色层与上下文层的只读验证；
- ❌ **没有**覆盖 `diyu_migrator` 路径（迁移与 seed 以更高权限运行，属设计意图）。

---

## 六、给监理的建议

P0-D1 应从 **「中危 · 生产加固缺口」改判为「观测 · 测量口径错误」**，
并在错误档案里记一条方法论教训：

> **用 `docker exec <db容器> psql -U $POSTGRES_USER` 测出来的 `current_user`，
> 是数据库管理员，不是应用的连接角色。** 要测应用角色，必须从
> 应用配置里取角色名，或 `SET ROLE` 后再测——否则会把 DBA 的
> `rolsuper/rolbypassrls` 属性错记到应用头上，凭空造出一个中危缺口。
