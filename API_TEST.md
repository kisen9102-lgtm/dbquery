# dbquery 接口测试文档

> **Base URL**: `http://127.0.0.1:8000`
> **鉴权**: 所有 `/databases/` 和 `/accounts/api/` 接口均需 Session 登录，curl 测试需先获取 Cookie 和 CSRF Token。

---

## 准备：登录并获取 Cookie / CSRF Token

```bash
# 1. 获取登录页 CSRF Token
CSRF=$(curl -sc /tmp/dbs_cookie.txt "http://127.0.0.1:8000/accounts/login/" \
  | grep -o 'csrfmiddlewaretoken" value="[^"]*"' | cut -d'"' -f3)

# 2. 登录（替换 admin/admin123 为实际账号）
curl -sb /tmp/dbs_cookie.txt -c /tmp/dbs_cookie.txt \
  -X POST "http://127.0.0.1:8000/accounts/login/" \
  -d "username=admin&password=admin123&csrfmiddlewaretoken=${CSRF}" \
  -H "Referer: http://127.0.0.1:8000/accounts/login/"

# 3. 后续请求读取 Cookie 文件（-b），写操作还需带 X-CSRFToken header
CSRFTOKEN=$(grep csrftoken /tmp/dbs_cookie.txt | awk '{print $NF}')
```

---

## 角色说明

| 角色 | 说明 |
|------|------|
| root | Django superuser，无限制 |
| admin | profile.role = 'admin'，可管理用户/组/实例 |
| query | 默认角色，只能执行只读 SQL，只能访问所在实例组的实例 |

---

## 数据库模块 `/databases/`

### 1. 数据库列表 `GET /databases/`

查询目标实例的数据库列表，支持 MySQL / TiDB / PostgreSQL / Redis / MongoDB。

**参数（二选一）**:
- `instance_id`：实例注册表中的 ID（所有角色可用，需在权限组内）
- `ip` + `port`：仅 root 可用

```bash
# 通过 instance_id
curl -sb /tmp/dbs_cookie.txt \
  "http://127.0.0.1:8000/databases/?instance_id=1"

# root 通过 ip+port（可选带账号）
curl -sb /tmp/dbs_cookie.txt \
  "http://127.0.0.1:8000/databases/?ip=127.0.0.1&port=3306"
```

**期望返回**:
```json
{"error": false, "message": "", "db_names": ["ops_db", "test"]}
```

---

### 2. 表列表 `GET /databases/tables/`

查询指定数据库的表和视图列表。

| 参数 | 必填 | 说明 |
|------|------|------|
| db | 是 | 数据库名 |
| instance_id | 否 | 实例 ID（与 ip+port 二选一） |
| ip / port | 否 | 仅 root 可用 |

```bash
curl -sb /tmp/dbs_cookie.txt \
  "http://127.0.0.1:8000/databases/tables/?instance_id=1&db=ops_db"
```

**期望返回**:
```json
{"error": false, "tables": [{"name": "t_orders", "type": "table"}, ...]}
```

---

### 3. 执行 SQL `POST /databases/execute_sql/`

执行 SQL 语句。query 角色仅允许只读语句（SELECT / SHOW / DESCRIBE / EXPLAIN / USE）。

| 参数 | 必填 | 说明 |
|------|------|------|
| sql | 是 | SQL 语句 |
| db | 否 | 数据库名 |
| instance_id | 否 | 实例 ID（与 ip+port 二选一） |
| ip / port | 否 | 仅 root 可用 |

```bash
curl -sb /tmp/dbs_cookie.txt \
  -X POST "http://127.0.0.1:8000/databases/execute_sql/" \
  -H "Content-Type: application/json" \
  -H "X-CSRFToken: ${CSRFTOKEN}" \
  -d '{"instance_id": 1, "db": "ops_db", "sql": "SELECT 1"}'
```

**期望返回**:
```json
{"error": false, "results": [{"columns": ["1"], "rows": [["1"]]}], "elapsed_ms": 3}
```

---

### 4. 数据库搜索 `GET /databases/search/`

按数据库名或 IP+端口跨实例查询数据库信息。

