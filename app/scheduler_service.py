#!/usr/bin/env python3
"""
Standalone scheduler service for PeachPie.

This service runs the task scheduler independently of the main web application,
checking for scheduled tasks and executing them at the appropriate times.

Usage:
    python -m app.scheduler_service
"""
import asyncio
import logging
import signal
import sys
from typing import Optional

from app.federation.scheduler import TaskScheduler
from app.federation.maintenance_processor import MaintenanceProcessor
from app import create_app
import redis.asyncio as redis
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class SchedulerService:
    """Main scheduler service class"""
    
    def __init__(self):
        self.app = create_app()
        self.scheduler: Optional[TaskScheduler] = None
        self.maintenance_processor: Optional[MaintenanceProcessor] = None
        self.redis_client: Optional[redis.Redis] = None
        self.async_session_maker = None
        self._shutdown_event = asyncio.Event()
    
    async def start(self):
        """Start the scheduler service"""
        logger.info("Starting PeachPie Scheduler Service")
        
        with self.app.app_context():
            # Initialize Redis
            redis_url = self.app.config['REDIS_URL']
            self.redis_client = await redis.from_url(redis_url, decode_responses=True)
            
            # Initialize database
            database_url = self.app.config['DATABASE_URL']
            # Convert to async URL
            if database_url.startswith('postgresql://'):
                async_database_url = database_url.replace('postgresql://', 'postgresql+asyncpg://')
            else:
                async_database_url = database_url
            
            engine = create_async_engine(async_database_url)
            self.async_session_maker = sessionmaker(
                engine, class_=AsyncSession, expire_on_commit=False
            )
            
            # Start scheduler
            self.scheduler = TaskScheduler(redis_url=redis_url)
            await self.scheduler.start()
            
            # Start maintenance processor
            self.maintenance_processor = MaintenanceProcessor(
                redis_client=self.redis_client,
                async_session_maker=self.async_session_maker
            )
            maintenance_task = asyncio.create_task(self.maintenance_processor.start())
            
            # Create default scheduled tasks if they don't exist
            await self._create_default_tasks()
            
            logger.info("Scheduler service started successfully")
            
            # Wait for shutdown signal
            await self._shutdown_event.wait()
            
            # Stop services
            logger.info("Shutting down scheduler service")
            await self.scheduler.stop()
            await self.maintenance_processor.stop()
            maintenance_task.cancel()
            await self.redis_client.close()
    
    async def _create_default_tasks(self):
        """Create default scheduled tasks if they don't exist"""
        tasks = await self.scheduler.list_tasks()
        task_names = {task.name for task in tasks}
        
        default_tasks = [
            {
                "name": "cleanup_old_activities",
                "task_type": "maintenance",
                "schedule": "0 2 * * *",  # Daily at 2 AM
                "payload": {"days_to_keep": 30, "batch_size": 1000},
                "schedule_type": "cron"
            },
            {
                "name": "update_instance_stats",
                "task_type": "maintenance",
                "schedule": "0 * * * *",  # Every hour
                "payload": {},
                "schedule_type": "cron"
            },
            {
                "name": "cleanup_orphaned_data",
                "task_type": "maintenance",
                "schedule": "0 3 * * 0",  # Weekly on Sunday at 3 AM
                "payload": {},
                "schedule_type": "cron"
            },
            {
                "name": "purge_deleted_content",
                "task_type": "maintenance",
                "schedule": "0 4 * * *",  # Daily at 4 AM
                "payload": {"days_to_retain": 90},
                "schedule_type": "cron"
            }
        ]
        
        for task_config in default_tasks:
            if task_config["name"] not in task_names:
                try:
                    await self.scheduler.schedule_task(**task_config)
                    logger.info(f"Created default scheduled task: {task_config['name']}")
                except Exception as e:
                    logger.error(f"Failed to create task {task_config['name']}: {e}")
    
    def handle_shutdown(self, signum, frame):
        """Handle shutdown signals"""
        logger.info(f"Received signal {signum}, initiating shutdown")
        self._shutdown_event.set()


async def main():
    """Main entry point"""
    service = SchedulerService()
    
    # Set up signal handlers
    signal.signal(signal.SIGINT, service.handle_shutdown)
    signal.signal(signal.SIGTERM, service.handle_shutdown)
    
    try:
        await service.start()
    except Exception as e:
        logger.error(f"Scheduler service failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    asyncio.run(main())