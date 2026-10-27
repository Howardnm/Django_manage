"""
SAP RFC 连接管理器 —— 线程安全 + DLL 引导 + 自动重连。

使用 threading.local 为每个线程维护独立 pyrfc 连接，
避免跨线程共享导致的段错误。

用法:
    mgr = ConnectionManager(config)
    result = mgr.call_rfc('ZRFC_MATERIAL_MESN', MAT_RANGE=[...])
"""

import ctypes
import os
import time
import threading
import logging

from .config import SAPConfig
from .exceptions import SAPConnectionError, SAPRfcError

logger = logging.getLogger('sap.connection')

_bootstrap_lock = threading.Lock()
_pyrfc_bootstrapped = False
_sdk_lib_path = ""

# libsapnwrfc.so 的依赖。必须先载入，dlopen 才找得到同目录里的库。
# libicudecnumber.so 只在这份 SDK 里有，没有就跳过。
_SDK_LIBS = (
    "libicudata.so.50",
    "libicuuc.so.50",
    "libicui18n.so.50",
    "libsapucum.so",
    "libsapnwrfc.so",
)
_SDK_OPTIONAL_LIB = "libicudecnumber.so"


def _preload_sdk_libs(sap_lib_path: str):
    """把 SDK 的 .so 载入当前进程。缺库时直接说明是哪一个。"""
    names = list(_SDK_LIBS)
    if os.path.isfile(os.path.join(sap_lib_path, _SDK_OPTIONAL_LIB)):
        names.insert(names.index("libsapucum.so"), _SDK_OPTIONAL_LIB)
    for name in names:
        path = os.path.join(sap_lib_path, name)
        if not os.path.isfile(path):
            raise SAPConnectionError(f"SAP NW RFC SDK 缺少 {name}: {sap_lib_path}")
        try:
            ctypes.CDLL(path, mode=ctypes.RTLD_GLOBAL)
        except OSError as exc:
            raise SAPConnectionError(f"无法加载 SAP NW RFC SDK 库 {path}: {exc}") from exc


def _drop_broken_pyrfc():
    """pyrfc 加载失败时仍会留在 sys.modules 里，而且没有 Connection。清掉才能重试。"""
    import sys

    loaded = sys.modules.get("pyrfc")
    if loaded is None or hasattr(loaded, "Connection"):
        return
    for name in list(sys.modules):
        if name == "pyrfc" or name.startswith("pyrfc."):
            del sys.modules[name]


def _pyrfc_import_message(exc: Exception) -> str:
    """扩展按短名字找 libsapnwrfc.so。这份库没有 SONAME，提前 dlopen 绝对路径不会登记这个名字。"""
    text = f"pyrfc 扩展加载失败: {exc}"
    if "cannot open shared object file" not in str(exc):
        return text
    path = _sdk_lib_path or "SDK 的 lib 目录"
    return (
        f"{text}\n"
        f"动态链接器不读 SAP_LIB_PATH。libsapnwrfc.so 没有 SONAME，"
        f"进程里提前加载绝对路径也登记不上这个短名字。\n"
        f"在系统里登记后重启网站进程:\n"
        f"  echo {path} > /etc/ld.so.conf.d/nwrfcsdk.conf && ldconfig\n"
        f"或在宝塔 Python 项目的环境变量（不是 .env）里设置 LD_LIBRARY_PATH={path}。"
        f"这个变量必须在 Python 启动前就存在。"
    )


def _import_pyrfc():
    """延迟导入 pyrfc，必须在引导之后。

    ``pyrfc/__init__.py`` 在扩展加载失败时把异常 print 掉，模块里就没有
    Connection。``from pyrfc import Connection`` 只会报「没有这个名字」，
    真正的原因（缺 .so、符号对不上）被盖住。这里直接导入扩展，失败时把原文抛出。
    """
    import sys

    _drop_broken_pyrfc()
    previous_flags = None
    if os.name != "nt":
        previous_flags = sys.getdlopenflags()
        sys.setdlopenflags(ctypes.RTLD_GLOBAL | os.RTLD_NOW)
    try:
        try:
            from pyrfc._cyrfc import Connection
        except Exception as exc:
            raise ImportError(_pyrfc_import_message(exc)) from exc
    finally:
        if previous_flags is not None:
            sys.setdlopenflags(previous_flags)
    return Connection


