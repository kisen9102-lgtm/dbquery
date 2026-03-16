# PostgreSQL 查询支持设计文档

**日期**: 2026-03-16
**状态**: 待实现
**范围**: 在现有 MySQL/TiDB 查询平台上增加 PostgreSQL 实例的查询能力

---

## 背景

当前项目（dbquery）支持 MySQL 和 TiDB 两种数据库类型，连接逻辑直接散落在 `databases/views.py` 中（pymysql 调用）。随着未来计划支持 Oracle、Redis、MongoDB 等多种数据库，需要引入连接器抽象层，避免 views.py 出现大量 `if db_type == ...` 分支。本次以 PostgreSQL 为契机，完成这一架构升级。

---

## 目标

1. 新增 `postgresql` 作为合法的 `db_type`
2. 支持 PostgreSQL 实例的核心三项功能：列数据库、列表（public schema）、执行 SQL
3. 支持 `DatabaseSearchView` 跨实例搜索时正确处理 PostgreSQL 实例
4. 引入连接器抽象层，为未来扩展 Oracle/Redis/MongoDB 奠基
5. **新增 `instance_id` 参数作为实例定位方式**，隐藏 ip/port 敏感信息
6. **ip/port 信息仅 root 角色可见/可用**，其他角色只能通过 `instance_id` 操作
7. 用 docker-compose 添加本地 PostgreSQL 测试服务，方便开发调试
8. 不影响现有 MySQL / TiDB 功能

---

## 架构设计

### 新增：`common/connector.py`

定义抽象基类和工厂函数：

```python
class BaseConnector:
    def get_databases(self) -> list[str]: ...
    def get_tables(self, db: str) -> list[dict]: ...
    def execute_sql(self, sql: str, db: str = '') -> tuple[list, float]: ...

class MySQLConnector(BaseConnector): ...    # 封装现有 pymysql 逻辑
class PostgreSQLConnector(BaseConnector): ...  # 新增 psycopg2 实现

def get_connector(db_type, host, port, user, password) -> BaseConnector:
    # 按 db_type 返回对应实例，未知类型抛 ValueError
```

`execute_sql` 的返回格式与现有 `ExecuteSqlView` 一致：
```python
[
  {'type': 'resultset', 'columns': [...], 'rows': [...], 'row_count': N, 'limited': bool, 'sql': str},
  {'type': 'affected', 'affected_rows': N, 'sql': str},
]
```

### 实例定位策略与 ip/port 权限控制

`DatabaseListView`、`TableListView`、`ExecuteSqlView` 支持两种定位方式，按优先级处理：

**方式一（推荐）：`instance_id`**
- 前端传 `instance_id`，后端从 `Instance` 表查出 ip/port/db_type，用户**永远看不到** ip/port
- 适用所有角色（前提：`_can_access_instance` 通过）

**方式二（仅 root）：`ip + port`**
- 前端传 `ip` + `port`，后端直接使用
- **非 root 角色调用时返回 403**，拒绝理由："ip/port 方式仅 root 角色可用，请使用 instance_id"
- 向后兼容现有 root 用户的调用方式

**`db_type` 获取**：两种方式均从 `Instance` 表读取 `db_type`。若 instance_id 方式查不到记录返回 404；若 ip+port 方式查不到则默认 `mysql`（兼容旧逻辑）。

**`InstanceListView.get` 响应中的 ip/port 可见性**：
- root 角色：返回完整字段（含 ip、port）
- admin/query 角色：响应中**隐藏 ip 和 port**，仅返回 `id`、`remark`、`env`、`db_type`

**`DatabaseSearchView` 结果中的 ip/port 可见性**：
- root 角色：返回完整 ip、port 字段
- 非 root 角色：ip 返回 `***`，port 返回 `0`（结果仍可见，但连接信息脱敏）

### 改造：`databases/views.py`

**所有直接操作 pymysql 的位置**替换为调用 `get_connector(db_type, ...)` 的统一接口：

| View | 改造要点 |
|------|---------|
| `DatabaseListView` | 优先取 `instance_id` 定位实例；无则取 `ip+port`（仅 root）；从 Instance 取 db_type，调用 `connector.get_databases()` |
| `TableListView` | 同上，调用 `connector.get_tables(db)` |
| `ExecuteSqlView` | 同上，调用 `connector.execute_sql(sql, db)` |
| `InstanceListView.get` | 非 root 角色响应中移除 `ip`、`port` 字段 |
| `InstanceListView.post` | 将硬编码校验 `if db_type not in ('mysql', 'tidb')` 改为 `('mysql', 'tidb', 'postgresql')` |
| `InstanceDetailView.put` | 同上，同一文件中有两处需同步修改 |
| `DatabaseSearchView` | 遍历实例时按 `inst.db_type` 创建对应 connector；非 root 响应中 ip 替换为 `***`，port 替换为 `0` |

新增辅助函数 `_resolve_instance(request, ip, port, instance_id)`：封装上述定位逻辑，返回 `(ip, port, db_type, instance)` 或抛异常，供三个查询 View 复用。

`_connect()` 辅助函数继续保留，由 `MySQLConnector` 内部使用，不对外暴露。

### DatabaseSearchView 的 PostgreSQL 处理

当 `inst.db_type == 'postgresql'` 时，使用以下等价查询：

**按数据库名搜索**（替代 MySQL 的 `information_schema.SCHEMATA`）：
```sql
SELECT 1 FROM pg_catalog.pg_database WHERE datname = %s AND datistemplate = false
```

