"""
Django settings for Django_manage project.
"""
import os
from pathlib import Path

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent


# ==============================================================================
# 核心安全配置
# ==============================================================================

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = 'django-insecure-)e+q_t^)%a1(&zrgpj=hgz6aeuj-(4edq4tgod(*s8e^(qwvcv'
# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True
# 允许所有ip访问
ALLOWED_HOSTS = ['*']


# ==============================================================================
# CSRF / 跨域受信域名
# ==============================================================================

# 默认值始终生效，环境变量 CSRF_TRUSTED_ORIGINS 逗号分隔追加
# 示例：export CSRF_TRUSTED_ORIGINS="http://192.168.5.10:8080,https://your-domain.com"
CSRF_TRUSTED_ORIGINS = [
    'http://192.168.123.18:8080',
    'https://www.yourdomain.com', # 若开启了HTTPS，必须添加对应https域名
]

_csrf_env = os.environ.get('CSRF_TRUSTED_ORIGINS', '')
if _csrf_env:
    CSRF_TRUSTED_ORIGINS.extend(origin.strip() for origin in _csrf_env.split(',') if origin.strip())

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
    'app_material_api.apps.AppMaterialApiConfig',
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
        'PASSWORD': os.environ.get('DB_PASSWORD', '123456'),
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
    # 'app_user.backends.EmailBackend', # 移除邮箱登录
    'django.contrib.auth.backends.ModelBackend',
]

# 注册页面邀请码（当注释掉邀请码时，自动关闭注册入口）
REGISTER_INVITE_CODE = '888888'

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

# 邮件配置 (使用163邮箱作为示例，请替换为实际配置)
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = 'smtp.163.com'
EMAIL_PORT = 994
EMAIL_USE_SSL = True
EMAIL_HOST_USER = 'bueess@163.com'
EMAIL_HOST_PASSWORD = 'DXHZGGWTFIIQAHCV'
DEFAULT_FROM_EMAIL = EMAIL_HOST_USER  # 默认发件人


# ==============================================================================
# django-axes（防暴力破解）
# ==============================================================================

AXES_FAILURE_LIMIT = 5  # 允许失败的次数
AXES_COOLOFF_TIME = 0.0833   # 锁定时间（小时），约5分钟
AXES_RESET_ON_SUCCESS = True # 登录成功后重置失败计数
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
}


# ==============================================================================
# 内部集成 — API Token & Webhook
# ==============================================================================
# 通信安全 Token (必须与主系统 INTERNAL_API_TOKEN 保持一致)
INTERNAL_API_TOKEN = 'catalog-portal-secure-token-2024'
# Webhook 校验密钥 (必须与主系统 WEBHOOK_SECRET_KEY 保持一致)
WEBHOOK_SECRET_KEY = 'your-secure-webhook-secret-key'
CATALOG_WEBHOOK_URL = 'http://127.0.0.1:8001/catalog/api/webhook/material/'
# 主系统 API 的基础地址 (结尾需带斜杠)
REMOTE_API_BASE_URL = 'http://127.0.0.1:8000/api/material/'


# ==============================================================================
# 日志配置
# ==============================================================================

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {'format': '{levelname} {asctime} {module} {process:d} {thread:d} {message}', 'style': '{'},
        'simple': {'format': '{levelname} {asctime} {message}', 'style': '{'},
    },
    'handlers': {
        'file': {
            'level': 'INFO',
            'class': 'logging.FileHandler',
            'filename': os.path.join(BASE_DIR, 'logs/system_integration.log'),
            'formatter': 'verbose',
        },
        'console': {'level': 'DEBUG', 'class': 'logging.StreamHandler', 'formatter': 'simple'},
    },
    'loggers': {
        'app_material_api.integration': {'handlers': ['file', 'console'], 'level': 'INFO', 'propagate': True},
        'app_catalog.api': {'handlers': ['file', 'console'], 'level': 'INFO', 'propagate': True},
    },
}

LOG_DIR = os.path.join(BASE_DIR, 'logs')
os.makedirs(LOG_DIR, exist_ok=True)


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

    # SAP 连接参数
    'connection': {
        'ashost': '192.168.103.181',  # SAP 服务器 IP 或主机名
        'sysnr': '00',                 # SAP 系统编号
        'client': '400',               # SAP 客户端号
        'user': 'RFC07',               # SAP 通信账号
        'passwd': 'Saite@2026',        # SAP 通信密码
        'lang': 'ZH',                  # 语言（ZH=中文, EN=英文）
    },

    # 连接池参数
    'max_idle_seconds': 300,  # 闲置连接超过此时长（秒）后自动重建
    'max_retries': 3,         # 连接失败重试次数
    'retry_delay': 1.0,       # 重试初始间隔（秒），每次重试翻倍
}

# SAP 日志
LOGGING['loggers']['sap'] = {
    'handlers': ['file', 'console'],
    'level': 'INFO',
    'propagate': True,
}
