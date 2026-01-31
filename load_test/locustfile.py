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

import os
import uuid
import json
import time
import logging
from urllib.parse import urlparse
from locust import HttpUser, task, between, events
import websocket

# Configure logging - force output to console
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    datefmt='%H:%M:%S',
    force=True  # Override any existing config
)
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Also print to stdout directly for visibility
import sys
handler = logging.StreamHandler(sys.stdout)
handler.setLevel(logging.INFO)
handler.setFormatter(logging.Formatter('%(asctime)s | %(levelname)s | %(message)s', '%H:%M:%S'))
logger.addHandler(handler)


def get_ws_url(http_host: str) -> str:
    """
    Convert HTTP host URL to WebSocket URL.
    http://localhost:8000 -> ws://localhost:8000
    https://api.example.com -> wss://api.example.com
    """
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
    
    # Wait 2-5 seconds between sending messages (like a real user)
    wait_time = between(2, 5)
    
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
        
        print(f">>> [{self.chat_id[:8]}] Connecting to WebSocket: {ws_url}")
        
        try:
            # Create connection with reasonable timeout
            self.ws = websocket.create_connection(ws_url, timeout=60)
            
            # Receive the "connected" message (should arrive immediately)
            self.ws.settimeout(10)
            msg = self.ws.recv()
            print(f">>> [{self.chat_id[:8]}] Received initial: {msg[:80]}...")
            
            self.ws_connected = True
            print(f">>> [{self.chat_id[:8]}] ✓ WebSocket connected and ready!")
            
        except Exception as e:
            print(f">>> [{self.chat_id[:8]}] ✗ FAILED to connect: {type(e).__name__}: {e}")
            self.ws_connected = False
            self.ws = None
    
    def on_stop(self):
        """Called when a user stops - close WebSocket."""
        if self.ws:
            try:
                self.ws.close()
                logger.info(f"[{self.chat_id[:8]}] WebSocket closed (user stopped)")
            except:
                pass
    
    @task(weight=1)
    def health_check(self):
        """Simple health check to verify API is responding."""
        self.client.get("/health")
    
    @task(weight=5)
    def send_chat_message(self):
        """
        Send a chat message (like clicking "Start Chat" button).
        Uses the SAME persistent WebSocket connection.
        """
        # Reconnect if connection was lost
        if not self.ws_connected or not self.ws:
            print(f">>> [{self.chat_id[:8]}] No connection, connecting...")
            self._connect_websocket()
            if not self.ws_connected:
                print(f">>> [{self.chat_id[:8]}] ✗ Could not connect, skipping")
                return
        
        start_time = time.time()
        messages_received = 0
        success = False
        
        print(f">>> [{self.chat_id[:8]}] POST /chat/{self.chat_id[:8]}.../start")
        
        try:
            # Trigger the chat task via HTTP (same chat_id, same WebSocket)
            response = self.client.post(f"/chat/{self.chat_id}/start")
            
            print(f">>> [{self.chat_id[:8]}] POST response: {response.status_code}")
            
            if response.status_code != 200:
                print(f">>> [{self.chat_id[:8]}] ERROR: {response.status_code} - {response.text[:100]}")
                raise Exception(f"HTTP {response.status_code}")
            
            print(f">>> [{self.chat_id[:8]}] Waiting for WebSocket messages...")
            
            # Receive messages on the persistent WebSocket until complete
            self.ws.settimeout(60)  # Wait up to 60s for full response
            
            while True:
                try:
                    result = self.ws.recv()
                    data = json.loads(result)
                    messages_received += 1
                    
                    msg_type = data.get("type", "unknown")
                    
                    if msg_type == "start":
                        print(f">>> [{self.chat_id[:8]}] Got 'start' message")
                    elif msg_type == "stream":
                        # Show progress periodically
                        if messages_received % 20 == 0:
                            progress = data.get("progress", {}).get("percent", "?")
                            print(f">>> [{self.chat_id[:8]}] Streaming... {progress}%")
                    elif msg_type == "complete":
                        success = True
                        elapsed = time.time() - start_time
                        print(f">>> [{self.chat_id[:8]}] ✓ COMPLETE! {messages_received} msgs in {elapsed:.1f}s")
                        break
                    else:
                        print(f">>> [{self.chat_id[:8]}] Got message type: {msg_type}")
                        
                except websocket.WebSocketTimeoutException:
                    print(f">>> [{self.chat_id[:8]}] ✗ TIMEOUT after {time.time() - start_time:.1f}s")
                    break
                except websocket.WebSocketConnectionClosedException as e:
                    print(f">>> [{self.chat_id[:8]}] ✗ CONNECTION CLOSED: {e}")
                    self.ws_connected = False
                    break
                except json.JSONDecodeError as e:
                    print(f">>> [{self.chat_id[:8]}] ✗ Invalid JSON: {result[:50]}")
                    break
            
        except Exception as e:
            print(f">>> [{self.chat_id[:8]}] ✗ ERROR: {type(e).__name__}: {e}")
            events.request.fire(
                request_type="WebSocket",
                name="send_chat_message",
                response_time=(time.time() - start_time) * 1000,
                response_length=0,
                exception=e,
            )
            return
        
        # Report to Locust
        total_time = (time.time() - start_time) * 1000
        events.request.fire(
            request_type="WebSocket",
            name="send_chat_message",
            response_time=total_time,
            response_length=messages_received,
            exception=None if success else Exception(f"Incomplete: got {messages_received} msgs"),
        )
        
        if success:
            print(f">>> [{self.chat_id[:8]}] Task SUCCESS, connection still open")


class WebSocketOnlyUser(HttpUser):
    """
    Simulates users who just maintain WebSocket connections WITHOUT sending messages.
    Useful for testing maximum connection capacity.
    
    Use this to answer: "How many idle WebSocket connections can the server handle?"
    """
    
    wait_time = between(5, 10)
    
    def on_start(self):
        """Connect WebSocket on user start."""
        self.chat_id = str(uuid.uuid4())
        ws_base = get_ws_url(self.host)
        ws_url = f"{ws_base}/ws/{self.chat_id}"
        
        logger.info(f"[IDLE-{self.chat_id[:8]}] Connecting (idle user)...")
        
        try:
            self.ws = websocket.create_connection(ws_url, timeout=10)
            # Receive the "connected" message
            self.ws.recv()
            logger.info(f"[IDLE-{self.chat_id[:8]}] ✓ Connected (will stay idle)")
        except Exception as e:
            logger.error(f"[IDLE-{self.chat_id[:8]}] ✗ Failed to connect: {e}")
            self.ws = None
    
    def on_stop(self):
        """Close WebSocket on user stop."""
        if self.ws:
            try:
                self.ws.close()
                logger.info(f"[IDLE-{self.chat_id[:8]}] Disconnected")
            except:
                pass
    
    @task
    def keep_alive(self):
        """Just maintain the connection (no chat messages)."""
        if self.ws:
            # Check if connection is still alive
            try:
                # Set a very short timeout to check for messages without blocking
                self.ws.settimeout(0.1)
                try:
                    self.ws.recv()
                except websocket.WebSocketTimeoutException:
                    pass  # No message, that's fine
                self.ws.settimeout(30)
            except Exception as e:
                logger.warning(f"[IDLE-{self.chat_id[:8]}] Connection lost, reconnecting...")
                self.on_start()