**获取数据库统计**（替代 MySQL 的 `information_schema.TABLES` size 统计）：
```sql
SELECT
  COUNT(*) AS table_count,
  ROUND(pg_database_size(%s) / 1024.0 / 1024.0, 2) AS size_mb
FROM information_schema.tables
WHERE table_schema = 'public' AND table_catalog = %s
```

**列出所有业务数据库**（替代 MySQL 的 `GROUP BY TABLE_SCHEMA`）：
```sql
SELECT
  datname AS db_name,
  ROUND(pg_database_size(datname) / 1024.0 / 1024.0, 2) AS size_mb
FROM pg_catalog.pg_database
WHERE datistemplate = false AND datname NOT IN ('postgres', 'template0', 'template1')
ORDER BY datname
```
table_count 在此路径返回 `-1`（未统计，与搜索路径的代价不同），前端显示为 `-`。

### PostgreSQL 连接器实现细节

**`get_databases()`**：
```sql
SELECT datname FROM pg_catalog.pg_database
WHERE datistemplate = false AND datname NOT IN ('postgres', 'template0', 'template1')
ORDER BY datname
```

**`get_tables(db)`**：连接时指定 `dbname=db`，查询：
```sql
SELECT
  t.table_name AS TABLE_NAME,
  t.table_type AS TABLE_TYPE,
  s.n_live_tup  AS TABLE_ROWS,
  ROUND(pg_total_relation_size(quote_ident(t.table_schema) || '.' || quote_ident(t.table_name)) / 1024.0 / 1024.0, 2) AS size_mb
FROM information_schema.tables t
LEFT JOIN pg_stat_user_tables s ON s.relname = t.table_name AND s.schemaname = t.table_schema
WHERE t.table_schema = 'public'
ORDER BY t.table_type, t.table_name
```
返回字段名与 MySQL 一致（`TABLE_NAME`、`TABLE_TYPE`、`TABLE_ROWS`、`size_mb`），前端无需修改。

**`execute_sql(sql, db)`**：psycopg2 连接到指定 `db`，逐条执行，`cursor.description` 判断结果集。支持多语句（分号分割）。

**只读校验**：`_is_readonly_sql()` 现有前缀列表（`select/show/describe/desc/explain/use`）对 PostgreSQL 同样适用。已知限制：
- CTE（`WITH ... SELECT ...`）以 `WITH` 开头，query 角色将被拒绝。这是已知限制，暂不处理（复杂度高，使用频率低）。
- `TABLE tablename` 简写不在白名单，query 角色无法使用，此为预期行为。

### 默认查询账号策略

PostgreSQL 的默认账号沿用 `QUERY_DEFAULT_ACCOUNT` / `QUERY_DEFAULT_PASSWORD` 环境变量，但实际账号名由 DBA 在 PostgreSQL 实例上自行创建（通常命名为 `dbs_admin`，与 MySQL 保持一致）。docker-compose 测试服务中使用 `POSTGRES_USER=dbs_admin` 以统一账号名。

### `databases/models.py`

`DB_TYPE_CHOICES` 新增 `('postgresql', 'PostgreSQL')`，新建 migration `0002_instance_add_postgresql.py`。

### `requirements.txt`

新增 `psycopg2-binary>=2.9.10`（binary 版本无需本地编译，开发/生产均适用）。

### 过滤库名

在现有 `FILTER_DB_NAMES` 中追加：
```python
'postgres', 'template0', 'template1',
```

### `docker-compose.override.yml`（新建，测试专用）

**不修改** `docker-compose.yml`，而是新建 `docker-compose.override.yml`（docker-compose 会自动合并）：

```yaml
# docker-compose.override.yml — 仅用于本地开发调试，不提交到生产
services:
  postgres-test:
    image: postgres:16
    restart: unless-stopped
    environment:
      POSTGRES_USER: dbs_admin
      POSTGRES_PASSWORD: dbs_password
      POSTGRES_DB: testdb
    ports:
      - "15432:5432"
```

本地启动测试：`docker-compose up postgres-test` 即可。`docker-compose.yml` 保持原样，生产部署不受影响。

---

## 测试计划

1. `docker-compose up postgres-test` 启动测试 PG 实例
2. root 角色在实例注册表中添加 `127.0.0.1:15432 / postgresql`，记录返回的 `instance_id`
3. 验证：`DatabaseListView?instance_id=<id>` 返回 `['testdb']`
4. 验证：`TableListView?instance_id=<id>&db=testdb` 返回表列表
5. 验证：`ExecuteSqlView` 使用 `instance_id` 执行 `SELECT version()`、多语句、DML 被 query 角色拒绝
6. 验证：非 root 角色使用 `ip+port` 直接调用时返回 403
7. 验证：`InstanceListView` 非 root 响应中无 ip/port 字段；root 响应中有
8. 验证：`DatabaseSearchView` 结果中非 root 角色 ip 为 `***`、port 为 `0`
9. 验证：`DatabaseSearchView` 按名搜索能正确返回 PG 实例结果
10. 验证：MySQL/TiDB 实例功能不受影响（回归测试）

---

## 不在范围内

- PostgreSQL 集群拓扑查询（primary/replica 状态、WAL 延迟）
- Schema 多层级导航（固定使用 public schema）
- 连接池（与现有 MySQL 行为一致，按需创建短连接）
- CTE 的 query 角色只读豁免
- 云托管 PG 系统库过滤（如 RDS 的 `rdsadmin`）
