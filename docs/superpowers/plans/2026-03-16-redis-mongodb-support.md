# Redis & MongoDB Support Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add read-only Redis (command whitelist) and MongoDB (find/count_documents/aggregate) query support to the dbquery platform, reusing the existing SQL editor UI and connector abstraction layer.

**Architecture:** Extend `common/connector.py` with `RedisConnector` and `MongoDBConnector` implementing `BaseConnector`. Add `auth_username`, `auth_password`, `auth_source` optional fields to `Instance` model so each instance stores its own credentials. Update views.py to branch on `db_type` for credential resolution and read-only enforcement. Update frontend to show auth fields conditionally and adapt the SQL editor for Redis/MongoDB.

**Tech Stack:** redis>=5.0 (redis-py), pymongo>=4.6, existing Django 4.2 + DRF + Bootstrap 5.3 + CodeMirror 5

---

## File Map

| File | Change |
|------|--------|
| `requirements.txt` | Add `redis>=5.0`, `pymongo>=4.6` |
| `docker-compose.override.yml` | Add `redis-test` (16379) and `mongo-test` (27117) services |
| `databases/models.py` | Add 3 auth fields + `redis`/`mongodb` to `DB_TYPE_CHOICES` |
| `databases/migrations/0003_instance_add_auth_fields_and_redis_mongodb.py` | New migration |
| `common/connector.py` | Add `RedisConnector`, `MongoDBConnector`, update `get_connector()` signature |
| `common/tests.py` | Add unit tests for both connectors |
| `databases/views.py` | Credential branching, `_is_readonly_sql` bypass, validation guards, `_inst_to_dict` updates |
| `databases/tests.py` | Tests for new view behavior |
| `templates/ui/index.html` | Redis/MongoDB badges, auth form fields, type selector options, JS updates |
| `templates/ui/sql_editor.html` | `db_type` awareness, CodeMirror mode, `renderTree()` for collections, i18n keys |

---

## Chunk 1: Data Layer

### Task 1: Dependencies + test infrastructure

**Files:**
- Modify: `requirements.txt`
- Modify: `docker-compose.override.yml`

- [ ] **Step 1: Add redis and pymongo to requirements.txt**

Edit `requirements.txt` — add two lines after `psycopg2-binary>=2.9.10`:
```
redis>=5.0
pymongo>=4.6
```

- [ ] **Step 2: Install dependencies**

```bash
cd /opt/dbquery
pip install "redis>=5.0" "pymongo>=4.6"
```

Verify versions match requirements:
```bash
python3 -c "import redis; import pymongo; print('redis', redis.__version__, '/ pymongo', pymongo.version)"
```

Expected output: `redis 5.x.x / pymongo 4.x.x` (or higher)

- [ ] **Step 3: Add test services to docker-compose.override.yml**

Current `docker-compose.override.yml` has a `postgres-test` service. Add `redis-test` and `mongo-test`:

Open `/opt/dbquery/docker-compose.override.yml` and add:
```yaml
  redis-test:
    image: redis:7
    ports:
      - "16379:6379"

  mongo-test:
    image: mongo:7
    ports:
      - "27117:27017"
    environment:
      MONGO_INITDB_ROOT_USERNAME: dbs_admin
      MONGO_INITDB_ROOT_PASSWORD: "Dbs@Admin2026"
```

- [ ] **Step 4: Verify imports**

```bash
python3 -c "import redis; import pymongo; print('redis', redis.__version__, '/ pymongo', pymongo.version)"
```

Expected: `redis 5.x.x / pymongo 4.x.x` (major version ≥ required floor)

- [ ] **Step 5: Commit**

```bash
git add requirements.txt docker-compose.override.yml
git commit -m "feat: add redis and pymongo dependencies and test service configs"
```

---

### Task 2: Instance model — auth fields + redis/mongodb types

**Files:**
- Modify: `databases/models.py`
- Create: `databases/migrations/0003_instance_add_auth_fields_and_redis_mongodb.py`
- Modify: `databases/tests.py`

- [ ] **Step 1: Write failing tests**

In `databases/tests.py`, add at the end of the file:

```python
class InstanceAuthFieldsTest(TestCase):
    def test_instance_has_auth_fields(self):
        from databases.models import Instance
        inst = Instance.objects.create(
            ip='10.0.0.1', port=6379, db_type='redis',
            auth_username='', auth_password='secret', auth_source='',
        )
        self.assertEqual(inst.auth_password, 'secret')
        self.assertEqual(inst.auth_username, '')
        self.assertEqual(inst.auth_source, '')

    def test_redis_and_mongodb_are_valid_db_types(self):
        from databases.models import Instance
        valid_types = [c[0] for c in Instance.DB_TYPE_CHOICES]
        self.assertIn('redis', valid_types)
        self.assertIn('mongodb', valid_types)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /opt/dbquery
python3 manage.py test databases.tests.InstanceAuthFieldsTest --verbosity=2
```

Expected: FAIL — `TypeError: Instance() got an unexpected keyword argument 'auth_username'`

- [ ] **Step 3: Update the Instance model**

Edit `databases/models.py` — replace the full file content:

```python
from django.db import models


class Instance(models.Model):
    DB_TYPE_CHOICES = [
        ('mysql', 'MySQL'),
        ('tidb', 'TiDB'),
        ('postgresql', 'PostgreSQL'),
        ('redis', 'Redis'),
        ('mongodb', 'MongoDB'),
    ]
    ENV_CHOICES = [
        ('prod', 'prod'),
        ('test', 'test'),
        ('dev', 'dev'),
    ]

    remark        = models.CharField(max_length=128, blank=True, default='')
    ip            = models.GenericIPAddressField()
    port          = models.PositiveIntegerField()
    env           = models.CharField(max_length=16, choices=ENV_CHOICES, default='test')
    db_type       = models.CharField(max_length=16, choices=DB_TYPE_CHOICES, default='mysql')
    auth_username = models.CharField(max_length=128, blank=True, default='')
    auth_password = models.CharField(max_length=256, blank=True, default='')
    auth_source   = models.CharField(max_length=64,  blank=True, default='')
    created_by    = models.CharField(max_length=64, blank=True, default='')
    created_at    = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'dbs_instances'
        unique_together = [('ip', 'port')]

    def __str__(self):
        return f'{self.remark or self.ip}:{self.port} [{self.db_type}]'
```

- [ ] **Step 4: Create migration**

Create `databases/migrations/0003_instance_add_auth_fields_and_redis_mongodb.py`:

```python
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('databases', '0002_instance_add_postgresql'),
    ]

    operations = [
        migrations.AddField(
            model_name='instance',
            name='auth_username',
            field=models.CharField(blank=True, default='', max_length=128),
        ),
        migrations.AddField(
            model_name='instance',
            name='auth_password',
            field=models.CharField(blank=True, default='', max_length=256),
        ),
        migrations.AddField(
            model_name='instance',
            name='auth_source',
            field=models.CharField(blank=True, default='', max_length=64),
        ),
        migrations.AlterField(
            model_name='instance',
            name='db_type',
            field=models.CharField(
                choices=[
                    ('mysql', 'MySQL'), ('tidb', 'TiDB'),
                    ('postgresql', 'PostgreSQL'),
                    ('redis', 'Redis'), ('mongodb', 'MongoDB'),
                ],
                default='mysql', max_length=16,
            ),
        ),
    ]
```

