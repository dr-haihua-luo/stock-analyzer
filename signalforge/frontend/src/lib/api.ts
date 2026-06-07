import { AnalysisResponse, AnalysisRequest } from '../types/signal';

const API_BASE_URL = import.meta.env.VITE_API_URL || '';

export const analyzeTicker = async (request: AnalysisRequest): Promise<AnalysisResponse> => {
  const response = await fetch(`${API_BASE_URL}/api/analyze`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(request),
  });

  if (!response.ok) {
    const errorData = await response.json();
    throw new Error(errorData.detail || 'Analysis failed');
  }

  return response.json();
};

export const getSignalHistory = async (limit: number = 100) => {
  const response = await fetch(`${API_BASE_URL}/api/signals/history?limit=${limit}`);

  if (!response.ok) {
    throw new Error('Failed to fetch signal history');
  }

  return response.json();
};

// WebSocket utility functions
export const createAnalysisWebSocket = (ticker: string, onMessage: (data: any) => void) => {
  const ws = new WebSocket(`${import.meta.env.VITE_WS_URL || 'ws://localhost:8000'}/ws/analysis/${ticker.toUpperCase()}`);

  ws.onopen = () => {
    console.log(`WebSocket connected for ${ticker}`);
  };

  ws.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      onMessage(data);
    } catch (error) {
      console.error('Error parsing WebSocket message:', error);
    }
  };

  ws.onclose = () => {
    console.log(`WebSocket disconnected for ${ticker}`);
  };

  ws.onerror = (error) => {
    console.error('WebSocket error:', error);
  };

  return ws;
};

export default {
  analyzeTicker,
  getSignalHistory,
  createAnalysisWebSocket
};