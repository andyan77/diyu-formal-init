# EXE-V1 · 生产部署 runbook（不可变镜像口径）

> 适用：把主线候选版本部署进 ECS 生产，并在出事时可确定性回退。
> 口径：**不可变镜像**——先在受控主机上 clean build 出一个绑定 SHA 的镜像，
> 记录其 digest，然后按 digest 切换容器。**不在生产 checkout 上做破坏性 pull/reset**。
> 本文命令级可复跑；主机名、用户名、密钥路径一律用变量表示，取运维端既有值，
> 不写进仓库（`DIYU_ECS_HOST` / `DIYU_ECS_USER` / `DIYU_ECS_SSH_KEY`）。

---

## 〇、现状锚点（2026-08-07T17:49:32Z 实测，`runtime_verified`）

| 项 | 实测值 |
|---|---|
| 生产部署仓 | `/opt/diyu-saas/repo`，HEAD `b12b3cbeb17c0af1b4a5452e54c4a5685adb0461`，`dirty=0` |
| 运行容器 | `diyu-m5-4-app-1`（compose project `diyu-m5-4`，service `app`） |
| 运行镜像 digest | `sha256:8281c1b59667d93a0c60ff47920a7cbd689d80554e4ef6154f9e9759a2e7e68d` |
| 镜像 label | `cc.diyu.tenant01.implementation_sha=b12b3cbeb17c0af1b4a5452e54c4a5685adb0461` |
| 容器内 env | `DIYU_RUNTIME_SHA=b12b3cbeb17c0af1b4a5452e54c4a5685adb0461` |
| release binding | `/opt/diyu-saas/releases/b12b3cb…/image-binding.json`（`build_count=1`） |
| schema revision | `20260817_44`（P0 实测；候选版本 **零迁移增量**，见 §4） |
| 健康（回环） | `/health/live` 200 · `/health/ready` 200 |
| 备份定时器 | `diyu-m5-4-backup.timer` = enabled / active |

**三者一致**：部署仓 HEAD = 镜像 label = 容器 `DIYU_RUNTIME_SHA`。这是"生产跑的到底是哪份代码"的唯一可信证明，部署后必须重新验证这三者仍然一致。

### 共享主机风险（本轮实测新增，非既往登记）

该 ECS **不是本项目专用**：同机运行 `dify-staging-*`（12 个容器，含 PostgreSQL 15 / Weaviate / Redis）、`diyu-infra-*`（PostgreSQL 16 / Qdrant / MinIO / Redis）等共 19 个容器。

> **根分区 40G，实测已用 95–96%。** 把盘写满会同时打掉其他项目的数据库。
> 因此"磁盘余量核对"是**部署前硬前置**（见 §1 步骤 0），不是可选项。

---

## 一、部署步骤（命令级）

前提：在本机（运维端）用既有密钥连接，**主机指纹必须已在 `known_hosts`**，禁止用 `accept-new` 代替身份确认。

```bash
SSH="ssh -i $DIYU_ECS_SSH_KEY -o StrictHostKeyChecking=yes -o PasswordAuthentication=no -o BatchMode=yes"
TARGET_SHA=<40 位小写完整 SHA>        # 候选版本
```

### 步骤 0 · 部署前硬前置（任一不过就不部署）

```bash
$SSH $DIYU_ECS_USER@$DIYU_ECS_HOST 'bash -s' <<'EOF'
# 0.1 回滚锚点存在且可加载
docker image inspect -f '{{.Id}}' diyu-saas:$(git -C /opt/diyu-saas/repo rev-parse HEAD)
cat /opt/diyu-saas/releases/$(git -C /opt/diyu-saas/repo rev-parse HEAD)/image-binding.json
# 0.2 生产 checkout 干净（脏就停：deploy.sh 会拒绝，且说明有人手改过）
test -z "$(git -C /opt/diyu-saas/repo status --porcelain)" && echo CLEAN
# 0.3 磁盘余量（见下方判据）
df -h /
# 0.4 配置文件存在（只看存在性与键名，不读值）
for f in /etc/diyu/app.env /etc/diyu/migrator.env; do test -f $f && echo "$f OK"; done
EOF
```

**磁盘判据**：一次部署的增量需求 = 预部署备份（实测 ~1.9 MB，可忽略）+ 新镜像独有层（~430 MB 量级）+ **构建瞬时占用**（前端 `npm ci` + `npm run build` 的中间层是大头）。

