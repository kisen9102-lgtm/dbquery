# PostgreSQL Support + Connector Abstraction Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 dbquery 增加 PostgreSQL 查询支持，引入连接器抽象层，并强制 ip/port 仅 root 可见。

**Architecture:** 新增 `common/connector.py` 定义 `BaseConnector`/`MySQLConnector`/`PostgreSQLConnector`，工厂函数 `get_connector()` 按 db_type 路由；`databases/views.py` 新增 `_resolve_instance()` 统一处理 `instance_id`（优先）或 `ip+port`（仅 root），`_inst_to_dict_full/safe` 按角色控制 ip/port 字段可见性。

**Tech Stack:** psycopg2-binary, pymysql (现有), Django 4.2, pytest + pytest-django (测试)

---

## File Map

| 操作 | 文件 | 职责 |
|------|------|------|
| CREATE | `common/connector.py` | BaseConnector 接口 + MySQLConnector + PostgreSQLConnector + get_connector 工厂 |
| CREATE | `common/tests.py` | 连接器单元测试 + PostgreSQL 集成测试 |
| CREATE | `databases/migrations/0002_instance_add_postgresql.py` | 新增 postgresql db_type |
| CREATE | `databases/tests.py` | View 层单元测试（mock connector） |
| CREATE | `docker-compose.override.yml` | 本地 postgres:16 测试服务 |
| CREATE | `conftest.py` | pytest-django 配置，用 SQLite 覆盖测试 DB |
| MODIFY | `requirements.txt` | 新增 psycopg2-binary, pytest, pytest-django |
| MODIFY | `databases/models.py` | DB_TYPE_CHOICES 新增 postgresql |
| MODIFY | `databases/views.py` | 全面重构：connector 路由、instance_id、ip/port 权限 |

---

## Chunk 1: 基础设施

### Task 1: 添加依赖与测试基础设施

**Files:**
- Modify: `requirements.txt`
- Create: `conftest.py`
- Create: `docker-compose.override.yml`

- [ ] **Step 1: 更新 requirements.txt**

```
Django==4.2.16
djangorestframework==3.15.2
python-decouple==3.8
mysql-connector-python==8.3.0
pymysql==1.1.1
paramiko==3.4.0
netaddr==1.3.0
requests==2.32.3
gunicorn==22.0.0
psycopg2-binary>=2.9.10
pytest>=8.0
pytest-django>=4.8
```

- [ ] **Step 2: 创建 conftest.py（项目根目录）**

```python
# conftest.py
import os

# python-decouple 会从 .env 读取配置，测试环境可能没有 .env。
# 在 Django 初始化之前设置必要的环境变量，避免 decouple 抛出 UndefinedValueError。
os.environ.setdefault("SECRET_KEY", "test-secret-key-not-for-production")
os.environ.setdefault("DBS_DB_HOST", "localhost")
os.environ.setdefault("DBS_DB_PORT", "3306")
os.environ.setdefault("DBS_DB_USER", "test_user")
os.environ.setdefault("DBS_DB_PASSWORD", "test_pass")
os.environ.setdefault("DBS_DB_NAME", "test_db")
os.environ.setdefault("QUERY_DEFAULT_ACCOUNT", "dbs_admin")
os.environ.setdefault("QUERY_DEFAULT_PASSWORD", "dbs_password")
os.environ.setdefault("ALLOWED_HOSTS", "127.0.0.1,localhost")


def pytest_configure(config):
    """覆盖 DATABASES 用 SQLite :memory:，无需运行中的 MySQL 即可跑测试。"""
    from django.conf import settings
    settings.DATABASES["default"] = {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
```

- [ ] **Step 3: 创建 pytest.ini（项目根目录）**

```ini
[pytest]
DJANGO_SETTINGS_MODULE = dbquery.settings
python_files = tests.py test_*.py *_tests.py
```

- [ ] **Step 4: 创建 docker-compose.override.yml**

```yaml
# docker-compose.override.yml
# 本地开发调试用，不影响生产 docker-compose.yml
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

- [ ] **Step 5: 安装新依赖**

```bash
pip install psycopg2-binary pytest pytest-django
```

Expected: 安装成功，无报错

- [ ] **Step 6: 验证 pytest 可以运行**

```bash
cd /opt/dbquery && pytest --co -q 2>&1 | head -20
```

Expected: `no tests ran` 或空输出（没有报错）

- [ ] **Step 7: 启动 postgres-test 服务**

```bash
docker-compose up -d postgres-test
```

Expected: `postgres-test` 容器启动，`docker-compose ps` 显示 Up

- [ ] **Step 8: 验证 PostgreSQL 连通性**

```bash
python -c "import psycopg2; conn = psycopg2.connect(host='127.0.0.1', port=15432, user='dbs_admin', password='dbs_password', dbname='testdb'); print('OK'); conn.close()"
```

Expected: 输出 `OK`

- [ ] **Step 9: Commit**

```bash
git add requirements.txt conftest.py pytest.ini docker-compose.override.yml
git commit -m "chore: add psycopg2-binary, pytest, and docker-compose test postgres"
```

---

### Task 2: 更新 Instance 模型，新增 postgresql db_type

**Files:**
- Modify: `databases/models.py`
- Create: `databases/migrations/0002_instance_add_postgresql.py`

- [ ] **Step 1: 先写测试（databases/tests.py）**

```python
# databases/tests.py
from django.test import TestCase
from databases.models import Instance


class InstanceModelTest(TestCase):
    def test_db_type_choices_include_postgresql(self):
        choices = dict(Instance.DB_TYPE_CHOICES)
        self.assertIn('postgresql', choices)
        self.assertEqual(choices['postgresql'], 'PostgreSQL')

    def test_create_postgresql_instance(self):
        inst = Instance.objects.create(
            remark='test-pg', ip='127.0.0.1', port=15432,
            env='test', db_type='postgresql',
        )
        self.assertEqual(inst.db_type, 'postgresql')
        self.assertIn('postgresql', str(inst))
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
pytest databases/tests.py::InstanceModelTest -v
```

Expected: FAIL — `postgresql not in choices`

- [ ] **Step 3: 修改 databases/models.py**

```python
class Instance(models.Model):
    DB_TYPE_CHOICES = [
        ('mysql', 'MySQL'),
        ('tidb', 'TiDB'),
        ('postgresql', 'PostgreSQL'),   # 新增
    ]
    # ... 其余不变
