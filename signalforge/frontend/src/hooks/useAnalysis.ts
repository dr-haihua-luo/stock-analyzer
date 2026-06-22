import { useState, useCallback } from 'react';
import type { AnalysisResponse } from '@/types/signal';

export const useAnalysis = () => {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const analyzeTicker = useCallback(async (ticker: string, skipTipranks: boolean = true): Promise<AnalysisResponse> => {
    setLoading(true);
    setError(null);

    try {
      const response = await fetch(`/api/analyze`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          ticker: ticker.toUpperCase(),
          skip_tipranks: skipTipranks,
        }),
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Analysis failed');
      }

      const data: AnalysisResponse = await response.json();
      return data;
    } catch (err) {
      setError(err instanceof Error ? err.message : 'An unknown error occurred');
      throw err;
    } finally {
      setLoading(false);
    }
  }, []);

  return { analyzeTicker, loading, error };
};