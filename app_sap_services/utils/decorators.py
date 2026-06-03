import functools
import logging
import time

from .exceptions import SapTimeoutError

logger = logging.getLogger('app_sap_services')


def log_rfc_call(func_name=None):

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            name = func_name or func.__name__
            logger.info(f"SAP RFC call start: {name}")
            start = time.perf_counter()
            try:
                result = func(*args, **kwargs)
                elapsed = time.perf_counter() - start
                logger.info(f"SAP RFC call done: {name} ({elapsed:.3f}s)")
                return result
            except Exception:
                elapsed = time.perf_counter() - start
                logger.error(f"SAP RFC call failed: {name} ({elapsed:.3f}s)", exc_info=True)
                raise
        return wrapper
    return decorator


def with_timeout(seconds=30):

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            import threading

            result = None
            exception = None

            def target():
                nonlocal result, exception
                try:
                    result = func(*args, **kwargs)
                except Exception as e:
                    exception = e

            thread = threading.Thread(target=target)
            thread.start()
            thread.join(timeout=seconds)

            if thread.is_alive():
                raise SapTimeoutError(f"SAP RFC call exceeded {seconds}s timeout")

            if exception:
                raise exception
            return result

        return wrapper

    return decorator