```

- [ ] **Step 4: 生成 migration**

```bash
python manage.py makemigrations databases --name instance_add_postgresql
```

Expected: 生成 `databases/migrations/0002_instance_add_postgresql.py`

> **注意：** `choices` 变更不影响数据库列结构（无 DDL），生成的 migration 仅记录元数据变更，这是预期行为。

- [ ] **Step 5: 运行测试，确认通过**

```bash
pytest databases/tests.py::InstanceModelTest -v
```

Expected: PASS（2 tests）

- [ ] **Step 6: Commit**

```bash
git add databases/models.py databases/migrations/0002_instance_add_postgresql.py databases/tests.py
git commit -m "feat: add postgresql to Instance.db_type choices"
```

---

## Chunk 2: Connector 抽象层

### Task 3: 创建 BaseConnector + MySQLConnector

**Files:**
- Create: `common/connector.py`
- Create: `common/tests.py`

- [ ] **Step 1: 先写 MySQLConnector 单元测试（mock pymysql）**

```python
# common/tests.py
import time
from unittest.mock import MagicMock, patch
from django.test import TestCase


class MySQLConnectorTest(TestCase):
    """MySQLConnector 单元测试：mock pymysql，不需要真实 MySQL。"""

    def _make_connector(self):
        from common.connector import MySQLConnector
        return MySQLConnector('127.0.0.1', 3306, 'user', 'pass')

    @patch('common.connector.pymysql')
    def test_get_databases_filters_system_dbs(self, mock_pymysql):
        conn = MagicMock()
        cursor = MagicMock()
        cursor.__enter__ = MagicMock(return_value=cursor)
        cursor.__exit__ = MagicMock(return_value=False)
        cursor.fetchall.return_value = [
            ('information_schema',), ('myapp',), ('mysql',), ('testdb',)
        ]
        conn.cursor.return_value = cursor
        mock_pymysql.connect.return_value = conn

        c = self._make_connector()
        result = c.get_databases()

        self.assertIn('myapp', result)
        self.assertIn('testdb', result)
        self.assertNotIn('information_schema', result)
        self.assertNotIn('mysql', result)

    @patch('common.connector.pymysql')
    def test_get_tables_returns_list(self, mock_pymysql):
        conn = MagicMock()
        cursor = MagicMock()
        cursor.__enter__ = MagicMock(return_value=cursor)
        cursor.__exit__ = MagicMock(return_value=False)
        cursor.fetchall.return_value = [
            {'TABLE_NAME': 'users', 'TABLE_TYPE': 'BASE TABLE',
             'TABLE_ROWS': 10, 'size_mb': 0.1}
        ]
        conn.cursor.return_value = cursor
        mock_pymysql.connect.return_value = conn

        c = self._make_connector()
        result = c.get_tables('myapp')

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['TABLE_NAME'], 'users')

    @patch('common.connector.pymysql')
    def test_execute_sql_resultset(self, mock_pymysql):
        conn = MagicMock()
        cursor = MagicMock()
        cursor.__enter__ = MagicMock(return_value=cursor)
        cursor.__exit__ = MagicMock(return_value=False)
        cursor.description = [('id',), ('name',)]
        cursor.fetchmany.return_value = [{'id': 1, 'name': 'Alice'}]
        cursor.fetchone.return_value = None  # no more rows
        conn.cursor.return_value = cursor
        mock_pymysql.connect.return_value = conn

        c = self._make_connector()
        results, elapsed = c.execute_sql('SELECT id, name FROM users', 'myapp')

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['type'], 'resultset')
        self.assertEqual(results[0]['columns'], ['id', 'name'])
        self.assertIsInstance(elapsed, float)

    @patch('common.connector.pymysql')
    def test_execute_sql_affected(self, mock_pymysql):
        conn = MagicMock()
        cursor = MagicMock()
        cursor.__enter__ = MagicMock(return_value=cursor)
        cursor.__exit__ = MagicMock(return_value=False)
        cursor.description = None
        cursor.rowcount = 3
        conn.cursor.return_value = cursor
        mock_pymysql.connect.return_value = conn

        c = self._make_connector()
        results, _ = c.execute_sql('UPDATE users SET x=1', 'myapp')

        self.assertEqual(results[0]['type'], 'affected')
        self.assertEqual(results[0]['affected_rows'], 3)


class GetConnectorTest(TestCase):
    def test_mysql_type_returns_mysql_connector(self):
        from common.connector import get_connector, MySQLConnector
        c = get_connector('mysql', '127.0.0.1', 3306, 'u', 'p')
        self.assertIsInstance(c, MySQLConnector)

    def test_tidb_type_returns_mysql_connector(self):
        from common.connector import get_connector, MySQLConnector
        c = get_connector('tidb', '127.0.0.1', 4000, 'u', 'p')
        self.assertIsInstance(c, MySQLConnector)

    def test_postgresql_type_returns_pg_connector(self):
        from common.connector import get_connector, PostgreSQLConnector
        c = get_connector('postgresql', '127.0.0.1', 5432, 'u', 'p')
        self.assertIsInstance(c, PostgreSQLConnector)

    def test_unknown_type_raises_value_error(self):
        from common.connector import get_connector
        with self.assertRaises(ValueError):
            get_connector('oracle', '127.0.0.1', 1521, 'u', 'p')
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
pytest common/tests.py -v
```

Expected: FAIL — `ModuleNotFoundError: common.connector`

- [ ] **Step 3: 创建 common/connector.py**

```python
# common/connector.py
"""
连接器抽象层：按 db_type 路由到对应数据库连接实现。
新增数据库类型时只需：1) 新建 XxxConnector 子类；2) 在 get_connector() 中注册。
"""
import time
from abc import ABC, abstractmethod

import pymysql
import pymysql.cursors

# MySQL / TiDB 系统库过滤集（供 MySQLConnector 和 views.py 共用）
MYSQL_SYSTEM_DBS = frozenset({
    'information_schema', 'performance_schema', 'mysql', 'sys', 'test',
    'checksum', 'dba_backup', 'backup_dba', 'percona',
    '#mysql50#lost found', '#mysql50#lost+found',
    'metrics_schema', 'INFORMATION_SCHEMA', 'PERFORMANCE_SCHEMA', 'METRICS_SCHEMA',
})

# PostgreSQL 系统库过滤集
PG_SYSTEM_DBS = frozenset({'postgres', 'template0', 'template1'})


