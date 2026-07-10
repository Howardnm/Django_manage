# Django_manage

企业级研发项目管理后台，覆盖项目管理、物料配方、工作流审批、试验排产、SAP 集成、AI MCP 服务等业务域。

## 功能模块

| 模块 | 路由 | 说明 |
|---|---|---|
| `app_panel` | `/` | 仪表盘、首页面板 |
| `app_user` | `/user/` | 用户管理、RBAC 权限控制、分子公司/基地 |
| `app_project` | `/project/` | 项目管理（9 阶段生命周期）、绩效考核 |
| `app_repository` | `/repository/` | 项目物料仓库、OEM/客户管理 |
| `app_material` | `/material/` | 物料主数据、性能指标、测试标准 |
| `app_material_api` | `/api/material/` | 物料 REST API、Webhook 同步 |
| `app_raw_material` | `/raw-material/` | 原材料类型、供应商、批次管理 |
| `app_process` | `/process/` | 挤出工艺参数、螺杆组合、设备管理 |
| `app_formula` | `/formula/` | 实验配方 BOM、测试结果、配色粉配方 |
| `app_basic_research` | `/research/` | 基础预研项目（6 阶段独立生命周期） |
| `app_catalog` | `/catalog/` | 产品电子手册（外部系统同步） |
| `app_workflow` | `/workflow/` | BPMN 工作流引擎、任务分配（4 种指派模式） |
| `app_form_management` | `/forms/` | 动态表单生成器（分步骤流程适配） |
| `app_trial_production` | `/trial-production/` | 试验排产、挤出注塑任务、样品库存 |
| `app_color_center` | `/color-center/` | 配色任务管理（与挤出并行） |
| `app_material_testing` | `/material-testing/` | 材料测试、结果回写配方 |
| `app_mold_injection` | `/mold-injection/` | 模具注塑中心、模具库管理 |
| `app_attachment` | `/attachment/` | 统一附件管理（上传/下载/安全令牌） |
| `app_notification` | `/notifications/` | 通知中心（Actor-Verb-Target 模型） |
| `app_sap_services` | — | SAP RFC 服务层（9 业务域，19 个 RFC 函数） |
| `app_mcp_server` | `/mcp/` | AI MCP Server（SSE + JSON-RPC） |
| `common_utils` | `/common/` | 通用工具（状态机、搜索注册表、图表服务） |

## 技术栈

| 层级 | 选型 |
|---|---|
| **后端** | Django 6.0 · Python 3.13 |
| **ASGI** | Gunicorn + Uvicorn Worker |
| **数据库** | PostgreSQL 15+ · pgvector / MySQL 8.0.11+ |
| **API** | Django REST Framework 3.17 |
| **工作流** | SpiffWorkflow 3.1 + BPMN XML（Camunda 兼容） |
| **SAP** | pyrfc 3.3 + NetWeaver RFC SDK 750P |
| **AI** | MCP Server（SSE transport） |
| **前端** | Django Templates · Tabler UI · HTMX · Tom Select |
| **安全** | django-axes · 自定义 SecurityShieldMiddleware |
| **CI/CD** | GitHub Actions → Docker Hub |

## 快速开始（本地开发）

**前置条件**：Python 3.13+ · PostgreSQL 15+ 或 MySQL 8.0.11+

```bash
git clone <repo-url> && cd Django_manage
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 编辑 Django_manage/settings.py 中的 DATABASES：
#   - PostgreSQL（默认启用）→ 需安装 pgvector 扩展
#   - MySQL（已注释备用）  → 取消注释 MySQL 配置块，注释掉 PostgreSQL 块
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
# → http://127.0.0.1:8000/admin/
```

