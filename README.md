# FastAPI + Celery + Next.js Chatbot Application

A full-stack chatbot application with FastAPI backend, Celery background task processing, WebSocket streaming, and a Next.js frontend. Features PostgreSQL database, Redis message broker, and Flower monitoring.

## Architecture

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Next.js   │────▶│  FastAPI    │────▶│   Redis     │
│  Frontend   │◀───▶│  (API/WS)   │     │  (Pub/Sub)  │
└─────────────┘     └─────────────┘     └──────┬──────┘
   (Port 3000)         (Port 8000)             │
                            │                  │
                            ▼                  ▼
                      ┌─────────────┐   ┌─────────────┐
                      │ PostgreSQL  │   │   Celery    │
                      │  (Database) │   │   Worker    │
                      └─────────────┘   └─────────────┘
                                              │
                                              ▼
                                        ┌─────────────┐
                                        │   Flower    │
                                        │  (Monitor)  │
                                        └─────────────┘
```

### WebSocket Streaming Flow

```
┌──────────────────────────────────────────────────────────────────────────────────────┐
│                              CHAT MESSAGE FLOW                                       │
└──────────────────────────────────────────────────────────────────────────────────────┘

  ┌─────────────┐         ┌─────────────┐         ┌─────────────┐         ┌─────────────┐
  │   Browser   │         │   FastAPI   │         │    Redis    │         │   Celery    │
  │  (Frontend) │         │  (Backend)  │         │  (Pub/Sub)  │         │   Worker    │
  └──────┬──────┘         └──────┬──────┘         └──────┬──────┘         └──────┬──────┘
         │                       │                       │                       │
═════════╪═══════════════════════╪═══════════════════════╪═══════════════════════╪═══════
         │    PHASE 1: ESTABLISH WEBSOCKET CONNECTION                            │
═════════╪═══════════════════════╪═══════════════════════╪═══════════════════════╪═══════
         │                       │                       │                       │
         │  1. Generate UUID     │                       │                       │
         │     (chat_id)         │                       │                       │
         │                       │                       │                       │
         │  2. WS Connect        │                       │                       │
         │ ─────────────────────►│                       │                       │
         │   /ws/{chat_id}       │                       │                       │
         │                       │  3. Subscribe         │                       │
         │                       │ ─────────────────────►│                       │
         │                       │   channel:chat:{id}   │                       │
         │                       │                       │                       │
         │  4. {"type":"connected"}                      │                       │
         │ ◄─────────────────────│                       │                       │
         │                       │                       │                       │
═════════╪═══════════════════════╪═══════════════════════╪═══════════════════════╪═══════
         │    PHASE 2: TRIGGER BACKGROUND TASK                                   │
═════════╪═══════════════════════╪═══════════════════════╪═══════════════════════╪═══════
         │                       │                       │                       │
         │  5. POST /chat/{id}/start                     │                       │
         │ ─────────────────────►│                       │                       │
         │                       │                       │                       │
         │                       │  6. Queue task        │                       │
         │                       │ ──────────────────────────────────────────────►
         │                       │   (via Redis broker)  │                       │
         │                       │                       │                       │
         │  7. 202 Accepted      │                       │                       │
         │ ◄─────────────────────│                       │                       │
         │   {task_id, status}   │                       │                       │
         │                       │                       │                       │
═════════╪═══════════════════════╪═══════════════════════╪═══════════════════════╪═══════
         │    PHASE 3: WORKER PROCESSES & STREAMS VIA REDIS                      │
═════════╪═══════════════════════╪═══════════════════════╪═══════════════════════╪═══════
         │                       │                       │                       │
         │                       │                       │  8. Pick up task      │
         │                       │                       │ ◄─────────────────────│
         │                       │                       │                       │
         │                       │                       │  9. PUBLISH start     │
         │                       │                       │ ◄─────────────────────│
         │                       │                       │   chat:{chat_id}      │
         │                       │                       │                       │
         │                       │  10. Receive message  │                       │
         │                       │ ◄─────────────────────│                       │
         │                       │   (subscribed)        │                       │
         │                       │                       │                       │
         │  11. WS: {"type":"start"}                     │                       │
         │ ◄─────────────────────│                       │                       │
         │                       │                       │                       │
         │                       │                       │        ┌──────────────┤
         │                       │                       │        │ 12. Process  │
         │                       │                       │        │   & generate │
         │                       │                       │        │   response   │
         │                       │                       │        │   word by    │
         │                       │                       │        │   word       │
         │                       │                       │        └──────────────┤
         │                       │                       │                       │
         │                       │                       │  13. PUBLISH stream   │
         │                       │ ◄─────────────────────│ ◄─────────────────────│
         │  14. WS: {"type":"stream", "content":"Hello"} │   "Hello"             │
         │ ◄─────────────────────│                       │                       │
         │                       │                       │                       │
         │                       │                       │  15. PUBLISH stream   │
         │                       │ ◄─────────────────────│ ◄─────────────────────│
         │  16. WS: {"type":"stream", "content":"World"} │   "World"             │
         │ ◄─────────────────────│                       │                       │
         │                       │                       │                       │
         │                       │         ...           │         ...           │
         │                       │   (repeat for each word)                      │
         │                       │                       │                       │
