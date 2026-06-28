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

export default {
  analyzeTicker,
  getSignalHistory,
};