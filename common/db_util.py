"""
数据库连接工具：统一管理到运维 MySQL 的连接池。
- 使用连接池避免频繁创建连接
- 所有业务 SQL 使用参数化查询（调用方负责），此处只负责连接管理
"""
from contextlib import contextmanager
import mysql.connector
import mysql.connector.pooling as pooling
from .config import DBS_DB_CONFIG

_pool: pooling.MySQLConnectionPool | None = None


def _get_pool() -> pooling.MySQLConnectionPool:
    global _pool
    if _pool is None:
        _pool = pooling.MySQLConnectionPool(
            pool_name='dbs_pool',
            pool_size=30,
            **DBS_DB_CONFIG,
        )
    return _pool


def get_connection() -> mysql.connector.MySQLConnection:
    return _get_pool().get_connection()


@contextmanager
def open_cursor(db_name: str = ''):
    """
    上下文管理器：获取连接、切换数据库、yield cursor，自动 commit/rollback/close。
    """
    conn = get_connection()
    try:
        cursor = conn.cursor(dictionary=True, buffered=True)
        if db_name:
            cursor.execute(f'USE `{db_name}`')
        try:
            yield cursor
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            cursor.close()
    finally:
        conn.close()


@contextmanager
def open_remote_cursor(host: str, port: int, user: str, password: str):
    """连接到目标 MySQL 实例的 cursor（用于 clusters/databases 等）"""
    conn = mysql.connector.connect(
        host=host, port=port, user=user, password=password,
        connection_timeout=3,
    )
    try:
        cursor = conn.cursor(dictionary=True, buffered=True)
        try:
            yield cursor
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            cursor.close()
    finally:
        conn.close()
