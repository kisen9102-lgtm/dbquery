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


if __name__ == '__main__':
    unittest.main()
