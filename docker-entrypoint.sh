#!/bin/bash
set -e

echo "=== Django Entrypoint ==="

# ── 1. 等待数据库就绪 ──
echo "[1/6] Waiting for database..."
until python -c "import psycopg2; psycopg2.connect(host='$DB_HOST', port='$DB_PORT', dbname='$DB_NAME', user='$DB_USER', password='$DB_PASSWORD')" 2>/dev/null; do
    echo "  Database not ready, retrying in 2s..."
    sleep 2
done
echo "  Database is ready."

# ── 2. 初始化 pgvector 扩展 ──
echo "[2/6] Creating pgvector extension..."
python -c "
import psycopg2
conn = psycopg2.connect(host='$DB_HOST', port='$DB_PORT', dbname='$DB_NAME', user='$DB_USER', password='$DB_PASSWORD')
conn.autocommit = True
conn.cursor().execute('CREATE EXTENSION IF NOT EXISTS vector;')
conn.close()
print('  pgvector extension ready.')
"

# ── 3. 检测模型变更并生成 migration 文件 ──
echo "[3/6] Checking for model changes..."
python manage.py makemigrations --noinput

# ── 4. 应用 migration 到数据库 ──
echo "[4/6] Applying migrations..."
python manage.py migrate --noinput

# ── 5. 创建管理员（仅首次） ──
echo "[5/6] Checking superuser..."
python manage.py shell -c "
import os
from django.contrib.auth import get_user_model
User = get_user_model()
username = os.environ.get('DJANGO_SUPERUSER_USERNAME', 'admin')
if not User.objects.filter(username=username).exists():
    User.objects.create_superuser(
        username=username,
        email=os.environ.get('DJANGO_SUPERUSER_EMAIL', 'admin@example.com'),
        password=os.environ.get('DJANGO_SUPERUSER_PASSWORD', 'admin123')
    )
    print(f'  Superuser \"{username}\" created.')
else:
    print(f'  Superuser \"{username}\" already exists, skipping.')
"

# ── 6. 收集静态文件 ──
echo "[6/6] Collecting static files..."
python manage.py collectstatic --noinput

echo "=== Starting: $@ ==="
exec "$@"
