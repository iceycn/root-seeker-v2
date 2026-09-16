# Admin 登录与用户管理设计规格

**日期：** 2026-09-15  
**状态：** 已实现  
**目标版本：** `v1.2.0`  
**相关模块：** `apps/admin/`、`apps/admin-web/`、`mysql/init/`、`rootseeker/storage/`

---

## 1. 背景与目标

当前 Admin 控制台（`:8010`）页面与 `/api/*` 均无认证。内网部署下控制台可改仓库 token、大模型 key、通知渠道，任何人能打开即等于拥有运维权限。

**目标：**

1. 增加登录界面；后端用拦截器校验 Cookie，未登录不能使用 Admin。
2. 增加一张用户表和一个用户管理界面；密码禁止明文存储。
3. 允许用户修改自己的密码；禁止修改账号名。

---

## 2. 非目标（本规格不做）

- 不保护对外 API（`:8000`）的 webhook、`/cases/run-default`、Gateway token。
- 不分角色：不引入管理员 / 普通用户权限位。
- 不引入第二张会话表；登录态只存在 Admin 进程内存。
- 不做验证码、记住登录、邮箱找回、SSO、CSRF token、强制 HTTPS。
- 不改 Gateway `rootseeker/gateway/auth.py` 的 token 认证。

---

## 3. 已锁定决策

| 议题 | 选择 |
|------|------|
| 保护范围 | 仅 Admin（`:8010` 页面与 `/api/*`） |
| 权限 | 所有登录用户能力相同 |
| 首个账号 | 用户表为空时，登录页变为「创建首个账号」 |
| 会话 | `users` 表持久化 + 进程内存 session；重启需重新登录 |
| 删除 | 可删自己和别人；删光后重新走创建首个账号 |
| 存储 | 跟 `ROOTSEEKER_STORAGE_BACKEND`：mysql / sqlite / memory |
| 实现 | FastAPI 中间件拦截 + HttpOnly Cookie（随机 `session_id`） |
| 密码算法 | bcrypt；最短 8 位 |

---

## 4. 架构

认证只挂在 Admin 进程，不进入 `apps/api`。

```text
浏览器
  → FastAPI 中间件（Cookie → 内存 SessionStore）
      ├ 白名单放行
      ├ 页面无会话：302 /login
      └ API 无会话：401 JSON
  → UserStore（users 表，按 storage_backend）
```

| 单元 | 职责 | 依赖 |
|------|------|------|
| `UserStore` | 用户增删、按用户名查找、更新密码哈希 | mysql / sqlite / memory |
| `SessionStore` | `session_id → {user_id, username, expires_at}` | 进程内 dict + 锁 |
| `PasswordHasher` | bcrypt 哈希与校验；调用方永不写明文 | `bcrypt` 库 |
| 中间件 | 白名单、验 Cookie、区分页面 302 与 API 401 | SessionStore |
| Auth / Users API | 登录、bootstrap、登出、列表、创建、删除、改密 | UserStore + SessionStore |
| Admin Web | `/login`、用户管理、顶栏改密/退出 | Auth / Users API |

`UserStore` 对调用方只暴露：`list_users`、`count`、`get_by_id`、`get_by_username`、`create(username, password_hash)`、`update_password_hash(user_id, password_hash)`、`delete(user_id)`。没有改用户名的方法。

---

## 5. 数据模型

持久化只有一张表：`users`。

| 列 | 类型 | 约束 |
|----|------|------|
| `id` | VARCHAR(36) | 主键，UUID |
| `username` | VARCHAR(64) | UNIQUE NOT NULL，创建后不可改 |
| `password_hash` | VARCHAR(255) | NOT NULL，bcrypt 输出 |
| `created_at` | VARCHAR(64) | NOT NULL，UTC ISO-8601 |
| `updated_at` | VARCHAR(64) | NOT NULL，改密时更新 |

MySQL 写入 `mysql/init/01_schema.sql`，运行时仍 `CREATE TABLE IF NOT EXISTS`（与现有 admin/cron 表一致）。SQLite 使用同结构表，库文件 `data/admin/users.sqlite`。`memory` 为进程内列表，供单测与默认本地 memory 模式。

