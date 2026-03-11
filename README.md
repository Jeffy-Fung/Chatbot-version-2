## FastAPI + Celery + Next.js Chatbot

A full-stack chatbot application built with:

- FastAPI backend (HTTP API + WebSocket streaming)
- Celery workers for background chat processing
- Redis as Celery broker and Pub/Sub transport
- Next.js frontend chat UI
- Flower dashboard for monitoring Celery workers and tasks

## Quick Start

### Prerequisites

- Docker and Docker Compose installed

### Start all services

```bash
docker-compose up --build
```

### Access points

- **Frontend Chat Room**: http://localhost:3000
- **FastAPI Application**: http://localhost:8000
- **API Documentation (Swagger)**: http://localhost:8000/docs
- **Alternative API Docs (ReDoc)**: http://localhost:8000/redoc
- **Flower Monitoring**: http://localhost:5555

## Architecture

```text
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Next.js   │────▶│  FastAPI    │────▶│   Redis     │
│  Frontend   │◀───▶│  (API/WS)   │     │  (Pub/Sub)  │
└─────────────┘     └─────────────┘     └──────┬──────┘
   (Port 3000)         (Port 8000)             │
                                               ▼
                                        ┌─────────────┐
                                        │   Celery    │
                                        │   Worker    │
                                        └──────┬──────┘
                                               │
                                               ▼
                                        ┌─────────────┐
                                        │   Flower    │
                                        │  (Monitor)  │
                                        └─────────────┘
```

### Services

| Service            | Port | Description                                |
|--------------------|------|--------------------------------------------|
| Next.js Frontend   | 3000 | Chat room UI with WebSocket client        |
| FastAPI            | 8000 | Main API + WebSocket server               |
| Redis              | 6379 | Celery broker + Pub/Sub for WebSocket     |
| Celery Worker      | -    | Background task processor                  |
| Flower             | 5555 | Celery monitoring dashboard                |

## WebSocket Streaming Flow

High-level streaming model:

```text
Browser ─WS─▶ FastAPI ─Pub/Sub─▶ Redis ─▶ Celery Worker
   ▲                                           │
   └────────────────── streamed tokens ◀───────┘
```

Detailed sequence:

1. Browser tab creates a unique `chat_id` (UUID).
2. Browser opens `WS /ws/{chat_id}` (one persistent WebSocket per tab).
3. User clicks "Start Chat" which sends `POST /chat/{chat_id}/start`.
4. FastAPI enqueues a Celery task and returns `202 Accepted` immediately.
5. Celery worker processes the chat request and publishes events to Redis on `chat:{chat_id}`.
6. FastAPI WebSocket handler subscribes to `chat:{chat_id}` and forwards events to the browser.
7. Frontend renders the streamed response word-by-word until completion.

### Message Types

| Type        | Direction       | Description                               |
|-------------|-----------------|-------------------------------------------|
| `connected` | Server → Client | WebSocket connection established          |
| `start`     | Server → Client | Task has started processing               |
| `stream`    | Server → Client | Streamed word/token from response         |
| `complete`  | Server → Client | Task finished, includes full response     |

## Load Testing with Locust

Load testing is available using [Locust](https://locust.io/) to simulate concurrent users and WebSocket connections.

Each simulated user:

- Establishes a persistent WebSocket connection (like a real browser tab)
- Repeatedly sends chat requests via HTTP POST
- Receives streamed responses through the WebSocket
- Waits between messages to mimic "connect once, chat multiple times"

### Running Load Tests

```bash
cd load_test

# With Web UI (interactive)
locust -f locustfile.py --host=http://localhost:8000

# Headless mode (automated)
locust -f locustfile.py --host=http://localhost:8000 --users 100 --spawn-rate 10 --run-time 1m --headless
```

Open http://localhost:8089 to configure and start the test via the web interface.

### User Types

| User Type           | Description                                                                    |
|---------------------|--------------------------------------------------------------------------------|
| `ChatUser`          | Connects WebSocket, sends chat messages, receives streamed responses          |
| `WebSocketOnlyUser` | Maintains idle WebSocket connections to test max connection capacity          |

### Key Metrics

| Metric            | Meaning                                     | What to Expect                                      |
|-------------------|---------------------------------------------|-----------------------------------------------------|
| **Response Time** | Time from request sent to full response     | Grows gradually; sharp spikes indicate bottlenecks  |
| **RPS**           | Requests per second (throughput)            | Scales with users until hitting system capacity     |
| **Failure Rate**  | Percentage of failed requests               | Should remain near 0%; rises under overload         |
| **Active Users**  | Concurrent users with open WebSocket conns  | Each holds memory and file-descriptor resources     |

As users increase, response times first grow gradually, then sharply when a bottleneck is reached. RPS plateaus when the system is saturated.

## Scalability Improvements

This application includes several optimizations for handling high concurrent load:

| Component  | Improvement                      | Details                                                                 |
|-----------|-----------------------------------|-------------------------------------------------------------------------|
| FastAPI   | 4 Uvicorn workers                 | Multi-process concurrency to handle more HTTP/WebSocket requests       |
| Celery    | Gevent pool with 100 concurrency | `--pool=gevent --concurrency=100` for efficient IO-bound chat tasks   |
| Celery    | 2 worker containers               | Horizontal scaling with multiple worker containers                     |
| Redis     | Connection pooling                | `from_url()` with built-in pooling to reuse connections                |

These defaults allow the app to handle hundreds of concurrent chat sessions. To scale further, increase the number of Celery worker containers or adjust concurrency settings for your environment.

## Monitoring with Flower

Access Flower at http://localhost:5555 to:

- View active, processed, and failed tasks
- Monitor worker status and performance
- Inspect task details and results
- View task execution graphs and timelines

## How It Works (End-to-End)

1. Each browser tab generates a unique UUID as the chat room ID.
2. The tab establishes a WebSocket connection to `/ws/{chat_id}`.
3. Clicking "Start Chat" sends a POST request to `/chat/{chat_id}/start`.
4. The backend queues a Celery task and returns immediately (`202 Accepted`).
5. The Celery worker processes the task and publishes messages to Redis.
6. The FastAPI WebSocket handler receives messages from Redis and forwards them to the connected client.
7. The frontend displays the streamed response word by word.

## API Endpoints

| Method | Endpoint                | Description                                        |
|--------|-------------------------|----------------------------------------------------|
| `GET`  | `/health`               | Health check - returns API status                 |
| `POST` | `/tasks/hello`          | Trigger a hello world background task             |
| `GET`  | `/tasks/{task_id}`      | Get task status and result                        |
| `POST` | `/chat/{chat_id}/start` | Start a chat task that streams via WebSocket      |
| `WS`   | `/ws/{chat_id}`         | WebSocket connection for receiving streamed responses |
| `GET`  | `/queue/stats`          | Get queue statistics (waiting, active, reserved)  |