def _bootstrap_pyrfc(sap_lib_path: str):
    """
    pyrfc DLL 引导 —— 必须在 import pyrfc 之前执行。

    Windows 用 os.add_dll_directory()，再把 lib 加进 PATH。
    Linux 上进程启动后改 LD_LIBRARY_PATH 不会影响当前进程的 dlopen。
    libsapnwrfc.so 没有 SONAME，按绝对路径预加载也满足不了扩展对短名字的查找，
    短名字要靠 ldconfig 或进程启动前的 LD_LIBRARY_PATH。
    """
    global _pyrfc_bootstrapped, _sdk_lib_path
    _sdk_lib_path = sap_lib_path
    if _pyrfc_bootstrapped:
        return

    with _bootstrap_lock:
        if _pyrfc_bootstrapped:
            return

        if not os.path.isdir(sap_lib_path):
            raise SAPConnectionError(
                f"SAP NW RFC SDK lib 路径不存在: {sap_lib_path}\n"
                f"请在 Django settings 中检查 SAP_SERVICES_CONFIG['sap_lib_path']"
            )

        if os.name == 'nt':
            os.add_dll_directory(sap_lib_path)
            os.environ['PATH'] = sap_lib_path + os.pathsep + os.environ.get('PATH', '')
        else:
            # 进程启动之后再改 LD_LIBRARY_PATH，当前进程的 dlopen 不会用。
            # 先按绝对路径载入，环境变量只留给以后拉起的子进程。
            _preload_sdk_libs(sap_lib_path)
            os.environ['LD_LIBRARY_PATH'] = (
                sap_lib_path + os.pathsep + os.environ.get('LD_LIBRARY_PATH', '')
            )
        _pyrfc_bootstrapped = True
        logger.info(f"SAP NW RFC SDK 初始化完成: {sap_lib_path}")


class ConnectionManager:
    """
    线程安全的 SAP RFC 连接管理。

    特性:
    - 每个线程独立连接 (threading.local), 避免跨线程段错误
    - 连接闲置超时自动重建
    - 连接失败自动重试（指数退避）
    - call_rfc() 统一入口，封装连接获取/释放/异常转换
    """

    def __init__(self, config: SAPConfig):
        _bootstrap_pyrfc(config.sap_lib_path)
        self._Connection = _import_pyrfc()

        self._conn_params = config.to_connection_params()
        self._max_idle_seconds = config.max_idle_seconds
        self._max_retries = config.max_retries
        self._retry_delay = config.retry_delay
        self._local = threading.local()

    # =========================================================================
    # 连接生命周期
    # =========================================================================

    def get_connection(self):
        """
        获取当前线程的 SAP 连接。

        - 首次调用：创建新连接
        - 后续调用：复用已有连接
        - 连接过期/断开：自动重建
        """
        conn = getattr(self._local, 'connection', None)
        last_used = getattr(self._local, 'last_used', 0)

        now = time.time()
        if conn is None or (now - last_used > self._max_idle_seconds):
            conn = self._create_connection()
            self._local.connection = conn

        self._local.last_used = now
        return conn

    def release_connection(self):
        """标记连接为闲置（不立即关闭，由过期机制处理）"""
        self._local.last_used = time.time()

    def close(self):
        """关闭当前线程的 SAP 连接"""
        conn = getattr(self._local, 'connection', None)
        if conn:
            try:
                conn.close()
            except Exception:
                pass
            self._local.connection = None
            logger.debug("已关闭当前线程的 SAP 连接")

    def _create_connection(self):
        """创建新 SAP 连接（带重试 + 指数退避）"""
        last_error = None
        for attempt in range(1, self._max_retries + 1):
            try:
                conn = self._Connection(**self._conn_params)
                conn.ping()
                logger.info(
                    f"SAP 连接建立成功 "
                    f"(ashost={self._conn_params.get('ashost')}, "
                    f"client={self._conn_params.get('client')}, "
                    f"attempt={attempt})"
                )
                return conn
            except Exception as e:
                last_error = e
                logger.warning(f"SAP 连接失败 (attempt={attempt}/{self._max_retries}): {e}")
                if attempt < self._max_retries:
                    time.sleep(self._retry_delay * attempt)

        raise SAPConnectionError(
            f"无法建立 SAP 连接，已重试 {self._max_retries} 次: {last_error}"
        )

    # =========================================================================
    # RFC 调用
    # =========================================================================

    def call_rfc(self, function_name: str, **params):
        """
        执行 RFC 调用 —— 统一入口。

        封装连接获取、释放、异常转换，消除 builder/gateway 中的重复代码。

        Args:
            function_name: RFC 函数名
            **params: pyrfc 调用参数

        Returns:
            SAP 返回的原始字典

        Raises:
            SAPRfcError: RFC 调用失败时
        """
        conn = None
        try:
            conn = self.get_connection()
            logger.debug(
                f"RFC 调用: {function_name}, params: {list(params.keys())}"
            )
            result = conn.call(function_name, **params)
            logger.info(f"RFC 调用成功: {function_name}")
            return result
        except SAPRfcError:
            raise
        except Exception as e:
            raise SAPRfcError(
                function=function_name,
                message=str(e),
                params={k: str(v)[:200] for k, v in params.items()},
            ) from e
        finally:
            if conn:
                self.release_connection()

    # =========================================================================
    # 健康检查
    # =========================================================================

    def health_check(self) -> dict:
        """健康检查：返回连接状态"""
        try:
            conn = self.get_connection()
            conn.ping()
            return {
                'status': 'healthy',
                'ashost': self._conn_params.get('ashost'),
                'client': self._conn_params.get('client'),
            }
        except Exception as e:
            return {'status': 'unhealthy', 'error': str(e)}
