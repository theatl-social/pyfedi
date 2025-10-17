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
    from sqlalchemy import create_engine
    from sqlalchemy.pool import NullPool

    # Dispose of the existing engine/pool to close any inherited connections
    db.engine.dispose()

    # Recreate engine with NullPool for thread safety
    # NullPool creates a fresh connection per request, preventing sharing between threads
    db.engine = create_engine(
        db.engine.url,
        poolclass=NullPool,
        pool_pre_ping=True,  # Verify connection before use
        echo=False,
    )

    worker.log.info(
        f"Worker {worker.pid}: SQLAlchemy configured with NullPool for gthread"
    )
