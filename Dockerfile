# --- Builder Stage ---
# 这个阶段安装构建依赖并编译 Python 包
FROM python:3.13-slim AS builder

# 设置环境变量，防止生成 .pyc 文件并以非缓冲模式运行
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# 为 mysqlclient 和 lxml 等包安装构建时所需的系统依赖
RUN apt-get update && apt-get install -y \
    build-essential \
    pkg-config \
    default-libmysqlclient-dev \
    libxml2-dev \
    libxslt1-dev \
    --no-install-recommends

# 设置工作目录
WORKDIR /app

# 复制依赖文件
COPY requirements.txt .

# 为依赖创建 wheelhouse
# 这会编译依赖并将其存储为 wheel 文件
RUN pip wheel --no-cache-dir --wheel-dir /app/wheels -r requirements.txt


# --- Final Stage ---
# 这个阶段构建最终的、精简的生产镜像
FROM python:3.13-slim

# 设置环境变量
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# 为应用程序创建一个专用的非 root 用户和组
RUN addgroup --system django && adduser --system --ingroup django django-user

# 安装运行时所需的系统依赖
RUN apt-get update && apt-get install -y \
    default-mysql-client \
    --no-install-recommends && \
    rm -rf /var/lib/apt/lists/*

# 设置工作目录
WORKDIR /home/django-user/app

# 从 builder 阶段复制已编译的 wheel 文件
COPY --from=builder /app/wheels /wheels

# 从 wheel 文件安装 Python 依赖
# 这样更快，且不需要在最终镜像中包含构建工具
RUN pip install --no-cache /wheels/*

# 将应用程序代码复制到容器中
# .dockerignore 文件会阻止不必要的文件被复制
COPY . .

# 运行 collectstatic 来收集所有静态文件
# 重要提示：请确保在你的 settings.py 中配置了 STATIC_ROOT (例如: STATIC_ROOT = BASE_DIR / "staticfiles")
RUN python manage.py collectstatic --noinput

# 将应用程序目录的所有权更改为非 root 用户
RUN chown -R django-user:django /home/django-user/app

# 切换到非 root 用户
USER django-user

# 暴露应用程序运行的端口
EXPOSE 8000

# 使用 Gunicorn 运行应用程序
CMD ["gunicorn", "Django_manage.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--threads", "2"]