> **SAP 功能**（可选）：Windows 本地需将 SDK `lib` 目录加入 PATH，路径见 [SDK 配置](#sdk-配置)。

---

## 部署

项目支持两种部署方式，共用同一套环境变量和 Nginx 配置。

| | Docker 部署 | 源码部署 |
|---|---|---|
| **适用场景** | 快速交付、容器化运维 | 裸机/虚拟机、需定制系统依赖 |
| **SAP SDK** | Dockerfile 内置（Linux 版） | 手动安装到 `/opt/sap_nwrfcsdk` |
| **进程管理** | Docker daemon | systemd |
| **静态文件路径** | `/app/staticfiles/` | `/opt/django-manage/staticfiles/` |

### 方式一：Docker

**单容器启动**：

```bash
docker build -t django-manage .
docker run -d --name django-manage -p 8000:8000 \
  -e SAP_LIB_PATH=/opt/sap_nwrfcsdk/lib \
  django-manage
```

**docker-compose 一键启动（推荐）**：

```bash
cp .env.example .env
# 编辑 .env 设置 DB_PASSWORD 和 MCP_API_KEY
docker compose up -d
```

docker-compose 包含 4 个服务：

| 服务 | 镜像 | 说明 |
|---|---|---|
| `db` | `pgvector/pgvector:pg16` | PostgreSQL 16 + pgvector 向量扩展 |
| `web` | 本地构建（Dockerfile） | Django ASGI (gunicorn + uvicorn) |
| `nginx` | `nginx:1.27-alpine` | 反向代理 + 静态文件 + MCP SSE |

启动时自动执行：等待数据库就绪 → migrate → collectstatic → 启动服务。

**镜像分层**：Builder 阶段编译 pyrfc + pip install → Final 阶段仅复制 venv + .so 库 + 代码，无编译残留。

### 方式二：源码部署（Linux）

**额外依赖**：`build-essential pkg-config libmysqlclient-dev libxml2-dev libxslt1-dev`（编译 mysqlclient/lxml/pyrfc）

```bash
# 创建用户和目录
sudo useradd --system --home-dir /opt/django-manage django
sudo -u django git clone <repo-url> /opt/django-manage && cd /opt/django-manage

# 虚拟环境 + 依赖
sudo -u django python3.13 -m venv /opt/venv
sudo -u django /opt/venv/bin/pip install -r requirements.txt

# SAP SDK（如需要）
sudo cp -r app_sap_services/SAP_NetWeaver_RFC_SDK_750P/linux-nwrfc750P_5-70002752/nwrfcsdk /opt/sap_nwrfcsdk

# settings.py 生产配置：DEBUG=False, ALLOWED_HOSTS, 数据库改为环境变量读取（见下方环境变量表）
sudo -u django /opt/venv/bin/python manage.py migrate
sudo -u django /opt/venv/bin/python manage.py collectstatic --noinput
```

**systemd 服务**（`/etc/systemd/system/django-manage.service`）：

```ini
[Unit]
Description=Django Manage ASGI
After=network.target

[Service]
User=django
Group=django
WorkingDirectory=/opt/django-manage
Environment="PATH=/opt/venv/bin"
Environment="SAP_LIB_PATH=/opt/sap_nwrfcsdk/lib"
Environment="MCP_API_KEY=your-key"
# 数据库 — 根据实际使用的库选择：
Environment="DB_ENGINE=django.db.backends.postgresql"   # PostgreSQL
# Environment="DB_ENGINE=django.db.backends.mysql"      # MySQL
Environment="DB_HOST=127.0.0.1"
Environment="DB_NAME=django_manage"
Environment="DB_USER=django"
Environment="DB_PASSWORD=your-password"
Environment="DB_PORT=5432"
ExecStart=/opt/venv/bin/gunicorn Django_manage.asgi:application \
    --bind 127.0.0.1:8000 --workers 3 \
    --worker-class uvicorn.workers.UvicornWorker \
    --timeout 120 --max-requests 1000
Restart=always

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload && sudo systemctl enable --now django-manage
```

| 运维操作 | 命令 |
|---|---|
| 状态 / 日志 | `systemctl status django-manage` · `journalctl -u django-manage -f` |
| 代码更新 | `git pull && sudo systemctl restart django-manage` |
| 数据库备份 | PostgreSQL: `pg_dump -U postgres django_manage > backup.sql` |
| | MySQL: `mysqldump -u root -p django_manage > backup.sql` |

### 环境变量

两种部署方式共用。`settings.py` 通过 `os.environ.get()` 读取。

| 变量 | 说明 | Docker 默认 | 源码部署建议 |
|---|---|---|---|
| `SAP_LIB_PATH` | SAP SDK lib 路径 | `/opt/sap_nwrfcsdk/lib` | 同左 |
| `MCP_API_KEY` | MCP 鉴权密钥 | 未设置（不鉴权） | **生产必设** |
| `DB_ENGINE` | 数据库引擎 | `django.db.backends.postgresql` | `django.db.backends.mysql`（MySQL 时） |
| `DB_HOST` | 数据库地址 | `127.0.0.1` | 生产库 IP |
| `DB_PORT` | 数据库端口 | `5432` | `3306`（MySQL 时） |
| `DB_NAME` | 数据库名 | `django_manage` | 同左 |
| `DB_USER` | 数据库用户 | `postgres` | `django` 或 `root` |
| `DB_PASSWORD` | 数据库密码 | — | **生产必设** |

### Nginx 反向代理

两台部署共用同一份 Nginx 配置，仅有**静态文件路径**不同：

| 部署方式 | `alias` 路径 |
|---|---|
| Docker | `/path/on/host/staticfiles/`（需挂载或 `docker cp` 到宿主机） |
| 源码部署 | `/opt/django-manage/staticfiles/` |

```nginx
# ── 真实 IP 还原（应对上游云 LB / CDN）──
real_ip_header    X-Forwarded-For;
real_ip_recursive on;
set_real_ip_from  10.0.0.0/8;
set_real_ip_from  172.16.0.0/12;
set_real_ip_from  192.168.0.0/16;

# ── 上游：ip_hash 保证 MCP session 亲和性 ──
upstream django_asgi {
    ip_hash;
    server 127.0.0.1:8000;
}

server {
    listen 80;
    server_name your-domain.com;
    client_max_body_size 100m;

    location /static/ {
        alias /opt/django-manage/staticfiles/;   # ← 按部署方式修改此行
        expires 30d;
    }

    # MCP SSE 长连接（关闭缓冲 + 长超时）
    location /mcp/ {
        proxy_pass http://django_asgi;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_buffering off;
        proxy_read_timeout 3600s;
    }

    location / {
        proxy_pass http://django_asgi;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

```bash
sudo ln -sf /etc/nginx/sites-available/django-manage /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

#### 上游反代层注意事项

如果 Nginx 前面还有云 LB / CDN / 自建网关：

**① 透传客户端 IP**——自建 Nginx 加一行：

```nginx
proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
```

云厂商（ALB/SLB/CLB）默认已透传；Cloudflare 默认提供 `X-Forwarded-For` 和 `CF-Connecting-IP`，如用后者改为 `real_ip_header CF-Connecting-IP;`。

**② 关闭 SSE 缓冲**——自建 Nginx：

```nginx
location /mcp/ {
    proxy_buffering off;
    proxy_read_timeout 3600s;
    proxy_http_version 1.1;
    proxy_set_header Connection "";
    proxy_pass http://<inner-nginx>;
}
```

AWS ALB / 阿里云 SLB 默认不缓冲，无需额外配置。

> **核心原则**：内层 Nginx 拿到的 `X-Forwarded-For` 最左端必须是真实客户端 IP，否则 `real_ip` 还原失败 → `ip_hash` 全部落到第一个 worker。

### CI/CD

推送 `master` 分支或 `v*` 标签时，GitHub Actions 自动构建并推送 Docker 镜像：

```
{DOCKERHUB_USERNAME}/django-manage:latest    # tag 触发
{DOCKERHUB_USERNAME}/django-manage:master    # 分支推送
{DOCKERHUB_USERNAME}/django-manage:v1.0.0    # semver tag
```

所需 Secrets：`DOCKERHUB_USERNAME`、`DOCKERHUB_TOKEN`。

---

## SAP RFC 集成

`app_sap_services` 通过 pyrfc 对接 SAP，线程安全连接池，9 个业务域共 19 个 RFC 函数。

| 服务 | RFC 函数（部分） | 说明 |
|---|---|---|
| MaterialService | `ZRFC_MATERIAL_MESN` · `ZFG_CHECK_MATERIAL` | 物料主数据查询/校验 |
| CustomerService | `ZRFC_GET_CUSTOMER` · `ZRFC_MODIFY_CUSTOMER` · `ZRFC_GET_KNMT` | 客户主数据 CRUD |
| SalesService | `ZRFC_GET_SALE_ORDERS` · `ZRFC_CREATE_SALE_ORDERS` · `ZRFC_GET_SALES_PRICE_LIST` | 销售订单 |
| PriceService | `ZRFC_GET_MBEW` · `ZRFC_GET_LAST_INVOICE_PRICE` | 价格/成本 |
| DeliveryService | `ZRFC_CREATE_OUTB_DELIVERY` · `ZRFC_UPDATE_OUTB_DELIVERY` | 交货单 |
| ProductionService | `ZIF_MES_GET_OPEN_PROD` · `ZIF_JJGZ_CREATE_PRODORDCF` · … | 生产订单/报工 |
| VendorService | `ZFG_CHECK_VENDOR` | 供应商校验 |
| WMSService | `ZRFC_GET_MAT_ORDER_ISSUE_DATA` | 仓库发料 |
| QuotaService | `ZRFC_QUOTA_CREATE` · `ZRFC_RV_CONDITION_COPY` | 配额/定价 |

### SDK 配置

| 平台 | SDK 路径 | 运行时配置 |
|---|---|---|
| **Windows** | `win-nwrfc750P_6-70002755/nwrfcsdk/lib` | PATH 追加 `lib` · `os.add_dll_directory()` |
| **Linux** | `/opt/sap_nwrfcsdk/lib` | `LD_LIBRARY_PATH` + `SAP_LIB_PATH` 环境变量 |
| **Docker** | `/opt/sap_nwrfcsdk/lib` | Dockerfile 自动设置上述变量 |

> SDK 文件位于 [app_sap_services/SAP_NetWeaver_RFC_SDK_750P/](app_sap_services/SAP_NetWeaver_RFC_SDK_750P/)，同时包含 Linux 和 Windows 版本。

---

## MCP Server

基于 [Model Context Protocol](https://modelcontextprotocol.io/)，通过 SSE 长连接向 AI Agent 暴露 Django 业务数据。

```
Client (AI Agent)                        Django
     │
     ├─ GET /mcp/sse/ ────────────────→ 建立 SSE 流，返回 sessionId
     │   ← event: endpoint               POST 地址：/mcp/messages/?sessionId=xxx
     │
     ├─ POST /mcp/messages/ ──────────→ JSON-RPC 工具调用
     │   ← SSE event: message ──────── 流式返回结果
```

### 鉴权

```python
# settings.py — 不设置则跳过鉴权（开发环境）
MCP_API_KEY = os.environ.get('MCP_API_KEY')
```

客户端请求头：`X-MCP-API-KEY: <key>`

### 工具清单

| 工具 | 说明 | 关键参数 |
|---|---|---|
| `search_projects` | 搜索项目（名称/负责人/客户/OEM） | `keyword`, `is_terminated` |
| `get_project_details` | 项目详情 + 进度时间线 + 附件 | `project_id` 或 `project_name` |
| `search_material_library` | 搜索物料库（牌号/制造商/类别） | `keyword`, `category` |
| `get_material_and_formulas` | 物料性能数据 + 关联实验配方 | `grade_name` |
| `search_formulas` | 搜索配方（编码/名称） | `keyword` |
| `get_formula_detail` | 配方详情（BOM、成本、测试结果） | `code` |

新增工具只需在 `app_mcp_server/tools/` 下添加 `.py` 文件，Django 启动时自动注册。

---

## 管理命令

| 命令 | 分类 | 说明 |
|---|---|---|
| `import_base_data` | 数据导入 | 导入物料类型、应用场景 |
| `import_configs` | 数据导入 | 导入指标类别、测试标准 |
| `import_raw_materials` | 数据导入 | 从 Excel 导入原材料 |
| `import_raw_material_types` | 数据导入 | 导入原材料类型 |
| `import_suppliers` | 数据导入 | 导入供应商 |
| `import_oems` | 数据导入 | 导入 OEM 厂商 |
| `sync_catalog` | 数据同步 | 同步产品目录 |
| `init_permissions` | 权限 | 初始化 L3 权限组 |
| `init_performance_rules` | 项目 | 初始化 RD+SALES 双轨绩效规则 |
| `cleanup_notifications` | 运维 | 清理过期通知 |
| `process_webhooks` | 运维 | 处理待发送 Webhook |
| `sap_test` | SAP | 连接健康检查 + 物料查询测试 |
| `run_mcp_server` | MCP | 独立 stdio 模式 MCP Server（Claude Desktop 本地模式） |

---

## 项目结构

```
Django_manage/
├── Django_manage/              # settings.py · urls.py · asgi.py · wsgi.py
├── templates/                  # 全局 Django 模板
├── static/                     # 静态资源（Tabler · HTMX · Tom Select · Highcharts）
├── staticfiles/                # collectstatic 输出（运行时）
├── init/                       # 种子数据（BPMN · 表单 · 物料 · 供应商 · Excel）
│
├── app_panel/                  # 仪表盘
├── app_user/                   # 用户 · 权限 · RBAC
├── app_project/                # 项目 · 绩效
├── app_repository/             # OEM · 客户 · 项目档案
├── app_material/               # 物料主数据
├── app_material_api/           # 物料 REST API · Webhook
├── app_raw_material/           # 原材料
├── app_process/                # 工艺参数
├── app_formula/                # 配方 BOM
├── app_basic_research/         # 基础研究
├── app_catalog/                # 产品目录同步
├── app_workflow/               # 工作流引擎
├── app_form_management/        # 动态表单
├── app_trial_production/       # 试验排产
├── app_color_center/           # 配色中心
├── app_material_testing/       # 材料测试
├── app_mold_injection/         # 模具注塑
├── app_attachment/             # 附件管理
├── app_notification/           # 通知中心
├── app_sap_services/           # SAP RFC 服务
├── app_mcp_server/             # AI MCP Server
├── common_utils/               # 通用工具
│
├── Dockerfile
├── requirements.txt
├── .dockerignore
└── .github/workflows/          # CI/CD
```
