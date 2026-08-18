"""
Django settings for Django_manage project.
"""
import os
from pathlib import Path

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# 加载 .env 文件（本地开发用；Docker 环境下环境变量已由 compose 注入，override=False 确保不覆盖）
from dotenv import load_dotenv
load_dotenv(BASE_DIR / '.env')


# ==============================================================================
# 核心安全配置
# ==============================================================================

# SECURITY WARNING: keep the secret key used in production secret!
# 通过环境变量 SECRET_KEY 设置（必须在 .env 或容器环境变量中配置）
SECRET_KEY = os.environ.get('SECRET_KEY', '')

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = os.environ.get('DEBUG', 'True').lower() in ('true', '1', 'yes')

# 允许访问的主机名/IP，逗号分隔。使用 '*' 仅允许开发环境
ALLOWED_HOSTS = [host.strip() for host in os.environ.get('ALLOWED_HOSTS', '*').split(',') if host.strip()]


# ==============================================================================
# CSRF / 跨域受信域名
# ==============================================================================

# CSRF 受信域名，逗号分隔（通过环境变量 CSRF_TRUSTED_ORIGINS 配置）
# 示例：http://192.168.5.10:8080,https://your-domain.com
_csrf_origins = os.environ.get('CSRF_TRUSTED_ORIGINS', '')
CSRF_TRUSTED_ORIGINS = [origin.strip() for origin in _csrf_origins.split(',') if origin.strip()]

# HTTPS 反向代理配置
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
USE_X_FORWARDED_HOST = True
USE_X_FORWARDED_PORT = True


# ==============================================================================
# Application 注册 & 中间件
# ==============================================================================

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.postgres',
    'pgvector.django',
    'rest_framework',
    'django_filters',
    'django_cleanup.apps.CleanupConfig',  # 删除数据库记录时，自动删除物理文件。
    'axes',
    'app_attachment.apps.AppAttachmentConfig',  # 附件管理（须在业务app之前）
    'app_panel.apps.AppPanelConfig',
    'app_project.apps.AppProjectConfig',
    'app_user.apps.AppUserConfig',
    'app_repository.apps.AppRepositoryConfig',
    'app_material.apps.AppMaterialConfig',
    'app_external_api.apps.AppExternalApiConfig',
    'app_notification.apps.AppNotificationConfig',
    'app_raw_material.apps.AppRawMaterialConfig',
    'app_process.apps.AppProcessConfig',
    'app_formula.apps.AppFormulaConfig',
    'app_basic_research.apps.AppBasicResearchConfig',
    'app_catalog.apps.AppCatalogConfig',
    'common_utils.apps.CommonUtilsConfig',
    'app_workflow.apps.AppWorkflowConfig',             # 工作流模块
    'app_form_management.apps.AppFormManagementConfig',  # 表单管理模块
    'app_trial_production.apps.AppTrialProductionConfig',  # 试验排产模块
    'app_color_center.apps.AppColorCenterConfig',  # 配色中心
    'app_material_testing.apps.AppMaterialTestingConfig',  # 材料测试中心
    'app_mold_injection.apps.AppMoldInjectionConfig',  # 模具注塑中心
    "debug_toolbar",                                    # 这是debug_toolbar的配置
    'app_mcp_server.apps.AppMcpServerConfig',           # AI MCP server
    'app_sap_services.apps.AppSapServicesConfig',     # SAP RFC 服务
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    "debug_toolbar.middleware.DebugToolbarMiddleware", # 这是debug_toolbar的配置
    'axes.middleware.AxesMiddleware', # django-axes 登录失败次数中间件
    'app_user.middleware.SecurityShieldMiddleware', # 访问盾中间件
    'app_notification.middleware.CurrentUserMiddleware', # 通知中间件
]

ROOT_URLCONF = 'Django_manage.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'app_notification.context_processors.notifications',
                'app_user.context_processors.menu_processor.sidebar_menu_permissions',
                'app_formula.context_processors.formula_permissions',
            ],
        },
    },
]

WSGI_APPLICATION = 'Django_manage.wsgi.application'


# ==============================================================================
# 数据库配置
# ==============================================================================

# DATABASES = {
#     'default': {
#         'ENGINE': 'django.db.backends.sqlite3',
#         'NAME': BASE_DIR / 'db.sqlite3',
#     }
# }

