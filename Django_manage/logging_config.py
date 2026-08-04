"""
日志根配置模块 — 声明式日志管理。

采用 Django 官方推荐的 dictConfig 格式，通过 MODULE_LOGGERS 注册表
实现一个模块 = 一行配置的声明式体验。

新增模块日志接入：
    在 MODULE_LOGGERS 表中添加一行即可：
    'app_new_module': {'handlers': ['console', 'file_app'], 'level': INFO},

使用方式（settings.py）：
    from .logging_config import build_logging
    LOGGING = build_logging(debug=DEBUG)

参考文档：
    D:\django-docs-6.0-en\howto\logging.html
    D:\django-docs-6.0-en\topics\logging.html
"""

import os
from pathlib import Path

# ==============================================================================
# 区1: 日志目录 & 级别常量
# ==============================================================================

BASE_DIR = Path(__file__).resolve().parent.parent
LOG_DIR = BASE_DIR / 'logs'
LOG_DIR.mkdir(exist_ok=True)

DEBUG = 'DEBUG'
INFO = 'INFO'
WARNING = 'WARNING'
ERROR = 'ERROR'
CRITICAL = 'CRITICAL'

# ==============================================================================
# 区2: Formatters（格式器）
# ==============================================================================

FORMATTERS = {
    'verbose': {
        'format': '{levelname} {asctime} {name} {module} {process:d} {thread:d} {message}',
        'style': '{',
    },
    'simple': {
        'format': '{levelname} {asctime} {name} {message}',
        'style': '{',
    },
}

# ==============================================================================
# 区3: Handlers（处理器）
# ==============================================================================


def _file_handler(filename, *, level=INFO, formatter='verbose',
                  max_bytes=10 * 1024 * 1024, backup_count=5):
    """轮转文件处理器 — 生产环境标配，防止日志文件无限增长。"""
    return {
        'level': level,
        'class': 'logging.handlers.RotatingFileHandler',
        'filename': str(LOG_DIR / filename),
        'formatter': formatter,
        'maxBytes': max_bytes,
        'backupCount': backup_count,
    }


HANDLERS = {
    # 控制台
    'console': {
        'level': DEBUG,
        'class': 'logging.StreamHandler',
        'formatter': 'simple',
    },
    # 通用应用日志
    'file_app': _file_handler('app.log'),
    # 错误专用日志（WARNING+ 由 root logger 集中归档）
    'file_error': _file_handler('error.log', level=WARNING),
    # 核心模块独立日志
    'file_sap': _file_handler('sap.log'),
    'file_mcp': _file_handler('mcp.log'),
    'file_trial': _file_handler('trial_production.log'),
    'file_workflow': _file_handler('workflow.log'),
    'file_catalog': _file_handler('catalog.log'),
    'file_material_api': _file_handler('material_api.log'),
    # RBAC 权限缓存独立日志（缓存失效/重载/版本变更审计）
    'file_rbac': _file_handler('rbac.log'),
}

# ==============================================================================
# 区4: 模块日志注册表（声明式配置 — 一行一个模块）
# ==============================================================================

MODULE_LOGGERS = {
    # ======== 核心模块（独立日志文件）========
    'sap': {'handlers': ['console', 'file_sap'], 'level': INFO},
    'app_mcp_server': {'handlers': ['console', 'file_mcp'], 'level': INFO},
    'app_trial_production': {'handlers': ['console', 'file_trial'], 'level': INFO},
    'app_workflow': {'handlers': ['console', 'file_workflow'], 'level': INFO},
    'app_catalog': {'handlers': ['console', 'file_catalog'], 'level': INFO},
    'app_material_api': {'handlers': ['console', 'file_material_api'], 'level': INFO},

    # ======== 轻量模块（共用 app.log）========
    'app_color_center': {'handlers': ['console', 'file_app'], 'level': INFO},
    'app_material_testing': {'handlers': ['console', 'file_app'], 'level': INFO},
    'app_mold_injection': {'handlers': ['console', 'file_app'], 'level': INFO},
    'app_project': {'handlers': ['console', 'file_app'], 'level': INFO},
    'app_repository': {'handlers': ['console', 'file_app'], 'level': INFO},
    'app_user': {'handlers': ['console', 'file_app'], 'level': INFO},
    # RBAC 缓存服务：独立 rbac.log 归档（缓存失效/重载/版本变更审计）。
    # propagate=False：避免与父级 app_user 的 console/file_app 重复输出。
    'app_user.services.identity_service': {
        'handlers': ['console', 'file_rbac'], 'level': INFO, 'propagate': False,
    },
    'common_utils': {'handlers': ['console', 'file_app'], 'level': INFO},

    # ======== 基础模块（本次适配新增）========
    'app_raw_material': {'handlers': ['console', 'file_app'], 'level': INFO},
    'app_attachment': {'handlers': ['console', 'file_app'], 'level': INFO},
    'app_notification': {'handlers': ['console', 'file_app'], 'level': INFO},
    'app_form_management': {'handlers': ['console', 'file_app'], 'level': INFO},
    'app_material': {'handlers': ['console', 'file_app'], 'level': INFO},
    'app_formula': {'handlers': ['console', 'file_app'], 'level': INFO},
    'app_process': {'handlers': ['console', 'file_app'], 'level': INFO},
    'app_panel': {'handlers': ['console', 'file_app'], 'level': INFO},
    'app_basic_research': {'handlers': ['console', 'file_app'], 'level': INFO},
}

# ==============================================================================
# 区5: 构建函数
# ==============================================================================


def build_logging(*, debug=False):
    """构建 LOGGING dictConfig 字典。

    Args:
        debug: Django DEBUG 模式。True 时所有模块 logger 降级到 DEBUG。

    设计概要：
        - 已注册模块：自己的 handler（console + 模块文件）处理所有级别日志
        - propagate: True → WARNING+ 继续向上传播到 root logger
        - root logger：仅挂 file_error handler（不加 console 避免重复，不加 file_app 避免
          共用 file_app 的模块日志重复写入）
        - 未注册模块：由 root logger 兜底，WARNING+ 写入 file_error.log
        - DJANGO_LOG_LEVEL 环境变量可临时覆盖所有级别
    """
    env_level = os.environ.get('DJANGO_LOG_LEVEL')

    loggers = {}
    for name, cfg in MODULE_LOGGERS.items():
        loggers[name] = {
            'handlers': cfg['handlers'],
            'level': env_level or (DEBUG if debug else cfg['level']),
            'propagate': cfg.get('propagate', True),
        }

    return {
        'version': 1,
        'disable_existing_loggers': False,
        'formatters': FORMATTERS,
        'handlers': HANDLERS,
        'loggers': loggers,
        'root': {
            'handlers': ['file_error'],
            'level': env_level or (DEBUG if debug else WARNING),
        },
    }
