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

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)


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
        
        logger.info(f"[{self.chat_id[:8]}] Connecting to WebSocket: {ws_url}")
        
        try:
            self.ws = websocket.create_connection(ws_url, timeout=30)
            # Set non-blocking for receiving
            self.ws.settimeout(0.1)
            # Receive the "connected" message
            try:
                self.ws.recv()
            except:
                pass
            self.ws_connected = True
            logger.info(f"[{self.chat_id[:8]}] ✓ WebSocket connected successfully")
        except Exception as e:
            logger.error(f"[{self.chat_id[:8]}] ✗ Failed to connect WebSocket: {e}")
            self.ws_connected = False
    
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
            logger.warning(f"[{self.chat_id[:8]}] Connection lost, reconnecting...")
            self._connect_websocket()
            if not self.ws_connected:
                logger.error(f"[{self.chat_id[:8]}] Reconnection failed, skipping task")
                return
        
        start_time = time.time()
        messages_received = 0
        success = False
        
        logger.info(f"[{self.chat_id[:8]}] Sending chat message (POST /chat/{{id}}/start)")
        
        try:
            # Trigger the chat task via HTTP (same chat_id, same WebSocket)
            response = self.client.post(f"/chat/{self.chat_id}/start")
            
            if response.status_code != 200:
                raise Exception(f"Failed to start chat: {response.status_code}")
            
            logger.info(f"[{self.chat_id[:8]}] Chat started, waiting for streamed response...")
            
            # Receive messages on the persistent WebSocket until complete
            self.ws.settimeout(30)  # Wait up to 30s for response
            while True:
                try:
                    result = self.ws.recv()
                    data = json.loads(result)
                    messages_received += 1
                    
                    msg_type = data.get("type", "unknown")
                    if msg_type == "stream":
                        # Log progress every 10 messages to avoid spam
                        if messages_received % 10 == 0:
                            progress = data.get("progress", {}).get("percent", "?")
                            logger.debug(f"[{self.chat_id[:8]}] Streaming... {progress}% ({messages_received} msgs)")
                    elif msg_type == "complete":
                        success = True
                        logger.info(f"[{self.chat_id[:8]}] ✓ Response complete ({messages_received} messages, {(time.time() - start_time):.1f}s)")
                        break
                        
                except websocket.WebSocketTimeoutException:
                    logger.warning(f"[{self.chat_id[:8]}] Timeout waiting for response")
                    break
                except websocket.WebSocketConnectionClosedException:
                    logger.error(f"[{self.chat_id[:8]}] WebSocket connection closed unexpectedly")
                    self.ws_connected = False
                    break
            
            # Reset to non-blocking for next iteration
            if self.ws_connected:
                self.ws.settimeout(0.1)
            
        except Exception as e:
            logger.error(f"[{self.chat_id[:8]}] ✗ Error: {e}")
            events.request.fire(
                request_type="WebSocket",
                name="send_chat_message",
                response_time=(time.time() - start_time) * 1000,
                response_length=0,
                exception=e,
            )
            return
        
        # Report success
        total_time = (time.time() - start_time) * 1000
        events.request.fire(
            request_type="WebSocket",
            name="send_chat_message",
            response_time=total_time,
            response_length=messages_received,
            exception=None if success else Exception("Did not receive complete message"),
        )


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