# DATABASES = {
#     "default": {
#         "ENGINE": "django.db.backends.mysql",
#         "NAME": "django_manage",
#         "USER": "root",
#         "PASSWORD": "123456",
#         "HOST": "127.0.0.1",
#         "PORT": "3306",
#     }
# }

# 默认 PostgreSQL，通过环境变量可覆盖为 MySQL
DATABASES = {
    'default': {
        'ENGINE': os.environ.get('DB_ENGINE', 'django.db.backends.postgresql'),
        'NAME': os.environ.get('DB_NAME', 'django_manage'),
        'USER': os.environ.get('DB_USER', 'postgres'),
        'PASSWORD': os.environ.get('DB_PASSWORD', ''),
        'HOST': os.environ.get('DB_HOST', '127.0.0.1'),
        'PORT': os.environ.get('DB_PORT', '5432'),
    }
}


# ==============================================================================
# 用户认证
# ==============================================================================

AUTH_USER_MODEL = 'app_user.User'

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

AUTHENTICATION_BACKENDS = [
    'axes.backends.AxesStandaloneBackend', # django-axes 认证后端
    'app_user.backends.EmailBackend',      # 仅邮箱登录（不再支持用户名登录）
]

# 注册页面邀请码（留空则关闭注册入口）
REGISTER_INVITE_CODE = os.environ.get('REGISTER_INVITE_CODE', '888888')

# 登录页邮箱后缀快捷选择（逗号分隔，可从环境变量 EMAIL_DOMAINS 配置）
# 用户只需填写邮箱前缀，再选一个后缀即可；同时提供"自定义域名"选项。
EMAIL_DOMAINS = [d.strip() for d in os.environ.get('EMAIL_DOMAINS', 'sunwill.com.cn').split(',') if d.strip()]

# ==============================================================================
# 国际化 & 时区
# ==============================================================================

LANGUAGE_CODE = 'zh-hans'
TIME_ZONE = 'Asia/Shanghai'
USE_I18N = True
USE_TZ = True


# ==============================================================================
# 静态文件 & 媒体文件
# ==============================================================================

STATIC_URL = 'static/'

# STATIC_ROOT是在部署的时候才发挥作用,执行 python managy.py collectstatic ，会在工程文件下生成staticfiles文件夹，把各个app下的静态文件收集到这个目录下。
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')
STATICFILES_DIRS = (os.path.join(BASE_DIR, 'static'),)


# ==============================================================================
# 登录 / 权限 / URL 跳转
# ==============================================================================

LOGIN_URL = 'login'
LOGIN_REDIRECT_URL = 'panel_home'
LOGOUT_REDIRECT_URL = 'login'
PERM_DENIED_URL = '/permission-denied/'
ADMIN_URL = '/admin'


# ==============================================================================
# Debug Toolbar
# ==============================================================================

INTERNAL_IPS = [
    "127.0.0.1",
]


# ==============================================================================
# 邮件配置
# ==============================================================================