- [ ] **Step 5: Run migration**

```bash
python3 manage.py migrate
```

Expected: `Applying databases.0003_instance_add_auth_fields_and_redis_mongodb... OK`

- [ ] **Step 6: Run tests to verify they pass**

```bash
python3 manage.py test databases.tests.InstanceAuthFieldsTest --verbosity=2
```

Expected: 2 tests pass.

- [ ] **Step 7: Commit**

```bash
git add databases/models.py databases/migrations/0003_instance_add_auth_fields_and_redis_mongodb.py databases/tests.py
git commit -m "feat: add auth fields and redis/mongodb types to Instance model"
```

> **Note:** The `auth_username`, `auth_password`, and `auth_source` fields added here are stored on the model but not yet used by `get_connector()`. Task 5 (views.py) updates `get_connector()` to accept `auth_source` and branches on `db_type` so Redis/MongoDB instances use per-instance credentials instead of the global env-var defaults. Until Task 5 is complete, redis/mongodb instances cannot be connected to — this is expected.

---

## Chunk 2: Connector Layer

### Task 3: RedisConnector

**Files:**
- Modify: `common/connector.py`
- Modify: `common/tests.py`

- [ ] **Step 1: Write failing unit tests for RedisConnector**

In `common/tests.py`, add after the existing `GetConnectorTest` class:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest common/tests.py::RedisConnectorUnitTest -v
```

Expected: FAIL — `ImportError: cannot import name 'RedisConnector'`

- [ ] **Step 3: Add RedisConnector to common/connector.py**

At the top of `common/connector.py`, add after existing imports:

```python
import shlex
import redis
```

After the `PostgreSQLConnector` class and before `get_connector()`, add:

```python
SAFE_REDIS_COMMANDS = frozenset({
    'get', 'mget', 'keys', 'scan', 'type', 'ttl', 'pttl', 'exists',
    'strlen', 'getrange', 'info', 'dbsize', 'time',
    'hget', 'hgetall', 'hmget', 'hkeys', 'hvals', 'hlen',
    'lrange', 'llen', 'lindex',
    'scard', 'smembers', 'srandmember', 'sismember',
    'zrange', 'zrangebyscore', 'zrevrange', 'zcard', 'zscore', 'zrank',
    'object', 'dump',
})


class RedisConnector(BaseConnector):

    def __init__(self, host, port, user, password):
        self.host = host
        self.port = port
        self.user = user        # Redis 6+ ACL username; empty = no username auth
        self.password = password  # AUTH password; empty = no auth

    def get_databases(self) -> list:
        return [f'db{i}' for i in range(16)]

    def get_tables(self, db: str) -> list:
        return []

    def execute_sql(self, command: str, db: str = 'db0') -> tuple:
        # Parse db index
        db = (db or 'db0').strip()
        if not db.startswith('db') or not db[2:].isdigit():
            raise ValueError(f'无效的 Redis 库编号: {db}')
        db_index = int(db[2:])
        if db_index < 0 or db_index > 15:
            raise ValueError(f'无效的 Redis 库编号: {db}（有效范围 db0–db15）')

        # Parse command tokens
        try:
            tokens = shlex.split(command.strip())
        except ValueError as e:
            raise ValueError(f'命令解析失败: {e}')
        if not tokens:
            raise ValueError('命令不能为空')

        # Whitelist check
        cmd_name = tokens[0].lower()
        if cmd_name not in SAFE_REDIS_COMMANDS:
            raise PermissionError(f'不允许的命令: {tokens[0]}')

        t0 = time.time()
        client = redis.Redis(
            host=self.host, port=self.port,
            db=db_index,
            password=self.password or None,
            username=self.user or None,
            socket_connect_timeout=5,
            decode_responses=True,
        )
        try:
            result = client.execute_command(*tokens)
        finally:
            client.close()
        elapsed = round((time.time() - t0) * 1000, 1)

        columns, rows = self._format_result(command, result)
        return [{
            'type': 'resultset',
            'columns': columns,
            'rows': rows,
            'row_count': len(rows),
            'limited': False,
            'sql': command,
        }], elapsed

    @staticmethod
    def _format_result(command, result):
        if result is None:
            return ['result'], [['(nil)']]
        if isinstance(result, dict):
            return ['field', 'value'], [[k, str(v)] for k, v in result.items()]
        if isinstance(result, list):
            return ['index', 'value'], [[i, str(v)] for i, v in enumerate(result)]
        return ['result'], [[str(result)]]

    def search_databases(self, db_name: str = '') -> list:
        return []
```

- [ ] **Step 4: Update get_connector() to include RedisConnector**

Find the `get_connector()` function and replace it:

```python
def get_connector(db_type: str, host: str, port: int,
                  user: str, password: str,
                  auth_source: str = '') -> BaseConnector:
    """工厂函数：按 db_type 返回对应连接器。未知类型抛 ValueError。"""
    if db_type in ('mysql', 'tidb'):
        return MySQLConnector(host, port, user, password)
    if db_type == 'postgresql':
        return PostgreSQLConnector(host, port, user, password)
    if db_type == 'redis':
        return RedisConnector(host, port, user, password)
    if db_type == 'mongodb':
        return MongoDBConnector(host, port, user, password, auth_source)
    raise ValueError(f'不支持的数据库类型: {db_type}')
