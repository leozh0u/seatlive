import threading

from psycopg_pool import ConnectionPool

from app.config import DATABASE_URL

_pool: ConnectionPool | None = None
_pool_lock = threading.Lock()


def get_pool() -> ConnectionPool:
    """
    The process-wide connection pool, opened on first use.

    Built lazily rather than at import time so that importing the app does not
    require a running database, and guarded by a lock because the first request
    can arrive on several threads at once (the concurrency tests do exactly
    that) and two pools would defeat the point of pooling.
    """
    global _pool
    if _pool is None:
        with _pool_lock:
            if _pool is None:
                _pool = ConnectionPool(DATABASE_URL, min_size=1, max_size=10, open=True)
    return _pool


def close_pool() -> None:
    """Close the pool and drop it, so a later call rebuilds it."""
    global _pool
    with _pool_lock:
        if _pool is not None:
            _pool.close()
            _pool = None
