# Redis & MongoDB Support Design

## Goal

Add read-only Redis and MongoDB query support to the dbquery platform, reusing the existing SQL editor UI and connector abstraction layer.

## Architecture

Extend `common/connector.py` with `RedisConnector` and `MongoDBConnector`, both implementing the existing `BaseConnector` interface. Add per-instance credential fields to the `Instance` model. Update the SQL editor frontend to adapt placeholder text and CodeMirror mode based on `db_type`.

## Tech Stack

- **Redis driver**: `redis>=5.0` (redis-py)
- **MongoDB driver**: `pymongo>=4.6`
- **Frontend**: No new libraries; CodeMirror mode switched to plain text for Redis/MongoDB

---

## Section 1: Data Model

### Instance model additions

```python
DB_TYPE_CHOICES = [
    ('mysql', 'MySQL'),
    ('tidb', 'TiDB'),
    ('postgresql', 'PostgreSQL'),
    ('redis', 'Redis'),
    ('mongodb', 'MongoDB'),
]

auth_username = models.CharField(max_length=128, blank=True, default='')
auth_password = models.CharField(max_length=256, blank=True, default='')
auth_source   = models.CharField(max_length=64,  blank=True, default='')
```

**Field semantics by db_type:**

| db_type    | auth_username | auth_password | auth_source |
|------------|---------------|---------------|-------------|
| mysql/tidb/postgresql | blank → fallback to env vars | blank → fallback to env vars | unused |
| redis | blank (or Redis 6+ ACL username) | AUTH password (blank = no auth) | unused |
| mongodb | MongoDB username | MongoDB password | authSource (blank defaults to 'admin') |

**Migration**: `0003_instance_add_auth_fields_and_redis_mongodb`. New nullable fields; no DDL change on existing rows; fully backward compatible.

### View-level validation guards

`InstanceListView.post` and `InstanceDetailView.put` currently validate:
```python
if db_type not in ('mysql', 'tidb', 'postgresql'):
    return Response({'error': 'db_type 不合法'}, ...)
```
These guards must be updated to:
```python
if db_type not in ('mysql', 'tidb', 'postgresql', 'redis', 'mongodb'):
```

---

## Section 2: Connector Design

### `get_connector()` factory — updated signature

```python
def get_connector(db_type: str, host: str, port: int,
                  user: str, password: str,
                  auth_source: str = '') -> BaseConnector:
```

- `mysql` / `tidb` / `postgresql`: behavior unchanged, `user`/`password` from `_resolve_credentials()` (env-var fallback)
- `redis`: `user` maps to `auth_username`, `password` maps to `auth_password` from the `Instance` model fields directly (no env-var fallback)
- `mongodb`: same as redis; `auth_source` passed through

**All call sites in `views.py` that build a connector** (`ExecuteSqlView`, `DatabaseListView`, `TableListView`, `DatabaseSearchView`) must branch on `db_type` before resolving credentials:

```python
if inst.db_type in ('redis', 'mongodb'):
    account = inst.auth_username
    passwd  = inst.auth_password
    asrc    = inst.auth_source
else:
    account, passwd = _resolve_credentials(inst.auth_username or None, inst.auth_password or None)
    asrc = ''
connector = get_connector(inst.db_type, inst.ip, inst.port, account, passwd, asrc)
```

This applies to `DatabaseSearchView` too — MongoDB needs real per-instance credentials for `search_databases()`.

### `_is_readonly_sql()` — bypass for Redis/MongoDB

`ExecuteSqlView.post` calls `_is_query_role(request.user)` and then `_is_readonly_sql(sql)`. After `_resolve_instance` returns `inst`, `inst.db_type` is available. The SQL read-only guard must be **skipped** for `redis` and `mongodb` (the connector whitelist enforces read-only instead):

```python
inst, ip, port, db_type = _resolve_instance(request, ...)
...
if _is_query_role(request.user) and db_type not in ('redis', 'mongodb'):
    if not _is_readonly_sql(stmt):
        return Response({'error': '...'}, status=403)
```

### `DatabaseSearchView` — Redis/MongoDB behavior

Redis instances: `search_databases()` returns `[]` — no database names to index. MongoDB instances: `search_databases(db_name)` makes an authenticated connection using per-instance credentials (see credential branching above) and returns matching db names. Both are handled by the same connector call; no special-casing needed beyond the credential branching.