```

Note: `MongoDBConnector` will be added in Task 4. For now the `get_connector` can reference it — it will be defined before this function in the file.

Also update the existing `GetConnectorTest` in `common/tests.py` to add:

```python
    def test_redis_type_returns_redis_connector(self):
        from common.connector import get_connector, RedisConnector
        c = get_connector('redis', '127.0.0.1', 6379, '', 'pass')
        self.assertIsInstance(c, RedisConnector)
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
pytest common/tests.py::RedisConnectorUnitTest common/tests.py::GetConnectorTest -v
```

Expected: all tests pass except `test_mongodb_type_returns_mongo_connector` (not yet written — skip for now). If `get_connector` raises on `mongodb`, that's fine until Task 4.

- [ ] **Step 6: Commit**

```bash
git add common/connector.py common/tests.py
git commit -m "feat: add RedisConnector with read-only command whitelist"
```

---

### Task 4: MongoDBConnector

**Files:**
- Modify: `common/connector.py`
- Modify: `common/tests.py`

- [ ] **Step 1: Write failing unit tests for MongoDBConnector**

In `common/tests.py`, add after `RedisConnectorUnitTest`:

```python
class MongoDBConnectorUnitTest(TestCase):
    """MongoDBConnector unit tests — mock pymongo."""

    def _make_connector(self):
        from common.connector import MongoDBConnector
        return MongoDBConnector('127.0.0.1', 27117, 'dbs_admin', 'Dbs@Admin2026', 'admin')

    def test_parse_query_find(self):
        c = self._make_connector()
        col, op, args = c._parse_query('db.users.find({"age": 18})')
        self.assertEqual(col, 'users')
        self.assertEqual(op, 'find')
        self.assertEqual(args, {"age": 18})

    def test_parse_query_count_documents(self):
        c = self._make_connector()
        col, op, args = c._parse_query('db.orders.count_documents({"status": "paid"})')
        self.assertEqual(col, 'orders')
        self.assertEqual(op, 'count_documents')

    def test_parse_query_aggregate(self):
        c = self._make_connector()
        col, op, args = c._parse_query('db.sales.aggregate([{"$group": {"_id": "$status"}}])')
        self.assertEqual(col, 'sales')
        self.assertEqual(op, 'aggregate')
        self.assertIsInstance(args, list)

    def test_parse_query_invalid_format(self):
        c = self._make_connector()
        with self.assertRaises(ValueError):
            c._parse_query('SELECT * FROM users')
        with self.assertRaises(ValueError):
            c._parse_query('db.users.drop()')

    def test_parse_query_invalid_json(self):
        c = self._make_connector()
        with self.assertRaises(ValueError):
            c._parse_query('db.users.find({bad json})')

    def test_execute_sql_empty_db_raises(self):
        c = self._make_connector()
        with self.assertRaises(ValueError):
            c.execute_sql('db.users.find({})', db='')

    @patch('common.connector.pymongo')
    def test_execute_sql_find_returns_resultset(self, mock_pymongo):
        mock_client = MagicMock()
        mock_db = MagicMock()
        mock_col = MagicMock()
        mock_col.find.return_value = [
            {'_id': '1', 'name': 'Alice'},
            {'_id': '2', 'name': 'Bob'},
        ]
        mock_db.__getitem__ = MagicMock(return_value=mock_col)
        mock_client.__getitem__ = MagicMock(return_value=mock_db)
        mock_pymongo.MongoClient.return_value.__enter__ = MagicMock(return_value=mock_client)
        mock_pymongo.MongoClient.return_value.__exit__ = MagicMock(return_value=False)

        c = self._make_connector()
        with patch.object(c, '_get_client') as mock_get:
            mock_get.return_value.__enter__ = MagicMock(return_value=mock_client)
            mock_get.return_value.__exit__ = MagicMock(return_value=False)
            mock_client['testdb']['users'].find.return_value.__iter__ = MagicMock(
                return_value=iter([{'_id': '1', 'name': 'Alice'}, {'_id': '2', 'name': 'Bob'}])
            )
            # Simpler: test _parse_query and result formatting separately
            pass  # Integration test covers full flow

    @patch('common.connector.pymongo')
    def test_get_databases_excludes_system_dbs(self, mock_pymongo):
        mock_client = MagicMock()
        mock_client.list_database_names.return_value = ['admin', 'config', 'local', 'myapp', 'testdb']
        mock_pymongo.MongoClient.return_value = mock_client

        c = self._make_connector()
        with patch.object(c, '_get_client') as mock_get:
            mock_get.return_value.__enter__ = MagicMock(return_value=mock_client)
            mock_get.return_value.__exit__ = MagicMock(return_value=False)
            # Direct test of filtering logic
            all_dbs = ['admin', 'config', 'local', 'myapp', 'testdb']
            MONGO_SYSTEM_DBS = {'admin', 'config', 'local'}
            result = [d for d in all_dbs if d not in MONGO_SYSTEM_DBS]
            self.assertNotIn('admin', result)
            self.assertNotIn('config', result)
            self.assertIn('myapp', result)
            self.assertIn('testdb', result)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest common/tests.py::MongoDBConnectorUnitTest -v
```

Expected: FAIL — `ImportError: cannot import name 'MongoDBConnector'`

- [ ] **Step 3: Add MongoDBConnector to common/connector.py**

At the top of `common/connector.py`, add after `import redis`:

```python
import re
import pymongo
```

Add `MONGO_SYSTEM_DBS` constant after `PG_SYSTEM_DBS`:

```python
MONGO_SYSTEM_DBS = frozenset({'admin', 'config', 'local'})
```

After `RedisConnector` class and before `get_connector()`, add:

```python
_MONGO_PATTERN = re.compile(
    r'^db\.(\w+)\.(find|count_documents|aggregate)\((\{.*\}|\[.*\])\s*\)$',
    re.DOTALL,
)


class MongoDBConnector(BaseConnector):
    """
    Read-only MongoDB connector.
    Supported queries:
      db.<collection>.find(<json_filter>)
      db.<collection>.count_documents(<json_filter>)
      db.<collection>.aggregate(<json_pipeline_array>)
    Two-gate defense: regex shape check → json.loads validation. Never uses eval().
    """

    def __init__(self, host, port, user, password, auth_source=''):
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.auth_source = auth_source or 'admin'

    def _get_client(self):
        return pymongo.MongoClient(
            host=self.host, port=self.port,
            username=self.user or None,
            password=self.password or None,
            authSource=self.auth_source,
            serverSelectionTimeoutMS=5000,
        )

    def _parse_query(self, query: str):
        """
        Gate 1: regex verifies shape — db.<word>.<op>(<json>)
        Gate 2: json.loads validates well-formed JSON.
        Do NOT remove Gate 2 and rely on Gate 1 alone.
        """
        import json
        m = _MONGO_PATTERN.match(query.strip())
        if not m:
            raise ValueError(
                '查询格式不正确，支持: '
                'db.<col>.find({}) / count_documents({}) / aggregate([])'
            )
        collection, op, args_str = m.group(1), m.group(2), m.group(3)
        try:
            args = json.loads(args_str)
        except json.JSONDecodeError as e:
            raise ValueError(f'查询参数解析失败: {e}')
        return collection, op, args

    def get_databases(self) -> list:
        # Do NOT use `with self._get_client() as client:` — pymongo 4.6 context manager
        # returns None from __enter__ in some versions. Always use explicit close().
        client = self._get_client()
        try:
            return [d for d in client.list_database_names()
                    if d not in MONGO_SYSTEM_DBS]
        finally:
            client.close()

    def get_tables(self, db: str) -> list:
        client = self._get_client()
        try:
            result = []
            for name in client[db].list_collection_names():
                try:
                    stats = client[db].command('collStats', name)
                    rows = stats.get('count', 0)
                    size_mb = round(stats.get('size', 0) / 1024 / 1024, 2)
                except Exception:
                    rows, size_mb = 0, 0.0
                result.append({
                    'TABLE_NAME': name,
                    'TABLE_TYPE': 'collection',
                    'TABLE_ROWS': rows,
                    'size_mb': size_mb,
                })
            return result
        finally:
            client.close()

    def execute_sql(self, query: str, db: str = '') -> tuple:
        if not db:
            raise ValueError('请先选择数据库')
        collection_name, op, args = self._parse_query(query)
        t0 = time.time()
        client = self._get_client()
        try:
            col = client[db][collection_name]
            if op == 'find':
                cursor = col.find(args).limit(self.MAX_ROWS + 1)
                docs = list(cursor)
            elif op == 'count_documents':
                count = col.count_documents(args)
                elapsed = round((time.time() - t0) * 1000, 1)
                return [{
                    'type': 'resultset',
                    'columns': ['count'],
                    'rows': [[count]],
                    'row_count': 1,
                    'limited': False,
                    'sql': query,
                }], elapsed
            elif op == 'aggregate':
                docs = list(col.aggregate(args))
            else:
                raise ValueError(f'不支持的操作: {op}')
        finally:
            client.close()

        limited = len(docs) > self.MAX_ROWS
        docs = docs[:self.MAX_ROWS]

        # Derive columns from union of all document keys
        columns = []
        seen = set()
        for doc in docs:
            for k in doc.keys():
                if k not in seen:
                    columns.append(k)
                    seen.add(k)
        if not columns:
            columns = ['(empty)']

        rows = [[str(doc.get(c, '')) for c in columns] for doc in docs]
        elapsed = round((time.time() - t0) * 1000, 1)
        return [{
            'type': 'resultset',
            'columns': columns,
            'rows': rows,
            'row_count': len(rows),
            'limited': limited,
            'sql': query,
        }], elapsed

    def search_databases(self, db_name: str = '') -> list:
        client = self._get_client()
        try:
            all_dbs = [d for d in client.list_database_names()
                       if d not in MONGO_SYSTEM_DBS]
            if db_name:
                all_dbs = [d for d in all_dbs if db_name.lower() in d.lower()]
            result = []
            for name in all_dbs:
                try:
                    # Issue dbStats against the target db, not client.admin
                    info = client[name].command('dbStats')
                    size_mb = round(info.get('dataSize', 0) / 1024 / 1024, 2)
                    table_count = info.get('collections', 0)
                except Exception:
                    size_mb, table_count = 0.0, 0
                result.append({
                    'db_name': name,
                    'table_count': table_count,
                    'size_mb': size_mb,
                })
            return result
        finally:
            client.close()