**用户名规则：** 3–64 字符，`^[A-Za-z0-9._-]+$`，大小写敏感、唯一。  
**密码规则：** 至少 8 个字符，且 UTF-8 编码不超过 72 字节（bcrypt 上限）；接口、日志、数据库、前端存储均不得出现明文；列表/详情 JSON 不得包含 `password_hash`。

**Cookie**

| 项 | 值 |
|----|----|
| 名 | `rootseeker_admin_session` |
| 值 | `secrets.token_urlsafe(32)`，仅作 session_id |
| 属性 | `HttpOnly`、`SameSite=Lax`、`Path=/`；默认不设 `Secure`（内网 HTTP） |
| 寿命 | 12 小时（Cookie `Max-Age` 与内存 `expires_at` 一致） |

进程重启后内存 session 清空，必须重新登录。过期 session 在读取时删除。删除某个用户时，清掉该 `user_id` 的全部内存 session。改密不踢当前会话，也不主动踢同账号其他会话。

---

## 6. 请求流

### 6.1 中间件白名单

以下路径不要求已登录：

- `GET /healthz`
- `GET /login`（以及登录页需要的 `GET /assets/*`）
- `GET /api/auth/status`
- `POST /api/auth/login`
- `POST /api/auth/bootstrap`
- `POST /api/auth/logout`（无 Cookie 也返回成功并清 Cookie）

其余：

- 路径以 `/api/` 开头 → 无有效会话则 `401` `{"detail":"未登录"}`
- 其他页面路由（含 `/`、`/admin`、`/users` 等现有 SPA 入口）→ `302 /login`

`/docs`、`/redoc`、`/openapi.json` 不在白名单，按页面规则跳转登录。

### 6.2 首个账号与登录

1. 打开任意需登录页面 → 中间件无 Cookie → `/login`。
2. 前端 `GET /api/auth/status` → `{ "authenticated": bool, "needs_bootstrap": bool, "user": {id, username} | null }`。
3. `needs_bootstrap === true`：表单为用户名、密码、确认密码；`POST /api/auth/bootstrap`。仅当用户表为空时由 `UserStore.create_first` 原子写入；表中已有用户则 `409`「已存在用户，请登录」。成功后建内存会话并 `Set-Cookie`。空表时若有人直接 `POST /api/auth/login`，仍返回 401「用户名或密码错误」，是否走创建流程只由 `status` + 前端决定。
4. 否则：用户名 + 密码；`POST /api/auth/login`；bcrypt 校验通过后建会话并 `Set-Cookie`。`needs_bootstrap` 时前端只展示创建表单。
5. 已登录访问 `/login`：前端跳到来源路径或 `/overview`。

登录与 bootstrap 的请求体：`{"username":"...","password":"..."}`。确认密码只在前端校验；后端只收一份 `password`。成功后进入来源路径（仅允许站内相对路径），没有则 `/overview`。

### 6.3 已登录操作

| 方法 | 路径 | 行为 |
|------|------|------|
| GET | `/api/auth/me` | 当前用户 `{id, username}` |
| POST | `/api/auth/logout` | 删当前 session，清除 Cookie |
| GET | `/api/users` | 列表，无哈希字段 |
| POST | `/api/users` | 创建用户 `{username, password}` |
| DELETE | `/api/users/{id}` | 删除；可删自己；可删最后一个 |
| POST | `/api/users/me/password` | `{old_password, new_password}` |

无任何修改 `username` 的路由或 Store 方法。

删除自己：使当前会话失效，前端回 `/login`。删光后 `needs_bootstrap` 为 `true`。

---

## 7. 错误处理