---

### RedisConnector

**Read-only command whitelist** (note: `KEYS` is included but carries a production-safety note):

```python
SAFE_REDIS_COMMANDS = {
    'get', 'mget', 'keys', 'scan', 'type', 'ttl', 'pttl', 'exists',
    'strlen', 'getrange', 'info', 'dbsize', 'time',
    'hget', 'hgetall', 'hmget', 'hkeys', 'hvals', 'hlen',
    'lrange', 'llen', 'lindex',
    'scard', 'smembers', 'srandmember', 'sismember',
    'zrange', 'zrangebyscore', 'zrevrange', 'zcard', 'zscore', 'zrank',
    'object', 'dump',
}
# Note: KEYS blocks server on large datasets; SCAN is safer. Both are allowed.
```

**Interface implementation:**

- `get_databases()` → `['db0', 'db1', ..., 'db15']` (fixed, no connection required)
- `get_tables(db)` → `[]` (intentional; object browser hidden in UI for Redis)
- `execute_sql(command, db='db0')`:
  1. Parse db index: strip `'db'` prefix, convert to int; invalid/out-of-range → HTTP 400 `"无效的 Redis 库编号: {db}"`
  2. Check first whitespace-split token (lowercased) against whitelist; not found → HTTP 400 `"不允许的命令: {cmd}"`
  3. `redis.Redis(host, port, db=db_index, password=auth_password or None, username=auth_username or None, socket_connect_timeout=5, decode_responses=True)`
  4. Parse command tokens: `shlex.split(command)` — catch `ValueError` (unmatched quotes) → HTTP 400 `"命令解析失败: {reason}"`
  5. Execute via `r.execute_command(*tokens)`
  5. Return `[{'type': 'resultset', 'columns': ['command', 'result'], 'rows': [[command, str(result)]], 'row_count': 1, 'limited': False, 'sql': command}]`
- `search_databases(db_name='')` → `[]`

---

### MongoDBConnector

**Supported read-only operations (no chained methods):**
```
db.<collection>.find(<json_filter>)
db.<collection>.count_documents(<json_filter>)
db.<collection>.aggregate(<json_pipeline_array>)
```

Note: `count()` was removed in pymongo 4.x. The user-facing command is `count_documents(...)`.

**Parsing strategy** — two-gate defense: regex shape check, then `json.loads()` validation. No `eval()`.

```python
import re, json

MONGO_PATTERN = re.compile(
    r'^db\.(\w+)\.(find|count_documents|aggregate)\((\{.*\}|\[.*\])\s*\)$',
    re.DOTALL
)
# Gate 1: regex verifies overall shape (db.<word>.<op>(<json>))
# Gate 2: json.loads() validates that the argument is well-formed JSON
# Together these prevent injection — Gate 1 enforces structure, Gate 2 enforces
# valid JSON syntax. Do NOT remove Gate 2 and rely on Gate 1 alone.

def _parse_query(self, query: str):
    m = MONGO_PATTERN.match(query.strip())
    if not m:
        raise ValueError("查询格式不正确，支持: db.<col>.find({}) / count_documents({}) / aggregate([])")
    collection, op, args_str = m.group(1), m.group(2), m.group(3)
    try:
        args = json.loads(args_str)
    except json.JSONDecodeError as e:
        raise ValueError(f"查询参数解析失败: {e}")
    return collection, op, args
```

**Interface implementation:**

- `get_databases()` → `MongoClient(...).list_database_names()` excluding `{'admin', 'config', 'local'}`
- `get_tables(db)` → for each collection in `client[db].list_collection_names()`, one `collStats` call per collection:
  ```python
  stats = client[db].command('collStats', name)   # single call, extract both fields
  {'TABLE_NAME': name, 'TABLE_TYPE': 'collection',
   'TABLE_ROWS': stats.get('count', 0),
   'size_mb':    round(stats.get('size', 0) / 1024 / 1024, 2)}
  ```
- `execute_sql(query, db='')`:
  1. If `db` is empty → return HTTP 400 `"请先选择数据库"`
  2. Call `_parse_query(query)`; invalid format/JSON → HTTP 400
  3. Execute: `find` → `col.find(filter).limit(MAX_ROWS+1)`; `count_documents` → `col.count_documents(filter)`; `aggregate` → `col.aggregate(pipeline)`
  4. Limit to MAX_ROWS; set `limited=True` if more rows exist
  5. Columns derived from union of all document keys (insertion order preserved)
