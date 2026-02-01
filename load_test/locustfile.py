"""
Load testing script for the Chatbot application.

Usage (local):
    locust -f locustfile.py --host=http://localhost:8000

Usage (production):
    locust -f locustfile.py --host=https://your-api.railway.app

Then open http://localhost:8089 to configure and start the test.

Headless mode:
    locust -f locustfile.py --host=https://your-api.railway.app --users 100 --spawn-rate 10 --run-time 1m --headless
"""

import uuid
import json
import time
from urllib.parse import urlparse
from locust import HttpUser, task, between, events
import websocket


def get_ws_url(http_host: str) -> str:
    """Convert HTTP host URL to WebSocket URL."""
    parsed = urlparse(http_host)
    ws_scheme = "wss" if parsed.scheme == "https" else "ws"
    return f"{ws_scheme}://{parsed.netloc}"


class ChatUser(HttpUser):
    """
    Simulates a real user who:
    1. Opens a chat room (connects WebSocket ONCE)
    2. Stays in the room (persistent connection)
    3. Sends multiple chat messages (POST requests)
    4. Receives streamed responses on the SAME WebSocket
    5. Only disconnects when leaving (on_stop)
    """
    
    # Increase wait time to reduce CPU load per user
    wait_time = between(3, 8)
    
    def on_start(self):
        """Called when a user starts - connect WebSocket once."""
        self.chat_id = str(uuid.uuid4())
        self.ws = None
        self.ws_connected = False
        self._connect_websocket()
    
    def _connect_websocket(self):
        """Establish persistent WebSocket connection."""
        ws_base = get_ws_url(self.host)
        ws_url = f"{ws_base}/ws/{self.chat_id}"
        
        try:
            self.ws = websocket.create_connection(ws_url, timeout=60)
            self.ws.settimeout(10)
            self.ws.recv()  # Receive "connected" message
            self.ws_connected = True
            print(f"[{self.chat_id[:8]}] ✓ WS connected")
        except Exception as e:
            print(f"[{self.chat_id[:8]}] ✗ WS failed: {e}")
            self.ws_connected = False
            self.ws = None
    
    def on_stop(self):
        """Called when a user stops - close WebSocket."""
        if self.ws:
            try:
                self.ws.close()
            except:
                pass
    
    @task(weight=1)
    def health_check(self):
        """Simple health check."""
        self.client.get("/health")
    
    @task(weight=5)
    def send_chat_message(self):
        """Send a chat message and receive streamed response."""
        if not self.ws_connected or not self.ws:
            self._connect_websocket()
            if not self.ws_connected:
                return
        
        start_time = time.time()
        messages_received = 0
        success = False
        
        try:
            response = self.client.post(f"/chat/{self.chat_id}/start")
            if response.status_code != 200:
                print(f"[{self.chat_id[:8]}] ✗ POST failed: {response.status_code}")
                raise Exception(f"HTTP {response.status_code}")
            
            self.ws.settimeout(60)
            
            while True:
                try:
                    result = self.ws.recv()
                    data = json.loads(result)
                    messages_received += 1
                    
                    if data.get("type") == "complete":
                        success = True
                        break
                        
                except websocket.WebSocketTimeoutException:
                    break
                except websocket.WebSocketConnectionClosedException:
                    self.ws_connected = False
                    break
                except json.JSONDecodeError:
                    break
            
        except Exception as e:
            events.request.fire(
                request_type="WebSocket",
                name="send_chat_message",
                response_time=(time.time() - start_time) * 1000,
                response_length=0,
                exception=e,
            )
            return
        
        total_time = (time.time() - start_time) * 1000
        events.request.fire(
            request_type="WebSocket",
            name="send_chat_message",
            response_time=total_time,
            response_length=messages_received,
            exception=None if success else Exception(f"Incomplete"),
        )


class WebSocketOnlyUser(HttpUser):
    """
    Simulates idle users who just maintain WebSocket connections.
    Useful for testing maximum connection capacity.
    """
    
    wait_time = between(5, 10)
    
    def on_start(self):
        """Connect WebSocket on user start."""
        self.chat_id = str(uuid.uuid4())
        ws_base = get_ws_url(self.host)
        ws_url = f"{ws_base}/ws/{self.chat_id}"
        
        try:
            self.ws = websocket.create_connection(ws_url, timeout=10)
            self.ws.recv()
            print(f"[IDLE-{self.chat_id[:8]}] ✓ Connected")
        except Exception as e:
            print(f"[IDLE-{self.chat_id[:8]}] ✗ Failed: {e}")
            self.ws = None
    
    def on_stop(self):
        """Close WebSocket on user stop."""
        if self.ws:
            try:
                self.ws.close()
            except:
                pass
    
    @task
    def keep_alive(self):
        """Maintain the connection."""
        if self.ws:
            try:
                self.ws.settimeout(0.1)
                try:
                    self.ws.recv()
                except websocket.WebSocketTimeoutException:
                    pass
                self.ws.settimeout(30)
            except:
                self.on_start()  # Reconnect if lost
