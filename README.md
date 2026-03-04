# Django_manage

这是一个基于 Django 开发的综合性管理后台项目。

## 功能模块

本项目包含了多个独立的应用（App），实现了不同业务功能：

- `app_panel`: 核心仪表盘和主页。
- `app_project`: 项目管理模块。
- `app_user`: 用户管理、认证和权限控制。
- `app_repository`: 原料库管理。
- `app_notification`: 通知中心。
- `app_dify_sync`: 与 Dify 平台进行数据同步。
- `app_raw_material`: 原材料管理。
- `app_process`: 工艺流程管理。
- `app_formula`: 配方管理。
- `app_basic_research`: 基础研究模块。
- `app_knowledge_base`: 文献知识库（可选）。

## 主要技术栈

- **后端框架**: Django
- **数据库**: 默认使用 SQLite，同时已配置好 PostgreSQL 和 MySQL 的连接方式。
- **前端**: 基于 Django 模板语言，集成了部分 JavaScript 和 CSS。
- **其他依赖**:
    - `django-axes`: 用于记录登录尝试并防止暴力破解。
    - `django-cleanup`: 在数据库记录删除时，自动清理关联的文件。
    - `django-debug-toolbar`: 用于开发环境下的调试。
    - `pgvector`: 为 PostgreSQL 提供向量搜索能力。
    - `gunicorn`: 用于生产环境部署。

## 安装与启动

### 1. 自动初始化 (推荐)

本项目提供了一个一键初始化脚本 `initialize.sh`，可以自动完成大部分设置步骤。

**使用方法:**

1.  确保你已经克隆了项目，并进入了项目根目录。
2.  在 `Django_manage/settings.py` 文件中，根据你的环境配置好数据库连接信息。
3.  如果你需要使用 Dify 同步功能，请先配置好 Dify 相关的 `API_KEY` 和 `API_BASE_URL`。
4.  激活 Python 虚拟环境。
5.  运行脚本：
    ```bash
    ./Initialize.sh
    ```
    该脚本将会引导你完成数据库迁移、基础数据导入、Dify 知识库初始化、静态文件收集和超级管理员创建。

### 2. 手动安装

如果你想手动完成每一步，请按照以下步骤操作：

1.  **克隆项目**
    ```bash
    git clone <your-repository-url>
    cd Django_manage
    ```

2.  **创建并激活虚拟环境**
    ```bash
    # Windows
    python -m venv venv
    venv\Scripts\activate

    # macOS / Linux
    source venv/bin/activate
    ```

3.  **安装依赖**
    ```bash
    pip install -r requirements.txt
    ```

4.  **数据库配置**
    项目默认使用 `db.sqlite3`。如果你想使用 PostgreSQL 或 MySQL，请在 `Django_manage/settings.py` 文件中，注释掉默认的 `DATABASES` 配置，并启用你需要的数据库配置。

5.  **执行数据库迁移**
    ```bash
    python manage.py migrate
    ```

6.  **创建管理员账号**
    ```bash
    python manage.py createsuperuser
    ```

7.  **启动开发服务器**
    ```bash
    python manage.py runserver
    ```
    项目将运行在 `http://127.0.0.1:8000`。

## 定时任务 / 管理命令

你可以通过 `python manage.py <command_name>` 来执行一些后台任务和数据处理。

### `app_dify_sync` (Dify 数据同步)

- **`prepare_dify_datasets`**:
  在 Dify 平台为项目中需要同步的模型创建对应的知识库（Dataset）。首次配置时运行。

- **`bootstrap_dify_sync_records`**:
  在本地数据库中为所有需要同步的数据模型创建同步任务记录。在 `prepare_dify_datasets` 之后运行。

- **`sync_to_dify`**:
  执行数据同步。该命令会查找本地发生变化（新增或修改）的数据，并将其同步到 Dify 对应的知识库中。你可以设置一个定时任务（如 Cron Job）来定期执行此命令，以保持数据同步。

- **`cleanup_dify_records`**:
  清理本地的 Dify 同步记录。当 Dify 端的知识库 ID 发生变化，或你想重新建立同步关系时使用。

### `app_notification` (通知中心)

- **`cleanup_notifications`**:
  清理旧的已读通知，以保持通知表不会无限增长。默认会删除30天前的已读通知。你可以设置一个定时任务（如 Cron Job）来定期执行此命令。

## 部署

### 生产环境建议

- **关闭 DEBUG 模式**: 在 `Django_manage/settings.py` 中，设置 `DEBUG = False`。
- **配置 `ALLOWED_HOSTS`**: 同样在 `settings.py` 中，将你的域名或服务器 IP 地址添加到 `ALLOWED_HOSTS` 列表中。
- **收集静态文件**: 运行 `python manage.py collectstatic`，确保所有静态文件都已收集到 `STATIC_ROOT` 指定的目录（默认为 `staticfiles`）。

### 使用 Gunicorn + Nginx 部署

在生产环境中，推荐使用 Nginx 作为反向代理，并将请求转发给 Gunicorn。

1.  **使用 Gunicorn 启动应用**

    在项目根目录下，运行以下命令来启动服务：
    ```bash
    gunicorn --workers 3 --bind 0.0.0.0:8000 Django_manage.wsgi:application
    ```
    - `--workers 3`: 指定工作进程的数量。通常建议设置为 `2 * CPU核心数 + 1`。
    - `--bind 0.0.0.0:8000`: 绑定监听的地址和端口。Gunicorn 将只在本地监听，等待 Nginx 的请求。
    - `Django_manage.wsgi:application`: 指向项目的 WSGI 应用。

2.  **配置 Nginx**

    下面是一个基础的 Nginx 配置示例。它将处理静态文件请求，并将其他所有请求代理到 Gunicorn。

    ```nginx
    server {
        listen 80;
        server_name your_domain.com; # 替换为你的域名

        # 静态文件映射
        # 当请求的 URL 以 /static/ 开头时，Nginx 会直接从文件系统提供服务
        location /static/ {
            # 'alias' 指向你通过 collectstatic 命令收集的静态文件目录
            alias /path/to/your/project/staticfiles/;
            expires 30d; # 缓存静态文件
        }

        # 媒体文件映射 (如果你的项目有用户上传的文件)
        # location /media/ {
        #     alias /path/to/your/project/media/;
        # }

        # 将所有其他请求转发给 Gunicorn
        location / {
            proxy_pass http://127.0.0.1:8000;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
        }
    }
    ```
    **注意**: 请务必将 `/path/to/your/project/staticfiles/` 替换为你项目中 `staticfiles` 目录的**绝对路径**。

### 容器化部署

本项目已包含 `Dockerfile`，可以方便地进行容器化部署。你可以根据自己的需求修改 `Dockerfile`，然后构建并运行 Docker 镜像。