| 情况 | HTTP | `detail` |
|------|------|----------|
| 用户名或密码错误 | 401 | 用户名或密码错误 |
| 已有用户仍调用 bootstrap | 409 | 已存在用户，请登录 |
| 用户名重复 | 409 | 用户名已存在 |
| 用户名或密码不符合规则 | 400 | 具体校验说明（长度/字符集） |
| 旧密码不正确 | 400 | 旧密码不正确 |
| 新密码与旧密码相同 | 400 | 新密码不能与旧密码相同 |
| 目标用户不存在 | 404 | 用户不存在 |
| 无/过期 Cookie 调 API | 401 | 未登录 |
| 无/过期 Cookie 打开页面 | 302 | Location: `/login` |

登录失败不创建 session、不 `Set-Cookie`。不在响应或日志中回显提交的密码。不区分「用户不存在」与「密码错误」。

---

## 8. 前端

沿用现有 Ant Design，不换视觉体系。`apps/admin/main.py` 为 `/login`、`/users` 增加与其他页面相同的 SPA `FileResponse`。

**`/login`：** 独立全屏卡片，无侧栏。bootstrap 模式按钮文案「创建首个账号」；登录模式为「登录」。错误展示在卡片内。成功后进入来源路径，没有则 `/overview`。

**已登录壳子：** 侧栏「设置」下增加「用户管理」。右上角当前用户名，菜单为「修改密码」「退出」。`api()` 遇到 401 则跳 `/login`。

**用户管理 `/users`：** 表格列为用户名（只读）、创建时间、删除。无编辑账号。新建弹窗：用户名 + 密码。删除二次确认。

**改密：** 右上角弹窗：旧密码、新密码、确认新密码。只作用于当前登录用户。

密码输入框使用 `type="password"`，前端不把密码写入 `localStorage`。

---

## 9. 测试

测试文件：

- `tests/unit/apps/test_admin_user_store.py`
- `tests/unit/apps/test_admin_auth.py`

必须覆盖：

1. `create` 写入的是 bcrypt 哈希，不是明文；同一明文两次哈希不同，但都能 `checkpw`。
2. `UserStore` 没有 `update_username`；创建后 `get_by_id` 的 `username` 与创建时一致。HTTP 不提供改用户名路由。
3. 空表 bootstrap 成功并种 Cookie；有用户后再 bootstrap 返回 409；空表 `POST /api/auth/login` 返回 401。
4. 正确密码登录种 Cookie；错误密码 401 且不种 Cookie。
5. 无 Cookie 访问 `GET /api/settings` 为 401；`GET /healthz` 与 `GET /api/auth/status` 仍 200。
6. 无 Cookie 访问 `GET /overview` 为 302 且 Location 含 `/login`。
7. 任意登录用户可列表、创建、删除用户。
8. 改密必须旧密码正确；只改当前用户哈希。
9. 删除最后一个用户后 `needs_bootstrap` 为 `true`；删除自己后该 session 失效。
10. 进程内新的 `SessionStore`（模拟重启）不接受旧 `session_id`。

现有 Admin API 单测需带登录 Cookie 或走测试夹具注入 session，避免大面积 401。

---

## 10. 文件落点

| 路径 | 作用 |
|------|------|
| `apps/admin/user_store.py` | UserStore 协议与 mysql/sqlite/memory 实现 |
| `apps/admin/session_store.py` | 内存 SessionStore |
| `apps/admin/passwords.py` | bcrypt hash / verify |
| `apps/admin/auth_middleware.py` | Cookie 拦截器 |
| `apps/admin/main.py` | 挂中间件、auth/users 路由、SPA `/login` `/users` |
| `apps/admin-web/src/App.tsx` | 登录页、用户管理、顶栏、401 跳转 |
| `mysql/init/01_schema.sql` | `users` 表 |
| `pyproject.toml` | 增加 `bcrypt` 依赖 |
| `tests/unit/apps/test_admin_user_store.py` | Store 与哈希 |
| `tests/unit/apps/test_admin_auth.py` | 中间件与 HTTP 流 |

---

## 11. 升级说明（写入 v1.2.0 发布文档时）

已有 Docker MySQL 数据卷不会自动重跑 `mysql/init`。应用启动时 `CREATE TABLE IF NOT EXISTS users` 即可补表，无需手工迁移脚本。升级后第一次打开 Admin 会进入「创建首个账号」，此前无用户数据。