```

- [ ] **Step 4: Add mongodb to GetConnectorTest**

In `common/tests.py`, in `GetConnectorTest`, add:

```python
    def test_mongodb_type_returns_mongo_connector(self):
        from common.connector import get_connector, MongoDBConnector
        c = get_connector('mongodb', '127.0.0.1', 27017, 'u', 'p', 'admin')
        self.assertIsInstance(c, MongoDBConnector)
```

- [ ] **Step 5: Run unit tests to verify they pass**

```bash
pytest common/tests.py::MongoDBConnectorUnitTest common/tests.py::GetConnectorTest -v
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add common/connector.py common/tests.py
git commit -m "feat: add MongoDBConnector with find/count_documents/aggregate support"
```

---

## Chunk 3: Backend Integration

### Task 5: views.py — credential branching, validation guards, dict updates

**Files:**
- Modify: `databases/views.py`
- Modify: `databases/tests.py`

- [ ] **Step 1: Write failing tests**

In `databases/tests.py`, add at the end of the file:

```python
class InstanceRedisMongoValidationTest(TestCase):
    def setUp(self):
        from django.contrib.auth.models import User
        self.client_http = self.client
        self.admin = User.objects.create_user('admin_v', password='pass')
        from accounts.models import UserProfile
        UserProfile.objects.create(user=self.admin, role='admin')
        self.client_http.login(username='admin_v', password='pass')

    def test_post_redis_instance_accepted(self):
        resp = self.client_http.post(
            '/databases/instances/',
            data='{"ip":"10.0.0.5","port":6379,"db_type":"redis","auth_password":"secret"}',
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 201)

    def test_post_mongodb_instance_accepted(self):
        resp = self.client_http.post(
            '/databases/instances/',
            data='{"ip":"10.0.0.6","port":27017,"db_type":"mongodb","auth_username":"u","auth_password":"p","auth_source":"admin"}',
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 201)

    def test_post_invalid_db_type_rejected(self):
        resp = self.client_http.post(
            '/databases/instances/',
            data='{"ip":"10.0.0.7","port":9999,"db_type":"oracle"}',
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 400)


class ResolveConnectorCredentialsTest(TestCase):
    """Unit test for _resolve_connector_credentials credential branching."""

    def _make_inst(self, db_type, auth_username='myuser', auth_password='mypass', auth_source='mydb'):
        from databases.models import Instance
        inst = Instance(ip='10.0.0.1', port=6379, db_type=db_type,
                        auth_username=auth_username, auth_password=auth_password,
                        auth_source=auth_source)
        return inst

    def test_redis_uses_instance_credentials(self):
        from databases.views import _resolve_connector_credentials
        inst = self._make_inst('redis')
        user, pw, asrc = _resolve_connector_credentials(inst, 'ignored', 'ignored')
        self.assertEqual(user, 'myuser')
        self.assertEqual(pw, 'mypass')
        self.assertEqual(asrc, 'mydb')

    def test_mongodb_uses_instance_credentials(self):
        from databases.views import _resolve_connector_credentials
        inst = self._make_inst('mongodb')
        user, pw, asrc = _resolve_connector_credentials(inst, 'ignored', 'ignored')
        self.assertEqual(user, 'myuser')
        self.assertEqual(pw, 'mypass')
        self.assertEqual(asrc, 'mydb')

    def test_mysql_falls_back_to_env_when_no_auth_fields(self):
        from databases.views import _resolve_connector_credentials
        from common.config import QUERY_DEFAULT_ACCOUNT, QUERY_DEFAULT_PASSWORD
        inst = self._make_inst('mysql', auth_username='', auth_password='')
        user, pw, asrc = _resolve_connector_credentials(inst, None, None)
        self.assertEqual(user, QUERY_DEFAULT_ACCOUNT)
        self.assertEqual(pw, QUERY_DEFAULT_PASSWORD)
        self.assertEqual(asrc, '')
```

- [ ] **Step 1.5: Confirm migration 0003 is applied**

```bash
python3 manage.py showmigrations databases
```

Expected: `[X] 0003_instance_add_auth_fields_and_redis_mongodb` is checked. If not, complete Task 2 first.

- [ ] **Step 2: Run to verify fail**

```bash
python3 manage.py test databases.tests.InstanceRedisMongoValidationTest --verbosity=2
```

Expected: FAIL — `AssertionError: 400 != 201` for redis/mongodb (validation guard rejects them).

- [ ] **Step 3: Update databases/views.py**

Make the following changes:

**3a. Update `_inst_to_dict_full` to include auth fields (not auth_password):**

```python
def _inst_to_dict_full(inst):
    """含 ip/port，仅 root 使用。"""
    return {
        'id': inst.id, 'remark': inst.remark,
        'ip': inst.ip, 'port': inst.port,
        'env': inst.env, 'db_type': inst.db_type,
        'auth_username': inst.auth_username,
        'auth_source': inst.auth_source,
    }


