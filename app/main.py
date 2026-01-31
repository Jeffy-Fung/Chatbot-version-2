import asyncio
import json
import os

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from celery.result import AsyncResult
from pydantic import BaseModel
from typing import Optional
import redis.asyncio as aioredis
import redis

from app.celery_app import celery_app
from app.tasks import hello_world_task, hello_with_name_task, chat_task

# Frontend URL for CORS (defaults to localhost for development)
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")

# Redis host/port for connections
REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))

# Redis client for queue inspection (sync)
redis_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=0)

# Async Redis client for WebSocket pub/sub (initialized on startup)
async_redis_client: aioredis.Redis = None

app = FastAPI(
    title="FastAPI Celery App",
    description="FastAPI application with Celery background tasks and WebSocket support",
    version="1.0.0",
)

# CORS middleware for frontend access
app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_URL],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class TaskResponse(BaseModel):
    task_id: str
    status: str
    message: str


class TaskStatusResponse(BaseModel):
    task_id: str
    status: str
    result: Optional[dict] = None


class HelloNameRequest(BaseModel):
    name: str


@app.on_event("startup")
async def startup_event():
    """Initialize async Redis client on startup."""
    global async_redis_client
    # Create async Redis client for WebSocket pub/sub
    # Note: Each pubsub subscription creates its own connection internally
    async_redis_client = aioredis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=0)
    # Test the connection
    try:
        await async_redis_client.ping()
        print("[STARTUP] ✓ Async Redis connected successfully")
    except Exception as e:
        print(f"[STARTUP] ✗ Async Redis connection failed: {e}")


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup async Redis client on shutdown."""
    global async_redis_client
    if async_redis_client:
        await async_redis_client.close()


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "fastapi-celery-app"}


@app.websocket("/ws/{chat_id}")
async def websocket_endpoint(websocket: WebSocket, chat_id: str):
    """
    WebSocket endpoint for receiving streamed chat responses.
    Each chat room (identified by chat_id) subscribes to its own Redis channel.
    """
    await websocket.accept()

    # Subscribe to Redis channel for this chat
    pubsub = async_redis_client.pubsub()
    await pubsub.subscribe(f"chat:{chat_id}")

    try:
        # Send connection confirmation
        await websocket.send_json(
            {
                "type": "connected",
                "chat_id": chat_id,
                "message": "Connected to chat room",
            }
        )

        # Listen for messages from Redis and forward to WebSocket
        # Connection stays open until client disconnects (e.g., leaves the page)
        async for message in pubsub.listen():
            if message["type"] == "message":
                data = message["data"]
                if isinstance(data, bytes):
                    data = data.decode("utf-8")
                try:
                    parsed_data = json.loads(data)
                    await websocket.send_json(parsed_data)
                except json.JSONDecodeError:
                    await websocket.send_text(data)

    except WebSocketDisconnect:
        pass
    finally:
        await pubsub.unsubscribe(f"chat:{chat_id}")
        await pubsub.close()


@app.post("/chat/{chat_id}/start", response_model=TaskResponse)
async def start_chat(chat_id: str):
    """
    Start a chat task that streams responses via WebSocket.
    Returns immediately with 202 Accepted status.
    The task runs in the background and publishes updates to Redis.
    """
    task = chat_task.delay(chat_id)
    return TaskResponse(
        task_id=task.id,
        status="accepted",
        message=f"Chat task started for room '{chat_id}'",
    )


@app.post("/tasks/hello", response_model=TaskResponse)
async def trigger_hello_world_task():
    """
    Trigger a hello world background task.
    Returns the task ID which can be used to check the status.
    """
    task = hello_world_task.delay()
    return TaskResponse(
        task_id=task.id, status="queued", message="Hello world task has been queued"
    )


@app.post("/tasks/hello/{name}", response_model=TaskResponse)
async def trigger_hello_name_task(name: str):
    """
    Trigger a hello task with a custom name.
    Returns the task ID which can be used to check the status.
    """
    task = hello_with_name_task.delay(name)
    return TaskResponse(
        task_id=task.id,
        status="queued",
        message=f"Hello task for '{name}' has been queued",
    )


@app.get("/tasks/{task_id}", response_model=TaskStatusResponse)
async def get_task_status(task_id: str):
    """
    Get the status and result of a task by its ID.
    Includes progress information for long-running tasks.
    """
    task_result = AsyncResult(task_id, app=celery_app)

    if task_result.state == "PENDING":
        return TaskStatusResponse(
            task_id=task_id,
            status="pending",
            result={"message": "Task is waiting to be processed"},
        )
    elif task_result.state == "STARTED":
        return TaskStatusResponse(
            task_id=task_id,
            status="started",
            result={"message": "Task has started processing"},
        )
    elif task_result.state == "PROGRESS":
        # Return progress information for long-running tasks
        meta = task_result.info or {}
        return TaskStatusResponse(
            task_id=task_id,
            status="in_progress",
            result={
                "current_step": meta.get("current", 0),
                "total_steps": meta.get("total", 0),
                "progress_percent": int(
                    (meta.get("current", 0) / meta.get("total", 1)) * 100
                ),
                "status_message": meta.get("status", "Processing..."),
            },
        )
    elif task_result.state == "SUCCESS":
        return TaskStatusResponse(
            task_id=task_id, status="completed", result=task_result.result
        )
    elif task_result.state == "FAILURE":
        return TaskStatusResponse(
            task_id=task_id, status="failed", result={"error": str(task_result.result)}
        )
    else:
        return TaskStatusResponse(
            task_id=task_id, status=task_result.state.lower(), result=None
        )


@app.get("/queue/stats")
async def get_queue_stats():
    """
    Get queue statistics including waiting tasks.
    Shows tasks in the queue that haven't been picked up by workers yet.
    """
    try:
        # Get the length of the default celery queue
        queue_length = redis_client.llen("celery")

        # Get active queues info from Celery
        inspect = celery_app.control.inspect()

        # Get active tasks (currently being processed)
        active = inspect.active() or {}
        active_count = sum(len(tasks) for tasks in active.values())

        # Get reserved tasks (prefetched by workers)
        reserved = inspect.reserved() or {}
        reserved_count = sum(len(tasks) for tasks in reserved.values())

        # Get scheduled tasks (eta/countdown)
        scheduled = inspect.scheduled() or {}
        scheduled_count = sum(len(tasks) for tasks in scheduled.values())

        return {
            "queue": {
                "waiting": queue_length,  # Tasks in Redis queue waiting to be picked up
                "active": active_count,  # Tasks currently being executed
                "reserved": reserved_count,  # Tasks prefetched by workers
                "scheduled": scheduled_count,  # Tasks scheduled for later
            },
            "workers": {
                "active_tasks": active,
                "reserved_tasks": reserved,
            },
        }
    except Exception as e:
        return {"error": str(e), "queue": {"waiting": 0, "active": 0}}


@app.get("/")
async def root():
    """Root endpoint with API information."""
    return {
        "message": "Welcome to FastAPI Celery App",
        "docs": "/docs",
        "health": "/health",
        "endpoints": {
            "trigger_hello_task": "POST /tasks/hello",
            "trigger_hello_name_task": "POST /tasks/hello/{name}",
            "get_task_status": "GET /tasks/{task_id}",
            "queue_stats": "GET /queue/stats",
            "start_chat": "POST /chat/{chat_id}/start",
            "websocket_chat": "WS /ws/{chat_id}",
        },
    }
