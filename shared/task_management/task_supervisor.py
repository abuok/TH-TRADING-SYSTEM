"""
Async task management with supervision, timeouts, and graceful shutdown.

Handles background task lifecycle including:
- Task creation with timeout protection
- Automatic error recovery
- Graceful shutdown handlers
- Task state monitoring and logging
"""

import asyncio
import logging
from typing import Callable, Optional, Any, Dict
from contextlib import asynccontextmanager
from datetime import datetime

logger = logging.getLogger(__name__)


class TaskSupervision:
    """Supervises and manages background tasks with timeouts and recovery."""

    def __init__(self, timeout_seconds: int = 30):
        """Initialize task supervisor.

        Args:
            timeout_seconds: Default timeout for tasks (can be overridden per task)
        """
        self.timeout_seconds = timeout_seconds
        self.tasks: Dict[str, asyncio.Task] = {}
        self.task_metadata: Dict[str, Dict[str, Any]] = {}
        self._shutdown = False

    async def create_task(
        self,
        name: str,
        coro: Callable,
        timeout_seconds: Optional[int] = None,
        max_retries: int = 3,
        retry_delay_seconds: int = 5,
    ) -> asyncio.Task:
        """Create and supervise a background task.

        Args:
            name: Unique task identifier
            coro: Coroutine or async function to run
            timeout_seconds: Timeout for task execution (default from __init__)
            max_retries: Number of times to retry on failure
            retry_delay_seconds: Delay between retries

        Returns:
            asyncio.Task with automatic supervision
        """
        timeout = timeout_seconds or self.timeout_seconds

        async def supervised_task():
            attempt = 0
            while attempt < max_retries:
                try:
                    logger.info(
                        f"Starting task '{name}' (attempt {attempt + 1}/{max_retries})"
                    )
                    self.task_metadata[name] = {
                        "started_at": datetime.utcnow(),
                        "attempt": attempt + 1,
                        "status": "running",
                    }

                    # Execute with timeout
                    if asyncio.iscoroutinefunction(coro):
                        result = await asyncio.wait_for(coro(), timeout=timeout)
                    else:
                        result = await asyncio.wait_for(coro, timeout=timeout)

                    self.task_metadata[name]["status"] = "completed"
                    self.task_metadata[name]["completed_at"] = datetime.utcnow()
                    logger.info(f"Task '{name}' completed successfully")
                    return result

                except asyncio.TimeoutError:
                    attempt += 1
                    logger.error(
                        f"Task '{name}' timed out ({timeout}s) on attempt {attempt}/{max_retries}"
                    )
                    if attempt >= max_retries:
                        self.task_metadata[name]["status"] = "failed"
                        self.task_metadata[name]["error"] = "Timeout"
                        raise
                    await asyncio.sleep(retry_delay_seconds)

                except Exception as e:
                    attempt += 1
                    logger.error(
                        f"Task '{name}' failed on attempt {attempt}/{max_retries}: {e}",
                        exc_info=True,
                    )
                    if attempt >= max_retries:
                        self.task_metadata[name]["status"] = "failed"
                        self.task_metadata[name]["error"] = str(e)
                        raise
                    await asyncio.sleep(retry_delay_seconds)

        # Create and track task
        task = asyncio.create_task(supervised_task())
        self.tasks[name] = task
        return task

    async def cancel_task(self, name: str) -> bool:
        """Cancel a background task gracefully.

        Args:
            name: Task identifier

        Returns:
            True if task was cancelled, False if not found
        """
        if name not in self.tasks:
            return False

        task = self.tasks[name]
        task.cancel()

        try:
            await asyncio.wait_for(asyncio.shield(task), timeout=5)
        except asyncio.CancelledError:
            logger.info(f"Task '{name}' cancelled")
        except asyncio.TimeoutError:
            logger.warning(f"Task '{name}' did not cancel within 5 seconds")

        return True

    async def shutdown_all(self, timeout_seconds: int = 10):
        """Gracefully shutdown all background tasks.

        Args:
            timeout_seconds: Maximum time to wait for tasks to complete
        """
        self._shutdown = True
        logger.info(f"Shutting down {len(self.tasks)} background tasks")

        # Cancel all tasks
        for name in list(self.tasks.keys()):
            await self.cancel_task(name)

        # Wait for all to complete
        if self.tasks:
            try:
                await asyncio.wait_for(
                    asyncio.gather(*self.tasks.values(), return_exceptions=True),
                    timeout=timeout_seconds,
                )
            except asyncio.TimeoutError:
                logger.error("Timeout waiting for tasks to shutdown")

        self.tasks.clear()
        logger.info("All background tasks shutdown complete")

    def get_task_status(self, name: str) -> Optional[Dict[str, Any]]:
        """Get metadata about a task.

        Args:
            name: Task identifier

        Returns:
            Task metadata or None if not found
        """
        return self.task_metadata.get(name)

    def get_all_tasks_status(self) -> Dict[str, Dict[str, Any]]:
        """Get status of all tasks.

        Returns:
            Dictionary of task_name -> metadata
        """
        return {
            name: {
                **self.task_metadata.get(name, {}),
                "done": self.tasks[name].done() if name in self.tasks else None,
                "cancelled": self.tasks[name].cancelled()
                if name in self.tasks
                else None,
            }
            for name in self.tasks.keys()
        }


# Global task supervisor instance
_task_supervisor: Optional[TaskSupervision] = None


def get_task_supervisor(timeout_seconds: int = 30) -> TaskSupervision:
    """Get or create global task supervisor.

    Args:
        timeout_seconds: Default timeout for tasks

    Returns:
        Global TaskSupervision instance
    """
    global _task_supervisor
    if _task_supervisor is None:
        _task_supervisor = TaskSupervision(timeout_seconds)
    return _task_supervisor


@asynccontextmanager
async def task_supervision(timeout_seconds: int = 30):
    """Context manager for task supervision in applications.

    Usage:
        async with task_supervision(timeout_seconds=30) as supervisor:
            await supervisor.create_task("my_job", my_async_function)
            # ... do work ...
        # Tasks automatically shutdown on exit
    """
    supervisor = TaskSupervision(timeout_seconds)
    try:
        yield supervisor
    finally:
        await supervisor.shutdown_all()
