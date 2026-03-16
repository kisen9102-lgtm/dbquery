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

| db_type    | auth_username       | auth_password    | auth_source              |
|------------|---------------------|------------------|--------------------------|
| mysql/tidb/postgresql | blank → fallback to env vars | blank → fallback to env vars | unused |
| redis      | blank (or Redis 6+ ACL username) | AUTH password | unused |
| mongodb    | MongoDB username    | MongoDB password | authSource (default: admin) |

**Migration**: new nullable fields, no DDL for existing rows, fully backward compatible.

---

## Section 2: Connector Design

### RedisConnector

**Read-only command whitelist:**
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
```

**Interface implementation:**

- `get_databases()` → `['db0', 'db1', ..., 'db15']` (fixed, no connection required)
- `get_tables(db)` → `[]` (Redis has no table concept; object browser hidden in UI)
- `execute_sql(command, db='db0')`:
  1. Parse db index from `'db3'` → `3`
  2. Check first token against whitelist; raise `PermissionError` if not allowed
  3. Execute via `redis-py`; return unified `resultset` format (one row per result)
- `search_databases(db_name='')` → `[]` (not applicable for Redis)

**Result format example** (`GET foo`):
```json
[{"type": "resultset", "columns": ["command", "result"], "rows": [["GET foo", "bar"]], "row_count": 1, "limited": false, "sql": "GET foo"}]
```

**Connection**: `redis.Redis(host, port, db=db_index, password=auth_password, username=auth_username or None, socket_connect_timeout=5, decode_responses=True)`

---

### MongoDBConnector

**Supported operations (read-only):**
- `db.<collection>.find(<filter>)` — optional: `.limit(N)` `.sort(<sort>)` `.skip(N)`
- `db.<collection>.count(<filter>)`
- `db.<collection>.aggregate([<pipeline>])`

**Parsing strategy**: regex extraction (no `eval()`):
```
pattern: db\.(\w+)\.(find|count|aggregate)\(([\s\S]*)\)
```
JSON arguments parsed with `json.loads()`. Returns `PermissionError` for unrecognised operations.

**Interface implementation:**

- `get_databases()` → `client.list_database_names()` filtered by system dbs (`admin`, `config`, `local`)
- `get_tables(db)` → collections list with `TABLE_NAME`, `TABLE_TYPE='collection'`, `TABLE_ROWS` (estimated), `size_mb`
- `execute_sql(query, db='')`:
  1. Parse operation type and collection name
  2. Reject any non-whitelisted operation
  3. Execute via pymongo; limit results to `MAX_ROWS=1000`
  4. Return `resultset` with columns derived from document keys
- `search_databases(db_name='')` → filter `list_database_names()` by `db_name` substring

**Connection**: `pymongo.MongoClient(host=host, port=port, username=auth_username or None, password=auth_password or None, authSource=auth_source or 'admin', serverSelectionTimeoutMS=5000)`

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

JS: `onchange` on db_type selector toggles field visibility.

### sql_editor.html (SQL Editor)

| Feature | Redis | MongoDB | MySQL/TiDB/PG |
|---------|-------|---------|---------------|
| DB selector | db0–db15 | actual database names | unchanged |
| Object browser (left panel) | hidden | shows collections | shows tables |
| CodeMirror mode | plain text | plain text | sql |
| Editor placeholder | `GET key` / `KEYS pattern` / `HGETALL key` | `db.collection.find({"field": "value"})` | `SELECT ...` |

**Permissions**: unchanged — `query` role uses `instance_id`, IP/port hidden, read-only enforced server-side.

---

## Error Handling

- Redis command not in whitelist → HTTP 400: `"不允许的命令: DEL"`
- MongoDB operation not in whitelist → HTTP 400: `"不支持的操作: drop"`
- Connection failure → HTTP 500 with error message (same as existing behavior)
- Invalid JSON in MongoDB query → HTTP 400: `"查询参数解析失败: ..."`

## Testing

- Unit tests (mock redis-py / pymongo): whitelist enforcement, command parsing, result formatting
- Integration tests (skipped unless test containers running): `@unittest.skipUnless(REDIS_AVAILABLE, ...)` / `@unittest.skipUnless(MONGO_AVAILABLE, ...)`
- `docker-compose.override.yml`: add `redis-test` (port 16379) and `mongo-test` (port 27017) services
