#!/usr/bin/env python3
"""
Redis Streams worker for processing federation activities

This replaces the Celery worker and processes activities from Redis Streams
using async I/O for better performance.

Usage:
    python worker.py [--name worker-1] [--processes 4]
"""
import asyncio
import logging
import argparse
import os
import sys
from multiprocessing import Process
from typing import List

# Add the app to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import Config
from app.federation.processor import run_processor

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def worker_process(worker_name: str, redis_url: str, database_url: str) -> None:
    """Run a single worker process"""
    logger.info(f"Starting worker process: {worker_name}")
    
    # Create new event loop for this process
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    try:
        loop.run_until_complete(
            run_processor(
                redis_url=redis_url,
                database_url=database_url,
                consumer_name=worker_name
            )
        )
    except KeyboardInterrupt:
        logger.info(f"Worker {worker_name} interrupted")
    except Exception as e:
        logger.error(f"Worker {worker_name} failed: {e}", exc_info=True)
    finally:
        loop.close()


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description='Redis Streams federation worker')
    parser.add_argument(
        '--name',
        default='worker',
        help='Base name for worker processes (default: worker)'
    )
    parser.add_argument(
        '--processes',
        type=int,
        default=1,
        help='Number of worker processes to spawn (default: 1)'
    )
    parser.add_argument(
        '--redis-url',
        default=None,
        help='Redis URL (default: from config)'
    )
    parser.add_argument(
        '--database-url',
        default=None,
        help='Database URL (default: from config)'
    )
    
    args = parser.parse_args()
    
    # Get configuration
    redis_url = args.redis_url or Config.REDIS_URL
    database_url = args.database_url or Config.SQLALCHEMY_DATABASE_URI
    
    # Validate configuration
    if not redis_url:
        logger.error("Redis URL not configured")
        sys.exit(1)
    
    if not database_url:
        logger.error("Database URL not configured")
        sys.exit(1)
    
    logger.info(f"Starting {args.processes} worker process(es)")
    logger.info(f"Redis URL: {redis_url}")
    logger.info(f"Database URL: {database_url.split('@')[0]}@***")  # Hide password
    
    if args.processes == 1:
        # Single process mode - run directly
        worker_process(args.name, redis_url, database_url)
    else:
        # Multi-process mode
        processes: List[Process] = []
        
        try:
            for i in range(args.processes):
                worker_name = f"{args.name}-{i+1}"
                p = Process(
                    target=worker_process,
                    args=(worker_name, redis_url, database_url),
                    name=worker_name
                )
                p.start()
                processes.append(p)
                logger.info(f"Started process {worker_name} (PID: {p.pid})")
            
            # Wait for all processes
            for p in processes:
                p.join()
                
        except KeyboardInterrupt:
            logger.info("Shutting down workers...")
            for p in processes:
                if p.is_alive():
                    p.terminate()
            
            # Wait for termination
            for p in processes:
                p.join(timeout=5)
                if p.is_alive():
                    logger.warning(f"Force killing {p.name}")
                    p.kill()
                    p.join()
    
    logger.info("All workers stopped")


if __name__ == '__main__':
    main()