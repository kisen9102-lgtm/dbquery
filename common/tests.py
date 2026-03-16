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
