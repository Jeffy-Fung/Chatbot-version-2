import time
import logging
import random
import json
import os
import redis

from app.celery_app import celery_app

logger = logging.getLogger(__name__)

# Redis URL (supports authentication for cloud deployments like Railway)
REDIS_URL = os.getenv("REDIS_URL") or "redis://redis:6379/0"

print(f"[TASKS] REDIS_URL = '{REDIS_URL}'")

# Redis client for publishing chat messages
redis_publisher = redis.from_url(REDIS_URL)


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


@celery_app.task(bind=True, name="chat_task")
def chat_task(self, chat_id: str):
    """
    A chat task that simulates a long IO-bound operation and streams
    responses back to the frontend via Redis Pub/Sub.

    This mimics a chatbot generating a response word by word.
    """
    channel = f"chat:{chat_id}"
    task_id = self.request.id

    logger.info(f"Chat task started for chat_id: {chat_id}, task_id: {task_id}")

    # Notify that task has started
    redis_publisher.publish(
        channel,
        json.dumps(
            {
                "type": "start",
                "task_id": task_id,
                "message": "Processing your request...",
            }
        ),
    )

    # Simulate initial processing delay
    time.sleep(random.uniform(1, 2))

    # Simulated chatbot response (streamed word by word)
    response_text = (
        "Hello! I'm your AI assistant. Thank you for starting this chat. "
        "I've been processing your request in the background. "
        "This demonstrates how we can stream responses from a long-running task "
        "back to the frontend using WebSockets and Redis Pub/Sub. "
        "Each word you see is being sent individually to simulate real-time streaming. "
        "This pattern is commonly used in chatbots and AI applications "
        "where responses are generated incrementally. "
        "The task is now complete. Have a great day!"
    )

    words = response_text.split()
    total_words = len(words)

    # Stream each word with a small delay to simulate typing
    for i, word in enumerate(words):
        # Publish each word/chunk
        redis_publisher.publish(
            channel,
            json.dumps(
                {
                    "type": "stream",
                    "task_id": task_id,
                    "content": word + " ",
                    "progress": {
                        "current": i + 1,
                        "total": total_words,
                        "percent": int(((i + 1) / total_words) * 100),
                    },
                }
            ),
        )

        # Simulate varying typing speed
        time.sleep(random.uniform(0.05, 0.15))

    # Send completion message
    redis_publisher.publish(
        channel,
        json.dumps(
            {
                "type": "complete",
                "task_id": task_id,
                "message": "Response complete",
                "full_response": response_text,
            }
        ),
    )

    logger.info(f"Chat task completed for chat_id: {chat_id}")

    return {
        "status": "completed",
        "chat_id": chat_id,
        "task_id": task_id,
        "response": response_text,
    }