class BaseConnector(ABC):
    """目标数据库实例的操作接口，所有类型均须实现。"""

    MAX_ROWS = 1000

    @abstractmethod
    def get_databases(self) -> list:
        """返回实例上的业务数据库名列表（已过滤系统库）。"""

    @abstractmethod
    def get_tables(self, db: str) -> list:
        """
        返回指定库的表列表。
        每项含：TABLE_NAME, TABLE_TYPE, TABLE_ROWS, size_mb
        """

    @abstractmethod
    def execute_sql(self, sql: str, db: str = '') -> tuple:
        """
        执行 SQL（支持分号分隔的多语句）。
        返回 (results, elapsed_ms)。
        results 每项：
          {'type':'resultset', 'columns':[], 'rows':[], 'row_count':N, 'limited':bool, 'sql':str}
          {'type':'affected',  'affected_rows':N, 'sql':str}
        """

    @abstractmethod
    def search_databases(self, db_name: str = '') -> list:
        """
        跨实例搜索用。
        若 db_name 非空：返回 [{'db_name', 'table_count', 'size_mb'}] 或 []
        若 db_name 为空：返回所有业务库的统计列表（同字段）
        """


class MySQLConnector(BaseConnector):

    def __init__(self, host, port, user, password):
        self.host = host
        self.port = port
        self.user = user
        self.password = password

    def _connect(self, db=None):
        kwargs = dict(
            host=self.host, port=self.port,
            user=self.user, password=self.password,
            charset='utf8mb4', connect_timeout=5,
        )
        if db:
            kwargs['db'] = db
        return pymysql.connect(**kwargs)

    def get_databases(self) -> list:
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute('SHOW DATABASES')
                rows = cur.fetchall()
            return [r[0] for r in rows if r[0] not in MYSQL_SYSTEM_DBS]
        finally:
            conn.close()

    def get_tables(self, db: str) -> list:
        conn = self._connect(db)
        try:
            with conn.cursor(pymysql.cursors.DictCursor) as cur:
                cur.execute(
                    "SELECT TABLE_NAME, TABLE_TYPE, TABLE_ROWS,"
                    " ROUND(DATA_LENGTH/1024/1024, 2) AS size_mb"
                    " FROM information_schema.TABLES"
                    " WHERE TABLE_SCHEMA = %s ORDER BY TABLE_TYPE, TABLE_NAME",
                    (db,)
                )
                return list(cur.fetchall())
        finally:
            conn.close()

    def execute_sql(self, sql: str, db: str = '') -> tuple:
        conn = self._connect(db or None)
        results = []
        t0 = time.time()
        try:
            with conn.cursor(pymysql.cursors.DictCursor) as cur:
                for stmt in [s.strip() for s in sql.split(';') if s.strip()]:
                    cur.execute(stmt)
                    if cur.description:
                        columns = [d[0] for d in cur.description]
                        rows = cur.fetchmany(self.MAX_ROWS)
                        limited = cur.fetchone() is not None
                        results.append({
                            'type': 'resultset',
                            'columns': columns,
                            'rows': [list(r.values()) for r in rows],
                            'row_count': len(rows),
                            'limited': limited,
                            'sql': stmt,
                        })
                    else:
                        conn.commit()
                        results.append({
                            'type': 'affected',
                            'affected_rows': cur.rowcount,
                            'sql': stmt,
                        })
        finally:
            conn.close()
        return results, round((time.time() - t0) * 1000, 1)

    def search_databases(self, db_name: str = '') -> list:
        conn = self._connect()
        try:
            with conn.cursor(pymysql.cursors.DictCursor) as cur:
                if db_name:
                    cur.execute(
                        "SELECT SCHEMA_NAME FROM information_schema.SCHEMATA"
                        " WHERE SCHEMA_NAME = %s",
                        (db_name,)
                    )
                    if not cur.fetchone():
                        return []
                    cur.execute(
                        "SELECT COUNT(*) AS table_count,"
                        " ROUND(SUM(DATA_LENGTH+INDEX_LENGTH)/1024/1024,2) AS size_mb"
                        " FROM information_schema.TABLES WHERE TABLE_SCHEMA = %s",
                        (db_name,)
                    )
                    row = cur.fetchone() or {}
                    return [{'db_name': db_name,
                             'table_count': int(row.get('table_count') or 0),
                             'size_mb': float(row.get('size_mb') or 0)}]
                else:
                    sys_tuple = tuple(MYSQL_SYSTEM_DBS)
                    cur.execute(
                        "SELECT TABLE_SCHEMA AS db_name, COUNT(*) AS table_count,"
                        " ROUND(SUM(DATA_LENGTH+INDEX_LENGTH)/1024/1024,2) AS size_mb"
                        " FROM information_schema.TABLES"
                        " WHERE TABLE_SCHEMA NOT IN %s"
                        " GROUP BY TABLE_SCHEMA ORDER BY TABLE_SCHEMA",
                        (sys_tuple,)
                    )
                    return [{'db_name': r['db_name'],
                             'table_count': int(r.get('table_count') or 0),
                             'size_mb': float(r.get('size_mb') or 0)}
                            for r in cur.fetchall()]
        finally:
            conn.close()