> 建议余量 **≥ 4 GB** 再开构建。低于此值先回收，回收优先级：
> ① `docker builder prune -f`（纯构建缓存，可再生，零风险）；
> ② 删除**没有 release binding 且未在运行**的历史 `diyu-saas` 镜像——
> 保留每一个 `/opt/diyu-saas/releases/` 下有 binding 的镜像，回滚协议只认 binding，
> 无 binding 的镜像本就不是可用回滚目标；
> ③ 仍不足 → **停，交 founder 裁决扩容**，不要赌构建能挤进去。

### 步骤 1 · 准备干净构建源（不碰生产 checkout）

`build_candidate.sh` 要求构建源是**恰好等于目标 SHA 且完全干净**的独立仓库，与 `/opt/diyu-saas/repo` 分离：

```bash
$SSH $DIYU_ECS_USER@$DIYU_ECS_HOST "bash -s $TARGET_SHA" <<'EOF'
set -euo pipefail
SHA="$1"
SRC=/opt/diyu-saas/build-sources/$SHA
if [ ! -d "$SRC/.git" ]; then
  install -d -m 700 /opt/diyu-saas/build-sources
  git clone --quiet https://github.com/andyan77/diyu-formal-init.git "$SRC"
fi
git -C "$SRC" fetch --quiet origin "$SHA"
umask 022
git -C "$SRC" checkout --detach --quiet "$SHA"
git -C "$SRC" checkout-index --all --force
git -C "$SRC" rev-parse HEAD
git -C "$SRC" status --porcelain | wc -l   # 必须为 0
EOF
```

### 步骤 2 · Clean build（一次性，产出 image digest）

```bash
$SSH $DIYU_ECS_USER@$DIYU_ECS_HOST \
  "/opt/diyu-saas/repo/deploy/build_candidate.sh $TARGET_SHA /opt/diyu-saas/build-sources/$TARGET_SHA"
# 标准输出即 IMAGE_DIGEST（sha256:…），记下来，后面每一步都要用
```

`build_candidate.sh` 自身的硬保证（读代码确认，非推断）：
- 拒绝非 root、拒绝非 40 位小写 SHA、拒绝脏或不等于该 SHA 的构建源；
- `flock` 串行化，**同一 SHA 已有镜像或已有 binding 就拒绝第二次构建**（build-once）；
- `--build-arg DIYU_RUNTIME_SHA` 注入 + `--label cc.diyu.tenant01.implementation_sha` 打标；
- 构建完立刻回读 digest 与 label 自校验，不一致即失败；
- 写 `releases/<sha>/image-binding.json`（0600）+ `SHA256SUMS`。

### 步骤 3 · 部署（按 digest 切换，仅上环回口）

```bash
$SSH $DIYU_ECS_USER@$DIYU_ECS_HOST \
  "/opt/diyu-saas/repo/deploy/deploy.sh $TARGET_SHA $IMAGE_DIGEST"
```

`deploy.sh` 依次做：校验 `/etc/diyu/*.env` 存在 → 生产仓 fetch + `checkout --detach`（**脏则拒绝，保护人工改动**）→ 校验候选镜像 digest 与 label 双匹配 → `backup.sh predeploy`（整库 pg_dump + 对象存储镜像）→ `migrate` → `seed` → `bootstrap`（仅首次）→ `up -d --no-build app` → 轮询 `127.0.0.1:18000/health/ready` 30 次 → 校验**实际运行容器的镜像 digest == 冻结 digest** → 装并启用备份 timer。

> ⚠️ **这里有一条我先前写错、已被 2026-08-07 实测推翻的说法，务必看清**：
>
> `deploy.sh` 确实**不修改 nginx 配置**，但这**不等于**存在"上线了还没暴露"的窗口。
> 实测：公网站点 `diyuai.cc` 本就处于 application 模式（反代到 `127.0.0.1:18000`），
> 所以 `up -d app` 把容器换掉的那一刻，**新版本立即对公网生效**。
>
> 只有当公网当前挂在**维护页**时，步骤 5 才是真正的"暴露"动作。
> 因此：**冒烟是在新版本已经对外服务的状态下做的**，兜底靠的是回滚够快
> （`rollback.sh` 按 digest 切回，秒级），不是靠一个并不存在的灰度窗口。
> 需要真正的灰度，得先 `switch_public_route.sh maintenance` 再部署，本轮未这样做。

### 步骤 4 · 上线前冒烟（在环回口做，公网仍是旧版本）

