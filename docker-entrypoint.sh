#!/bin/bash
set -e

echo "[entrypoint] Waiting for MySQL at ${DBS_DB_HOST}:${DBS_DB_PORT} ..."
until python -c "
import pymysql, os, sys
try:
    pymysql.connect(
        host=os.environ.get('DBS_DB_HOST','mysql'),
        port=int(os.environ.get('DBS_DB_PORT','3306')),
        user=os.environ.get('DBS_DB_USER','ops_user'),
        password=os.environ.get('DBS_DB_PASSWORD',''),
        database=os.environ.get('DBS_DB_NAME','ops_db'),
        connect_timeout=3,
    )
    sys.exit(0)
except Exception as e:
    sys.exit(1)
" 2>/dev/null; do
    echo "[entrypoint] MySQL not ready, retrying in 3s..."
    sleep 3
done

echo "[entrypoint] MySQL is ready."

echo "[entrypoint] Running migrations..."
python manage.py migrate --noinput

echo "[entrypoint] Creating dbsroot (skipped if already exists)..."
python manage.py create_dbsroot 2>/dev/null || true

echo "[entrypoint] Starting gunicorn..."
exec gunicorn dbquery.wsgi:application \
    --bind 0.0.0.0:8000 \
    --workers 4 \
    --timeout 120 \
    --access-logfile logs/gunicorn_access.log \
    --error-logfile logs/gunicorn_error.log \
    --log-level info