class PostgreSQLConnector(BaseConnector):

    def __init__(self, host, port, user, password):
        self.host = host
        self.port = port
        self.user = user
        self.password = password

    def _connect(self, db='postgres'):
        import psycopg2
        return psycopg2.connect(
            host=self.host, port=self.port,
            user=self.user, password=self.password,
            dbname=db, connect_timeout=5,
        )

    def get_databases(self) -> list:
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT datname FROM pg_catalog.pg_database"
                    " WHERE datistemplate = false AND datname NOT IN %s"
                    " ORDER BY datname",
                    (tuple(PG_SYSTEM_DBS),)
                )
                return [r[0] for r in cur.fetchall()]
        finally:
            conn.close()

    def get_tables(self, db: str) -> list:
        import psycopg2.extras
        conn = self._connect(db)
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT
                      t.table_name  AS "TABLE_NAME",
                      t.table_type  AS "TABLE_TYPE",
                      s.n_live_tup  AS "TABLE_ROWS",
                      CASE WHEN t.table_type = 'BASE TABLE'
                           THEN ROUND(
                             pg_total_relation_size(
                               quote_ident(t.table_schema)||'.'||quote_ident(t.table_name)
                             ) / 1024.0 / 1024.0, 2)
                           ELSE NULL
                      END           AS "size_mb"
                    FROM information_schema.tables t
                    LEFT JOIN pg_stat_user_tables s
                      ON s.relname = t.table_name AND s.schemaname = t.table_schema
                    WHERE t.table_schema = 'public'
                    ORDER BY t.table_type, t.table_name
                    """
                )
                return [dict(r) for r in cur.fetchall()]
        finally:
            conn.close()

    def execute_sql(self, sql: str, db: str = '') -> tuple:
        import psycopg2
        import psycopg2.extras
        conn = self._connect(db or 'postgres')
        conn.autocommit = False
        results = []
        t0 = time.time()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                for stmt in [s.strip() for s in sql.split(';') if s.strip()]:
                    cur.execute(stmt)
                    if cur.description:
                        columns = [d[0] for d in cur.description]
                        rows = cur.fetchmany(self.MAX_ROWS)
                        limited = cur.fetchone() is not None
                        results.append({
                            'type': 'resultset',
                            'columns': columns,
                            'rows': [list(r.values()) for r in rows],
                            'row_count': len(rows),
                            'limited': limited,
                            'sql': stmt,
                        })
                    else:
                        results.append({
                            'type': 'affected',
                            'affected_rows': cur.rowcount,
                            'sql': stmt,
                        })
            conn.commit()  # 所有语句执行完后统一提交
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
        return results, round((time.time() - t0) * 1000, 1)

    def search_databases(self, db_name: str = '') -> list:
        if db_name:
            return self._search_databases_single(db_name)
        return self._search_all()

    def _search_databases_single(self, db_name: str) -> list:
        if db_name in PG_SYSTEM_DBS:
            return []
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT ROUND(pg_database_size(%s)/1024.0/1024.0,2)"
                    " FROM pg_catalog.pg_database"
                    " WHERE datname=%s AND datistemplate=false",
                    (db_name, db_name)
                )
                row = cur.fetchone()
                if not row:
                    return []
                size_mb = float(row[0] or 0)
        finally:
            conn.close()

        conn2 = self._connect(db_name)
        try:
            with conn2.cursor() as cur:
                cur.execute(
                    "SELECT COUNT(*) FROM information_schema.tables"
                    " WHERE table_schema='public'"
                )
                table_count = cur.fetchone()[0]
        finally:
            conn2.close()

        return [{'db_name': db_name, 'table_count': table_count, 'size_mb': size_mb}]

    def _search_all(self) -> list:
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT datname, ROUND(pg_database_size(datname)/1024.0/1024.0,2)"
                    " FROM pg_catalog.pg_database"
                    " WHERE datistemplate=false AND datname NOT IN %s"
                    " ORDER BY datname",
                    (tuple(PG_SYSTEM_DBS),)
                )
                rows = cur.fetchall()
        finally:
            conn.close()
        # table_count=-1 表示"未统计"，前端显示 '-'
        return [{'db_name': r[0], 'table_count': -1, 'size_mb': float(r[1] or 0)}
                for r in rows]


def get_connector(db_type: str, host: str, port: int,
                  user: str, password: str) -> BaseConnector:
    """工厂函数：按 db_type 返回对应连接器。未知类型抛 ValueError。"""
    if db_type in ('mysql', 'tidb'):
        return MySQLConnector(host, port, user, password)
    if db_type == 'postgresql':
        return PostgreSQLConnector(host, port, user, password)
    raise ValueError(f'不支持的数据库类型: {db_type}')
```

- [ ] **Step 4: 运行 MySQLConnector 和 get_connector 测试**

```bash
pytest common/tests.py -v
```

Expected: PASS（8 tests）

- [ ] **Step 5: Commit**

```bash
git add common/connector.py common/tests.py
git commit -m "feat: add connector abstraction layer with MySQLConnector"
```

---

### Task 4: PostgreSQL 连接器集成测试

> **前提：** `docker-compose up -d postgres-test` 已运行，postgres 监听在 `127.0.0.1:15432`

**Files:**
- Modify: `common/tests.py`（追加）

- [ ] **Step 1: 在 common/tests.py 追加 PostgreSQL 集成测试**

```python
# 追加到 common/tests.py 末尾
import os
import unittest
from unittest.mock import MagicMock, patch


class PostgreSQLConnectorUnitTest(TestCase):
    """PostgreSQLConnector 单元测试：mock _connect，无需运行容器。"""

    def _make_connector(self):
        from common.connector import PostgreSQLConnector
        return PostgreSQLConnector('127.0.0.1', 15432, 'u', 'p')

    def _mock_conn(self, fetchall_result=None, fetchone_result=None):
        conn = MagicMock()
        cursor = MagicMock()
        cursor.__enter__ = MagicMock(return_value=cursor)
        cursor.__exit__ = MagicMock(return_value=False)
        if fetchall_result is not None:
            cursor.fetchall.return_value = fetchall_result
        if fetchone_result is not None:
            cursor.fetchone.return_value = fetchone_result
        conn.cursor.return_value = cursor
        return conn, cursor

    def test_get_databases_returns_list(self):
        c = self._make_connector()
        conn, _ = self._mock_conn(fetchall_result=[('testdb',), ('myapp',)])
        with patch.object(c, '_connect', return_value=conn):
            result = c.get_databases()
        self.assertIn('testdb', result)
        self.assertIn('myapp', result)

    def test_search_databases_single_system_db_returns_empty(self):
        from common.connector import PG_SYSTEM_DBS
        c = self._make_connector()
        for sys_db in PG_SYSTEM_DBS:
            result = c._search_databases_single(sys_db)
            self.assertEqual(result, [], f'{sys_db} should be filtered')

    def test_search_databases_empty_calls_search_all(self):
        c = self._make_connector()
        conn, _ = self._mock_conn(
            fetchall_result=[('testdb', 1.5), ('myapp', 0.3)]
        )
        with patch.object(c, '_connect', return_value=conn):
            result = c.search_databases('')
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]['table_count'], -1)  # _search_all 不统计表数


PG_AVAILABLE = False
try:
    import psycopg2
    psycopg2.connect(
        host='127.0.0.1', port=15432,
        user='dbs_admin', password='dbs_password',
        dbname='testdb', connect_timeout=2,
    ).close()
    PG_AVAILABLE = True
except Exception:
    pass


@unittest.skipUnless(PG_AVAILABLE, "postgres-test 未运行，跳过集成测试")
class PostgreSQLConnectorIntegrationTest(TestCase):
    """需要 docker-compose up postgres-test 才能运行。"""

    def _make_connector(self):
        from common.connector import PostgreSQLConnector
        return PostgreSQLConnector('127.0.0.1', 15432, 'dbs_admin', 'dbs_password')

    def test_get_databases_returns_testdb(self):
        c = self._make_connector()
        dbs = c.get_databases()
        self.assertIn('testdb', dbs)
        # 系统库不应出现
        self.assertNotIn('postgres', dbs)
        self.assertNotIn('template0', dbs)

    def test_get_tables_empty_on_fresh_db(self):
        c = self._make_connector()
        tables = c.get_tables('testdb')
        # 新建的 testdb 无用户表
        self.assertIsInstance(tables, list)

    def test_execute_sql_select_version(self):
        c = self._make_connector()
        results, elapsed = c.execute_sql('SELECT version()', 'testdb')
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['type'], 'resultset')
        self.assertIn('PostgreSQL', results[0]['rows'][0][0])
        self.assertGreater(elapsed, 0)

    def test_execute_sql_multi_statement(self):
        c = self._make_connector()
        sql = 'SELECT 1 AS a; SELECT 2 AS b'
        results, _ = c.execute_sql(sql, 'testdb')
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]['rows'][0][0], 1)
        self.assertEqual(results[1]['rows'][0][0], 2)

    def test_search_databases_finds_testdb(self):
        c = self._make_connector()
        result = c.search_databases('testdb')
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['db_name'], 'testdb')

    def test_search_databases_not_found(self):
        c = self._make_connector()
        result = c.search_databases('nonexistent_db_xyz')
        self.assertEqual(result, [])

    def test_search_all_databases(self):
        c = self._make_connector()
        result = c.search_databases('')
        self.assertIsInstance(result, list)
        db_names = [r['db_name'] for r in result]
        self.assertIn('testdb', db_names)
```

- [ ] **Step 2: 运行集成测试**

```bash
pytest common/tests.py::PostgreSQLConnectorIntegrationTest -v
```

Expected: PASS（7 tests）

- [ ] **Step 3: 运行全部 common 测试确保无回归**

```bash
pytest common/tests.py -v
```

Expected: 全部 PASS

- [ ] **Step 4: Commit**

```bash
git add common/tests.py
git commit -m "test: add PostgreSQL connector integration tests"
```

---

## Chunk 3: Views 层重构

### Task 5: 新增辅助函数（_resolve_instance, _inst_to_dict_full/safe）

**Files:**
- Modify: `databases/views.py`
- Modify: `databases/tests.py`（追加）

- [ ] **Step 1: 先写辅助函数测试**

```python
# 追加到 databases/tests.py

from unittest.mock import patch, MagicMock
from django.contrib.auth.models import User
from rest_framework.test import APIClient
from databases.models import Instance


class ResolveInstanceTest(TestCase):

    def setUp(self):
        # root 用户
        self.root = User.objects.create_superuser('root', password='root')
        # query 用户
        self.query_user = User.objects.create_user('quser', password='quser')
        # 测试实例
        self.inst = Instance.objects.create(
            remark='pg-test', ip='127.0.0.1', port=15432,
            env='test', db_type='postgresql',
        )

    def _call(self, user, ip='', port=0, instance_id=''):
        from databases.views import _resolve_instance
        request = MagicMock()
        request.user = user
        return _resolve_instance(request, ip, port, instance_id)

    def test_instance_id_resolves_correctly(self):
        with patch('databases.views._can_access_instance', return_value=True):
            ip, port, db_type, inst = self._call(
                self.root, instance_id=str(self.inst.pk)
            )
        self.assertEqual(ip, '127.0.0.1')
        self.assertEqual(port, 15432)
        self.assertEqual(db_type, 'postgresql')

    def test_instance_id_not_found_raises(self):
        from databases.views import _resolve_instance
        request = MagicMock(); request.user = self.root
        with self.assertRaises(ValueError):
            _resolve_instance(request, '', 0, '999999')

    def test_ip_port_allowed_for_root(self):
        ip, port, db_type, _ = self._call(
            self.root, ip='127.0.0.1', port=15432
        )
        self.assertEqual(ip, '127.0.0.1')
        self.assertEqual(port, 15432)

    def test_ip_port_forbidden_for_non_root(self):
        with self.assertRaises(PermissionError):
            self._call(self.query_user, ip='127.0.0.1', port=15432)

    def test_no_params_raises_value_error(self):
        with self.assertRaises(ValueError):
            self._call(self.root)


class InstToDictTest(TestCase):

    def setUp(self):
        self.root = User.objects.create_superuser('root2', password='root2')
        self.admin = User.objects.create_user('admin2', password='admin2')
        from accounts.models import UserProfile
        UserProfile.objects.create(user=self.admin, role='admin')
        self.query_user = User.objects.create_user('quser2', password='quser2')
        self.inst = Instance.objects.create(
            remark='pg', ip='10.0.0.1', port=5432, env='prod', db_type='postgresql'
        )

    def test_full_dict_contains_ip_port(self):
        from databases.views import _inst_to_dict_full
        d = _inst_to_dict_full(self.inst)
        self.assertIn('ip', d)
        self.assertIn('port', d)

    def test_safe_dict_excludes_ip_port(self):
        from databases.views import _inst_to_dict_safe
        d = _inst_to_dict_safe(self.inst)
        self.assertNotIn('ip', d)
        self.assertNotIn('port', d)
        self.assertIn('id', d)
        self.assertIn('remark', d)
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
pytest databases/tests.py::ResolveInstanceTest databases/tests.py::InstToDictTest -v
```

Expected: FAIL — `_resolve_instance` 不存在

- [ ] **Step 3: 修改 databases/views.py — 替换 _inst_to_dict，新增辅助函数**

在 `views.py` 中找到 `_inst_to_dict` 函数（当前约第 257 行），替换为：

```python
def _inst_to_dict_full(inst):
    """含 ip/port，仅 root 使用。"""
    return {
        'id': inst.id, 'remark': inst.remark,
        'ip': inst.ip, 'port': inst.port,
        'env': inst.env, 'db_type': inst.db_type,
    }


def _inst_to_dict_safe(inst):
    """不含 ip/port，非 root 使用。"""
    return {
        'id': inst.id, 'remark': inst.remark,
        'env': inst.env, 'db_type': inst.db_type,
    }


def _inst_to_dict(inst, user=None):
    """按用户角色返回对应格式（兼容旧调用）。"""
    if user and user.is_superuser:
        return _inst_to_dict_full(inst)
    return _inst_to_dict_safe(inst)
```

在文件顶部 import 区域，新增：

```python
from common.connector import get_connector, MYSQL_SYSTEM_DBS
```

将现有的 `FILTER_DB_NAMES` 定义改为：

```python
# 保留名字供 DatabaseSearchView 用；MySQL 系统库 + PG 系统库合并
FILTER_DB_NAMES = MYSQL_SYSTEM_DBS | {'postgres', 'template0', 'template1'}
_FILTER_DB_TUPLE = tuple(FILTER_DB_NAMES)
```

在 `_can_access_instance` 函数之后新增：

```python
def _resolve_instance(request, ip, port, instance_id):
    """
    从请求参数解析目标实例，返回 (ip, port, db_type, inst_or_None)。
    优先使用 instance_id；无则用 ip+port（仅 root）。
    失败时抛 ValueError（参数错误）或 PermissionError（权限不足）。
    """
    if instance_id:
        try:
            inst = Instance.objects.get(pk=instance_id)
        except (Instance.DoesNotExist, ValueError):
            raise ValueError(f'实例 {instance_id} 不存在')
        if not _can_access_instance(request.user, inst.ip, inst.port):
            raise PermissionError('无权限访问该实例，请联系管理员')
        return inst.ip, inst.port, inst.db_type, inst

    if ip and port:
        if not request.user.is_superuser:
            raise PermissionError('ip/port 方式仅 root 角色可用，请使用 instance_id')
        try:
            inst = Instance.objects.filter(ip=ip, port=int(port)).first()
        except (TypeError, ValueError):
            inst = None
        db_type = inst.db_type if inst else 'mysql'
        return ip, int(port), db_type, inst

    raise ValueError('instance_id 或 ip+port 不能同时为空')
```

- [ ] **Step 4: 运行辅助函数测试**

```bash
pytest databases/tests.py::ResolveInstanceTest databases/tests.py::InstToDictTest -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add databases/views.py databases/tests.py
git commit -m "feat: add _resolve_instance and split _inst_to_dict by role"
```

---

### Task 6: 重构 DatabaseListView、TableListView、ExecuteSqlView

**Files:**
- Modify: `databases/views.py`
- Modify: `databases/tests.py`（追加）

- [ ] **Step 1: 先写 View 测试**

```python
# 追加到 databases/tests.py

from unittest.mock import patch
from rest_framework.test import APIClient
from django.urls import reverse


class DatabaseListViewTest(TestCase):

    def setUp(self):
        self.root = User.objects.create_superuser('root3', password='root3')
        self.quser = User.objects.create_user('quser3', password='quser3')
        self.inst = Instance.objects.create(
            remark='pg', ip='10.0.0.1', port=5432, env='test', db_type='postgresql'
        )
        self.client = APIClient()

    def test_instance_id_returns_db_list(self):
        self.client.force_authenticate(self.root)
        with patch('databases.views.get_connector') as mock_gc:
            mock_gc.return_value.get_databases.return_value = ['mydb']
            with patch('databases.views._can_access_instance', return_value=True):
                resp = self.client.get(
                    '/databases/', {'instance_id': self.inst.pk}
                )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['db_names'], ['mydb'])

    def test_ip_port_forbidden_for_query_user(self):
        self.client.force_authenticate(self.quser)
        resp = self.client.get('/databases/', {'ip': '10.0.0.1', 'port': 5432})
        self.assertEqual(resp.status_code, 403)

    def test_missing_params_returns_400(self):
        self.client.force_authenticate(self.root)
        resp = self.client.get('/databases/')
        self.assertEqual(resp.status_code, 400)


class ExecuteSqlViewTest(TestCase):

    def setUp(self):
        self.root = User.objects.create_superuser('root4', password='root4')
        self.quser = User.objects.create_user('quser4', password='quser4')
        self.inst = Instance.objects.create(
            remark='pg', ip='10.0.0.1', port=5432, env='test', db_type='postgresql'
        )
        self.client = APIClient()

    def test_execute_sql_with_instance_id(self):
        self.client.force_authenticate(self.root)
        mock_results = [{'type': 'resultset', 'columns': ['v'], 'rows': [['16']], 'row_count': 1, 'limited': False, 'sql': 'SELECT version()'}]
        with patch('databases.views.get_connector') as mock_gc:
            mock_gc.return_value.execute_sql.return_value = (mock_results, 5.0)
            with patch('databases.views._can_access_instance', return_value=True):
                resp = self.client.post('/databases/execute_sql/', {
                    'instance_id': self.inst.pk,
                    'sql': 'SELECT version()',
                }, format='json')
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.data['error'])

    def test_query_role_blocked_from_dml(self):
        self.client.force_authenticate(self.quser)
        with patch('databases.views._resolve_instance',
                   return_value=('10.0.0.1', 5432, 'postgresql', self.inst)):
            resp = self.client.post('/databases/execute_sql/', {
                'instance_id': self.inst.pk,
                'sql': 'DELETE FROM users',
            }, format='json')
        self.assertEqual(resp.status_code, 403)
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
pytest databases/tests.py::DatabaseListViewTest databases/tests.py::ExecuteSqlViewTest -v
```

Expected: FAIL（views 还未重构）

- [ ] **Step 3: 重构 DatabaseListView**

将 `DatabaseListView.get` 方法替换为：

```python
def get(self, request):
    instance_id = request.GET.get('instance_id', '').strip()
    account     = request.GET.get('account', '')
    passwd      = request.GET.get('passwd', '')
    ip          = request.GET.get('ip', '')
    port_str    = request.GET.get('port', '')
    try:
        port = int(port_str) if port_str else 0
    except (TypeError, ValueError):
        port = 0

    try:
        ip, port, db_type, inst = _resolve_instance(request, ip, port, instance_id)
    except PermissionError as e:
        return Response({'error': True, 'message': str(e), 'db_names': []},
                        status=status.HTTP_403_FORBIDDEN)
    except ValueError as e:
        return Response({'error': True, 'message': str(e), 'db_names': []},
                        status=status.HTTP_400_BAD_REQUEST)

    account, passwd = _resolve_credentials(account, passwd)
    try:
        connector = get_connector(db_type, ip, port, account, passwd)
        db_names = connector.get_databases()
        return Response({'error': False, 'message': '', 'db_names': db_names})
    except Exception as exc:
        logger.error('查询数据库列表失败 %s:%d %s', ip, port, exc)
        err_msg = str(exc)
        if 'Access denied' in err_msg or 'authentication' in err_msg.lower():
            err_msg = f'连接失败：请在目标实例上创建账号并授权。（原始错误：{err_msg}）'
        return Response({'error': True, 'message': err_msg, 'db_names': []},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR)
```

- [ ] **Step 4: 重构 TableListView**

将 `TableListView.get` 替换为：

```python
def get(self, request):
    instance_id = request.GET.get('instance_id', '').strip()
    account     = request.GET.get('account', '')
    passwd      = request.GET.get('passwd', '')
    db          = request.GET.get('db', '')
    ip          = request.GET.get('ip', '')
    port_str    = request.GET.get('port', '')
    try:
        port = int(port_str) if port_str else 0
    except (TypeError, ValueError):
        port = 0

    if not db:
        return Response({'error': True, 'message': '参数不完整', 'tables': []},
                        status=status.HTTP_400_BAD_REQUEST)

    try:
        ip, port, db_type, inst = _resolve_instance(request, ip, port, instance_id)
    except PermissionError as e:
        return Response({'error': True, 'message': str(e), 'tables': []},
                        status=status.HTTP_403_FORBIDDEN)
    except ValueError as e:
        return Response({'error': True, 'message': str(e), 'tables': []},
                        status=status.HTTP_400_BAD_REQUEST)

    account, passwd = _resolve_credentials(account, passwd)
    try:
        connector = get_connector(db_type, ip, port, account, passwd)
        tables = connector.get_tables(db)
        return Response({'error': False, 'tables': tables})
    except Exception as exc:
        logger.error('查询表列表失败 %s:%d/%s %s', ip, port, db, exc)
        err_msg = str(exc)
        if 'Access denied' in err_msg or 'authentication' in err_msg.lower():
            err_msg = f'连接失败：请在目标实例上创建账号并授权。（原始错误：{err_msg}）'
        return Response({'error': True, 'message': err_msg, 'tables': []},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR)
```

- [ ] **Step 5: 重构 ExecuteSqlView**

将 `ExecuteSqlView.post` 替换为：

```python
def post(self, request):
    data        = request.data
    instance_id = str(data.get('instance_id', '')).strip()
    account     = data.get('account', '')
    passwd      = data.get('passwd', '')
    db          = data.get('db', '')
    sql         = data.get('sql', '').strip()
    ip          = data.get('ip', '')
    try:
        port = int(data.get('port', 0))
    except (TypeError, ValueError):
        port = 0

    if not sql:
        return Response({'error': True, 'message': '参数不完整'},
                        status=status.HTTP_400_BAD_REQUEST)

    try:
        ip, port, db_type, inst = _resolve_instance(request, ip, port, instance_id)
    except PermissionError as e:
        return Response({'error': True, 'message': str(e)},
                        status=status.HTTP_403_FORBIDDEN)
    except ValueError as e:
        return Response({'error': True, 'message': str(e)},
                        status=status.HTTP_400_BAD_REQUEST)

    if _is_query_role(request.user):
        ok, bad_stmt = _is_readonly_sql(sql)
        if not ok:
            return Response(
                {'error': True,
                 'message': f'query 角色仅允许执行查询语句，禁止执行：{bad_stmt[:60]}'},
                status=status.HTTP_403_FORBIDDEN,
            )

    account, passwd = _resolve_credentials(account, passwd)
    try:
        connector = get_connector(db_type, ip, port, account, passwd)
        results, elapsed = connector.execute_sql(sql, db or '')
        return Response({'error': False, 'results': results, 'elapsed_ms': elapsed})
    except Exception as exc:
        logger.error('执行 SQL 失败 %s:%d %s', ip, port, exc)
        err_msg = str(exc)
        if 'Access denied' in err_msg or 'authentication' in err_msg.lower():
            err_msg = f'连接失败：请在目标实例上创建账号并授权。（原始错误：{err_msg}）'
        return Response({'error': True, 'message': err_msg},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR)
```

- [ ] **Step 6: 运行测试**

```bash
pytest databases/tests.py::DatabaseListViewTest databases/tests.py::ExecuteSqlViewTest -v
```

Expected: PASS

- [ ] **Step 7: 运行全部 databases 测试**

```bash
pytest databases/tests.py -v
```

Expected: 全部 PASS

- [ ] **Step 8: Commit**

```bash
git add databases/views.py databases/tests.py
git commit -m "feat: refactor DatabaseListView/TableListView/ExecuteSqlView to use connector + instance_id"
```

---

### Task 7: 更新 InstanceListView（响应字段 + db_type 校验）

**Files:**
- Modify: `databases/views.py`
- Modify: `databases/tests.py`（追加）

- [ ] **Step 1: 先写测试**

```python
# 追加到 databases/tests.py

class InstanceListViewTest(TestCase):

    def setUp(self):
        self.root = User.objects.create_superuser('root5', password='root5')
        self.quser = User.objects.create_user('quser5', password='quser5')
        self.inst = Instance.objects.create(
            remark='pg', ip='10.0.0.1', port=5432, env='test', db_type='postgresql'
        )
        self.client = APIClient()

    def test_root_sees_ip_port(self):
        self.client.force_authenticate(self.root)
        resp = self.client.get('/databases/instances/')
        self.assertEqual(resp.status_code, 200)
        item = resp.data[0]
        self.assertIn('ip', item)
        self.assertIn('port', item)

    def test_non_root_cannot_see_ip_port(self):
        self.client.force_authenticate(self.quser)
        resp = self.client.get('/databases/instances/')
        self.assertEqual(resp.status_code, 200)
        for item in resp.data:
            self.assertNotIn('ip', item)
            self.assertNotIn('port', item)

    def test_post_postgresql_db_type_allowed(self):
        self.client.force_authenticate(self.root)
        resp = self.client.post('/databases/instances/', {
            'remark': 'new-pg', 'ip': '10.0.0.2', 'port': 5433,
            'env': 'test', 'db_type': 'postgresql',
        }, format='json')
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.data['db_type'], 'postgresql')

    def test_post_invalid_db_type_rejected(self):
        self.client.force_authenticate(self.root)
        resp = self.client.post('/databases/instances/', {
            'ip': '10.0.0.3', 'port': 5434, 'db_type': 'oracle',
        }, format='json')
        self.assertEqual(resp.status_code, 400)
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
pytest databases/tests.py::InstanceListViewTest -v
```

Expected: FAIL（ip/port 当前对所有人可见，postgresql 可能被拒）

- [ ] **Step 3: 更新 InstanceListView.get**

将 `InstanceListView.get` 方法中的 `return Response(...)` 行替换为：

```python
    def get(self, request):
        qs = Instance.objects.all().order_by('id')

        if _is_query_role(request.user):
            from accounts.models import InstanceGroup
            allowed = set()
            for group in InstanceGroup.objects.filter(members=request.user):
                for item in (group.instances or []):
                    allowed.add((str(item.get('ip')), int(item.get('port', 0))))
            qs = [inst for inst in qs if (str(inst.ip), inst.port) in allowed]

        to_dict = _inst_to_dict_full if request.user.is_superuser else _inst_to_dict_safe
        return Response([to_dict(inst) for inst in qs])
```

- [ ] **Step 4: 更新 InstanceListView.post 和 InstanceDetailView.put 中的 db_type 校验**

将两处（约第 302 行和第 342 行）：
```python
if db_type not in ('mysql', 'tidb'):
```
改为：
```python
if db_type not in ('mysql', 'tidb', 'postgresql'):
```

- [ ] **Step 5: 更新 InstanceListView.post 和 InstanceDetailView.put 的返回值**

这两个端点均为 root/admin 专用，返回结果应始终包含完整字段。找到两处 `return Response(_inst_to_dict(inst),` 语句（一处在 post 末尾，一处在 put 末尾），替换为：
```python
return Response(_inst_to_dict_full(inst), ...)
```

- [ ] **Step 6: 运行测试**

```bash
pytest databases/tests.py::InstanceListViewTest -v
```

Expected: PASS（4 tests）

- [ ] **Step 7: Commit**

```bash
git add databases/views.py databases/tests.py
git commit -m "feat: hide ip/port from non-root in InstanceListView, allow postgresql db_type"
```

---

### Task 8: 更新 DatabaseSearchView

**Files:**
- Modify: `databases/views.py`
- Modify: `databases/tests.py`（追加）

- [ ] **Step 1: 先写测试**

```python
# 追加到 databases/tests.py

class DatabaseSearchViewTest(TestCase):

    def setUp(self):
        self.root = User.objects.create_superuser('root6', password='root6')
        self.quser = User.objects.create_user('quser6', password='quser6')
        self.mysql_inst = Instance.objects.create(
            remark='mysql-1', ip='10.0.0.1', port=3306, env='test', db_type='mysql'
        )
        self.pg_inst = Instance.objects.create(
            remark='pg-1', ip='10.0.0.2', port=5432, env='test', db_type='postgresql'
        )
        self.client = APIClient()

    def test_root_response_contains_ip_port(self):
        self.client.force_authenticate(self.root)
        with patch('databases.views.get_connector') as mock_gc:
            mock_gc.return_value.search_databases.return_value = [
                {'db_name': 'mydb', 'table_count': 3, 'size_mb': 1.0}
            ]
            resp = self.client.get('/databases/search/', {'db_name': 'mydb'})
        self.assertEqual(resp.status_code, 200)
        results = resp.data['results']
        if results:
            self.assertIn('ip', results[0])
            self.assertIn('port', results[0])

    def test_non_root_response_excludes_ip_port(self):
        self.client.force_authenticate(self.quser)
        with patch('databases.views.get_connector') as mock_gc:
            mock_gc.return_value.search_databases.return_value = [
                {'db_name': 'mydb', 'table_count': 3, 'size_mb': 1.0}
            ]
            resp = self.client.get('/databases/search/', {'db_name': 'mydb'})
        self.assertEqual(resp.status_code, 200)
        for item in resp.data.get('results', []):
            self.assertNotIn('ip', item)
            self.assertNotIn('port', item)
            self.assertIn('id', item)
            self.assertIn('remark', item)
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
pytest databases/tests.py::DatabaseSearchViewTest -v
```

Expected: FAIL

- [ ] **Step 3: 重构 DatabaseSearchView.get**

将整个 `DatabaseSearchView.get` 方法替换为：

```python
def get(self, request):
    db_name   = request.GET.get('db_name', '').strip()
    ip_filter = request.GET.get('ip', '').strip()
    port_str  = request.GET.get('port', '').strip()

    if not db_name and not (ip_filter and port_str) and _is_query_role(request.user):
        return Response(
            {'error': True, 'message': '请输入数据库名称，或同时输入 IP 和端口', 'results': []},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if db_name and _is_query_role(request.user) and db_name.lower() in FILTER_DB_NAMES:
        return Response(
            {'error': True, 'message': f'禁止查询系统库：{db_name}', 'results': []},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if ip_filter and port_str and _is_query_role(request.user):
        return Response(
            {'error': True, 'message': '无权限通过 IP+端口 方式查询，请使用数据库名称查询', 'results': []},
            status=status.HTTP_403_FORBIDDEN,
        )

    try:
        qs = Instance.objects.all().order_by('id')
        if ip_filter and port_str:
            qs = qs.filter(ip=ip_filter, port=int(port_str))
        instances = list(qs)
    except Exception as exc:
        logger.error('获取实例列表失败: %s', exc)
        return Response({'error': True, 'message': str(exc), 'results': []},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    is_root = request.user.is_superuser
    results = []

    for inst in instances:
        try:
            connector = get_connector(
                inst.db_type, inst.ip, inst.port,
                QUERY_DEFAULT_ACCOUNT, QUERY_DEFAULT_PASSWORD,
            )
            db_stats = connector.search_databases(db_name)
        except Exception as exc:
            logger.warning('搜索实例 %s:%s 失败: %s', inst.ip, inst.port, exc)
            base = _inst_to_dict_full(inst) if is_root else _inst_to_dict_safe(inst)
            base.update({'db_name': '-', 'table_count': '-', 'size_mb': '-',
                         'error': str(exc)})
            results.append(base)
            continue

        for db in db_stats:
            base = _inst_to_dict_full(inst) if is_root else _inst_to_dict_safe(inst)
            base.update({
                'db_name':     db['db_name'],
                'table_count': db['table_count'],
                'size_mb':     db['size_mb'],
            })
            results.append(base)

    return Response({'error': False, 'results': results})
```

- [ ] **Step 4: 运行测试**

```bash
pytest databases/tests.py::DatabaseSearchViewTest -v
```

Expected: PASS

- [ ] **Step 5: 运行全部测试**

```bash
pytest -v
```

Expected: 全部 PASS

- [ ] **Step 6: Commit**

```bash
git add databases/views.py databases/tests.py
git commit -m "feat: refactor DatabaseSearchView to use connector + hide ip/port from non-root"
```

---

## 端到端验证

运行完所有任务后，做一次手动验证：

- [ ] **Step 1: 启动服务**

```bash
python manage.py migrate
python manage.py runserver
```

- [ ] **Step 2: 在实例注册表中添加 PostgreSQL 实例**（通过 UI 或 API）

```bash
curl -X POST http://localhost:8000/databases/instances/ \
  -H "Content-Type: application/json" \
  -d '{"remark":"pg-local","ip":"127.0.0.1","port":15432,"env":"test","db_type":"postgresql"}'
```

记录返回的 `id`（例如 `3`）

- [ ] **Step 3: 验证列数据库**

```bash
curl "http://localhost:8000/databases/?instance_id=3"
```

Expected: `{"error": false, "db_names": ["testdb"]}`

- [ ] **Step 4: 验证执行 SQL**

```bash
curl -X POST http://localhost:8000/databases/execute_sql/ \
  -H "Content-Type: application/json" \
  -d '{"instance_id":3,"sql":"SELECT version()","db":"testdb"}'
```

Expected: 返回 PostgreSQL 版本字符串

- [ ] **Step 5: 验证非 root 用户 InstanceListView 无 ip/port**

以非 root 用户登录，调用 `GET /databases/instances/`，确认响应中无 ip/port 字段。

- [ ] **Step 6: 验证旧 MySQL 实例不受影响**（回归测试）

用已有 MySQL 实例的 `instance_id` 执行查询，确认正常返回。

- [ ] **Final Commit**

```bash
git add -A
git commit -m "feat: complete PostgreSQL support with connector abstraction and ip/port access control"
```
