"""MCP 在 Django 请求周期外打 ORM 时的连接回收。

`/mcp` 是 Starlette 路由，不发 request_started / request_finished。
线程池线程上的 MySQL 连接会一直留到服务端按 wait_timeout 断开（4031），
下一次查询还拿着这条死连接。这里在鉴权和工具调用前后显式关掉它。
"""
import logging

from django.db import close_old_connections, connections

logger = logging.getLogger(__name__)


def recycle_db_connections():
    """关掉当前线程上已过期或已死的数据库连接。

    必须在跑 ORM 的那条同步线程里调用。连接是线程局部的，
    在 async 请求协程里调用关不到工作线程上的连接。

    CONN_MAX_AGE 默认 0：连接一建立 close_at 就是现在，
    close_old_connections() 会把它关掉，下次查询另开一条。
    同一次鉴权或工具调用里的多条 SQL 仍共用这一条。

    TestCase 把测试包在事务里。这时关连接会置 closed_in_transaction，
    后续查询变成 ProgrammingError，所以事务中直接跳过。
    生产环境的 MCP 请求进这里时不在事务里。
    """
    if any(conn.in_atomic_block for conn in connections.all(initialized_only=True)):
        return
    try:
        close_old_connections()
    except Exception:
        # close() 打到已被服务端丢弃的 socket 时可能再抛。
        # Django 的 finally 已经把抛错的那条 connection 置空；这里把它余下的别名也丢掉，
        # 避免回收本身变成 500，下次查询会另开连接。
        logger.warning("MCP database connection recycle failed", exc_info=True)
        for conn in connections.all(initialized_only=True):
            conn.connection = None
