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

    def test_redis_type_returns_redis_connector(self):
        from common.connector import get_connector, RedisConnector
        c = get_connector('redis', '127.0.0.1', 6379, '', 'pass')
        self.assertIsInstance(c, RedisConnector)


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
        # 第一次调用返回库名列表，后续调用返回 (schema, table_count) 列表
        conn_dbs, _ = self._mock_conn(fetchall_result=[('testdb',)])
        conn_schemas, _ = self._mock_conn(fetchall_result=[('public', 3), ('sales', 1)])
        with patch.object(c, '_connect', side_effect=[conn_dbs, conn_schemas]):
            result = c.get_databases()
        self.assertIn('testdb_public', result)
        self.assertIn('testdb_sales', result)

    def test_search_databases_single_system_db_returns_empty(self):
        from common.connector import PG_SYSTEM_DBS
        c = self._make_connector()
        for sys_db in PG_SYSTEM_DBS:
            result = c._search_databases_single(sys_db)
            self.assertEqual(result, [], f'{sys_db} should be filtered')

    def test_search_databases_empty_calls_search_all(self):
        c = self._make_connector()
        # 第一次调用：返回库列表；后续调用：返回 schema 列表
        conn_dbs, _ = self._mock_conn(fetchall_result=[('testdb', 1.5)])
        conn_schemas, _ = self._mock_conn(fetchall_result=[('public', 3), ('sales', 1)])
        with patch.object(c, '_connect', side_effect=[conn_dbs, conn_schemas]):
            result = c.search_databases('')
        self.assertEqual(len(result), 2)
        db_names = [r['db_name'] for r in result]
        self.assertIn('testdb_public', db_names)
        self.assertIn('testdb_sales', db_names)
        self.assertEqual(result[0]['table_count'], 3)


class RedisConnectorUnitTest(TestCase):
    """RedisConnector unit tests — mock redis-py."""

    def _make_connector(self):
        from common.connector import RedisConnector
        return RedisConnector('127.0.0.1', 16379, '', 'testpass')

    def test_get_databases_returns_fixed_16_dbs(self):
        c = self._make_connector()
        dbs = c.get_databases()
        self.assertEqual(dbs, [f'db{i}' for i in range(16)])
        self.assertEqual(len(dbs), 16)

    def test_get_tables_returns_empty(self):
        c = self._make_connector()
        self.assertEqual(c.get_tables('db0'), [])

    def test_search_databases_returns_empty(self):
        c = self._make_connector()
        self.assertEqual(c.search_databases('anything'), [])
        self.assertEqual(c.search_databases(''), [])

    def test_execute_sql_rejects_write_command(self):
        c = self._make_connector()
        with self.assertRaises(PermissionError):
            c.execute_sql('DEL mykey', 'db0')

    def test_execute_sql_rejects_invalid_db_index(self):
        c = self._make_connector()
        with self.assertRaises(ValueError):
            c.execute_sql('GET foo', 'db99')
        with self.assertRaises(ValueError):
            c.execute_sql('GET foo', 'notadb')

    @patch('common.connector.redis')
    def test_execute_sql_get_returns_resultset(self, mock_redis_module):
        mock_client = MagicMock()
        mock_client.execute_command.return_value = 'hello'
        mock_redis_module.Redis.return_value = mock_client

        c = self._make_connector()
        results, elapsed = c.execute_sql('GET mykey', 'db0')

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['type'], 'resultset')
        self.assertEqual(results[0]['columns'], ['result'])
        self.assertEqual(results[0]['rows'], [['hello']])
        self.assertIsInstance(elapsed, float)

    @patch('common.connector.redis')
    def test_execute_sql_keys_returns_list_format(self, mock_redis_module):
        mock_client = MagicMock()
        mock_client.execute_command.return_value = ['key1', 'key2', 'key3']
        mock_redis_module.Redis.return_value = mock_client

        c = self._make_connector()
        results, _ = c.execute_sql('KEYS *', 'db0')

        self.assertEqual(results[0]['columns'], ['index', 'value'])
        self.assertEqual(len(results[0]['rows']), 3)

    @patch('common.connector.redis')
    def test_execute_sql_hgetall_returns_dict_format(self, mock_redis_module):
        mock_client = MagicMock()
        mock_client.execute_command.return_value = {'field1': 'val1', 'field2': 'val2'}
        mock_redis_module.Redis.return_value = mock_client

        c = self._make_connector()
        results, _ = c.execute_sql('HGETALL myhash', 'db0')

        self.assertEqual(results[0]['columns'], ['field', 'value'])
        self.assertEqual(len(results[0]['rows']), 2)

    @patch('common.connector.redis')
    def test_execute_sql_none_result(self, mock_redis_module):
        mock_client = MagicMock()
        mock_client.execute_command.return_value = None
        mock_redis_module.Redis.return_value = mock_client

        c = self._make_connector()
        results, _ = c.execute_sql('GET nosuchkey', 'db0')

        self.assertEqual(results[0]['rows'], [['(nil)']])

    @patch('common.connector.redis')
    def test_execute_sql_scan_extracts_keys(self, mock_redis_module):
        mock_client = MagicMock()
        # SCAN returns [cursor, [key1, key2]]
        mock_client.execute_command.return_value = ['7', ['key1', 'key2', 'key3']]
        mock_redis_module.Redis.return_value = mock_client

        c = self._make_connector()
        results, _ = c.execute_sql('SCAN 0', 'db0')

        self.assertEqual(results[0]['columns'], ['index', 'value'])
        # Should show the keys, not the cursor
        self.assertEqual(len(results[0]['rows']), 3)
        self.assertEqual(results[0]['rows'][0], [0, 'key1'])

    @patch('common.connector.redis')
    def test_execute_sql_respects_max_rows(self, mock_redis_module):
        mock_client = MagicMock()
        # Return more than MAX_ROWS items
        mock_client.execute_command.return_value = [f'key{i}' for i in range(1500)]
        mock_redis_module.Redis.return_value = mock_client

        c = self._make_connector()
        results, _ = c.execute_sql('KEYS *', 'db0')

        self.assertTrue(results[0]['limited'])
        self.assertEqual(results[0]['row_count'], c.MAX_ROWS)
        self.assertEqual(len(results[0]['rows']), c.MAX_ROWS)