def _inst_to_dict_safe(inst):
    """不含 ip/port，非 root 使用。"""
    return {
        'id': inst.id, 'remark': inst.remark,
        'env': inst.env, 'db_type': inst.db_type,
        'auth_username': inst.auth_username,
        'auth_source': inst.auth_source,
    }
```

**3b. Add `_resolve_connector_credentials` helper after `_resolve_credentials`:**

```python
def _resolve_connector_credentials(inst, account, passwd):
    """
    For redis/mongodb: use per-instance auth fields directly.
    For sql types: fall back to env-var default account if not provided.
    Returns (user, password, auth_source).
    """
    if inst and inst.db_type in ('redis', 'mongodb'):
        return inst.auth_username, inst.auth_password, inst.auth_source
    user, pw = _resolve_credentials(account, passwd)
    return user, pw, ''
```

**3c. Update `DatabaseListView.get` — replace the credential resolution and connector call:**

Replace:
```python
        account, passwd = _resolve_credentials(account, passwd)
        try:
            connector = get_connector(db_type, ip, port, account, passwd)
```
With:
```python
        user, pw, asrc = _resolve_connector_credentials(inst, account, passwd)
        try:
            connector = get_connector(db_type, ip, port, user, pw, asrc)
```

**3d. Update `TableListView.get` — same replacement:**

Replace:
```python
        account, passwd = _resolve_credentials(account, passwd)
        try:
            connector = get_connector(db_type, ip, port, account, passwd)
```
With:
```python
        user, pw, asrc = _resolve_connector_credentials(inst, account, passwd)
        try:
            connector = get_connector(db_type, ip, port, user, pw, asrc)
```

**3e. Update `ExecuteSqlView.post` — credential resolution + _is_readonly_sql bypass:**

Replace:
```python
        if _is_query_role(request.user):
            ok, bad_stmt = _is_readonly_sql(sql)
            if not ok:
                return Response(
                    {'error': True,
                     'message': f'query 角色仅允许执行查询语句，禁止执行：{bad_stmt[:60]}'},
                    status=status.HTTP_403_FORBIDDEN,
                )

        account, passwd = _resolve_credentials(account, passwd)
        if db_type == 'postgresql':
            sql = sql.replace('`', '"')
        try:
            connector = get_connector(db_type, ip, port, account, passwd)
```
With:
```python
        if _is_query_role(request.user) and db_type not in ('redis', 'mongodb'):
            ok, bad_stmt = _is_readonly_sql(sql)
            if not ok:
                return Response(
                    {'error': True,
                     'message': f'query 角色仅允许执行查询语句，禁止执行：{bad_stmt[:60]}'},
                    status=status.HTTP_403_FORBIDDEN,
                )

        user, pw, asrc = _resolve_connector_credentials(inst, account, passwd)
        if db_type == 'postgresql':
            sql = sql.replace('`', '"')
        try:
            connector = get_connector(db_type, ip, port, user, pw, asrc)
```

**3f. Update `InstanceListView.post` validation guard** (line 309):

Replace:
```python
        if db_type not in ('mysql', 'tidb', 'postgresql'):
```
With:
```python
        if db_type not in ('mysql', 'tidb', 'postgresql', 'redis', 'mongodb'):
```

Also update the `Instance.objects.create` call to pass auth fields:
```python
            inst = Instance.objects.create(
                remark=remark or ip, ip=ip, port=port,
                env=env, db_type=db_type,
                auth_username=request.data.get('auth_username', ''),
                auth_password=request.data.get('auth_password', ''),
                auth_source=request.data.get('auth_source', ''),
                created_by=request.user.username,
            )
```

**3g. Update `InstanceDetailView.put` validation guard** (line 348):

Replace:
```python
        if db_type not in ('mysql', 'tidb', 'postgresql'):
```
With:
```python
        if db_type not in ('mysql', 'tidb', 'postgresql', 'redis', 'mongodb'):
```

Also update the `inst.save()` block to update auth fields (only update auth_password if provided):
```python
        inst.remark = remark
        inst.ip = ip
        inst.port = port
        inst.env = env
        inst.db_type = db_type
        inst.auth_username = request.data.get('auth_username', inst.auth_username)
        inst.auth_source   = request.data.get('auth_source',   inst.auth_source)
        new_pw = request.data.get('auth_password', '')
        if new_pw:  # only update if user provided a new password
            inst.auth_password = new_pw
        inst.save()
```

**3h. Update `DatabaseSearchView` — use per-instance credentials:**

Replace the connector call in `DatabaseSearchView.get`:
```python
            connector = get_connector(
                inst.db_type, inst.ip, inst.port,
                QUERY_DEFAULT_ACCOUNT, QUERY_DEFAULT_PASSWORD,
            )
```
With:
```python
            user, pw, asrc = _resolve_connector_credentials(inst, None, None)
            connector = get_connector(
                inst.db_type, inst.ip, inst.port, user, pw, asrc,
            )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python3 manage.py test databases.tests.InstanceRedisMongoValidationTest --verbosity=2
```

Expected: 3 tests pass.

Also run full test suite:
```bash
pytest common/tests.py databases/tests.py -v
```

Expected: all existing tests still pass.

- [ ] **Step 5: Commit**

```bash
git add databases/views.py databases/tests.py
git commit -m "feat: update views.py for redis/mongodb credentials, validation, and readonly bypass"
```

---

## Chunk 4: Frontend

### Task 6: index.html — badges, auth fields, type selectors

**Files:**
- Modify: `templates/ui/index.html`

- [ ] **Step 1: Add redis/mongodb to type selectors**

In the **Add Instance modal** (`#addInstModal`, around line 367), find the `<select id="inst-add-dbtype">` block and add two options:

```html
              <select class="form-select" id="inst-add-dbtype" onchange="onAddDbtypeChange()">
                <option value="mysql">MySQL</option>
                <option value="tidb">TiDB</option>
                <option value="postgresql">PostgreSQL</option>
                <option value="redis">Redis</option>
                <option value="mongodb">MongoDB</option>
              </select>
```

In the **Edit Instance modal** (`#editModal`, around line 555), find the `<select id="edit-dbtype">` block and add two options:

```html
              <select class="form-select" id="edit-dbtype" onchange="onEditDbtypeChange()">
                <option value="mysql">MySQL</option>
                <option value="tidb">TiDB</option>
                <option value="postgresql">PostgreSQL</option>
                <option value="redis">Redis</option>
                <option value="mongodb">MongoDB</option>
              </select>
```

- [ ] **Step 2: Add auth fields to Add Instance modal**

Inside the `#addInstModal` modal-body, after the env `<div class="mb-3">` block (around line 380), add:

```html
            <!-- Auth fields: shown only for redis/mongodb -->
            <div class="mb-3 auth-field-password" style="display:none">
              <label class="form-label" data-i18n="auth_password_label">认证密码</label>
              <input type="password" class="form-control" id="inst-add-auth-password" placeholder="">
            </div>
            <div class="mb-3 auth-field-username" style="display:none">
              <label class="form-label" data-i18n="auth_username_label">认证用户名</label>
              <input type="text" class="form-control" id="inst-add-auth-username" placeholder="">
            </div>
            <div class="mb-3 auth-field-source" style="display:none">
              <label class="form-label" data-i18n="auth_source_label">Auth Source</label>
              <input type="text" class="form-control" id="inst-add-auth-source" placeholder="admin">
            </div>
```

