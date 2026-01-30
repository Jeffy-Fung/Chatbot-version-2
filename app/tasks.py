import time
import logging

from app.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, name="hello_world_task")
def hello_world_task(self):
    """
    A simple hello world background task.
    Includes a small delay to demonstrate async behavior.
    """
    logger.info("Hello World task started!")
    
    # Simulate some work with a delay
    time.sleep(5)
    
    message = "Hello World from Celery!"
    logger.info(f"Task completed: {message}")
    
    return {
        "status": "completed",
        "message": message,
        "task_id": self.request.id
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
    
    return {
        "status": "completed",
        "message": message,
        "task_id": self.request.id
    }
