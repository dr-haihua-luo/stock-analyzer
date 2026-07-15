import { useState, useCallback } from 'react';
import type { PerformanceReport } from '../types/signal';

export function usePerformance() {
  const [report, setReport] = useState<PerformanceReport | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [visible, setVisible] = useState(false);

  const fetchReport = useCallback(async (ticker: string) => {
    if (!ticker.trim()) return;
    setLoading(true);
    setError(null);
    setVisible(true);
    try {
      const response = await fetch(`/api/performance/${ticker.trim().toUpperCase()}`);
      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail ?? 'Failed to load performance data');
      }
      const data: PerformanceReport = await response.json();
      setReport(data);
    } catch (err: any) {
      setError(err.message ?? 'Failed to load performance data');
      setReport(null);
    } finally {
      setLoading(false);
    }
  }, []);

  const closeReport = useCallback(() => {
    setVisible(false);
    setReport(null);
  }, []);

  return { report, loading, error, visible, fetchReport, closeReport };
}