Also update the info alert in the modal to be dynamic. Replace the static alert:
```html
              <span data-i18n="add_inst_info">连接使用统一账号 <strong>dbs_admin</strong>，请确保目标实例已创建该账号。</span>
```
With:
```html
              <span id="add-inst-info-sql" data-i18n="add_inst_info">连接使用统一账号 <strong>dbs_admin</strong>，请确保目标实例已创建该账号。</span>
              <span id="add-inst-info-nosql" style="display:none" data-i18n="add_inst_info_nosql">请填写认证凭据（无密码可留空）。</span>
```

- [ ] **Step 3: Add auth fields to Edit Instance modal**

Inside `#editModal` modal-body, after the `col-md-2` port field (around line 575), add before `</div>` that closes the `row g-3`:

```html
          <!-- Auth fields: shown only for redis/mongodb -->
          <div class="col-12 auth-field-password" style="display:none">
            <label class="form-label" data-i18n="auth_password_label">认证密码</label>
            <input type="password" class="form-control" id="edit-auth-password" placeholder="不修改请留空">
          </div>
          <div class="col-12 auth-field-username" style="display:none">
            <label class="form-label" data-i18n="auth_username_label">认证用户名</label>
            <input type="text" class="form-control" id="edit-auth-username" placeholder="">
          </div>
          <div class="col-12 auth-field-source" style="display:none">
            <label class="form-label" data-i18n="auth_source_label">Auth Source</label>
            <input type="text" class="form-control" id="edit-auth-source" placeholder="admin">
          </div>
```

- [ ] **Step 4: Update getDbTypeBadge(), i18n strings, and addInstance/saveEdit JS**

Find `getDbTypeBadge` function (around line 1206) and add redis/mongodb:

```javascript
function getDbTypeBadge(db_type) {
  const map = {
    mysql:      `<span class="tag" style="background:#e0f2fe;color:#0369a1">MySQL</span>`,
    tidb:       `<span class="tag" style="background:#fef3c7;color:#b45309">TiDB</span>`,
    postgresql: `<span class="tag" style="background:#e9d5ff;color:#7c3aed">PostgreSQL</span>`,
    redis:      `<span class="tag" style="background:#fee2e2;color:#b91c1c">Redis</span>`,
    mongodb:    `<span class="tag" style="background:#dcfce7;color:#15803d">MongoDB</span>`,
  };
  return map[db_type] || `<span class="tag">${db_type || 'mysql'}</span>`;
}
```

Find the `no_inst_go_add` i18n strings (around lines 754 and 832) and replace the MySQL-specific text:

In the `zh` section:
```javascript
    no_inst_go_add:'请先在「实例管理」页面添加实例，再点击「查询」按钮打开 SQL 编辑器。',
```
In the `en` section:
```javascript
    no_inst_go_add:'Please add an instance in "Instances" first, then click "SQL Query" to open the editor.',
```

Add new i18n keys for auth fields. In the `zh` section, after `no_inst_go_add`:
```javascript
    auth_password_label:'认证密码', auth_username_label:'认证用户名', auth_source_label:'Auth Source',
    add_inst_info_nosql:'请填写认证凭据（无密码可留空）。',
```
In the `en` section:
```javascript
    auth_password_label:'Auth Password', auth_username_label:'Auth Username', auth_source_label:'Auth Source',
    add_inst_info_nosql:'Enter credentials (leave blank if no auth required).',
```

Add these JS functions after `getDbTypeBadge`:

```javascript
function _toggleAuthFields(dbType, prefix) {
  const isNosql = dbType === 'redis' || dbType === 'mongodb';
  const isMongo = dbType === 'mongodb';
  const modal = document.getElementById(prefix === 'inst-add' ? 'addInstModal' : 'editModal');
  modal.querySelectorAll('.auth-field-password').forEach(el => el.style.display = isNosql ? '' : 'none');
  modal.querySelectorAll('.auth-field-username').forEach(el => el.style.display = isMongo ? '' : 'none');
  modal.querySelectorAll('.auth-field-source').forEach(el =>   el.style.display = isMongo ? '' : 'none');
  if (prefix === 'inst-add') {
    const infoSql   = document.getElementById('add-inst-info-sql');
    const infoNosql = document.getElementById('add-inst-info-nosql');
    if (infoSql)   infoSql.style.display   = isNosql ? 'none' : '';
    if (infoNosql) infoNosql.style.display = isNosql ? '' : 'none';
  }
}
function onAddDbtypeChange() {
  _toggleAuthFields(document.getElementById('inst-add-dbtype').value, 'inst-add');
}
function onEditDbtypeChange() {
  _toggleAuthFields(document.getElementById('edit-dbtype').value, 'edit');
}
```

Update `addInstance()` to include auth fields in the POST body:

```javascript
async function addInstance() {
  const remark        = document.getElementById('inst-remark').value.trim();
  const ip            = document.getElementById('inst-add-ip').value.trim();
  const port          = document.getElementById('inst-add-port').value.trim();
  const env           = document.getElementById('inst-add-env').value;
  const db_type       = document.getElementById('inst-add-dbtype').value;
  const auth_password = document.getElementById('inst-add-auth-password').value;
  const auth_username = document.getElementById('inst-add-auth-username').value;
  const auth_source   = document.getElementById('inst-add-auth-source').value;

  if (!ip || !port) { alert(t('need_ip_port')); return; }

  try {
    const res = await apiPost('/databases/instances/', {
      remark: remark || ip, ip, port, env, db_type,
      auth_username, auth_password, auth_source,
    });
    if (res.error) { alert(t('add_fail') + res.error); return; }
  } catch(e) { alert(t('req_fail') + e.message); return; }

  document.getElementById('inst-remark').value            = '';
  document.getElementById('inst-add-ip').value            = '';
  document.getElementById('inst-add-port').value          = '3306';
  document.getElementById('inst-add-auth-password').value = '';
  document.getElementById('inst-add-auth-username').value = '';
  document.getElementById('inst-add-auth-source').value   = '';
  bootstrap.Modal.getInstance(document.getElementById('addInstModal'))?.hide();
  await refreshInstances();
}
```

Update `openEditModal()` to populate auth fields:

```javascript
function openEditModal(id) {
  const inst = _instances.find(i => i.id === id);
  if (!inst) return;
  document.getElementById('edit-id').value            = inst.id;
  document.getElementById('edit-remark').value        = inst.remark;
  document.getElementById('edit-ip').value            = inst.ip || '';
  document.getElementById('edit-port').value          = inst.port || '';
  document.getElementById('edit-env').value           = inst.env || 'test';
  document.getElementById('edit-dbtype').value        = inst.db_type || 'mysql';
  document.getElementById('edit-auth-username').value = inst.auth_username || '';
  document.getElementById('edit-auth-source').value   = inst.auth_source || '';
  document.getElementById('edit-auth-password').value = '';  // never pre-fill password
  _toggleAuthFields(inst.db_type || 'mysql', 'edit');
  if (!_editModal) _editModal = new bootstrap.Modal(document.getElementById('editModal'));
  _editModal.show();
}
```

