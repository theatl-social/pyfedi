import multiprocessing

cpu_cores = multiprocessing.cpu_count()

workers = max(2, cpu_cores // 2)  # Number of worker processes. Keep low because gthread
threads = min(
    16, cpu_cores * 2
)  # Number of threads within each worker. Should be high in gthread worker class

worker_tmp_dir = "/dev/shm"

bind = "0.0.0.0:5000"
umask = 0o007
reload = False

worker_class = "gthread"

# logging
accesslog = "-"
errorlog = "-"

max_requests = 2000
max_requests_jitter = 50


def post_fork(server, worker):
    """
    Called after a worker has been forked.
    Disposes of the connection pool inherited from the parent process.

    This prevents "lost synchronization with server" errors caused by
    multiple Gunicorn workers sharing the same PostgreSQL connection
    file descriptors.

    Reference: https://docs.sqlalchemy.org/en/20/core/pooling.html#using-connection-pools-with-multiprocessing-or-os-fork
    """
    from app import db

    # close=False prevents closing parent process connections
    db.engine.dispose(close=False)
    server.log.info(f"Worker {worker.pid}: Disposed of inherited connection pool")


def post_worker_init(worker):
    """
    Called after a worker has been initialized (after post_fork).
    Recreates the SQLAlchemy engine with a fresh connection pool.

    This is critical for gthread workers because:
    1. post_fork disposes the inherited pool
    2. We need to create a FRESH pool after fork (not inherited from parent)
    3. QueuePool is thread-safe with Flask-SQLAlchemy's scoped_session
    4. Each worker gets its own pool, preventing protocol corruption

    Without this, workers may reuse parent's pool state, causing
    PGRES_TUPLES_OK errors and connection protocol corruption.

    Reference: SQLALCHEMY_POOLING_BEST_PRACTICES.md
    """
    from app import db
    from config import Config
    from sqlalchemy import create_engine

    # Save original pool configuration before disposing
    original_url = db.engine.url
    original_pool_size = Config.DB_POOL_SIZE
    original_max_overflow = Config.DB_MAX_OVERFLOW

    # Dispose any remaining pool state
    db.engine.dispose()

    # Recreate engine with fresh QueuePool
    # Uses same configuration from config.py
    db.engine = create_engine(
        original_url,
        pool_size=int(original_pool_size),
        max_overflow=int(original_max_overflow),
        pool_pre_ping=True,
        pool_recycle=3600,
        echo=False,
    )

    worker.log.info(
        f"Worker {worker.pid}: Recreated engine with fresh QueuePool "
        f"(pool_size={original_pool_size}, max_overflow={original_max_overflow})"
    )
