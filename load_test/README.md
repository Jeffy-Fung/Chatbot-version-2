# Load Testing

Load testing scripts for the Chatbot application using [Locust](https://locust.io/).

## Setup

```bash
cd load_test
pip install -r requirements.txt
```

## Running Load Tests

### Option 1: Web UI (Recommended for exploration)

**Local testing:**
```bash
locust -f locustfile.py --host=http://localhost:8000
```

**Production/Cloud testing (e.g., Railway):**
```bash
locust -f locustfile.py --host=https://your-api.up.railway.app
```

Then open http://localhost:8089 in your browser.

- **Number of users**: Total concurrent users to simulate
- **Spawn rate**: Users to add per second

### Option 2: Headless (For CI/CD or scripted tests)

**Test 100 concurrent users (local):**
```bash
locust -f locustfile.py --host=http://localhost:8000 --users 100 --spawn-rate 10 --run-time 2m --headless
```

**Test 100 concurrent users (production):**
```bash
locust -f locustfile.py --host=https://your-api.up.railway.app --users 100 --spawn-rate 10 --run-time 2m --headless
```

**Test 500 concurrent users:**
```bash
locust -f locustfile.py --host=https://your-api.up.railway.app --users 500 --spawn-rate 50 --run-time 5m --headless
```

**Test 1000 concurrent users:**
```bash
locust -f locustfile.py --host=https://your-api.up.railway.app --users 1000 --spawn-rate 100 --run-time 5m --headless
```

### Note on HTTPS/WSS

The script automatically converts:
- `http://` → `ws://` (local)
- `https://` → `wss://` (production with SSL)

## Test Scenarios

The load test includes two user types:

### 1. ChatUser (Full flow)
- Connects WebSocket
- Triggers chat task via HTTP
- Receives all streamed messages
- Reports total time and success

### 2. WebSocketOnlyUser (Connection test)
- Just maintains WebSocket connections
- Useful for testing max connection capacity

## Metrics to Watch

| Metric | Good | Warning | Bad |
|--------|------|---------|-----|
| Response time (p95) | < 500ms | 500ms-2s | > 2s |
| Failure rate | < 1% | 1-5% | > 5% |
| RPS | Stable | Declining | Crashing |

## Monitoring During Tests

While running load tests, monitor:

1. **Flower Dashboard**: http://localhost:5555
   - Task queue length
   - Worker status

2. **Docker Stats**:
   ```bash
   docker stats
   ```

3. **Redis Queue**:
   ```bash
   docker exec app_redis redis-cli LLEN celery
   ```

## Troubleshooting

### High failure rate?
- Check if backend is running: `docker-compose ps`
- Check logs: `docker-compose logs -f api celery_worker`

### Slow response times?
- Increase Celery concurrency in `docker-compose.yml`
- Add more Celery workers

### Connection refused?
- Backend might be overwhelmed
- Reduce spawn rate or total users
