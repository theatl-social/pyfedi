"""
Test database connection pool thread-safety for gthread workers.

This test simulates the Gunicorn gthread worker model where:
1. Parent process creates a connection pool
2. Workers fork from parent (inheriting pool state)
3. Multiple workers use inherited connections (CAUSES PGRES_TUPLES_OK)
4. post_worker_init hook should fix this by recreating engine

The PGRES_TUPLES_OK errors occur when:
1. Multiple worker processes share inherited connection file descriptors
2. Workers attempt to use connections simultaneously
3. Protocol state corruption occurs (lost synchronization with server)
"""

import concurrent.futures
import multiprocessing
import os
import tempfile
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
    # Create a temporary database file
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name

    try:
        # Create engine with QueuePool (default) - this is UNSAFE for threads
        engine = create_engine(
            f"sqlite:///{db_path}",
            poolclass=QueuePool,
            pool_size=2,
            max_overflow=0,
            pool_pre_ping=False,  # THIS IS THE PROBLEM
        )

        # Create a table
        with engine.connect() as conn:
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
    finally:
        # Cleanup
        import pathlib

        pathlib.Path(db_path).unlink(missing_ok=True)


def test_concurrent_database_queries_with_queuepool_safe():
    """
    Demonstrate that QueuePool WITH pool_pre_ping IS SAFE for threaded access.

    This is what our gunicorn.conf.py post_worker_init does - uses QueuePool
    with proper configuration (pool_pre_ping=True) which is thread-safe with
    Flask-SQLAlchemy's scoped_session.
    """
    # Create a temporary database file
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name

    try:
        # Create engine with QueuePool + pool_pre_ping - this is SAFE for threads
        engine = create_engine(
            f"sqlite:///{db_path}",
            poolclass=QueuePool,
            pool_size=10,
            max_overflow=30,
            pool_pre_ping=True,  # Critical for thread safety
            pool_recycle=3600,
        )

        # Create a table
        with engine.connect() as conn:
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

        print("\nQueuePool with pool_pre_ping (SAFE) Test Results:")
        print(f"  Successful queries: {success_count}/{num_threads}")
        print(f"  Errors: {len(errors)}")

        # With QueuePool + pool_pre_ping, all should succeed
        assert (
            len(errors) == 0
        ), f"QueuePool with pool_pre_ping should be thread-safe! Errors: {errors}"
        assert success_count == num_threads

        engine.dispose()
    finally:
        # Cleanup
        import pathlib

        pathlib.Path(db_path).unlink(missing_ok=True)


def test_gunicorn_post_worker_init_exists():
    """
    Verify that gunicorn.conf.py has the post_worker_init hook.

    This hook is critical for recreating the engine with a fresh QueuePool
    after worker initialization. QueuePool is thread-safe when used with
    Flask-SQLAlchemy's scoped_session and proper configuration.
    """
    with open("gunicorn.conf.py", "r") as f:
        content = f.read()

    assert "def post_worker_init" in content, (
        "gunicorn.conf.py missing post_worker_init hook! "
        "This is required for thread-safe database access with gthread workers."
    )

    assert (
        "create_engine" in content
    ), "gunicorn.conf.py post_worker_init should recreate the engine with fresh pool"

    assert (
        "pool_pre_ping" in content
    ), "gunicorn.conf.py should enable pool_pre_ping for connection health checks"

    # Verify it uses QueuePool (the correct approach), not NullPool
    assert (
        "QueuePool" in content or "pool_size" in content
    ), "gunicorn.conf.py should use QueuePool (default) with proper pool_size configuration"

    print(
        "\n✓ gunicorn.conf.py has proper post_worker_init configuration with QueuePool"
    )


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


