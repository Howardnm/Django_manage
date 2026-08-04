# ==========================================
# 第一阶段：Builder (构建依赖与环境)
# ==========================================
FROM python:3.13-slim-bookworm AS builder

# 设置环境变量
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# 安装系统构建依赖 (编译 mysqlclient/lxml/pyrfc 需要)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    pkg-config \
    default-libmysqlclient-dev \
    libxml2-dev \
    libxslt1-dev

# 复制 SAP NetWeaver RFC SDK 并设置环境变量
# pyrfc 编译时需要 SAPNWRFC_HOME 指向 SDK 根目录
COPY app_sap_services/SAP_NetWeaver_RFC_SDK_750P/linux-nwrfc750P_5-70002752/nwrfcsdk /opt/sap_nwrfcsdk
ENV SAPNWRFC_HOME=/opt/sap_nwrfcsdk

# 创建并激活虚拟环境
# 我们将环境安装在 /opt/venv 下
RUN python -m venv /opt/venv
# 将虚拟环境的 bin 目录加入 PATH，后续的 pip 安装就会自动装入该环境
ENV PATH="/opt/venv/bin:$PATH"

# 复制依赖文件并安装
COPY requirements.txt .
# 升级 pip 并安装依赖
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt


# ==========================================
# 第二阶段：Final (运行时镜像)
# ==========================================
FROM python:3.13-slim-bookworm

# 1. 设置环境变量
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    UVICORN_LIFESPAN=off

# 2. 设置工作目录
WORKDIR /app

# 3. 创建非 root 用户
RUN addgroup --system --gid 1001 django && \
    adduser --system --uid 1001 --ingroup django django-user

# 4. 安装运行时必需的系统库 (比 default-mysql-client 更小)
# 只需要 libmariadb3 (MySQL 运行时) 和 libxml2
RUN apt-get update && apt-get install -y --no-install-recommends \
    libmariadb3 \
    libxml2 \
    && rm -rf /var/lib/apt/lists/*

# 5. 【核心优化】从 Builder 阶段直接复制整个虚拟环境
# 这样 Final 镜像里连构建工具产生的垃圾都没有，只有纯粹的库
COPY --from=builder --chown=django-user:django /opt/venv /opt/venv

# 5.5 复制 SAP NW RFC SDK 运行时库 (pyrfc 运行时依赖)
COPY --from=builder --chown=django-user:django /opt/sap_nwrfcsdk/lib /opt/sap_nwrfcsdk/lib
ENV SAP_LIB_PATH=/opt/sap_nwrfcsdk/lib \
    LD_LIBRARY_PATH=/opt/sap_nwrfcsdk/lib

# 6. 复制项目代码 (使用 --chown 避免双倍体积)
COPY --chown=django-user:django . .

# 7. 准备运行时需要的可写目录 (静态文件 + 日志)
RUN mkdir -p staticfiles logs && chown django-user:django staticfiles logs

# 切换用户
USER django-user

# 8. 收集静态文件
# 此时环境里已经有 django 了 (在 /opt/venv 里)
RUN python manage.py collectstatic --noinput

# 暴露端口
# 8000: 业务应用 (gunicorn 3 worker)
# 8001: MCP 单 worker 服务 (nginx 反向代理 /mcp/ 到此)
EXPOSE 8000 8001

# 启动命令 (ASGI 模式：gunicorn + uvicorn worker)
# --max-requests-jitter 300: 给 worker 重启阈值加 0~300 随机抖动，
# 避免 3 个 worker 同时达到 1000 请求而集体重启（惊群效应），
# 错峰重启可避免 L1 缓存与 DB 连接同时重建的瞬时峰值。
CMD ["gunicorn", "Django_manage.asgi:application", \
     "--bind", "0.0.0.0:8000", \
     "--workers", "3", \
     "--worker-class", "uvicorn.workers.UvicornWorker", \
     "--timeout", "120", \
     "--max-requests", "1000", \
     "--max-requests-jitter", "300"]