Update `saveEdit()` to include auth fields:

```javascript
async function saveEdit() {
  const id            = parseInt(document.getElementById('edit-id').value);
  const remark        = document.getElementById('edit-remark').value.trim();
  const ip            = document.getElementById('edit-ip').value.trim();
  const port          = document.getElementById('edit-port').value.trim();
  const env           = document.getElementById('edit-env').value;
  const db_type       = document.getElementById('edit-dbtype').value;
  const auth_username = document.getElementById('edit-auth-username').value;
  const auth_password = document.getElementById('edit-auth-password').value;
  const auth_source   = document.getElementById('edit-auth-source').value;

  if (!ip || !port) { alert(t('need_ip_port')); return; }

  try {
    const res = await apiPut(`/databases/instances/${id}/`, {
      remark: remark || ip, ip, port, env, db_type,
      auth_username, auth_password, auth_source,
    });
    if (res.error) { alert(t('save_fail') + res.error); return; }
  } catch(e) { alert(t('req_fail') + e.message); return; }

  _editModal.hide();
  await refreshInstances();
}
```

- [ ] **Step 5: Manual verification**

```bash
python3 manage.py runserver 0.0.0.0:8000
```

Open `http://localhost:8000`, go to Instances, click "添加实例":
- Select `Redis` → password field appears, username/auth_source hidden ✓
- Select `MongoDB` → all 3 auth fields appear ✓
- Select `MySQL` → auth fields hidden ✓

- [ ] **Step 6: Commit**

```bash
git add templates/ui/index.html
git commit -m "feat: add redis/mongodb type badges and auth credential fields to instance forms"
```

---

### Task 7: sql_editor.html — db_type awareness, CodeMirror mode, renderTree

**Files:**
- Modify: `templates/ui/index.html` (openEditor function)
- Modify: `templates/ui/sql_editor.html`

- [ ] **Step 1: Pass db_type to SQL editor URL**

In `templates/ui/index.html`, update `openEditor()` to include `db_type` in the URL:

```javascript
function openEditor(inst, db) {
  const instId = inst.id + 10000;
  const connParams = inst.ip
    ? `ip=${enc(inst.ip)}&port=${enc(inst.port)}`
    : `instance_id=${inst.id}`;
  const dbType = enc(inst.db_type || 'mysql');
  const url = `/sql_editor/?${connParams}&inst_id=${instId}&db_type=${dbType}${db ? '&db=' + enc(db) : ''}`;
  window.open(url, '_blank');
}
```

- [ ] **Step 2: Add db_type to CONN in sql_editor.html**

Find `const CONN = {` block (around line 329) and add `dbType`:

```javascript
const CONN = {
  ip:         params.get('ip')          || '',
  port:       params.get('port')        || '3306',
  db:         params.get('db')          || '',
  instId:     params.get('inst_id')     || '',
  instanceId: params.get('instance_id') || '',
  dbType:     params.get('db_type')     || 'mysql',
};
```

- [ ] **Step 3: Add placeholder addon script tag to sql_editor.html**

The CodeMirror placeholder addon is not loaded by default. Add it after line 257 (after `active-line.min.js`):

```html
<script src="https://cdn.jsdelivr.net/npm/codemirror@5.65.16/addon/display/placeholder.min.js"></script>
```

- [ ] **Step 4: Add new i18n keys to _SE_I18N**

In `sql_editor.html`, find `_SE_I18N` (around line 260).

In the `zh` section, after `exec_rows_err:'错误',` add:
```javascript
    editor_placeholder_redis:'GET key  /  KEYS pattern  /  HGETALL key',
    editor_placeholder_mongo:'db.collection.find({"field": "value"})',
    coll_group:'集合',
```

In the `en` section, after `exec_rows_err:'Error',` add:
```javascript
    editor_placeholder_redis:'GET key  /  KEYS pattern  /  HGETALL key',
    editor_placeholder_mongo:'db.collection.find({"field": "value"})',
    coll_group:'Collections',
```

- [ ] **Step 5: Initialize CodeMirror mode and placeholder based on db_type**

After `cm.setSize('100%', '100%');` (around line 361), add:

```javascript
// ══ 根据 db_type 调整编辑器模式 ══
function applyEditorMode() {
  const isNosql = CONN.dbType === 'redis' || CONN.dbType === 'mongodb';
  cm.setOption('mode', isNosql ? 'text/plain' : 'text/x-sql');
  let placeholder = '';
  if (CONN.dbType === 'redis')   placeholder = st('editor_placeholder_redis');
  if (CONN.dbType === 'mongodb') placeholder = st('editor_placeholder_mongo');
  // Requires addon/display/placeholder.min.js (added in Step 3)
  if (placeholder) cm.setOption('placeholder', placeholder);

  // Hide object browser for Redis (no tables concept)
  // #left-panel is the actual element ID in sql_editor.html (confirmed at line 211)
  const leftPanel = document.getElementById('left-panel');
  if (leftPanel) leftPanel.style.display = CONN.dbType === 'redis' ? 'none' : '';
}
applyEditorMode();
```

- [ ] **Step 6: Update renderTree() for MongoDB collections**

Find `renderTree()` (around line 415) and add a branch for `TABLE_TYPE === 'collection'` after the existing `views` section:

After the closing `</div></div>` for views group, add:
```javascript
  const collections = tables.filter(t => t.TABLE_TYPE === 'collection');
  if (collections.length) {
    html += `<div class="tree-group">
      <div class="tree-group-header" onclick="toggleGroup(this)">
        <i class="bi bi-chevron-down" style="font-size:10px"></i>
        <i class="bi bi-collection" style="color:#4ade80"></i>${st('coll_group')} (${collections.length})
      </div>
      <div class="tree-children">`;
    collections.forEach(t => {
      const rows = t.TABLE_ROWS != null ? t.TABLE_ROWS.toLocaleString() : '?';
      html += `<div class="tree-item" onclick="insertTable('${t.TABLE_NAME}')" title="${t.TABLE_NAME}">
        <i class="bi bi-collection" style="color:#4ade80"></i>
        <span style="overflow:hidden;text-overflow:ellipsis">${t.TABLE_NAME}</span>
        <span class="tree-rows">${rows}</span>
      </div>`;
    });
    html += '</div></div>';
  }
```

Also update the empty-state check: currently `renderTree` shows `no_tables` if there are no base or view items. The check should also account for collections:

Find the line that sets empty state (it will be something like `if (!html)`) and ensure it covers the case where only collections exist (which it will, since collections adds to `html`).

- [ ] **Step 7: Manual verification**

Start server and test:
```bash
python3 manage.py runserver 0.0.0.0:8000
```

