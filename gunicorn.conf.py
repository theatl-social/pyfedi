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
    For gthread worker class, ensures proper SQLAlchemy configuration.

    This is critical because gthread uses threads within each worker process,
    and SQLAlchemy needs specific settings for thread-safe operation.
    """
    from app import db

    # Set pool_pre_ping to check connections before using them
    # This prevents "PGRES_TUPLES_OK" errors from stale/broken connections
    db.engine.pool._pre_ping = True

    # Ensure NullPool for gthread to avoid connection sharing between threads
    from sqlalchemy.pool import NullPool

    if not isinstance(db.engine.pool, NullPool):
        # Recreate engine with NullPool for thread safety
        from sqlalchemy import create_engine

        db.engine = create_engine(db.engine.url, poolclass=NullPool, echo=False)

    worker.log.info(f"Worker {worker.pid}: SQLAlchemy configured for gthread")
