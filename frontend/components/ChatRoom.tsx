'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import { v4 as uuidv4 } from 'uuid';

interface Message {
  id: string;
  type: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: Date;
}

interface StreamMessage {
  type: 'connected' | 'start' | 'stream' | 'complete';
  task_id?: string;
  message?: string;
  content?: string;
  chat_id?: string;
  full_response?: string;
  progress?: {
    current: number;
    total: number;
    percent: number;
  };
}

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
const WS_URL = process.env.NEXT_PUBLIC_WS_URL || 'ws://localhost:8000';

export default function ChatRoom() {
  const [chatId] = useState(() => uuidv4());
  const [messages, setMessages] = useState<Message[]>([]);
  const [isConnected, setIsConnected] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [currentResponse, setCurrentResponse] = useState('');
  const [progress, setProgress] = useState<number | null>(null);
  
  const wsRef = useRef<WebSocket | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  const getMessageStyles = (type: 'user' | 'assistant' | 'system') => {
    switch (type) {
      case 'user':
        return 'bg-blue-500 text-white';
      case 'assistant':
        return 'bg-white dark:bg-gray-700 text-gray-800 dark:text-white shadow';
      case 'system':
        return 'bg-gray-200 dark:bg-gray-600 text-gray-600 dark:text-gray-300 text-sm italic';
    }
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, currentResponse]);

  const connectWebSocket = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      return;
    }

    const ws = new WebSocket(`${WS_URL}/ws/${chatId}`);
    
    ws.onopen = () => {
      console.log('WebSocket connected');
      setIsConnected(true);
    };

    ws.onmessage = (event) => {
      try {
        const data: StreamMessage = JSON.parse(event.data);
        console.log('Received:', data);

        switch (data.type) {
          case 'connected':
            setMessages((prev) => [
              ...prev,
              {
                id: uuidv4(),
                type: 'system',
                content: `Connected to chat room: ${chatId.slice(0, 8)}...`,
                timestamp: new Date(),
              },
            ]);
            break;

          case 'start':
            setCurrentResponse('');
            setProgress(0);
            break;

          case 'stream':
            setCurrentResponse((prev) => prev + (data.content || ''));
            if (data.progress) {
              setProgress(data.progress.percent);
            }
            break;

          case 'complete':
            // Finalize the assistant message
            setMessages((prev) => [
              ...prev,
              {
                id: uuidv4(),
                type: 'assistant',
                content: data.full_response || currentResponse,
                timestamp: new Date(),
              },
            ]);
            setCurrentResponse('');
            setProgress(null);
            setIsLoading(false);
            break;
        }
      } catch (error) {
        console.error('Failed to parse message:', error);
      }
    };

    ws.onclose = () => {
      console.log('WebSocket disconnected');
      setIsConnected(false);
    };

    ws.onerror = (error) => {
      console.error('WebSocket error:', error);
      setIsConnected(false);
    };

    wsRef.current = ws;
  }, [chatId, currentResponse]);

  useEffect(() => {
    connectWebSocket();

    return () => {
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, [connectWebSocket]);

  const startChat = async () => {
    if (isLoading) return;

    setIsLoading(true);
    
    // Add user message
    setMessages((prev) => [
      ...prev,
      {
        id: uuidv4(),
        type: 'user',
        content: 'Start chat',
        timestamp: new Date(),
      },
    ]);

    try {
      const response = await fetch(`${API_URL}/chat/${chatId}/start`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const data = await response.json();
      console.log('Task started:', data);
    } catch (error) {
      console.error('Failed to start chat:', error);
      setMessages((prev) => [
        ...prev,
        {
          id: uuidv4(),
          type: 'system',
          content: `Error: Failed to start chat. Make sure the backend is running.`,
          timestamp: new Date(),
        },
      ]);
      setIsLoading(false);
    }
  };

  return (
    <div className="flex flex-col h-screen max-w-4xl mx-auto p-4">
      {/* Header */}
      <div className="flex items-center justify-between mb-4 pb-4 border-b border-gray-200 dark:border-gray-700">
        <div>
          <h1 className="text-2xl font-bold text-gray-800 dark:text-white">
            Chat Room
          </h1>
          <p className="text-sm text-gray-500 dark:text-gray-400">
            Room ID: {chatId.slice(0, 8)}...
          </p>
        </div>
        <div className="flex items-center gap-2">
          <div
            className={`w-3 h-3 rounded-full ${
              isConnected ? 'bg-green-500' : 'bg-red-500'
            }`}
          />
          <span className="text-sm text-gray-600 dark:text-gray-300">
            {isConnected ? 'Connected' : 'Disconnected'}
          </span>
        </div>
      </div>

      {/* Messages Container */}
      <div className="flex-1 overflow-y-auto mb-4 space-y-4 p-4 bg-gray-50 dark:bg-gray-800 rounded-lg">
        {messages.length === 0 && !currentResponse && (
          <div className="text-center text-gray-500 dark:text-gray-400 py-8">
            <p>No messages yet. Click "Start Chat" to begin!</p>
          </div>
        )}

        {messages.map((message) => (
          <div
            key={message.id}
            className={`flex ${
              message.type === 'user' ? 'justify-end' : 'justify-start'
            }`}
          >
            <div
              className={`max-w-[80%] rounded-lg px-4 py-2 ${getMessageStyles(message.type)}`}
            >
              {message.type !== 'system' && (
                <div className="text-xs opacity-70 mb-1">
                  {message.type === 'user' ? 'You' : 'Assistant'}
                </div>
              )}
              <p className="whitespace-pre-wrap">{message.content}</p>
            </div>
          </div>
        ))}

        {/* Streaming response */}
        {currentResponse && (
          <div className="flex justify-start">
            <div className="max-w-[80%] rounded-lg px-4 py-2 bg-white dark:bg-gray-700 text-gray-800 dark:text-white shadow">
              <div className="text-xs opacity-70 mb-1">Assistant</div>
              <p className="whitespace-pre-wrap">{currentResponse}</p>
              {progress !== null && (
                <div className="mt-2">
                  <div className="w-full bg-gray-200 dark:bg-gray-600 rounded-full h-1.5">
                    <div
                      className="bg-blue-500 h-1.5 rounded-full transition-all duration-100"
                      style={{ width: `${progress}%` }}
                    />
                  </div>
                </div>
              )}
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Action Bar */}
      <div className="flex gap-2">
        <button
          onClick={startChat}
          disabled={isLoading || !isConnected}
          className={`flex-1 py-3 px-6 rounded-lg font-semibold text-white transition-all ${
            isLoading || !isConnected
              ? 'bg-gray-400 cursor-not-allowed'
              : 'bg-blue-500 hover:bg-blue-600 active:scale-[0.98]'
          }`}
        >
          {isLoading ? (
            <span className="flex items-center justify-center gap-2">
              <svg
                className="animate-spin h-5 w-5"
                xmlns="http://www.w3.org/2000/svg"
                fill="none"
                viewBox="0 0 24 24"
              >
                <circle
                  className="opacity-25"
                  cx="12"
                  cy="12"
                  r="10"
                  stroke="currentColor"
                  strokeWidth="4"
                />
                <path
                  className="opacity-75"
                  fill="currentColor"
                  d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                />
              </svg>
              Processing...
            </span>
          ) : (
            'Start Chat'
          )}
        </button>
        
        {!isConnected && (
          <button
            onClick={connectWebSocket}
            className="py-3 px-6 rounded-lg font-semibold text-blue-500 border border-blue-500 hover:bg-blue-50 dark:hover:bg-blue-900/20 transition-all"
          >
            Reconnect
          </button>
        )}
      </div>
    </div>
  );
}
