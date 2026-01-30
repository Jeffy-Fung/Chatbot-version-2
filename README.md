# FastAPI + Celery + Docker Application

A FastAPI application with Celery background task processing, PostgreSQL database, Redis message broker, and Flower monitoring.

## Architecture

```
┌─────────┐     ┌─────────────┐     ┌─────────────┐
│ Client  │────▶│  FastAPI    │────▶│   Redis     │
└─────────┘     │  (API)      │     │  (Broker)   │
                └─────────────┘     └──────┬──────┘
                      │                    │
                      ▼                    ▼
                ┌─────────────┐     ┌─────────────┐
                │ PostgreSQL  │     │   Celery    │
                │  (Database) │     │   Worker    │
                └─────────────┘     └─────────────┘
                                          │
                                          ▼
                                    ┌─────────────┐
                                    │   Flower    │
                                    │  (Monitor)  │
                                    └─────────────┘
```

## Services

| Service | Port | Description |
|---------|------|-------------|
| FastAPI | 8000 | Main API application |
| PostgreSQL | 5432 | Database |
| Redis | 6379 | Celery message broker |
| Celery Worker | - | Background task processor |
| Flower | 5555 | Celery monitoring dashboard |

## Quick Start

### Prerequisites

- Docker and Docker Compose installed

### Start All Services

```bash
docker-compose up --build
```

### Access Points

- **FastAPI Application**: http://localhost:8000
- **API Documentation (Swagger)**: http://localhost:8000/docs
- **Alternative API Docs (ReDoc)**: http://localhost:8000/redoc
- **Flower Monitoring**: http://localhost:5555

## API Endpoints

### Health Check

```bash
GET /health
```

Returns the health status of the API.

### Trigger Hello World Task

```bash
POST /tasks/hello
```

Triggers a hello world background task. Returns a task ID.

**Example:**

```bash
curl -X POST http://localhost:8000/tasks/hello
```

**Response:**

```json
{
  "task_id": "abc123-...",
  "status": "queued",
  "message": "Hello world task has been queued"
}
```

### Trigger Hello Task with Name

```bash
POST /tasks/hello/{name}
```

Triggers a hello task with a custom name.

**Example:**

```bash
curl -X POST http://localhost:8000/tasks/hello/John
```

### Check Task Status

```bash
GET /tasks/{task_id}
```

Get the status and result of a task.

**Example:**

```bash
curl http://localhost:8000/tasks/abc123-...
```

**Response:**

```json
{
  "task_id": "abc123-...",
  "status": "completed",
  "result": {
    "status": "completed",
    "message": "Hello World from Celery!",
    "task_id": "abc123-..."
  }
}
```

## Monitoring with Flower

Access Flower at http://localhost:5555 to:

- View active, processed, and failed tasks
- Monitor worker status and performance
- Inspect task details and results
- View task execution graphs

## Development

### View Logs

```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f api
docker-compose logs -f celery_worker
```

### Stop Services

```bash
docker-compose down
```

### Stop and Remove Volumes

```bash
docker-compose down -v
```

### Rebuild After Changes

```bash
docker-compose up --build
```

## Project Structure

```
├── app/
│   ├── __init__.py       # Package marker
│   ├── main.py           # FastAPI application
│   ├── celery_app.py     # Celery configuration
│   ├── tasks.py          # Background tasks
│   └── database.py       # Database configuration
├── docker-compose.yml    # Docker Compose configuration
├── Dockerfile            # Docker image definition
├── requirements.txt      # Python dependencies
└── README.md             # This file
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| DATABASE_URL | postgresql+asyncpg://postgres:postgres@postgres:5432/app_db | PostgreSQL connection string |
| CELERY_BROKER_URL | redis://redis:6379/0 | Redis broker URL |
| CELERY_RESULT_BACKEND | redis://redis:6379/1 | Redis result backend URL |
