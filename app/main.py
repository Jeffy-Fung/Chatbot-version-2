from fastapi import FastAPI, HTTPException
from celery.result import AsyncResult
from pydantic import BaseModel
from typing import Optional

from app.celery_app import celery_app
from app.tasks import hello_world_task, hello_with_name_task
from app.database import init_db

app = FastAPI(
    title="FastAPI Celery App",
    description="FastAPI application with Celery background tasks",
    version="1.0.0",
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
    """Initialize database on startup."""
    await init_db()


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "fastapi-celery-app"}


@app.post("/tasks/hello", response_model=TaskResponse)
async def trigger_hello_world_task():
    """
    Trigger a hello world background task.
    Returns the task ID which can be used to check the status.
    """
    task = hello_world_task.delay()
    return TaskResponse(
        task_id=task.id,
        status="queued",
        message="Hello world task has been queued"
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
        message=f"Hello task for '{name}' has been queued"
    )


@app.get("/tasks/{task_id}", response_model=TaskStatusResponse)
async def get_task_status(task_id: str):
    """
    Get the status and result of a task by its ID.
    """
    task_result = AsyncResult(task_id, app=celery_app)
    
    if task_result.state == "PENDING":
        return TaskStatusResponse(
            task_id=task_id,
            status="pending",
            result=None
        )
    elif task_result.state == "STARTED":
        return TaskStatusResponse(
            task_id=task_id,
            status="started",
            result=None
        )
    elif task_result.state == "SUCCESS":
        return TaskStatusResponse(
            task_id=task_id,
            status="completed",
            result=task_result.result
        )
    elif task_result.state == "FAILURE":
        return TaskStatusResponse(
            task_id=task_id,
            status="failed",
            result={"error": str(task_result.result)}
        )
    else:
        return TaskStatusResponse(
            task_id=task_id,
            status=task_result.state.lower(),
            result=None
        )


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
            "get_task_status": "GET /tasks/{task_id}"
        }
    }