见 [冒烟记录.md](冒烟记录.md) 的冻结路由矩阵；外加：
- 三者一致复核：部署仓 HEAD == 镜像 label == 容器 `DIYU_RUNTIME_SHA` == `$TARGET_SHA`；
- 运行容器 digest == `$IMAGE_DIGEST`。

### 步骤 5 · 切公网路由

```bash
$SSH $DIYU_ECS_USER@$DIYU_ECS_HOST \
  "/opt/diyu-saas/repo/deploy/switch_public_route.sh application"
```

`switch_public_route.sh` 会先把现有 nginx 配置备份到 `/etc/nginx/diyu-m5-4-backups/<时间戳>/`，`nginx -t` 失败自动还原并退非零。

### 步骤 6 · 版本 tag

本仓当前**没有任何 release tag**（只有三个 `archive/*` 历史标记）。本 runbook 确立命名法：

```
prod/<YYYYMMDD>-<短SHA>      例：prod/20260807-95fa010
```

打法（在本机执行，指向已部署的确切提交；tag 只是人类可读的锚，**权威仍是 SHA + digest**）：

```bash
git tag -a prod/$(date -u +%Y%m%d)-$(git rev-parse --short $TARGET_SHA) $TARGET_SHA \
  -m "production deploy $TARGET_SHA image $IMAGE_DIGEST"
git push origin prod/$(date -u +%Y%m%d)-$(git rev-parse --short $TARGET_SHA)
```

**打 tag 前置**：该 SHA 必须已手工 dispatch 过一次 CI 且三件套核验通过（`headSha == 目标 SHA` / `conclusion == success` / `event == workflow_dispatch`）。

---

## 二、回滚预案

### 何时**必须**回滚（不需要再请示，出现即执行）

按 D-COMM-09 与本包刹车条款，以下任一出现即回滚：

| 触发 | 判据 |
|---|---|
| 租户隔离破裂 | 任一账号/页面看到**不属于本租户**的数据 |
| 事实性错误 | 生成内容出现无来源的商品/价格/工艺断言，或编造的人物与门店经历 |
| 疑似数据损坏 | 快照 digest 校验失败、历史版本内容被改写、append-only 表出现改写 |
| 冒烟红 | 冻结路由矩阵任一行与预期不符，或健康检查不过 |
| 安全退化 | 未授权可达受保护入口、会话串用、密钥泄漏迹象 |

> **注意区分**：出现"疑似数据损坏"时**只回滚运行时代码，不回滚数据**——
> 先停写、保留现场，数据处置单独裁决。回滚是为了止血，不是为了掩盖。

### 回滚命令

```bash
# 回到部署前锚点（本轮 = b12b3cb + 其 digest）
$SSH $DIYU_ECS_USER@$DIYU_ECS_HOST \
  "/opt/diyu-saas/repo/deploy/rollback.sh $ROLLBACK_SHA $ROLLBACK_IMAGE_DIGEST"
```

`rollback.sh` 会：校验目标镜像 digest 与 label 匹配 → 按 digest `up -d app` → 轮询健康 → 校验运行 digest → **自动把公网路由切回 application**。健康不过则公网路由保持不动并退非零。

极端情况（新旧都起不来）：

```bash
$SSH … "/opt/diyu-saas/repo/deploy/rollback.sh maintenance"   # 挂维护页并停 app，数据与镜像全留
```

### 回滚可行性的**前置条件**（每次部署前都要确认）

回滚**只在旧镜像仍在本机时可行**。`build_candidate.sh` 拒绝重复构建同一 SHA，
所以旧镜像一旦被删，回滚路径就断了（需先删 binding 才能重建，属破坏性操作）。

> 本轮实测：`/opt/diyu-saas/releases/` 有 10 条 binding，但其中
> `dffa79a2227c1f09c87985bbafdf93816146b126` 的镜像**已不在本机**——
> 说明历史上发生过未登记的镜像回收，该版本实际已不可回滚。
> 这是"binding 存在 ≠ 可回滚"的实证，故步骤 0.1 必须**同时**验 binding 与 `docker image inspect`。

### 迁移方向的回滚安全性（本轮实测）

`b12b3cb..<候选>` 的 `alembic/` 差异为**空**，两端各 44 个 revision，
`schema_revision` 保持 `20260817_44`。因此本轮回滚**不需要 schema 降级**，
旧运行时代码面对的是同一套表结构。

