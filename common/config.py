"""
全局配置：从环境变量读取，消除代码中的硬编码凭证。
"""
from decouple import config

# ── 数据库连接 ─────────────────────────────────────────────────────────────────
DBS_DB_CONFIG = {
    'host': config('DBS_DB_HOST', default='localhost'),
    'port': config('DBS_DB_PORT', default=3306, cast=int),
    'user': config('DBS_DB_USER', default='ops_user'),
    'password': config('DBS_DB_PASSWORD', default=''),
    'database': config('DBS_DB_NAME', default='ops_db'),
    'charset': config('DBS_DB_CHARSET', default='utf8mb4'),
}

# ── SQL 查询默认账号 ───────────────────────────────────────────────────────────
QUERY_DEFAULT_ACCOUNT  = config('QUERY_DEFAULT_ACCOUNT',  default='dbs_admin')
QUERY_DEFAULT_PASSWORD = config('QUERY_DEFAULT_PASSWORD', default='')