import unittest

PG_AVAILABLE = False
try:
    import psycopg2
    psycopg2.connect(
        host='127.0.0.1', port=15432,
        user='dbs_admin', password='Dbs@Admin2026',
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
        return PostgreSQLConnector('127.0.0.1', 15432, 'dbs_admin', 'Dbs@Admin2026')

    def test_get_databases_returns_testdb(self):
        c = self._make_connector()
        dbs = c.get_databases()
        self.assertIn('testdb_public', dbs)
        # 系统库不应出现
        self.assertNotIn('postgres', dbs)
        self.assertNotIn('template0', dbs)

    def test_get_tables_returns_list(self):
        c = self._make_connector()
        tables = c.get_tables('testdb_public')
        self.assertIsInstance(tables, list)
        table_names = [t['TABLE_NAME'] for t in tables]
        self.assertIn('users', table_names)
        self.assertIn('products', table_names)
        self.assertIn('orders', table_names)

    def test_execute_sql_select_version(self):
        c = self._make_connector()
        results, elapsed = c.execute_sql('SELECT version()', 'testdb_public')
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['type'], 'resultset')
        self.assertIn('PostgreSQL', results[0]['rows'][0][0])
        self.assertGreater(elapsed, 0)

    def test_execute_sql_multi_statement(self):
        c = self._make_connector()
        sql = 'SELECT 1 AS a; SELECT 2 AS b'
        results, _ = c.execute_sql(sql, 'testdb_public')
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]['rows'][0][0], 1)
        self.assertEqual(results[1]['rows'][0][0], 2)

    def test_search_databases_finds_testdb(self):
        c = self._make_connector()
        result = c.search_databases('testdb')
        db_names = [r['db_name'] for r in result]
        self.assertIn('testdb_public', db_names)
        self.assertIn('testdb_inventory', db_names)
        self.assertIn('testdb_sales', db_names)

    def test_search_databases_not_found(self):
        c = self._make_connector()
        result = c.search_databases('nonexistent_db_xyz')
        self.assertEqual(result, [])

    def test_search_all_databases(self):
        c = self._make_connector()
        result = c.search_databases('')
        self.assertIsInstance(result, list)
        db_names = [r['db_name'] for r in result]
        self.assertIn('testdb_public', db_names)
