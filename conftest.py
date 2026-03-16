# conftest.py
import os

# python-decouple 会从 .env 读取配置，测试环境可能没有 .env。
# 在 Django 初始化之前设置必要的环境变量，避免 decouple 抛出 UndefinedValueError。
os.environ.setdefault("SECRET_KEY", "test-secret-key-not-for-production")
os.environ.setdefault("DBS_DB_HOST", "localhost")
os.environ.setdefault("DBS_DB_PORT", "3306")
os.environ.setdefault("DBS_DB_USER", "test_user")
os.environ.setdefault("DBS_DB_PASSWORD", "test_pass")
os.environ.setdefault("DBS_DB_NAME", "test_db")
os.environ.setdefault("QUERY_DEFAULT_ACCOUNT", "dbs_admin")
os.environ.setdefault("QUERY_DEFAULT_PASSWORD", "dbs_password")
os.environ.setdefault("ALLOWED_HOSTS", "127.0.0.1,localhost")


def pytest_configure(config):
    """覆盖 DATABASES 用 SQLite :memory:，无需运行中的 MySQL 即可跑测试。"""
    from django.conf import settings
    settings.DATABASES["default"] = {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
    # 清除 Django 连接层缓存，确保 test DB setup 使用新的 SQLite 配置
    try:
        from django.db import connections
        # connections.settings 是 cached_property，删除实例缓存以强制重新读取
        connections.__dict__.pop('settings', None)
        connections._settings = None
        # 清除 asgiref.local.Local 的线程存储，移除已缓存的 MySQL 连接对象
        storage = getattr(connections._connections, '_storage', None)
        if storage is not None:
            for alias in list(vars(storage).keys()):
                try:
                    delattr(storage, alias)
                except AttributeError:
                    pass
    except Exception:
        pass
