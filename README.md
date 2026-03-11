# FastAPI + Celery + Next.js Chatbot Application

A full-stack chatbot application combining a FastAPI backend, Celery background task processing, WebSocket streaming, and a Next.js frontend. Redis acts as the message broker/pub-sub layer, and Flower provides task monitoring.

## Architecture

```
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

### WebSocket Streaming Flow

```
┌─────────────────┐          ┌─────────────────┐          ┌─────────────────┐          ┌─────────────────┐
│     Browser     │          │     FastAPI     │          │      Redis      │          │  Celery Worker  │
└────────┬────────┘          └────────┬────────┘          └────────┬────────┘          └────────┬────────┘
         │                            │                            │                            │
         │  1. Connect WebSocket      │                            │                            │
         │  ─────────────────────────►│                            │                            │
         │     /ws/{chat_id}          │  2. Subscribe channel      │                            │
         │                            │  ─────────────────────────►│                            │
         │                            │     chat:{chat_id}         │                            │
         │  3. {"type":"connected"}   │                            │                            │
         │  ◄─────────────────────────│                            │                            │
         │                            │                            │                            │
         │  4. POST /chat/{id}/start  │                            │                            │
         │  ─────────────────────────►│  5. Queue task (broker)    │                            │
         │                            │  ─────────────────────────────────────────────────────►│
         │  6. 202 Accepted           │                            │                            │
         │  ◄─────────────────────────│                            │                            │
         │                            │                            │                            │
         │                            │                            │  7. Worker picks up task   │
         │                            │                            │  ◄─────────────────────────│
         │                            │                            │                            │
         │                            │                            │  8. PUBLISH "start"        │
         │                            │  9. Receive (subscribed)   │  ◄─────────────────────────│
         │  10. WS {"type":"start"}   │  ◄─────────────────────────│                            │
         │  ◄─────────────────────────│                            │                            │
         │                            │                            │                            │
         │                            │                            │  11. PUBLISH "stream"      │
         │                            │  ◄─────────────────────────│  ◄─────────────────────────│
         │  WS {"type":"stream",...}  │                            │      (word by word)        │
         │  ◄─────────────────────────│                            │                            │
         │                            │                            │           ...              │
         │          ...               │           ...              │  ◄─────────────────────────│
         │  ◄─────────────────────────│  ◄─────────────────────────│      (repeat for each)     │
         │                            │                            │                            │
         │                            │                            │  12. PUBLISH "complete"    │
         │                            │  ◄─────────────────────────│  ◄─────────────────────────│
         │  13. WS {"type":"complete"}│                            │                            │
         │  ◄─────────────────────────│                            │                            │
         │                            │                            │                            │
┌────────┴────────┐          ┌────────┴────────┐          ┌────────┴────────┐          ┌────────┴────────┐
│     Browser     │          │     FastAPI     │          │      Redis      │          │  Celery Worker  │
└─────────────────┘          └─────────────────┘          └─────────────────┘          └─────────────────┘
```

### Message Types

| Type | Direction | Description |
|------|-----------|-------------|
| `connected` | Server → Client | WebSocket connection established |
| `start` | Server → Client | Task has started processing |
| `stream` | Server → Client | Streamed word/token from response |
| `complete` | Server → Client | Task finished, includes full response |

## Load Testing

Load testing is implemented with [Locust](https://locust.io/) to simulate concurrent users and WebSocket connections.

Each simulated user opens a persistent WebSocket connection (like a real browser tab), repeatedly sends chat requests via HTTP POST, and receives streamed responses on the same WebSocket. After each response completes, the user waits briefly before sending another message, mimicking real behavior: connect once, chat many times.

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

| User Type | Description |
|-----------|-------------|
| `ChatUser` | Simulates real users: connects WebSocket, sends chat messages, receives streamed responses |
| `WebSocketOnlyUser` | Simulates idle users maintaining WebSocket connections (for testing max connection capacity) |

### Key Metrics

| Metric | Meaning | What to Expect |
|--------|---------|----------------|
| **Response Time** | Time from request sent to complete response received | Increases as users grow; spikes indicate bottlenecks |
| **RPS (Requests/sec)** | Throughput - how many requests the system handles | Should scale with users until hitting capacity |
| **Failure Rate** | Percentage of failed requests | Should stay near 0%; rising failures indicate overload |
| **Active Users** | Concurrent users with open WebSocket connections | Each holds server resources (memory, file descriptors) |

As the number of users grows, response times increase gradually at first, then sharply once a bottleneck is reached. RPS eventually plateaus when the system becomes saturated.

### Potential Bottlenecks

| Component | Bottleneck | Symptoms | Solution |
|-----------|------------|----------|----------|
| **Celery Workers** | Too many chats exceed worker capacity | Tasks queue up, high latency | Add more workers |
| **Redis** | Connection limits, memory, pub/sub fanout | Connection refused, high Redis CPU | Use Redis cluster, increase `maxclients` |
| **FastAPI** | WebSocket connections consume memory & file descriptors | Connection drops, memory exhaustion | Increase `ulimit -n`, scale API horizontally |

## Scalability Improvements

This application includes several optimizations to handle high concurrent load:

| Component | Improvement | Details |
|-----------|-------------|---------|
| **FastAPI** | 4 Uvicorn workers | Multi-process concurrency to handle more HTTP/WebSocket requests in parallel |
| **Celery** | Gevent pool with 100 concurrency | Uses `--pool=gevent --concurrency=100` for efficient IO-bound task handling (ideal for chat tasks with network waits) |
| **Celery** | 2 worker containers | Horizontal scaling with multiple worker containers for higher throughput |
| **Redis** | Connection pooling | Uses `from_url()` which includes built-in connection pooling, reusing connections instead of creating new ones per request |

These settings allow the app to support hundreds of concurrent chat sessions. To scale further, increase the number of Celery worker containers and/or adjust concurrency values.

## Services

| Service | Port | Description |
|---------|------|-------------|
| Next.js Frontend | 3000 | Chat room UI with WebSocket |
| FastAPI | 8000 | Main API + WebSocket server |
| Redis | 6379 | Celery broker + Pub/Sub for WebSocket |
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

- **Frontend Chat Room**: http://localhost:3000
- **FastAPI Application**: http://localhost:8000
- **API Documentation (Swagger)**: http://localhost:8000/docs
- **Alternative API Docs (ReDoc)**: http://localhost:8000/redoc
- **Flower Monitoring**: http://localhost:5555

## Monitoring with Flower

Access Flower at http://localhost:5555 to:

- Track active, scheduled, and failed tasks
- Monitor worker health and performance
- Inspect individual task details and results
- Visualize task execution over time

## How It Works

1. Each browser tab generates a unique UUID that serves as the chat room ID.
2. The tab opens a WebSocket connection to `/ws/{chat_id}`.
3. Clicking **Start Chat** sends a POST request to `/chat/{chat_id}/start`.
4. The backend enqueues a Celery task and immediately returns `202 Accepted`.
5. The Celery worker processes the chat task and publishes messages to Redis.
6. The FastAPI WebSocket handler consumes messages from Redis and forwards them to the client.
7. The frontend renders the streamed response incrementally (word by word).

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/health` | Health check - returns API status |
| `POST` | `/tasks/hello` | Trigger a hello world background task |
| `GET` | `/tasks/{task_id}` | Get task status and result |
| `POST` | `/chat/{chat_id}/start` | Start a chat task that streams via WebSocket |
| `WS` | `/ws/{chat_id}` | WebSocket connection for receiving streamed responses |
| `GET` | `/queue/stats` | Get queue statistics (waiting, active, reserved tasks) |
