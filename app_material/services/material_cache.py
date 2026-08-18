"""材料库对外数据缓存服务。

复用 RBAC 缓存先例（app_user/services/identity_service.py）的两级缓存策略：

    L1  模块级内存缓存 — 零延迟，各 Worker 进程独立持有实际数据
    L2  DatabaseCache 版本号 — 共享，用于跨 Worker 同步失效

工作流程:
    1. 每次读取时优先返回 L1 内存缓存
    2. 每 5 秒通过 L2 版本号检查一次是否需要刷新
    3. 任何材料库变更（视图、Admin、shell、管理命令）→ 信号触发
       invalidate() → 更新 L2 版本号 + 清空本地 L1
    4. 其他 Worker 在下次定期检查时发现版本变化 → 重载 L1
    5. 缓存不可用时自动降级为直接执行 load_fn 查 DB

并发安全（stale-while-revalidate）:
    - L1 每个条目为 (version, data) 元组，读取时比较条目版本与 _cached_version
    - 读取永不返回 None：版本过期或缓存在清空时，返回旧数据（stale），
      由下一个调用方在锁内完成重载，彻底消除"重载期间空响应"窗口。
    - 重载在 _reload_lock 内串行执行，多线程不并发查 DB。

导出: MaterialCache。
"""

import logging
import os
import threading
import time
import uuid

from django.core.cache import caches

logger = logging.getLogger(__name__)

# 当前进程的 Worker 标识（gunicorn 多 worker 下各进程 PID 不同，用于缓存审计日志）
_worker_label = f"pid{os.getpid()}"

# ── L1 模块级内存缓存 ─────────────────────────────────────
# key → (version, data) 元组；None 表示尚未加载。
# 读取回退语义：条目缺失或版本过期时返回旧数据，由锁内重载刷新。
_cache = {}

# 重载锁：保证多线程下 L1 重载串行化，避免并发查 DB 与读写竞态
_reload_lock = threading.Lock()

# ── L2 版本号 — 跨 Worker 同步 ─────────────────────────────
MATERIAL_VERSION_KEY = 'material:version'
VERSION_CHECK_INTERVAL = 5  # 每 5 秒检查一次 L2 版本号
_last_version_check = 0
_cached_version = ''


def _material_cache():
    """获取 material 缓存后端；若不可用，回退到 default。"""
    try:
        return caches['material']
    except Exception:
        return caches['default']


def _is_cache_stale():
    """检查 L2 版本号，判断是否需要重载。

    每 VERSION_CHECK_INTERVAL 秒最多检查一次，避免每次请求都查 DB。
    版本变化时更新 _cached_version 并返回 True（调用方据此重载）。
    注意：此函数绝不修改 L1 缓存，避免与正在读取的线程产生竞态；
    版本过期由 _current_entry() 的版本比较兜底。
    Returns: True 若 L1 缓存需要刷新。
    """
    global _last_version_check, _cached_version
    now = time.time()
    if now - _last_version_check < VERSION_CHECK_INTERVAL:
        return False  # 快速路径: 跳过 DB 检查
    _last_version_check = now
    try:
        cache = _material_cache()
        current_version = cache.get(MATERIAL_VERSION_KEY, '')
        if current_version != _cached_version:
            old_version = _cached_version
            _cached_version = current_version
            logger.info(
                "worker %s 同步 L2 版本 %s → %s",
                _worker_label, old_version, current_version,
            )
            return True
    except Exception as e:
        _handle_cache_error(e, "version check")
    return False


def _bump_version():
    """更新 L2 版本号，通知所有 Worker 缓存已过期。"""
    try:
        cache = _material_cache()
        new_version = str(uuid.uuid4())
        cache.set(MATERIAL_VERSION_KEY, new_version, timeout=None)
        return new_version
    except Exception as e:
        _handle_cache_error(e, "version bump")
        return ''


def _handle_cache_error(exc, operation):
    """统一处理缓存错误：表不存在 → debug，其他 → warning。"""
    msg = str(exc)
    if "doesn't exist" in msg or "does not exist" in msg or "1146" in msg:
        logger.debug("material cache %s skipped (table not available): %s", operation, msg)
    else:
        logger.warning("material cache %s failed: %s", operation, msg)


def _current_entry(entry):
    """返回有效缓存条目；None（未加载）或版本过期时返回 None。"""
    if entry is None:
        return None
    if entry[0] != _cached_version:
        return None
    return entry


def _get_or_reload(key, load_fn):
    """通用带锁缓存读取：优先返回有效缓存，否则锁内重载。

    Args:
        key: L1 缓存键（如 'nav_tree'、'list:materials:...'、'detail:materials:1:member'）。
        load_fn: 无参函数，返回要缓存的数据。
    Returns: 缓存的数据（永不返回 None）。
    """
    entry = _cache.get(key)
    if _current_entry(entry) is not None and not _is_cache_stale():
        return entry[1]
    with _reload_lock:
        # 双重检查：锁内可能已被其他线程重载
        entry = _cache.get(key)
        if _current_entry(entry) is not None and not _is_cache_stale():
            return entry[1]
        data = load_fn()
        _cache[key] = (_cached_version, data)
        logger.info(
            "worker %s 重载 L1 缓存 %s（版本 %s）",
            _worker_label, key, _cached_version,
        )
        return data


class MaterialCache:
    """材料库对外数据两级缓存。

    L1 模块级内存 + L2 DatabaseCache 版本号 实现跨 Worker 同步。
    所有方法为静态方法，可在 view、registry 中直接调用。
    """

    @staticmethod
    def get(key, load_fn):
        """读取缓存；未命中或过期时调用 load_fn 重载并写入。

        Args:
            key: L1 缓存键。
            load_fn: 无参函数，返回要缓存的数据。
        """
        return _get_or_reload(key, load_fn)

    @staticmethod
    def current_version():
        """返回权威 L2 版本号（直接读 DatabaseCache，跨 worker 一致）。

        供主系统对外暴露给电子手册子系统做一致性校验；缓存不可用时返回空字符串。
        """
        try:
            return _material_cache().get(MATERIAL_VERSION_KEY, '')
        except Exception as e:
            _handle_cache_error(e, "version read")
            return ''

    @staticmethod
    def invalidate(trigger=None):
        """清除材料库缓存（材料库相关模型变更时由信号调用）。

        Args:
            trigger: 触发源描述（如 'MaterialLibrary.post_save'、'MaterialBulkPublishView'）。
                     用于日志审计，定位是哪个变更触发了缓存版本变更。
        - 清除当前 Worker 的 L1 内存缓存（即时生效）
        - 更新 L2 版本号（通知其他 Worker，5 秒内生效）
        在锁内执行，保证清空与版本号更新原子性。
        """
        global _cache, _cached_version
        logger.info("worker %s 触发材料库缓存失效（起因：%s）", _worker_label, trigger or "手动调用")
        with _reload_lock:
            _cache = {}
            _cached_version = _bump_version()
            logger.info(
                "worker %s 更新 L2 版本 → %s（起因：%s）",
                _worker_label, _cached_version, trigger or "手动调用",
            )