- `search_databases(db_name='')`:
  - empty → return all dbs with `{'db_name': name, 'table_count': len(collections), 'size_mb': ...}`
  - non-empty → filter by substring match

**Connection**:
```python
pymongo.MongoClient(
    host=host, port=port,
    username=auth_username or None,
    password=auth_password or None,
    authSource=auth_source or 'admin',
    serverSelectionTimeoutMS=5000,
)
```

---

## Section 3: Frontend Changes

### index.html (Instance Management)

**Type badges:**
- Redis: red badge (`bg-danger`)
- MongoDB: green badge (`bg-success`)

**Add/Edit instance form** — new fields shown conditionally by `db_type`:

| Field | Redis | MongoDB | MySQL/TiDB/PG |
|-------|-------|---------|---------------|
| 认证用户名 (auth_username) | hidden | visible | hidden |
| 认证密码 (auth_password) | visible | visible | hidden |
| Auth Source | hidden | visible | hidden |

JS `onchange` on db_type selector toggles field visibility.

**Hardcoded "MySQL" string**: `index.html` contains `"请先添加一个 MySQL 实例"` in two places. Update to `"请先在「实例管理」页面添加实例"`.

### sql_editor.html (SQL Editor)

| Feature | Redis | MongoDB | MySQL/TiDB/PG |
|---------|-------|---------|---------------|
| DB selector | db0–db15 | actual database names | unchanged |
| Object browser (left panel) | hidden | shows collections | shows tables |
| CodeMirror mode | plain text | plain text | sql |
| Editor placeholder | `GET key` / `KEYS pattern` / `HGETALL key` | `db.collection.find({"field": "value"})` | unchanged |

**`renderTree()` update**: currently filters on `TABLE_TYPE === 'BASE TABLE'` and `TABLE_TYPE === 'VIEW'`. Must add a branch for `TABLE_TYPE === 'collection'` to display MongoDB collections in the object browser.

**i18n keys** (both `zh` and `en` entries required in `_SE_I18N`):
- `editorPlaceholderRedis`: Redis command placeholder text
- `editorPlaceholderMongo`: MongoDB query placeholder text
- `noObjectBrowser`: text shown when object browser is hidden (Redis)

**Permissions**: `query` role uses `instance_id`, IP/port hidden — unchanged. Read-only enforcement moves to connector whitelist for Redis/MongoDB (see `_is_readonly_sql` bypass above).

---

## Error Handling

| Condition | HTTP status | Message |
|-----------|------------|---------|
| Redis command not in whitelist | 400 | `不允许的命令: {cmd}` |
| Redis invalid db index | 400 | `无效的 Redis 库编号: {db}` |
| Redis shlex parse failure | 400 | `命令解析失败: {reason}` |
| MongoDB empty db | 400 | `请先选择数据库` |
| MongoDB invalid query format | 400 | `查询格式不正确，支持: db.<col>.find({}) / count_documents({}) / aggregate([])` |
| MongoDB invalid JSON | 400 | `查询参数解析失败: {reason}` |
| Connection failure | 500 | existing behavior unchanged |

---

## Testing

**Unit tests** (mock redis-py / pymongo):
- Whitelist enforcement (allowed and blocked commands)
- Redis db index parsing (valid, invalid, out-of-range)
- MongoDB query parsing (valid find/count_documents/aggregate, invalid format, invalid JSON)
- Result formatting for both connectors

**Integration tests** (skip unless test containers running):
```python
@unittest.skipUnless(REDIS_AVAILABLE, "redis-test 未运行，跳过")
@unittest.skipUnless(MONGO_AVAILABLE, "mongo-test 未运行，跳过")
```

**`docker-compose.override.yml` additions:**
```yaml
redis-test:
  image: redis:7
  ports: ["16379:6379"]

mongo-test:
  image: mongo:7
  ports: ["27117:27017"]   # offset port to avoid conflict with local MongoDB
  environment:
    MONGO_INITDB_ROOT_USERNAME: dbs_admin
    MONGO_INITDB_ROOT_PASSWORD: Dbs@Admin2026
```
