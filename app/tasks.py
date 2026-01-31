import time
import logging
import random

from app.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, name="hello_world_task")
def hello_world_task(self):
    """
    A hello world task simulating a long IO blocking operation.
    This mimics real-world scenarios like:
    - External API calls
    - Large file processing
    - Database migrations
    - Report generation
    """
    total_steps = 5

    # Step 1: Simulate connecting to external service
    logger.info("Step 1/5: Connecting to external service...")
    self.update_state(
        state="PROGRESS",
        meta={
            "current": 1,
            "total": total_steps,
            "status": "Connecting to external service...",
        },
    )
    time.sleep(random.uniform(2, 4))  # Simulate network latency

    # Step 2: Simulate fetching data from API
    logger.info("Step 2/5: Fetching data from API...")
    self.update_state(
        state="PROGRESS",
        meta={
            "current": 2,
            "total": total_steps,
            "status": "Fetching data from API...",
        },
    )
    time.sleep(2 * 60)  # Simulate API response time

    # Step 3: Simulate processing large dataset
    logger.info("Step 3/5: Processing large dataset...")
    self.update_state(
        state="PROGRESS",
        meta={
            "current": 3,
            "total": total_steps,
            "status": "Processing large dataset...",
        },
    )
    time.sleep(random.uniform(4, 6))  # Simulate CPU-bound processing

    # Step 4: Simulate writing to database
    logger.info("Step 4/5: Writing results to database...")
    self.update_state(
        state="PROGRESS",
        meta={
            "current": 4,
            "total": total_steps,
            "status": "Writing results to database...",
        },
    )
    time.sleep(random.uniform(2, 3))  # Simulate database write

    # Step 5: Simulate cleanup and finalization
    logger.info("Step 5/5: Finalizing and cleaning up...")
    self.update_state(
        state="PROGRESS",
        meta={
            "current": 5,
            "total": total_steps,
            "status": "Finalizing and cleaning up...",
        },
    )
    time.sleep(random.uniform(1, 2))  # Simulate cleanup

    message = "Hello World! Long IO task completed successfully."
    logger.info(f"Task completed: {message}")

    return {
        "status": "completed",
        "message": message,
        "task_id": self.request.id,
        "steps_completed": total_steps,
    }


@celery_app.task(bind=True, name="hello_with_name_task")
def hello_with_name_task(self, name: str):
    """
    A hello task that accepts a name parameter.
    """
    logger.info(f"Hello task started for: {name}")

    time.sleep(3)

    message = f"Hello, {name}! Greetings from Celery!"
    logger.info(f"Task completed: {message}")

    return {"status": "completed", "message": message, "task_id": self.request.id}