═════════╪═══════════════════════╪═══════════════════════╪═══════════════════════╪═══════
         │    PHASE 4: COMPLETION                                                │
═════════╪═══════════════════════╪═══════════════════════╪═══════════════════════╪═══════
         │                       │                       │                       │
         │                       │                       │  17. PUBLISH complete │
         │                       │ ◄─────────────────────│ ◄─────────────────────│
         │                       │                       │   chat:{chat_id}      │
         │                       │                       │                       │
         │  18. WS: {"type":"complete", "full_response":"..."}                   │
         │ ◄─────────────────────│                       │                       │
         │                       │                       │                       │
  ┌──────┴──────┐         ┌──────┴──────┐         ┌──────┴──────┐         ┌──────┴──────┐
  │   Browser   │         │   FastAPI   │         │    Redis    │         │   Celery    │
  │  (Frontend) │         │  (Backend)  │         │  (Pub/Sub)  │         │   Worker    │
  └─────────────┘         └─────────────┘         └─────────────┘         └─────────────┘
```

### Message Types

| Type | Direction | Description |
|------|-----------|-------------|
| `connected` | Server → Client | WebSocket connection established |
| `start` | Server → Client | Task has started processing |
| `stream` | Server → Client | Streamed word/token from response |
| `complete` | Server → Client | Task finished, includes full response |

## Services

| Service | Port | Description |
|---------|------|-------------|
| Next.js Frontend | 3000 | Chat room UI with WebSocket |
| FastAPI | 8000 | Main API + WebSocket server |
| PostgreSQL | 5432 | Database |
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

### Start Chat (WebSocket Streaming)

```bash
POST /chat/{chat_id}/start
```

Starts a background chat task that streams responses via WebSocket.

**Example:**

```bash
curl -X POST http://localhost:8000/chat/my-chat-room-id/start
```

**Response:**

```json
{
  "task_id": "abc123-...",
  "status": "accepted",
  "message": "Chat task started for room 'my-chat-room-id'"
}
```

### WebSocket Connection

```
WS /ws/{chat_id}
```

Connect to receive streamed responses for a chat room.

**JavaScript Example:**

```javascript
const chatId = 'unique-uuid-for-this-tab';
const ws = new WebSocket(`ws://localhost:8000/ws/${chatId}`);

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  
  switch (data.type) {
    case 'connected':
      console.log('Connected to chat room');
      break;
    case 'start':
      console.log('Task started');
      break;
    case 'stream':
      // Append streamed content (word by word)
      console.log(data.content);
      break;
    case 'complete':
      console.log('Response complete:', data.full_response);
      break;
  }
};

// Start the chat task
fetch(`http://localhost:8000/chat/${chatId}/start`, { method: 'POST' });
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
├── app/                      # Backend (Python/FastAPI)
│   ├── __init__.py           # Package marker
│   ├── main.py               # FastAPI app + WebSocket endpoint
│   ├── celery_app.py         # Celery configuration
│   ├── tasks.py              # Background tasks (including chat_task)
│   └── database.py           # Database configuration
├── frontend/                 # Frontend (Next.js/React)
│   ├── app/
│   │   ├── layout.tsx        # Root layout
│   │   ├── page.tsx          # Main chat page
│   │   └── globals.css       # Global styles
│   ├── components/
│   │   └── ChatRoom.tsx      # Chat room component with WebSocket
│   ├── package.json          # Node dependencies
│   ├── Dockerfile            # Frontend Docker image
│   └── ...
├── docker-compose.yml        # Full-stack Docker configuration
├── Dockerfile                # Backend Docker image
├── requirements.txt          # Python dependencies
└── README.md                 # This file
```

## Environment Variables

### Backend

| Variable | Default | Description |
|----------|---------|-------------|
| DATABASE_URL | postgresql+asyncpg://postgres:postgres@postgres:5432/app_db | PostgreSQL connection string |
| CELERY_BROKER_URL | redis://redis:6379/0 | Redis broker URL |
| CELERY_RESULT_BACKEND | redis://redis:6379/1 | Redis result backend URL |
| FRONTEND_URL | http://localhost:3000 | Frontend URL for CORS |

### Frontend

| Variable | Default | Description |
|----------|---------|-------------|
| NEXT_PUBLIC_API_URL | http://localhost:8000 | Backend API URL |
| NEXT_PUBLIC_WS_URL | ws://localhost:8000 | Backend WebSocket URL |

## Frontend Development

### Running Locally (without Docker)

```bash
cd frontend
npm install
npm run dev
```

The frontend will be available at http://localhost:3000.

### How It Works

1. Each browser tab generates a unique UUID as the chat room ID
2. The tab establishes a WebSocket connection to `/ws/{chat_id}`
3. Clicking "Start Chat" sends a POST request to `/chat/{chat_id}/start`
4. The backend queues a Celery task and returns immediately (202 Accepted)
5. The Celery worker processes the task and publishes messages to Redis
6. The FastAPI WebSocket handler receives messages from Redis and forwards them to the connected client
7. The frontend displays the streamed response word by word
