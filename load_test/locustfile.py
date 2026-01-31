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
from urllib.parse import urlparse
from locust import HttpUser, task, between, events
import websocket


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
    Simulates a user who:
    1. Connects to a chat room via WebSocket
    2. Triggers a chat task via HTTP
    3. Receives streamed response via WebSocket
    """
    
    # Wait 1-3 seconds between tasks
    wait_time = between(1, 3)
    
    def on_start(self):
        """Called when a user starts. Generate unique chat_id."""
        self.chat_id = str(uuid.uuid4())
        self.ws = None
        self.messages_received = 0
    
    def on_stop(self):
        """Called when a user stops. Close WebSocket."""
        if self.ws:
            try:
                self.ws.close()
            except:
                pass
    
    @task(weight=1)
    def health_check(self):
        """Simple health check to verify API is responding."""
        self.client.get("/health")
    
    @task(weight=5)
    def full_chat_flow(self):
        """
        Complete chat flow:
        1. Connect WebSocket
        2. Trigger chat task
        3. Receive all messages until complete
        4. Close WebSocket
        """
        chat_id = str(uuid.uuid4())
        ws_base = get_ws_url(self.host)
        ws_url = f"{ws_base}/ws/{chat_id}"
        
        start_time = time.time()
        messages_received = 0
        success = False
        
        try:
            # Connect WebSocket
            ws = websocket.create_connection(ws_url, timeout=30)
            
            # Trigger the chat task via HTTP
            response = self.client.post(f"/chat/{chat_id}/start")
            
            if response.status_code != 200:
                raise Exception(f"Failed to start chat: {response.status_code}")
            
            # Receive messages until complete
            while True:
                try:
                    result = ws.recv()
                    data = json.loads(result)
                    messages_received += 1
                    
                    if data.get("type") == "complete":
                        success = True
                        break
                        
                except websocket.WebSocketTimeoutException:
                    break
            
            ws.close()
            
        except Exception as e:
            events.request.fire(
                request_type="WebSocket",
                name="full_chat_flow",
                response_time=(time.time() - start_time) * 1000,
                response_length=0,
                exception=e,
            )
            return
        
        # Report success
        total_time = (time.time() - start_time) * 1000
        events.request.fire(
            request_type="WebSocket",
            name="full_chat_flow",
            response_time=total_time,
            response_length=messages_received,
            exception=None if success else Exception("Did not receive complete message"),
        )


class WebSocketOnlyUser(HttpUser):
    """
    Simulates users who just maintain WebSocket connections.
    Useful for testing connection capacity.
    """
    
    wait_time = between(5, 10)
    
    def on_start(self):
        """Connect WebSocket on user start."""
        self.chat_id = str(uuid.uuid4())
        ws_base = get_ws_url(self.host)
        ws_url = f"{ws_base}/ws/{self.chat_id}"
        
        try:
            self.ws = websocket.create_connection(ws_url, timeout=10)
            # Receive the "connected" message
            self.ws.recv()
        except Exception as e:
            print(f"Failed to connect WebSocket: {e}")
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
        """Just maintain the connection."""
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
                # Connection lost, try to reconnect
                self.on_start()