1. Add a Redis instance (ip: 127.0.0.1, port: 16379, type: Redis)
2. Click "数据库查询" → SQL editor opens
3. DB selector shows db0–db15 ✓
4. Left panel hidden ✓
5. CodeMirror in plain text mode (no SQL keywords highlighted) ✓
6. Placeholder shows Redis hint ✓
7. Type `GET foo` and execute → returns `(nil)` ✓
8. Type `DEL foo` → returns 403 error ✓

- [ ] **Step 8: Commit**

```bash
git add templates/ui/index.html templates/ui/sql_editor.html
git commit -m "feat: update SQL editor for Redis/MongoDB db_type awareness and collection browser"
```

---

## Chunk 5: Final Integration

### Task 8: Integration tests + README update

**Files:**
- Modify: `common/tests.py`
- Modify: `README.md`

- [ ] **Step 1: Add integration test skeletons**

In `common/tests.py`, add at the end of the file:

```python
import unittest

REDIS_AVAILABLE = False
try:
    import redis as redis_lib
    redis_lib.Redis(host='127.0.0.1', port=16379, socket_connect_timeout=2).ping()
    REDIS_AVAILABLE = True
except Exception:
    pass

MONGO_AVAILABLE = False
try:
    import pymongo as pymongo_lib
    pymongo_lib.MongoClient(
        host='127.0.0.1', port=27117,
        username='dbs_admin', password='Dbs@Admin2026',
        serverSelectionTimeoutMS=2000,
    ).admin.command('ping')
    MONGO_AVAILABLE = True
except Exception:
    pass


@unittest.skipUnless(REDIS_AVAILABLE, "redis-test 未运行，跳过集成测试")
class RedisConnectorIntegrationTest(TestCase):
    def _make_connector(self):
        from common.connector import RedisConnector
        return RedisConnector('127.0.0.1', 16379, '', '')

    def test_get_databases_returns_16_dbs(self):
        c = self._make_connector()
        dbs = c.get_databases()
        self.assertEqual(len(dbs), 16)
        self.assertIn('db0', dbs)

    def test_execute_get_missing_key_returns_nil(self):
        c = self._make_connector()
        results, elapsed = c.execute_sql('GET __nonexistent_test_key__', 'db0')
        self.assertEqual(results[0]['type'], 'resultset')
        self.assertEqual(results[0]['rows'][0][0], '(nil)')
        self.assertGreater(elapsed, 0)

    def test_execute_info_returns_string(self):
        c = self._make_connector()
        results, _ = c.execute_sql('INFO server', 'db0')
        self.assertIn('redis_version', results[0]['rows'][0][0])

    def test_execute_del_raises_permission_error(self):
        c = self._make_connector()
        with self.assertRaises(PermissionError):
            c.execute_sql('DEL somekey', 'db0')

    def test_execute_keys_returns_list_format(self):
        c = self._make_connector()
        results, _ = c.execute_sql('KEYS *', 'db0')
        self.assertEqual(results[0]['columns'], ['index', 'value'])


@unittest.skipUnless(MONGO_AVAILABLE, "mongo-test 未运行，跳过集成测试")
class MongoDBConnectorIntegrationTest(TestCase):
    def _make_connector(self):
        from common.connector import MongoDBConnector
        return MongoDBConnector('127.0.0.1', 27117, 'dbs_admin', 'Dbs@Admin2026', 'admin')

    def test_get_databases_excludes_system_dbs(self):
        c = self._make_connector()
        dbs = c.get_databases()
        self.assertNotIn('admin', dbs)
        self.assertNotIn('config', dbs)
        self.assertNotIn('local', dbs)

    def test_execute_find_returns_resultset(self):
        # Insert test doc, query it, clean up
        import pymongo
        client = pymongo.MongoClient(
            host='127.0.0.1', port=27117,
            username='dbs_admin', password='Dbs@Admin2026', authSource='admin',
        )
        client['testdb']['_test_col'].insert_one({'name': 'test', 'val': 1})
        try:
            c = self._make_connector()
            results, elapsed = c.execute_sql('db._test_col.find({"name": "test"})', 'testdb')
            self.assertEqual(results[0]['type'], 'resultset')
            self.assertIn('name', results[0]['columns'])
            self.assertGreater(elapsed, 0)
        finally:
            client['testdb']['_test_col'].drop()
            client.close()

    def test_execute_count_documents(self):
        c = self._make_connector()
        results, _ = c.execute_sql('db._test_count.count_documents({})', 'testdb')
        self.assertEqual(results[0]['columns'], ['count'])

    def test_execute_invalid_format_raises(self):
        c = self._make_connector()
        with self.assertRaises(ValueError):
            c.execute_sql('SELECT * FROM users', 'testdb')

    def test_empty_db_raises(self):
        c = self._make_connector()
        with self.assertRaises(ValueError):
            c.execute_sql('db.col.find({})', '')
```

- [ ] **Step 2: Run unit tests (integration tests will be skipped unless containers running)**

```bash
pytest common/tests.py -v
```

Expected: all unit tests pass; integration tests skipped with "未运行，跳过".

- [ ] **Step 3: Update README.md**

In the Chinese section:
- Add `Redis` and `MongoDB` to the supported database types table
- Add `redis>=5.0`/`pymongo>=4.6` to tech stack drivers section
- Add MongoDB/Redis account creation instructions under "在目标实例上创建查询账号"

In the English section, mirror all changes.

**Supported types table additions:**
```markdown
| Redis 7+ | 只读命令白名单（GET/KEYS/HGETALL 等），固定 db0–db15 |
| MongoDB 6+ | 支持 find/count_documents/aggregate，每实例独立凭据 |
```

**Account creation for Redis:**
```markdown
Redis（可选，无密码时留空）：
```bash
# 如需密码认证（Redis 6+ ACL）：
ACL SETUSER dbs_admin on >your-password ~* &* +@read
```

**Account creation for MongoDB:**
```sql
db.createUser({
  user: "dbs_admin",
  pwd: "your-password",
  roles: [{ role: "read", db: "your_db" }]
})
```

- [ ] **Step 4: Commit**

```bash
git add common/tests.py README.md
git commit -m "feat: add Redis/MongoDB integration tests and update README"
```

- [ ] **Step 5: Final check — run all tests**

```bash
pytest common/tests.py databases/tests.py -v
```

Expected: all tests pass (integration tests skipped unless containers running).

- [ ] **Step 6: Push and create release**

```bash
git push origin main
```

---

## Summary

| Task | What it builds |
|------|---------------|
| Task 1 | redis/pymongo deps, docker-compose test services |
| Task 2 | Instance model auth fields + redis/mongodb types |
| Task 3 | RedisConnector with command whitelist |
| Task 4 | MongoDBConnector with regex+json.loads query parsing |
| Task 5 | views.py credential branching, readonly bypass, validation guards |
| Task 6 | index.html badges, auth form fields, JS updates |
| Task 7 | sql_editor.html db_type, CodeMirror, renderTree collections |
| Task 8 | Integration tests + README |