# 邮件配置（通过环境变量配置；默认值仅用于本地开发）
EMAIL_BACKEND = os.environ.get('EMAIL_BACKEND', 'django.core.mail.backends.smtp.EmailBackend')
EMAIL_HOST = os.environ.get('EMAIL_HOST', 'smtp.163.com')
EMAIL_PORT = int(os.environ.get('EMAIL_PORT', '994') or '994')
EMAIL_USE_SSL = os.environ.get('EMAIL_USE_SSL', 'True').lower() in ('true', '1', 'yes')
EMAIL_HOST_USER = os.environ.get('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = os.environ.get('EMAIL_HOST_PASSWORD', '')
DEFAULT_FROM_EMAIL = os.environ.get('DEFAULT_FROM_EMAIL', os.environ.get('EMAIL_HOST_USER', ''))  # 默认发件人


# ==============================================================================
# django-axes（防暴力破解）
# ==============================================================================

AXES_FAILURE_LIMIT = int(os.environ.get('AXES_FAILURE_LIMIT', '5'))
AXES_COOLOFF_TIME = float(os.environ.get('AXES_COOLOFF_TIME', '0.0833'))
AXES_RESET_ON_SUCCESS = os.environ.get('AXES_RESET_ON_SUCCESS', 'True').lower() in ('true', '1', 'yes')
AXES_LOCKOUT_URL = '/user/login/?locked=1' # 锁定后重定向的URL (带参数)


# ==============================================================================
# Session 配置
# ==============================================================================

SESSION_COOKIE_AGE = 36000  # 保持登录10小时 (10 * 60 * 60)
SESSION_EXPIRE_AT_BROWSER_CLOSE = True  # 默认关闭浏览器后需重新登录 (除非勾选"保持登录")


# ==============================================================================
# Django REST Framework
# ==============================================================================

REST_FRAMEWORK = {
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
    'DEFAULT_THROTTLE_RATES': {
        'auth_verify': '10/min',
    },
}


# ==============================================================================
# 主系统 ↔ 电子手册子系统（app_catalog）集成配置
# ==============================================================================
# 当前为「单工程双实例」部署：主系统与手册系统共用本 settings.py。
# 手册系统（app_catalog）设计为可独立迁移，迁移时按下侧标注摘取配置。

# 通信安全 Token（两侧必须一致）：
#   主系统侧 —— InternalApiTokenPermission 校验入站请求头 X-Internal-Api-Token
#   手册系统侧 —— CatalogGateway 出站请求携带该头
INTERNAL_API_TOKEN = os.environ.get('INTERNAL_API_TOKEN', '')

# ── 手册系统侧配置（迁移手册系统时，以下 3 项需一并带走）──────────────
# 主系统对外接口基础地址：手册系统连接主系统的入口（结尾需带斜杠）
EXTERNAL_API_BASE_URL = os.environ.get('EXTERNAL_API_BASE_URL', 'http://127.0.0.1:8000/api/external/')
# 手册系统本地 worker 内存缓存：轮询主系统数据版本号的间隔（秒）
CATALOG_CACHE_VERSION_CHECK_INTERVAL = int(os.environ.get('CATALOG_CACHE_VERSION_CHECK_INTERVAL', '5'))
# 手册系统请求主系统的超时（秒）
REMOTE_API_TIMEOUT = float(os.environ.get('REMOTE_API_TIMEOUT', '15'))

# ── 主系统侧配置（本实例作为主系统对外提供数据时使用）──────────────
# 材料库对外接口的 L2 版本号缓存见下方 CACHES['material']，无需在此额外配置。


# ==============================================================================
# 日志配置 — 详见 logging_config.py
# ==============================================================================
from .logging_config import build_logging

LOGGING = build_logging(debug=DEBUG)


# ==============================================================================
# SAP RFC 服务配置
# ==============================================================================

SAP_SERVICES_CONFIG = {
    # SAP NW RFC SDK lib 目录的绝对路径（必须存在）
    # Linux/Docker 通过环境变量 SAP_LIB_PATH 覆盖，Windows 使用本地路径
    'sap_lib_path': os.environ.get(
        'SAP_LIB_PATH',
        r"D:\SAP_SDK\win-nwrfc750P_6-70002755\nwrfcsdk\lib"
    ),

    # SAP 连接参数（通过环境变量配置）
    'connection': {
        'ashost': os.environ.get('SAP_HOST', ''),
        'sysnr': os.environ.get('SAP_SYSNR', '00'),
        'client': os.environ.get('SAP_CLIENT', '400'),
        'user': os.environ.get('SAP_USER', ''),
        'passwd': os.environ.get('SAP_PASSWORD', ''),
        'lang': os.environ.get('SAP_LANG', 'ZH'),
    },

    # 连接池参数
    'max_idle_seconds': int(os.environ.get('SAP_MAX_IDLE_SECONDS', '300')),
    'max_retries': int(os.environ.get('SAP_MAX_RETRIES', '3')),
    'retry_delay': float(os.environ.get('SAP_RETRY_DELAY', '1.0')),
}


# ==============================================================================
# 缓存配置 — RBAC 权限缓存使用 DatabaseCache 实现跨 Worker 共享
# ==============================================================================

CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
    },
    'rbac': {
        'BACKEND': 'django.core.cache.backends.db.DatabaseCache',
        'LOCATION': 'rbac_cache',
        'TIMEOUT': 3600,  # 1 小时 TTL，兜底保护：即使缓存失效遗漏，1 小时后自动过期
    },
    # [主系统侧] 材料库对外接口数据缓存：L2 版本号（跨 Worker 失效信号），L1 为各 Worker 进程内存
    'material': {
        'BACKEND': 'django.core.cache.backends.db.DatabaseCache',
        'LOCATION': 'material_cache',
        'TIMEOUT': 3600,
    },
}
