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

    @staticmethod
    def _split_db_schema(db_schema: str) -> tuple:
        """
        将 'dbname_schema' 拆分为 (dbname, schema)。
        使用从右侧第一个 '_' 分割，保证含下划线的库名也能正确处理。
        若无 '_' 则 schema 默认为 'public'。
        """
        if '_' in db_schema:
            idx = db_schema.rfind('_')
            return db_schema[:idx], db_schema[idx + 1:]
        return db_schema, 'public'

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
                db_names = [r[0] for r in cur.fetchall()]
        finally:
            conn.close()

        # 每个库展开所有用户 schema，返回 dbname_schema 格式列表
        result = []
        for dbname in db_names:
            db_conn = self._connect(dbname)
            try:
                with db_conn.cursor() as cur:
                    cur.execute(
                        "SELECT schema_name FROM information_schema.schemata"
                        " WHERE schema_name NOT IN ('pg_catalog','information_schema')"
                        "   AND schema_name NOT LIKE 'pg_%'"
                        " ORDER BY schema_name"
                    )
                    for (schema,) in cur.fetchall():
                        result.append(f"{dbname}_{schema}")
            finally:
                db_conn.close()
        return result

    def get_tables(self, db: str) -> list:
        import psycopg2.extras
        dbname, schema = self._split_db_schema(db)
        conn = self._connect(dbname)
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
                    WHERE t.table_schema = %s
                    ORDER BY t.table_type, t.table_name
                    """,
                    (schema,)
                )
                return [dict(r) for r in cur.fetchall()]
        finally:
            conn.close()

    def execute_sql(self, sql: str, db: str = '') -> tuple:
        import psycopg2
        import psycopg2.extras
        dbname, schema = self._split_db_schema(db) if db else ('postgres', 'public')
        conn = self._connect(dbname)
        conn.autocommit = False
        # 设置 search_path，让用户可以不加 schema 前缀直接查表
        with conn.cursor() as cur:
            cur.execute(f'SET search_path TO {schema}, public')
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
            conn.commit()
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

    def _get_schemas(self, dbname: str) -> list:
        """返回指定库的所有用户 schema 名列表。"""
        db_conn = self._connect(dbname)
        try:
            with db_conn.cursor() as cur:
                cur.execute(
                    "SELECT schema_name FROM information_schema.schemata"
                    " WHERE schema_name NOT IN ('pg_catalog','information_schema')"
                    "   AND schema_name NOT LIKE 'pg_%'"
                    " ORDER BY schema_name"
                )
                return [r[0] for r in cur.fetchall()]
        finally:
            db_conn.close()

    def _search_databases_single(self, db_name: str) -> list:
        # 支持搜索词为 'testdb' 或 'testdb_public' 两种形式
        real_db, target_schema = self._split_db_schema(db_name)
        # 如果输入本身就是一个纯库名（无下划线或库名在 pg_database 中），优先作为库名处理
        if real_db in PG_SYSTEM_DBS:
            return []

        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT ROUND(pg_database_size(%s)/1024.0/1024.0,2)"
                    " FROM pg_catalog.pg_database"
                    " WHERE datname=%s AND datistemplate=false",
                    (real_db, real_db)
                )
                row = cur.fetchone()
                if not row:
                    return []
                size_mb = float(row[0] or 0)
        finally:
            conn.close()

        # 如果搜索词包含下划线且 target_schema 有意义，只返回指定 schema
        # 否则返回该库下所有 schema
        all_schemas = self._get_schemas(real_db)
        if '_' in db_name and target_schema in all_schemas:
            schemas = [target_schema]
        else:
            schemas = all_schemas

        result = []
        for schema in schemas:
            db_conn = self._connect(real_db)
            try:
                with db_conn.cursor() as cur:
                    cur.execute(
                        "SELECT COUNT(*) FROM information_schema.tables"
                        " WHERE table_schema=%s",
                        (schema,)
                    )
                    table_count = cur.fetchone()[0]
            finally:
                db_conn.close()
            result.append({'db_name': f"{real_db}_{schema}", 'table_count': table_count, 'size_mb': size_mb})
        return result

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

        result = []
        for datname, size_mb in rows:
            for schema in self._get_schemas(datname):
                result.append({'db_name': f"{datname}_{schema}", 'table_count': -1, 'size_mb': float(size_mb or 0)})
        return result


def get_connector(db_type: str, host: str, port: int,
                  user: str, password: str) -> BaseConnector:
    """工厂函数：按 db_type 返回对应连接器。未知类型抛 ValueError。"""
    if db_type in ('mysql', 'tidb'):
        return MySQLConnector(host, port, user, password)
    if db_type == 'postgresql':
        return PostgreSQLConnector(host, port, user, password)
    raise ValueError(f'不支持的数据库类型: {db_type}')
