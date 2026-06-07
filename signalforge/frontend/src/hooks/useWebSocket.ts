import { useState, useEffect, useCallback } from 'react';

export const useWebSocket = (ticker: string) => {
  const [wsConnected, setWsConnected] = useState(false);
  const [ws, setWs] = useState<WebSocket | null>(null);

  // Send message through WebSocket
  const sendMessage = useCallback((message: string) => {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(message);
    }
  }, [ws]);

  useEffect(() => {
    // Clean up previous connection
    if (ws) {
      ws.close();
    }

    // Create new WebSocket connection
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws/analysis/${ticker}`;
    const newWs = new WebSocket(wsUrl);

    setWs(newWs);

    newWs.onopen = () => {
      console.log('WebSocket connected');
      setWsConnected(true);
    };

    newWs.onclose = () => {
      console.log('WebSocket disconnected');
      setWsConnected(false);
      setWs(null);
    };

    newWs.onerror = (error) => {
      console.error('WebSocket error:', error);
      setWsConnected(false);
    };

    // Return cleanup function
    return () => {
      if (newWs) {
        newWs.close();
      }
    };
  }, [ticker]);

  return { wsConnected, sendMessage };
};