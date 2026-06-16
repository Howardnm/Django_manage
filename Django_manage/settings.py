"""
Django settings for Django_manage project.
"""
import os
from pathlib import Path

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = 'django-insecure-)e+q_t^)%a1(&zrgpj=hgz6aeuj-(4edq4tgod(*s8e^(qwvcv'

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True

# 允许所有ip访问
ALLOWED_HOSTS = ['*']

# 跨域受信域名
CSRF_TRUSTED_ORIGINS = [
    'http://192.168.123.18:8080',  # 你的域名（http协议）
    'https://www.yourdomain.com',  # 若开启了HTTPS，必须添加对应https域名
    'http://你的服务器公网IP',  # 若用IP访问，也需添加
]

# Secure settings for HTTPS
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
USE_X_FORWARDED_HOST = True
USE_X_FORWARDED_PORT = True

# Application definition

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
    "debug_toolbar",                                    # 这是debug_toolbar的配置
    'app_mcp_server.apps.AppMcpServerConfig',           # AI MCP server
    'app_sap_services.apps.AppSapServicesConfig',     # SAP RFC 服务
    # 'app_knowledge_base.apps.AppKnowledgeBaseConfig', # 文献知识库
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
                # 新增：通知上下文处理器
                'app_notification.context_processors.notifications',
                # 核心：侧边栏权限处理器 (新路径)
                'app_user.context_processors.menu_processor.sidebar_menu_permissions',
            ],
        },
    },
]

WSGI_APPLICATION = 'Django_manage.wsgi.application'

# Database
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

# DATABASES = {
#     "default": {
#         "ENGINE": "django.db.backends.mysql",
#         "NAME": "django_manage",
#         "USER": "django_manage",
#         "PASSWORD": "6THtw4rFdHpmZ3Ze",
#         "HOST": "127.0.0.1",
#         "PORT": "3306",
#     }
# }

# DATABASES = {
#     'default': {
#         'ENGINE': 'django.db.backends.postgresql',
#         'NAME': 'django_manage',
#         'USER': 'admin',
#         'PASSWORD': '850996480',
#         'HOST': '192.168.123.47',
#         'PORT': '3307',
#     }
# }

# 自定义用户模型
AUTH_USER_MODEL = 'app_user.User'

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# Internationalization
LANGUAGE_CODE = 'zh-hans'
TIME_ZONE = 'Asia/Shanghai'
USE_I18N = True
USE_TZ = True

# Static files
STATIC_URL = 'static/'
# MEDIA_URL = 'images/'

# STATIC_ROOT是在部署的时候才发挥作用,执行 python managy.py collectstatic ，会在工程文件下生成staticfiles文件夹，把各个app下的静态文件收集到这个目录下。
# 1.在Django中setting.py文件中加入
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')
STATICFILES_DIRS = (os.path.join(BASE_DIR, 'static'),)

# 【新增配置】登录/注销后的跳转地址
LOGIN_URL = 'login'  # 没登录时自动跳到这里
LOGIN_REDIRECT_URL = 'panel_home'  # 登录成功后跳到这里
LOGOUT_REDIRECT_URL = 'login'  # 注销后跳到这里

# 当用户已登录但没有所需权限时，PermissionRequiredMixin 会重定向到此 URL
PERM_DENIED_URL = '/permission-denied/'
ADMIN_URL = '/admin'

# 这是debug_toolbar的配置
INTERNAL_IPS = [
    "127.0.0.1",
]


# 注册页面邀请码（当注释掉邀请码时，自动关闭注册入口）
# REGISTER_INVITE_CODE = '888888'

# 自定义认证后端 (支持邮箱登录)
AUTHENTICATION_BACKENDS = [
    'axes.backends.AxesStandaloneBackend', # django-axes 认证后端
    # 'app_user.backends.EmailBackend', # 移除邮箱登录
    'django.contrib.auth.backends.ModelBackend',
]

# 邮件配置 (使用163邮箱作为示例，请替换为实际配置)
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = 'smtp.163.com'  # SMTP服务器地址
EMAIL_PORT = 994  # SMTP端口
EMAIL_USE_SSL = True  # 使用SSL
EMAIL_HOST_USER = 'bueess@163.com'  # 发件人邮箱
EMAIL_HOST_PASSWORD = 'DXHZGGWTFIIQAHCV'  # 邮箱授权码 (非登录密码)
DEFAULT_FROM_EMAIL = EMAIL_HOST_USER  # 默认发件人

# django-axes 配置
AXES_FAILURE_LIMIT = 5  # 允许失败的次数
AXES_COOLOFF_TIME = 0.0833   # 锁定时间（小时），0.0833小时约等于5分钟
AXES_RESET_ON_SUCCESS = True # 登录成功后重置失败计数
AXES_LOCKOUT_URL = '/user/login/?locked=1' # 锁定后重定向的URL (带参数)

# Session 配置
SESSION_COOKIE_AGE = 36000  # 保持登录10小时 (10 * 60 * 60)
SESSION_EXPIRE_AT_BROWSER_CLOSE = True  # 默认关闭浏览器后需重新登录 (除非勾选"保持登录")


# --- REST FRAMEWORK ---
REST_FRAMEWORK = {
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
}

# --- 内部集成安全性与同步配置 ---
# 通信安全 Token (必须与主系统 INTERNAL_API_TOKEN 保持一致)
INTERNAL_API_TOKEN = 'catalog-portal-secure-token-2024'
# Webhook 校验密钥 (必须与主系统 WEBHOOK_SECRET_KEY 保持一致)
WEBHOOK_SECRET_KEY = 'your-secure-webhook-secret-key'
CATALOG_WEBHOOK_URL = 'http://127.0.0.1:8001/catalog/api/webhook/material/'
# 主系统 API 的基础地址 (结尾需带斜杠)
REMOTE_API_BASE_URL = 'http://127.0.0.1:8000/api/material/'

# --- 日志配置 ---
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
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)

# ==============================================================================
# SAP RFC 服务配置
# ==============================================================================
SAP_SERVICES_CONFIG = {
    # SAP NW RFC SDK lib 目录的绝对路径（必须存在）
    'sap_lib_path': r"D:\SAP_SDK\win-nwrfc750P_6-70002755\nwrfcsdk\lib",

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

# SAP 日志配置
LOGGING['loggers']['sap'] = {
    'handlers': ['file', 'console'],
    'level': 'INFO',
    'propagate': True,
}