新增的 `task_value_assembly` 是写进既有 `business_tasks.content_context_snapshot`（jsonb）
的**新键**，属"只扩不改"。旧代码读到多出来的键不应报错——该性质由
[回滚兼容实证.md](回滚兼容实证.md) 在隔离环境实证，**实证不过不得部署**。

---

## 三、配置核对清单（只核对存在性与可达，不读值不打印值）

| # | 检查 | 命令 | 通过判据 |
|---|---|---|---|
| C1 | app 配置存在 | `test -f /etc/diyu/app.env` | 存在，`mode=600` |
| C2 | migrator 配置存在 | `test -f /etc/diyu/migrator.env` | 存在，`mode=600` |
| C3 | 必需键齐备 | `grep -oE '^[A-Z0-9_]+=' /etc/diyu/app.env` | 见下方必需键表，**只输出键名** |
| C4 | 服务可达 | `curl -sf http://127.0.0.1:18000/health/ready` | HTTP 200 |
| C5 | 公网可达 | `curl -sf https://<公网域名>/health/live` | HTTP 200 |
| C6 | 备份定时器 | `systemctl is-active diyu-m5-4-backup.timer` | `active` |
| C7 | 数据库容器在跑 | `docker ps --filter name=diyu-infra-postgres` | 有输出 |

**必需键**（2026-08-07 实测 `app.env` 实有 19 个键，与代码消费面一致）：
`DIYU_RUNTIME_MODE` `DIYU_APP_DATABASE_URL` `DIYU_SESSION_SECRET` `DIYU_GENERATOR_MODE`
`DEEPSEEK_API_BASE_URL` `DEEPSEEK_MODEL` `DEEPSEEK_API_KEY`
`DIYU_S3_ENDPOINT_URL` `DIYU_S3_BUCKET` `DIYU_S3_ACCESS_KEY_ID` `DIYU_S3_SECRET_ACCESS_KEY` `DIYU_S3_REGION`
`DIYU_LOGIN_RATE_LIMIT_PER_MINUTE` `DIYU_MODEL_GLOBAL_CONCURRENCY` `DIYU_MODEL_TENANT_CONCURRENCY`
`DIYU_MODEL_TENANT_RATE_PER_MINUTE` `DIYU_MODEL_TIMEOUT_SECONDS` `DIYU_MODEL_MAX_RETRIES` `DIYU_PUBLIC_URL`

`migrator.env` 仅 `DIYU_MIGRATOR_DATABASE_URL`；`bootstrap.env` 4 个键，且
`/etc/diyu/bootstrap-output` 实测 **ABSENT**（`deploy.sh` 据此判断是否首次 bootstrap）。

> 纪律：**任何时候都不读这些文件的值、不打印值、不回显**。上表全部只做存在性与键名判断。
> 需要密钥或配置**变更**时，属独立 founder 裁决，不在部署流程内顺手做。

---

## 四、P0-D1 RLS 加固方案（本节为**方案**；执行见 [RLS加固执行记录.md](RLS加固执行记录.md)）

### 问题（P0 实测）

生产容器连接角色 `diyu` 是 **superuser 且 `rolbypassrls=t`**，导致 `row_security_active=f`。
本仓所有租户表都写了 `FORCE ROW LEVEL SECURITY`，但对 BYPASSRLS 角色**一律失效**——
租户隔离实际只剩应用层单防线。全库 13 个 `content_accounts` 里 4 个属演示租户，
一条忘了加 `tenant_id` 谓词的查询就会串租户。

### 为什么这是"配置漂移"而不是"设计缺陷"（本轮代码实证）

系统**本来就是按非超管角色设计的**，三条独立证据：

1. `deploy/provision_ecs.sh:52-53` 创建的是
   `diyu_migrator` / `diyu_app`，两者均显式 `NOSUPERUSER NOCREATEDB NOCREATEROLE **NOBYPASSRLS**`；
2. 基础迁移 `20260722_01_m3_p1_rls.py:150-159` 对每张租户表 `ENABLE`+`FORCE ROW LEVEL SECURITY`，
   建 `USING (tenant_id = current_setting('app.tenant_id')::uuid)` 策略，
   并 `GRANT SELECT,INSERT,UPDATE,DELETE … TO diyu_app`；
3. 跨租户 ops 读取**全部走 `SECURITY DEFINER` 函数**（10 个迁移文件里定义），
   并 `GRANT EXECUTE … TO diyu_app`——这正是"非超管应用角色也能做受控跨租户 ops 查询"的标准做法。

