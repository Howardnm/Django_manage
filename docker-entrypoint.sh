#!/bin/bash
set -e

echo "=== Django Entrypoint ==="

# 等待数据库就绪
echo "[1/3] Waiting for database..."
until python -c "import psycopg2; psycopg2.connect(host='$DB_HOST', port='$DB_PORT', dbname='$DB_NAME', user='$DB_USER', password='$DB_PASSWORD')" 2>/dev/null; do
    echo "  Database not ready, retrying in 2s..."
    sleep 2
done
echo "  Database is ready."

# 执行数据库迁移
echo "[2/3] Running migrations..."
python manage.py migrate --noinput

# 收集静态文件（写入共享 volume）
echo "[3/3] Collecting static files..."
python manage.py collectstatic --noinput

echo "=== Starting: $@ ==="
exec "$@"
