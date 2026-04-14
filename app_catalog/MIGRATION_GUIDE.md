# 产品电子手册 (app_catalog) 迁移与部署指南

本模块采用了 **“本地结构化镜像 + 远程 API 实时拉取”** 的高性能架构。本指南旨在指导如何将 `app_catalog` 迁移到一套全新的 Django 系统中。

## 1. 迁移内容清单
请拷贝以下目录到您的新系统中：

- **后端逻辑**: `app_catalog/` (整个 App 文件夹)
- **前端模板**: `templates/apps/app_catalog/` (包含 layouts, includes, product_detail 目录)
- **静态资源**: `static/tabler/` (确保新系统中有 Tabler UI 核心文件)

## 2. 环境依赖
在目标系统中执行：
```bash
pip install djangorestframework requests django-filter
```

## 3. 目标系统配置 (settings.py)

### 3.1 注册应用
```python
INSTALLED_APPS = [
    ...
    'rest_framework',
    'app_catalog',
]
```

### 3.2 通信安全配置
必须确保与主系统的配置 **完全一致**：
```python
# 主系统 API 基地址
REMOTE_API_BASE_URL = 'http://主系统IP或域名:端口/api/material/'

# 通信安全 Token
INTERNAL_API_TOKEN = 'catalog-portal-secure-token-2024'

# Webhook 校验密钥
WEBHOOK_SECRET_KEY = 'your-secure-webhook-secret-key'
```

### 3.3 缓存配置 (建议)
为保证导航树和详情页的极速加载，建议开启缓存：
```python
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
    }
}
```

## 4. 路由注册 (urls.py)
在总路由中引入：
```python
urlpatterns = [
    ...
    path('catalog/', include('app_catalog.urls')),
]
```

## 5. 部署与初始化

1. **建立数据库结构**:
   ```bash
   python manage.py makemigrations app_catalog
   python manage.py migrate app_catalog
   ```

2. **首次全量镜像同步**:
   运行以下命令，从主系统抓取所有已发布的场景、特征、分类和物料：
   ```bash
   python manage.py sync_catalog
   ```

3. **配置主系统 Webhook**:
   在**主系统**的 `settings.py` 中，更新推送目标地址：
   ```python
   CATALOG_WEBHOOK_URL = 'http://新系统IP:端口/catalog/api/webhook/material/'
   ```

## 6. 运维与验证
- **全量同步**: 任何时候数据不一致，均可再次运行 `sync_catalog` 指令。
- **实时同步**: 查看 `logs/system_integration.log` 确认 Webhook 接收是否正常。
- **发布控制**: 进入新系统的 Admin 后台，在“手册产品列表”中控制牌号的对外可见性。

---
**SUNWILL 技术团队自研 - 2024**
