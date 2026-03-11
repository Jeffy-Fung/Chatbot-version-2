# FastAPI + Celery + Next.js Chatbot

A full‑stack chatbot application built with:

- FastAPI backend (HTTP API + WebSocket)
- Celery workers for background chat processing
- Redis as message broker and pub/sub
- Next.js frontend chat UI
- Flower dashboard for monitoring Celery

This README is focused on helping you run and understand the app quickly.

## 1. Quick Start (Docker)

### Prerequisites

- Docker
- Docker Compose

### Start the whole stack

```bash
docker-compose up --build
```

### Main URLs

- Frontend chat UI: `http://localhost:3000`
- FastAPI app: `http://localhost:8000`
- Swagger docs: `http://localhost:8000/docs`
- ReDoc docs: `http://localhost:8000/redoc`
- Flower (Celery monitoring): `http://localhost:5555`

## 2. What's Running

| Service          | Port | Role                                      |
|------------------|------|-------------------------------------------|
| Next.js frontend | 3000 | Chat UI with WebSocket                    |
| FastAPI          | 8000 | HTTP API + WebSocket server               |
| Redis            | 6379 | Celery broker + pub/sub for streaming     |
| Celery worker(s) | -    | Background processing of chat tasks        |
| Flower           | 5555 | Celery monitoring dashboard               |

## 3. Chat Flow (High Level)

1. The browser generates a `chat_id` (UUID).
2. It opens a WebSocket to `/ws/{chat_id}`.
3. The user clicks **Start Chat**, which sends `POST /chat/{chat_id}/start`.
4. FastAPI enqueues a Celery task and returns `202 Accepted` immediately.
5. The Celery worker processes the chat and publishes messages to Redis on channel `chat:{chat_id}`.
6. FastAPI, subscribed to that Redis channel, forwards messages to the WebSocket.
7. The frontend renders the response as it streams in (word by word) until completion.

### WebSocket message types

| Type        | Direction       | Description                                   |
|-------------|-----------------|-----------------------------------------------|
| `connected` | Server → Client | WebSocket connection established              |
| `start`     | Server → Client | Task has started processing                   |
| `stream`    | Server → Client | Streamed word/token from the response         |
| `complete`  | Server → Client | Task finished; includes the full final reply  |

## 4. API Endpoints (Backend)

| Method | Endpoint                | Description                                         |
|--------|-------------------------|-----------------------------------------------------|
| `GET`  | `/health`               | Simple health check                                 |
| `POST` | `/tasks/hello`          | Example background task                             |
| `GET`  | `/tasks/{task_id}`      | Get task status and result                          |
| `POST` | `/chat/{chat_id}/start` | Start chat task; response is streamed via WebSocket |
| `WS`   | `/ws/{chat_id}`         | WebSocket for receiving streamed responses          |
| `GET`  | `/queue/stats`          | Queue statistics (waiting, active, reserved)        |

## 5. Load Testing (Locust)

This project includes a Locust setup to simulate concurrent chat users and WebSocket connections.

From the `load_test` directory:

```bash
cd load_test

# Web UI (recommended while exploring)
locust -f locustfile.py --host=http://localhost:8000

# Headless mode (example)
locust -f locustfile.py --host=http://localhost:8000 --users 100 --spawn-rate 10 --run-time 1m --headless
```

Then open `http://localhost:8089` in your browser to control tests via the Locust UI.

### User types

| User Type            | Description                                                                 |
|----------------------|-----------------------------------------------------------------------------|
| `ChatUser`           | Opens WS, sends chat messages, receives streamed responses repeatedly       |
| `WebSocketOnlyUser`  | Keeps WS connections open without sending messages (tests connection limits) |

### Key metrics to watch

- **Response Time** – from request to full response; spikes signal bottlenecks.
- **RPS (Requests/sec)** – throughput; should rise with users until capacity is reached.
- **Failure Rate** – should stay near 0%; rising failures mean overload.
- **Active Users** – concurrent WebSocket connections (each consumes server resources).

## 6. Scaling Notes

The default configuration is tuned to handle reasonably high concurrency:

- FastAPI: multiple Uvicorn workers for parallel HTTP/WS handling.
- Celery: gevent worker pool with high concurrency for IO‑bound chat tasks.
- Celery: multiple worker containers for horizontal scaling.
- Redis: connection pooling via `from_url()` to reuse connections efficiently.

To scale further, increase the number of Celery worker containers and/or adjust worker concurrency, and ensure Redis and FastAPI have sufficient resources and connection limits.
