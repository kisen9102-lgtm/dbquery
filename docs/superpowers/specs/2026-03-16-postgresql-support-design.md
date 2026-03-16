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
3. 引入连接器抽象层，为未来扩展 Oracle/Redis/MongoDB 奠基
4. 用 docker-compose 添加本地 PostgreSQL 测试服务，方便开发调试
5. 不影响现有 MySQL / TiDB 功能

---

## 架构设计

### 新增：`common/connector.py`

定义抽象基类和工厂函数：

```
BaseConnector
├── get_databases() -> list[str]
├── get_tables(db: str) -> list[dict]
└── execute_sql(sql: str, db: str = '') -> tuple[list[dict], float]
    # 返回 (results, elapsed_ms)
    # results 每项结构同现有 ExecuteSqlView 返回格式

MySQLConnector(BaseConnector)   # 封装现有 pymysql 逻辑
PostgreSQLConnector(BaseConnector)  # 新增 psycopg2 实现

def get_connector(db_type, host, port, user, password) -> BaseConnector
    # 工厂函数，未知类型抛 ValueError
```

### 改造：`databases/views.py`

- `DatabaseListView`、`TableListView`、`ExecuteSqlView`、`DatabaseSearchView` 中直接操作 pymysql 的部分，替换为调用 `get_connector(db_type, ...)` 的统一接口
- `db_type` 来源：
  - 单实例操作（list/table/execute）：由前端传入 `db_type` 参数，或从 `Instance` 记录中查询
  - 搜索：从 `Instance.db_type` 字段取得
- `InstanceListView.post` / `InstanceDetailView.put`：`db_type` 合法值改为 `('mysql', 'tidb', 'postgresql')`

### PostgreSQL 数据映射

| 功能 | SQL |
|------|-----|
| 列数据库 | `SELECT datname FROM pg_database WHERE datistemplate = false AND datname NOT IN ('postgres')` |
| 过滤系统库 | 额外过滤 `pg_catalog`、`information_schema` 等 |
| 列表（public schema） | `SELECT table_name, table_type FROM information_schema.tables WHERE table_schema = 'public' ORDER BY table_type, table_name` |
| 执行 SQL | psycopg2 cursor，`cursor.description` 判断结果集，与 MySQL 分支逻辑相同 |
| 表大小 | `SELECT pg_size_pretty(pg_total_relation_size(quote_ident(table_name)))` |

### `databases/models.py`

`DB_TYPE_CHOICES` 新增 `('postgresql', 'PostgreSQL')`，新建 migration `0002_instance_add_postgresql.py`。

### `requirements.txt`

新增 `psycopg2-binary==2.9.9`（binary 版本无需本地编译，开发/生产均适用）。

### `docker-compose.yml`（测试用）

```yaml
services:
  app:
    # 现有配置不变，添加 depends_on
    depends_on:
      - postgres-test

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

> **注意**：`postgres-test` 服务仅用于本地开发调试，生产部署时不需要包含此服务。构建镜像前移除或使用独立的 `docker-compose.override.yml`。

---

## 数据流

```
前端请求 (db_type=postgresql, ip, port, ...)
    ↓
databases/views.py
    ↓ get_connector('postgresql', ip, port, user, passwd)
common/connector.py → PostgreSQLConnector
    ↓ psycopg2.connect(host, port, user, password, dbname)
目标 PostgreSQL 实例
```

---

## 只读校验

`_is_readonly_sql()` 现有逻辑基于关键字前缀，对 PostgreSQL 同样适用（SELECT/SHOW 等），无需修改。

---

## 过滤库名

PostgreSQL 系统库过滤列表（追加到现有 `FILTER_DB_NAMES`）：

```python
'postgres', 'template0', 'template1',
```

---

## 测试计划

1. docker-compose 启动 `postgres-test` 服务
2. 在实例注册表中添加 `127.0.0.1:15432 / postgresql` 实例
3. 验证：列数据库（应返回 `testdb`）
4. 验证：列表（testdb 下的 public schema 表）
5. 验证：执行 `SELECT version()`、多语句、非只读语句被 query 角色拒绝
6. 验证：MySQL/TiDB 实例功能不受影响

---

## 不在范围内

- PostgreSQL 集群拓扑查询（primary/replica 状态）
- Schema 多层级导航（固定使用 public schema）
- 连接池（与现有 MySQL 行为一致，按需创建短连接）