| 参数 | 必填 | 说明 |
|------|------|------|
| db_name | 否 | 数据库名（query 角色必填） |
| ip / port | 否 | 仅 root/admin 可通过 ip+port 筛选 |

```bash
curl -sb /tmp/dbs_cookie.txt \
  "http://127.0.0.1:8000/databases/search/?db_name=ops_db"
```

**期望返回**:
```json
{"error": false, "results": [{"id": 1, "remark": "本地测试", "env": "test", "db_type": "mysql", "db_name": "ops_db", "table_count": 5, "size_mb": 0.1}]}
```

---

### 5. 实例注册表 `/databases/instances/`

#### GET — 列出实例

```bash
curl -sb /tmp/dbs_cookie.txt "http://127.0.0.1:8000/databases/instances/"
```

root 返回含 ip/port 字段，query 角色只返回所在组的实例且不含 ip/port。

#### POST — 新增实例（admin/root）

| 参数 | 必填 | 说明 |
|------|------|------|
| ip | 是 | 实例 IP |
| port | 是 | 端口 |
| remark | 否 | 备注（默认为 ip） |
| env | 否 | 环境标签，默认 `test` |
| db_type | 否 | `mysql`/`tidb`/`postgresql`/`redis`/`mongodb`，默认 `mysql` |
| auth_username | 否 | 认证用户名（Redis/MongoDB 使用） |
| auth_password | 否 | 认证密码 |
| auth_source | 否 | 认证数据库（MongoDB） |

```bash
curl -sb /tmp/dbs_cookie.txt \
  -X POST "http://127.0.0.1:8000/databases/instances/" \
  -H "Content-Type: application/json" \
  -H "X-CSRFToken: ${CSRFTOKEN}" \
  -d '{"ip": "127.0.0.1", "port": 3306, "remark": "本地MySQL", "env": "test", "db_type": "mysql"}'
```

**期望返回** (201):
```json
{"id": 1, "remark": "本地MySQL", "ip": "127.0.0.1", "port": 3306, "env": "test", "db_type": "mysql", "auth_username": "", "auth_source": ""}
```

#### PUT — 修改实例（admin/root）`/databases/instances/<id>/`

```bash
curl -sb /tmp/dbs_cookie.txt \
  -X PUT "http://127.0.0.1:8000/databases/instances/1/" \
  -H "Content-Type: application/json" \
  -H "X-CSRFToken: ${CSRFTOKEN}" \
  -d '{"remark": "新备注", "env": "prod"}'
```

#### DELETE — 删除实例（admin/root）`/databases/instances/<id>/`

```bash
curl -sb /tmp/dbs_cookie.txt \
  -X DELETE "http://127.0.0.1:8000/databases/instances/1/" \
  -H "X-CSRFToken: ${CSRFTOKEN}"
```

---

## 账号模块 `/accounts/`

### 6. 当前用户信息 `GET /accounts/api/me/`

```bash
curl -sb /tmp/dbs_cookie.txt "http://127.0.0.1:8000/accounts/api/me/"
```

**期望返回**:
```json
{"id": 1, "username": "admin", "role": "root", "is_admin_or_root": true}
```

---

### 7. 用户管理 `/accounts/api/users/`

#### GET — 列出用户（admin/root）

```bash
curl -sb /tmp/dbs_cookie.txt "http://127.0.0.1:8000/accounts/api/users/"
```

#### POST — 新增用户（admin/root）

| 参数 | 必填 | 说明 |
|------|------|------|
| username | 是 | 用户名 |
| password | 是 | 密码（至少 6 位） |
| role | 否 | `admin` 或 `query`（默认 query；创建 admin 仅 root 可操作） |

```bash
curl -sb /tmp/dbs_cookie.txt \
  -X POST "http://127.0.0.1:8000/accounts/api/users/" \
  -H "Content-Type: application/json" \
  -H "X-CSRFToken: ${CSRFTOKEN}" \
  -d '{"username": "alice", "password": "alice123", "role": "query"}'
```

#### PUT — 修改用户 `/accounts/api/users/<id>/`（admin/root）