def test_forked_workers_with_inherited_pool_unsafe():
    """
    Simulate the ACTUAL problem: parent process forks workers that inherit
    the same connection pool file descriptors.

    This is what causes PGRES_TUPLES_OK errors in production.

    WITHOUT post_worker_init recreating the engine, child processes share
    the parent's connection pool state, causing protocol corruption.
    """
    # Create a temporary database file
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name

    try:
        # PARENT PROCESS: Create engine with QueuePool
        parent_engine = create_engine(
            f"sqlite:///{db_path}",
            poolclass=QueuePool,
            pool_size=2,
            max_overflow=0,
            pool_pre_ping=False,
        )

        # Create table in parent
        with parent_engine.connect() as conn:
            conn.execute(text("CREATE TABLE test (id INTEGER PRIMARY KEY, value TEXT)"))
            conn.execute(text("INSERT INTO test VALUES (1, 'parent_data')"))
            conn.commit()

        def worker_without_dispose(worker_id: int, result_queue):
            """
            Worker that uses inherited engine WITHOUT disposing.
            This simulates the bug - workers inherit parent's pool.
            """
            errors = []
            success_count = 0
            try:
                # BUG: Using parent's engine directly (shared file descriptors)
                for i in range(5):
                    with parent_engine.connect() as conn:
                        result = conn.execute(text("SELECT * FROM test WHERE id = 1"))
                        row = result.fetchone()
                        if row:
                            success_count += 1
                        time.sleep(0.001)
            except Exception as e:
                errors.append(f"Worker {worker_id}: {type(e).__name__}: {str(e)}")

            result_queue.put(
                {"worker_id": worker_id, "success": success_count, "errors": errors}
            )

        # Simulate 2 forked workers (like Gunicorn)
        result_queue = multiprocessing.Queue()
        processes = []

        for worker_id in range(2):
            p = multiprocessing.Process(
                target=worker_without_dispose, args=(worker_id, result_queue)
            )
            p.start()
            processes.append(p)

        # Wait for workers
        for p in processes:
            p.join(timeout=10)

        # Collect results
        results = []
        while not result_queue.empty():
            results.append(result_queue.get())

        total_errors = sum(len(r["errors"]) for r in results)
        total_success = sum(r["success"] for r in results)

        print("\nForked Workers (UNSAFE - inherited pool) Results:")
        print(f"  Total successful queries: {total_success}")
        print(f"  Total errors: {total_errors}")
        for r in results:
            if r["errors"]:
                print(f"  Worker {r['worker_id']} errors: {r['errors']}")

        # NOTE: This test documents the problem but doesn't assert failure
        # because SQLite may or may not error depending on timing
        # With PostgreSQL, this WOULD reliably cause PGRES_TUPLES_OK errors

        parent_engine.dispose()
    finally:
        import pathlib

        pathlib.Path(db_path).unlink(missing_ok=True)


def test_forked_workers_with_engine_recreation_safe():
    """
    Simulate the FIX: parent process forks workers, but workers recreate
    their own engines (like our post_worker_init hook does).

    This PREVENTS PGRES_TUPLES_OK errors by ensuring each worker has its
    own connection pool with no shared file descriptors.
    """
    # Create a temporary database file
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name

    try:
        # PARENT PROCESS: Create engine with QueuePool
        parent_engine = create_engine(
            f"sqlite:///{db_path}",
            poolclass=QueuePool,
            pool_size=2,
            max_overflow=0,
        )

        # Create table in parent
        with parent_engine.connect() as conn:
            conn.execute(text("CREATE TABLE test (id INTEGER PRIMARY KEY, value TEXT)"))
            conn.execute(text("INSERT INTO test VALUES (1, 'parent_data')"))
            conn.commit()

        def worker_with_recreation(worker_id: int, db_path: str, result_queue):
            """
            Worker that RECREATES its own engine after fork.
            This simulates our post_worker_init hook - FIXES the bug.
            """
            errors = []
            success_count = 0
            try:
                # FIX: Create fresh engine in child process (like post_worker_init)
                worker_engine = create_engine(
                    f"sqlite:///{db_path}",
                    poolclass=QueuePool,
                    pool_size=2,
                    max_overflow=0,
                    pool_pre_ping=True,
                    pool_recycle=3600,
                )

                # Now safe to use - each worker has its own pool
                for i in range(5):
                    with worker_engine.connect() as conn:
                        result = conn.execute(text("SELECT * FROM test WHERE id = 1"))
                        row = result.fetchone()
                        if row:
                            success_count += 1
                        time.sleep(0.001)

                worker_engine.dispose()
            except Exception as e:
                errors.append(f"Worker {worker_id}: {type(e).__name__}: {str(e)}")

            result_queue.put(
                {"worker_id": worker_id, "success": success_count, "errors": errors}
            )

        # Simulate 2 forked workers (like Gunicorn)
        result_queue = multiprocessing.Queue()
        processes = []

        for worker_id in range(2):
            p = multiprocessing.Process(
                target=worker_with_recreation, args=(worker_id, db_path, result_queue)
            )
            p.start()
            processes.append(p)

        # Wait for workers
        for p in processes:
            p.join(timeout=10)

        # Collect results
        results = []
        while not result_queue.empty():
            results.append(result_queue.get())

        total_errors = sum(len(r["errors"]) for r in results)
        total_success = sum(r["success"] for r in results)

        print("\nForked Workers (SAFE - recreated engine) Results:")
        print(f"  Total successful queries: {total_success}")
        print(f"  Total errors: {total_errors}")
        for r in results:
            if r["errors"]:
                print(f"  Worker {r['worker_id']} errors: {r['errors']}")

        # All workers should succeed with no errors
        assert (
            total_errors == 0
        ), f"Should have no errors with recreated engines! Errors: {results}"
        assert total_success == 10, "Expected 10 total queries (2 workers × 5 queries)"

        parent_engine.dispose()
    finally:
        import pathlib

        pathlib.Path(db_path).unlink(missing_ok=True)


if __name__ == "__main__":
    # Run tests standalone
    pytest.main([__file__, "-v", "-s"])
