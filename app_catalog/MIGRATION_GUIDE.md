# 产品电子手册 (app_catalog) 迁移与部署指南

## 1. 模块概述
`app_catalog` 模块采用了 **“本地轻量索引 + 远程 API 实时拉取”** 的架构设计。该模块与主系统 (`app_material`) 在逻辑和数据上已完全解耦，具备独立部署到新服务器的条件。

## 2. 迁移内容清单
在迁移时，请确保拷贝以下目录及文件：

- **后端代码**: `app_catalog/` 全文件夹
- **前端模板**: `templates/apps/app_catalog/` 全文件夹
- **静态资源**: `static/tabler/` (确保目标系统拥有 Tabler UI 核心文件)

## 3. 目标系统环境配置

### 3.1 依赖安装
目标系统需安装以下 Python 包：
```bash
pip install djangorestframework requests django-filter
```

### 3.2 `settings.py` 必要参数
在目标系统的配置文件中，必须包含以下“通信钥匙”：

```python
# 1. 注册应用
INSTALLED_APPS = [
    ...
    'rest_framework',
    'app_catalog',
]

# 2. 远程通信配置
# 主系统 API 的基础地址 (结尾需带斜杠)
REMOTE_API_BASE_URL = 'http://主系统域名或IP:端口/api/material/'

# 通信安全 Token (必须与主系统 INTERNAL_API_TOKEN 保持一致)
INTERNAL_API_TOKEN = 'catalog-portal-secure-token-2024'

# Webhook 校验密钥 (必须与主系统 WEBHOOK_SECRET_KEY 保持一致)
WEBHOOK_SECRET_KEY = 'your-secure-webhook-secret-key'

# 3. 缓存配置 (建议开启以提升详情页性能)
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
    }
}
```

### 3.3 `urls.py` 路由注册
在目标系统的总路由中引入模块路由：
```python
urlpatterns = [
    ...
    path('catalog/', include('app_catalog.urls')),
]
```

## 4. 部署与初始化步骤

1. **同步数据库结构**:
   ```bash
   python manage.py makemigrations app_catalog
   python manage.py migrate app_catalog
   ```

2. **执行全量初始化同步**:
   运行此命令从主系统抓取所有已有的材质分类和物料索引：
   ```bash
   python manage.py sync_catalog
   ```

3. **配置主系统 Webhook 推送地址**:
   在**主系统**的 `settings.py` 中，更新推送目标地址指向新服务器：
   ```python
   CATALOG_WEBHOOK_URL = 'http://新服务器IP:端口/catalog/api/webhook/material/'
   ```

## 5. 运维监控
- **日志排查**: 查看 `logs/system_integration.log` (需在 settings 中配置 LOGGING)。
- **同步状态**: 进入目标系统的 Admin 后台，在“手册产品列表”中可以查看同步过来的物料，并控制 `is_published` (对外发布) 状态。

---
**提示**: 迁移后，请务必执行一次 `sync_catalog` 以验证 API 通信和 Token 校验是否正常。