可修改 `username`、`role`、`password`（空则不改），不能修改超级用户。

#### DELETE — 删除用户 `/accounts/api/users/<id>/`（仅 root）

---

### 8. 用户组管理 `/accounts/api/groups/`

#### GET — 列出组

admin/root 返回所有组；query 角色只返回自己所在的组。

#### POST — 新增组（admin/root）

```bash
curl -sb /tmp/dbs_cookie.txt \
  -X POST "http://127.0.0.1:8000/accounts/api/groups/" \
  -H "Content-Type: application/json" \
  -H "X-CSRFToken: ${CSRFTOKEN}" \
  -d '{"name": "dev-team", "description": "开发组"}'
```

#### PUT — 修改组 `/accounts/api/groups/<id>/`（admin/root）

修改 `name` / `description`。

#### DELETE — 删除组 `/accounts/api/groups/<id>/`（仅 root）

---

### 9. 组成员管理 `/accounts/api/groups/<id>/members/`

#### POST — 添加成员（admin/root）

```bash
curl -sb /tmp/dbs_cookie.txt \
  -X POST "http://127.0.0.1:8000/accounts/api/groups/1/members/" \
  -H "Content-Type: application/json" \
  -H "X-CSRFToken: ${CSRFTOKEN}" \
  -d '{"user_id": 2}'
```

#### DELETE — 移除成员 `/accounts/api/groups/<id>/members/<user_id>/`（admin/root）

```bash
curl -sb /tmp/dbs_cookie.txt \
  -X DELETE "http://127.0.0.1:8000/accounts/api/groups/1/members/2/" \
  -H "X-CSRFToken: ${CSRFTOKEN}"
```

---

### 10. 组内实例管理 `/accounts/api/groups/<id>/instances/`

#### POST — 添加实例到组（admin/root）

```bash
curl -sb /tmp/dbs_cookie.txt \
  -X POST "http://127.0.0.1:8000/accounts/api/groups/1/instances/" \
  -H "Content-Type: application/json" \
  -H "X-CSRFToken: ${CSRFTOKEN}" \
  -d '{"ip": "127.0.0.1", "port": 3306}'
```

#### DELETE — 从组移除实例（admin/root）

```bash
curl -sb /tmp/dbs_cookie.txt \
  -X DELETE "http://127.0.0.1:8000/accounts/api/groups/1/instances/" \
  -H "Content-Type: application/json" \
  -H "X-CSRFToken: ${CSRFTOKEN}" \
  -d '{"ip": "127.0.0.1", "port": 3306}'
```

---

## 接口状态总览

| 接口 | 方法 | 最低角色 | 说明 |
|------|------|----------|------|
| `/databases/` | GET | query | 需 instance_id 或 root 用 ip+port |
| `/databases/tables/` | GET | query | 同上 |
| `/databases/execute_sql/` | POST | query | query 角色只允许只读 SQL |
| `/databases/search/` | GET | query | query 角色只能按 db_name 搜索 |
| `/databases/instances/` | GET | query | query 只看所在组的实例 |
| `/databases/instances/` | POST | admin | 新增实例 |
| `/databases/instances/<id>/` | PUT/DELETE | admin | 修改/删除实例 |
| `/accounts/api/me/` | GET | query | 当前用户信息 |
| `/accounts/api/users/` | GET/POST | admin | 列出/新增用户 |
| `/accounts/api/users/<id>/` | PUT | admin | 修改用户（创建 admin 仅 root） |
| `/accounts/api/users/<id>/` | DELETE | root | 删除用户 |
| `/accounts/api/groups/` | GET | query | query 只看自己的组 |
| `/accounts/api/groups/` | POST | admin | 新增组 |
| `/accounts/api/groups/<id>/` | PUT | admin | 修改组 |
| `/accounts/api/groups/<id>/` | DELETE | root | 删除组 |
| `/accounts/api/groups/<id>/members/` | POST | admin | 添加成员 |
| `/accounts/api/groups/<id>/members/<uid>/` | DELETE | admin | 移除成员 |
| `/accounts/api/groups/<id>/instances/` | POST/DELETE | admin | 组内实例增删 |
