import multiprocessing

cpu_cores = multiprocessing.cpu_count()

workers = max(2, cpu_cores // 2)
threads = 2

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

# Timeout configuration - kill workers that hang
timeout = 30
graceful_timeout = 30
keepalive = 5


def post_fork(server, worker):
    """
    Called after a worker has been forked.
    Disposes of the connection pool inherited from the parent process.
    Prevents "lost synchronization with server" errors from shared PostgreSQL
    connection file descriptors across forked workers.
    """
    from app import db

    db.engine.dispose(close=False)
    server.log.info(f"Worker {worker.pid}: Disposed of inherited connection pool")


def post_worker_init(worker):
    """
    Called after a worker has been initialized (after post_fork).
    Recreates the SQLAlchemy engine with a fresh connection pool.
    Critical for gthread workers to prevent protocol corruption.
    """
    from app import db
    from config import Config
    from sqlalchemy import create_engine

    original_url = db.engine.url
    original_pool_size = Config.DB_POOL_SIZE
    original_max_overflow = Config.DB_MAX_OVERFLOW

    db.engine.dispose()

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
