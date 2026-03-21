import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cli.config import load_config, save_config


class TestConfig(unittest.TestCase):

    def test_load_missing_returns_empty(self):
        result = load_config('/tmp/__dbcli_nonexistent__.json')
        self.assertEqual(result, {})

    def test_save_and_load_roundtrip(self):
        with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as f:
            path = f.name
        try:
            save_config({'url': 'http://localhost:8000', 'cookies': {'sessionid': 'abc'}}, path)
            result = load_config(path)
            self.assertEqual(result['url'], 'http://localhost:8000')
            self.assertEqual(result['cookies']['sessionid'], 'abc')
        finally:
            os.unlink(path)

    def test_save_sets_600_permissions(self):
        with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as f:
            path = f.name
        try:
            save_config({'url': 'test'}, path)
            mode = os.stat(path).st_mode & 0o777
            self.assertEqual(oct(mode), oct(0o600))
        finally:
            os.unlink(path)


from unittest.mock import MagicMock, patch

from cli.api_client import ApiClient


class TestApiClientLogin(unittest.TestCase):

    def _make_client(self, mock_session_cls):
        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session
        mock_session.cookies = MagicMock()
        mock_session.cookies.get.return_value = 'csrftoken123'
        return ApiClient('http://localhost:8000'), mock_session

    @patch('cli.api_client.requests.Session')
    def test_login_success(self, MockSession):
        client, mock_session = self._make_client(MockSession)
        mock_post_resp = MagicMock()
        mock_post_resp.status_code = 302
        mock_session.post.return_value = mock_post_resp
        self.assertTrue(client.login('admin', 'secret'))

    @patch('cli.api_client.requests.Session')
    def test_login_failure(self, MockSession):
        client, mock_session = self._make_client(MockSession)
        mock_post_resp = MagicMock()
        mock_post_resp.status_code = 200  # stayed on login page = failure
        mock_session.post.return_value = mock_post_resp
        self.assertFalse(client.login('admin', 'wrong'))

    @patch('cli.api_client.requests.Session')
    def test_list_instances(self, MockSession):
        client, mock_session = self._make_client(MockSession)
        mock_resp = MagicMock()
        mock_resp.json.return_value = [{'id': 1, 'ip': '10.0.0.1', 'port': 3306}]
        mock_session.get.return_value = mock_resp
        result = client.list_instances()
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['id'], 1)

    @patch('cli.api_client.requests.Session')
    def test_execute_sql_returns_tuple(self, MockSession):
        client, mock_session = self._make_client(MockSession)
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            'error': False,
            'results': [{'type': 'resultset', 'columns': ['id'], 'rows': [[1]], 'row_count': 1, 'limited': False, 'sql': 'SELECT 1'}],
            'elapsed_ms': 5.2,
        }
        mock_session.post.return_value = mock_resp
        results, elapsed = client.execute_sql(1, 'mydb', 'SELECT 1')
        self.assertEqual(len(results), 1)
        self.assertEqual(elapsed, 5.2)

    @patch('cli.api_client.requests.Session')
    def test_execute_sql_raises_on_error(self, MockSession):
        client, mock_session = self._make_client(MockSession)
        mock_resp = MagicMock()
        mock_resp.json.return_value = {'error': True, 'message': '连接失败'}
        mock_session.post.return_value = mock_resp
        with self.assertRaises(RuntimeError):
            client.execute_sql(1, 'mydb', 'SELECT 1')


from cli.direct_client import DirectClient


class TestDirectClientReadonly(unittest.TestCase):

    @patch('cli.direct_client.get_connector')
    def test_readonly_select_allowed(self, mock_get_connector):
        mock_conn = MagicMock()
        mock_conn.execute_sql.return_value = ([], 0)
        mock_get_connector.return_value = mock_conn
        client = DirectClient('127.0.0.1', 3306, 'mysql', 'user', 'pass')
        client.execute_sql('SELECT 1', 'mydb')  # should not raise
        mock_conn.execute_sql.assert_called_once_with('SELECT 1', 'mydb')

    @patch('cli.direct_client.get_connector')
    def test_readonly_insert_blocked(self, mock_get_connector):
        mock_get_connector.return_value = MagicMock()
        client = DirectClient('127.0.0.1', 3306, 'mysql', 'user', 'pass')
        with self.assertRaises(PermissionError):
            client.execute_sql('INSERT INTO t VALUES (1)', 'mydb')

    @patch('cli.direct_client.get_connector')
    def test_get_databases_delegates(self, mock_get_connector):
        mock_conn = MagicMock()
        mock_conn.get_databases.return_value = ['db1', 'db2']
        mock_get_connector.return_value = mock_conn
        client = DirectClient('127.0.0.1', 3306, 'mysql', 'user', 'pass')
        result = client.get_databases()
        self.assertEqual(result, ['db1', 'db2'])

    @patch('cli.direct_client.get_connector')
    def test_redis_show_tables_sends_keys_star(self, mock_get_connector):
        mock_conn = MagicMock()
        mock_conn.execute_sql.return_value = ([{
            'type': 'resultset', 'columns': ['index', 'value'],
            'rows': [[0, 'key1'], [1, 'key2']], 'row_count': 2,
            'limited': False, 'sql': 'KEYS *',
        }], 1.0)
        mock_get_connector.return_value = mock_conn
        client = DirectClient('127.0.0.1', 6379, 'redis', '', '')
        tables = client.get_tables('db0')
        mock_conn.execute_sql.assert_called_once_with('KEYS *', 'db0')
        self.assertEqual(len(tables), 2)
        self.assertEqual(tables[0]['TABLE_NAME'], 'key1')


if __name__ == '__main__':
    unittest.main()
