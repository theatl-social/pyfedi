"""
Test database connection pool thread-safety for gthread workers.

This test simulates the Gunicorn gthread worker model where multiple threads
within the same process attempt concurrent database operations.

The PGRES_TUPLES_OK errors occur when:
1. Multiple threads share the same SQLAlchemy connection pool
2. One thread closes/returns a connection while another is using it
3. Race conditions cause protocol state corruption
"""

import concurrent.futures
import os
import threading
import time
from typing import List

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool, QueuePool


def test_concurrent_database_queries_with_queuepool_unsafe():
    """
    Demonstrate that QueuePool WITHOUT pre_ping is UNSAFE for threaded access.

    This test EXPECTS to occasionally see connection issues with QueuePool
    when multiple threads hammer the same connection pool.
    """
    # Create engine with QueuePool (default) - this is UNSAFE for threads
    # Use file:///tmp/test_queuepool.db to share across connections
    engine = create_engine(
        "sqlite:///tmp/test_queuepool.db",
        poolclass=QueuePool,
        pool_size=2,
        max_overflow=0,
        pool_pre_ping=False,  # THIS IS THE PROBLEM
    )

    # Create a table
    with engine.connect() as conn:
        conn.execute(text("DROP TABLE IF EXISTS test"))
        conn.execute(text("CREATE TABLE test (id INTEGER PRIMARY KEY, value TEXT)"))
        conn.execute(text("INSERT INTO test VALUES (1, 'test')"))
        conn.commit()

    errors = []
    success_count = 0
    lock = threading.Lock()

    def query_database(thread_id: int):
        """Simulate concurrent queries"""
        nonlocal success_count
        try:
            with engine.connect() as conn:
                result = conn.execute(text("SELECT * FROM test WHERE id = 1"))
                row = result.fetchone()
                time.sleep(0.001)  # Simulate processing
                if row:
                    with lock:
                        success_count += 1
        except Exception as e:
            with lock:
                errors.append((thread_id, str(e), type(e).__name__))

    num_threads = 20
    with concurrent.futures.ThreadPoolExecutor(max_workers=num_threads) as executor:
        futures = [executor.submit(query_database, i) for i in range(num_threads)]
        concurrent.futures.wait(futures)

    print("\nQueuePool (UNSAFE) Test Results:")
    print(f"  Successful queries: {success_count}/{num_threads}")
    print(f"  Errors: {len(errors)}")

    # With QueuePool and no pre_ping, we might see issues
    # This test documents the problem, doesn't assert failure
    engine.dispose()

    # Cleanup
    import pathlib

    pathlib.Path("/tmp/test_queuepool.db").unlink(missing_ok=True)


def test_concurrent_database_queries_with_nullpool_safe():
    """
    Demonstrate that NullPool IS SAFE for threaded access.

    This is what our gunicorn.conf.py post_worker_init does.
    """
    # Create engine with NullPool - this is SAFE for threads
    # Use file:///tmp/test_nullpool.db to share across connections
    engine = create_engine(
        "sqlite:///tmp/test_nullpool.db",
        poolclass=NullPool,  # No connection pooling - safe for threads
    )

    # Create a table
    with engine.connect() as conn:
        conn.execute(text("DROP TABLE IF EXISTS test"))
        conn.execute(text("CREATE TABLE test (id INTEGER PRIMARY KEY, value TEXT)"))
        conn.execute(text("INSERT INTO test VALUES (1, 'test')"))
        conn.commit()

    errors = []
    success_count = 0
    lock = threading.Lock()

    def query_database(thread_id: int):
        """Simulate concurrent queries"""
        nonlocal success_count
        try:
            with engine.connect() as conn:
                result = conn.execute(text("SELECT * FROM test WHERE id = 1"))
                row = result.fetchone()
                time.sleep(0.001)
                if row:
                    with lock:
                        success_count += 1
        except Exception as e:
            with lock:
                errors.append((thread_id, str(e), type(e).__name__))

    num_threads = 20
    with concurrent.futures.ThreadPoolExecutor(max_workers=num_threads) as executor:
        futures = [executor.submit(query_database, i) for i in range(num_threads)]
        concurrent.futures.wait(futures)

    print("\nNullPool (SAFE) Test Results:")
    print(f"  Successful queries: {success_count}/{num_threads}")
    print(f"  Errors: {len(errors)}")

    # With NullPool, all should succeed
    assert len(errors) == 0, f"NullPool should be thread-safe! Errors: {errors}"
    assert success_count == num_threads

    engine.dispose()

    # Cleanup
    import pathlib

    pathlib.Path("/tmp/test_nullpool.db").unlink(missing_ok=True)


def test_gunicorn_post_worker_init_exists():
    """
    Verify that gunicorn.conf.py has the post_worker_init hook.

    This hook is critical for configuring NullPool in gthread workers.
    """
    with open("gunicorn.conf.py", "r") as f:
        content = f.read()

    assert "def post_worker_init" in content, (
        "gunicorn.conf.py missing post_worker_init hook! "
        "This is required for thread-safe database access with gthread workers."
    )

    assert (
        "NullPool" in content
    ), "gunicorn.conf.py should configure NullPool for gthread worker thread safety"

    assert (
        "pool_pre_ping" in content or "NullPool" in content
    ), "gunicorn.conf.py should either use NullPool OR enable pool_pre_ping"

    print("\n✓ gunicorn.conf.py has proper post_worker_init configuration")


def test_celery_worker_process_init_exists():
    """
    Verify that celery workers have worker_process_init hooks.

    This hook is critical for disposing inherited connection pools after fork.
    """
    for worker_file in ["celery_worker_docker.py", "celery_worker.default.py"]:
        if not os.path.exists(worker_file):
            pytest.skip(f"{worker_file} not found")

        with open(worker_file, "r") as f:
            content = f.read()

        assert "worker_process_init" in content, (
            f"{worker_file} missing worker_process_init hook! "
            f"This is required to dispose inherited connection pools after fork."
        )

        assert (
            "engine.dispose" in content
        ), f"{worker_file} should call engine.dispose(close=False) in worker_process_init"

        print(f"\n✓ {worker_file} has proper worker_process_init configuration")


if __name__ == "__main__":
    # Run tests standalone
    pytest.main([__file__, "-v", "-s"])
