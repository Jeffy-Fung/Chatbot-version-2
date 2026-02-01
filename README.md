# FastAPI + Celery + Next.js Chatbot Application

A full-stack chatbot application with FastAPI backend, Celery background task processing, WebSocket streaming, and a Next.js frontend. Features Redis message broker and Flower monitoring.

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

Load testing is available using [Locust](https://locust.io/) to simulate concurrent users and WebSocket connections.

Each simulated user establishes a persistent WebSocket connection (just like a real browser tab), then repeatedly sends chat requests via HTTP POST. The user receives streamed responses through the WebSocket until completion, then waits before sending another message. This mimics real user behavior: connect once, chat multiple times.

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

As users increase: response times grow gradually at first, then sharply when a bottleneck is reached. RPS plateaus when the system is saturated.

### Potential Bottlenecks

| Component | Bottleneck | Symptoms | Solution |
|-----------|------------|----------|----------|
| **Celery Workers** | Too many chats exceed worker capacity | Tasks queue up, high latency | Add more workers |
| **Redis** | Connection limits, memory, pub/sub fanout | Connection refused, high Redis CPU | Use Redis cluster, increase `maxclients` |
| **FastAPI** | WebSocket connections consume memory & file descriptors | Connection drops, memory exhaustion | Increase `ulimit -n`, scale API horizontally |

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

- View active, processed, and failed tasks
- Monitor worker status and performance
- Inspect task details and results
- View task execution graphs

## How It Works

1. Each browser tab generates a unique UUID as the chat room ID
2. The tab establishes a WebSocket connection to `/ws/{chat_id}`
3. Clicking "Start Chat" sends a POST request to `/chat/{chat_id}/start`
4. The backend queues a Celery task and returns immediately (202 Accepted)
5. The Celery worker processes the task and publishes messages to Redis
6. The FastAPI WebSocket handler receives messages from Redis and forwards them to the connected client
7. The frontend displays the streamed response word by word

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/health` | Health check - returns API status |
| `POST` | `/tasks/hello` | Trigger a hello world background task |
| `GET` | `/tasks/{task_id}` | Get task status and result |
| `POST` | `/chat/{chat_id}/start` | Start a chat task that streams via WebSocket |
| `WS` | `/ws/{chat_id}` | WebSocket connection for receiving streamed responses |
| `GET` | `/queue/stats` | Get queue statistics (waiting, active, reserved tasks) |