也就是说：`diyu_app` 角色、策略、授权、ops 函数**都已就位**，
生产只是把连接串指到了超管 `diyu`。加固 = 把连接串换回既有的 `diyu_app`，而非新建体系。

### 步骤

**前置勘察（只读，必须先做）**——加固前要用实测数据回答三个问题：

```sql
-- Q1 diyu_app 角色是否存在、属性是否正确
SELECT rolname, rolsuper, rolbypassrls, rolcanlogin FROM pg_roles WHERE rolname IN ('diyu','diyu_app','diyu_migrator');

-- Q2 是否有任何表 diyu_app 读不到（切角色会当场炸的清单）
SELECT c.relname
FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname='public' AND c.relkind='r'
  AND NOT has_table_privilege('diyu_app', c.oid, 'SELECT');

-- Q3 是否有任何表 diyu_app 写不了
SELECT c.relname
FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname='public' AND c.relkind='r'
  AND NOT has_table_privilege('diyu_app', c.oid, 'INSERT,UPDATE,DELETE');

-- Q4 ops 函数 diyu_app 是否可执行
SELECT p.proname, has_function_privilege('diyu_app', p.oid, 'EXECUTE') AS can_exec
FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
WHERE n.nspname='public' AND p.prosecdef;
```

> Q2/Q3/Q4 **必须全部为空 / 全部 true** 才允许切换。任一有缺口 → 先补 `GRANT`（属 schema 变更，
> 需单独裁决），**不允许"先切了再看哪里报错"**。

**回退语句先落盘**（切换前就写好，放进私有证据根）：

```
# 回退 = 把 /etc/diyu/app.env 的 DIYU_APP_DATABASE_URL 改回原值并重启 app 容器。
# 原值在切换前先备份：cp -a /etc/diyu/app.env /etc/diyu/app.env.bak-<时间戳>（0600）
# 回退命令：cp -a /etc/diyu/app.env.bak-<时间戳> /etc/diyu/app.env
#           docker compose -f /opt/diyu-saas/repo/docker-compose.production.yml up -d --no-build app
```

**切换**：把 `app.env` 里 `DIYU_APP_DATABASE_URL` 的角色部分由 `diyu` 改为 `diyu_app`
（口令取运维端既有值；**全程不回显任何值**），然后重建 app 容器。

**验证（硬判据）**：以应用角色连库，在设了租户上下文的会话里实测

```sql
SELECT current_user, row_security_active('content_accounts');
```

必须得到 `diyu_app` 与 **`t`**。同时复核：
- 应用主流程可用（登录 / 列任务 / 读画像）；
- ops 跨租户入口仍可用（走 SECURITY DEFINER 函数）；
- 不带 `tenant_id` 谓词的查询**只能看到当前上下文租户**——这是加固真正生效的正面证据。

**不达标即回退**（用上面的回退语句），并停止后续阶段。

### 影响面

| 面 | 影响 |
|---|---|
| 应用读写 | 全部受 RLS 约束；任何**忘记设 `app.tenant_id` 的代码路径会从"静默串租户"变成"查不到数据"**——这是期望的失败方向（fail-closed） |
| ops 跨租户 | 不受影响（SECURITY DEFINER 函数持有定义者权限） |
| 迁移 | 不受影响（migrate/seed 用 `migrator.env` 的 `diyu_migrator`，与 app 分离） |
| 备份 | 不受影响（`backup.sh` 用 `docker exec` 进 postgres 容器以 `POSTGRES_USER` 跑 `pg_dump`） |
| 回退成本 | 改一个 env 值 + 重启容器，秒级，无数据变更 |

---

## 五、本 runbook 证明不了什么

- **没有证明**候选版本在生产真实数据下内容质量更好——本包只证明部署机制与组装机制成立。
- **没有证明**回滚在真实故障下一定成功——回滚演练是桌面推演 + 锚点可加载性实测，
  未做"真的把生产打挂再救回来"的破坏性演练。
- **没有证明**磁盘扩容后可持续——96% 占用是本轮实测现状，属需要 founder 决策的运维债。
- `scripts/tenant01_deploy_entry.sh` 的 `--action deploy|cleanup` 闸门属 **TENANT-01 里程碑**
  自己的状态机（`var/execution-control/TENANT-01`），与本包无关；其 `cleanup` 指合成数据清理，
  **不是**镜像回收。本 runbook 直接调用 `deploy/*.sh`，与 v1.1 第 5 条口径一致。
