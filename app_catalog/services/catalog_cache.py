"""电子手册侧 worker 内存缓存服务。

与主系统 MaterialCache 同构的「L1 内存 + 版本号」两级缓存，但 L2 版本号不在
本地 DatabaseCache，而是通过 HTTP 从主系统 cache-version/ 接口获取——目录子
系统与主系统共用同一 Django 工程，但为架构解耦，目录侧只经网关 HTTP 访问主系
统，不直接读其缓存表。

    L1  模块级内存缓存 — 各 worker 进程独立持有实际数据
    L2  主系统数据版本号 — 按需异步 HTTP 校验，跨实例一致性信号

与主系统 MaterialCache 的关键差异：版本号校验是**按需异步**的——只有当有请求
到来、且距上次校验超过 CATALOG_CACHE_VERSION_CHECK_INTERVAL 秒时，才派生一个
后台线程做 HTTP 校验。请求路径绝不阻塞在版本校验上，零流量时零 HTTP（无常驻
轮询线程）。

工作流程:
    1. 读取时先触发一次「按需校验」（节流 + 非阻塞抢锁去重）
    2. 命中 L1 且版本一致 → 直接返回内存（微秒级，无任何 HTTP）
    3. 未命中 / 版本过期 → 锁内重载数据（stale-while-revalidate，永不返回 None）
    4. 后台校验发现版本变化 → 更新 _cached_version → 旧 L1 条目因版本标记
       不匹配自动失效，下一次读取才重载；主系统不可用则保持旧版本继续用旧数据

并发安全（stale-while-revalidate）:
    - L1 每个条目为 (version, data) 元组，读取时比较条目版本与 _cached_version
    - 读取永不返回 None：版本过期时返回旧数据（stale），由下一个调用方在锁内重载
    - 重载在 _reload_lock 内串行执行，多线程不并发访问上游
    - _cached_version 仅后台校验线程写、请求线程读；CPython GIL 保证引用赋值原子
    - _version_check_lock 用非阻塞抢锁去重，同一时刻最多一个校验线程在飞

导出: CatalogCache。
"""

import logging
import threading
import time

from django.conf import settings

logger = logging.getLogger(__name__)

# ── L1 模块级内存缓存 ─────────────────────────────────────
# key → (version, data) 元组；None 表示尚未加载。
_cache = {}

# 重载锁：保证多线程下 L1 重载串行化，避免并发访问上游与读写竞态
_reload_lock = threading.Lock()

# ── L2 主系统版本号（按需异步校验）──────────────────────────
VERSION_CHECK_INTERVAL = getattr(settings, 'CATALOG_CACHE_VERSION_CHECK_INTERVAL', 5)
_cached_version = ''

# 版本校验的节流与去重：仅在有请求时按需触发，零流量时静默
_last_version_check = 0  # 上次触发校验的时间戳（节流）
_version_check_lock = threading.Lock()  # 非阻塞互斥：同一时刻仅一个校验在飞

# L1 容量护栏：条目超限时整体清空（材料列表按 query 串分片，防无限增长）
MAX_ENTRIES = 500


def _fetch_upstream_version():
    """通过网关 HTTP 拉取主系统当前数据版本号；失败返回 None。"""
    from .gateway import get_gateway  # 局部导入，避免与 gateway 的循环依赖
    try:
        return get_gateway().cache_version()
    except Exception as e:
        logger.warning('catalog cache version fetch failed: %s', e)
        return None


def _poll_version():
    """拉取主系统版本号；变化则更新 _cached_version（旧 L1 条目随之自动失效）。"""
    global _cached_version
    upstream_version = _fetch_upstream_version()
    if upstream_version is None or upstream_version == _cached_version:
        return
    old_version = _cached_version
    _cached_version = upstream_version
    logger.info('catalog cache 同步主系统版本 %s → %s', old_version, upstream_version)


def _maybe_trigger_version_check():
    """按需触发后台版本校验（非阻塞）。

    请求路径调用：距上次校验不足 VERSION_CHECK_INTERVAL 秒直接返回；否则
    非阻塞抢锁，抢到则登记时间戳并派生后台线程做 HTTP 校验，抢不到说明已有
    校验在飞，同样直接返回。请求绝不等待校验结果——命中 L1 即返回内存旧值。
    """
    global _last_version_check
    if time.time() - _last_version_check < VERSION_CHECK_INTERVAL:
        return
    if not _version_check_lock.acquire(blocking=False):
        return  # 已有校验线程在飞
    _last_version_check = time.time()
    # 锁由后台线程在校验完成后释放（见 _run_version_check 的 finally）
    threading.Thread(
        target=_run_version_check, name='catalog-cache-version-check', daemon=True,
    ).start()


def _run_version_check():
    """后台执行一次版本校验，完成后释放互斥锁。"""
    try:
        _poll_version()
    finally:
        _version_check_lock.release()


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
        key: L1 缓存键（如 'nav_tree'、'materials:page=1'、'material:1:member'）。
        load_fn: 无参函数，返回要缓存的数据。
    Returns: 缓存的数据（永不返回 None）。
    """
    _maybe_trigger_version_check()
    entry = _cache.get(key)
    if _current_entry(entry) is not None:
        return entry[1]
    with _reload_lock:
        # 双重检查：锁内可能已被其他线程重载
        entry = _cache.get(key)
        if _current_entry(entry) is not None:
            return entry[1]
        if len(_cache) >= MAX_ENTRIES:
            _cache.clear()
        data = load_fn()
        _cache[key] = (_cached_version, data)
        logger.info('catalog cache 重载 L1 %s（版本 %s）', key, _cached_version)
        return data


class CatalogCache:
    """电子手册侧 worker 内存缓存（版本由主系统数据驱动，按需异步校验）。

    L1 模块级内存 + 主系统版本号（按需异步 HTTP 校验）实现跨实例一致性。
    所有方法为静态方法，可在 gateway 中直接调用。
    """

    @staticmethod
    def get(key, load_fn):
        """读取缓存；未命中或主系统版本过期时调用 load_fn 重载。

        Args:
            key: L1 缓存键。
            load_fn: 无参函数，返回要缓存的数据。
        """
        return _get_or_reload(key, load_fn)
