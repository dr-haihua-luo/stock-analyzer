import React, { useState, useEffect } from 'react';
import { useAnalysis } from './hooks/useAnalysis';
import { useWebSocket } from './hooks/useWebSocket';
import SignalCard from './components/SignalCard';
import MarketOverview from './components/MarketOverview';
import SectorHeatmap from './components/SectorHeatmap';
import StockChart from './components/StockChart';
import ConfidenceBreakdown from './components/ConfidenceBreakdown';
import SentimentPanel from './components/SentimentPanel';

function App() {
  const [ticker, setTicker] = useState('AAPL');
  const [analysisResult, setAnalysisResult] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const { analyzeTicker } = useAnalysis();
  const { wsConnected, sendMessage } = useWebSocket(ticker);

  const handleAnalyze = async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await analyzeTicker(ticker.toUpperCase());
      setAnalysisResult(result);
    } catch (err: any) {
      setError(err.message || 'Analysis failed');
    } finally {
      setLoading(false);
    }
  };

  // Initial analysis on mount only - runs once when component mounts
  useEffect(() => {
    handleAnalyze();
  }, []); // Empty dependency array ensures this only runs on mount

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-white shadow-md">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
          <h1 className="text-3xl font-bold text-gray-900">
            SignalForge Trading Analysis
          </h1>
          <p className="mt-2 text-sm text-gray-600">
            AI-powered trading signals using LangGraph agents
          </p>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Search Bar */}
        <div className="mb-6">
          <div className="flex max-w-xl">
            <input
              type="text"
              value={ticker}
              onChange={(e) => setTicker(e.target.value.toUpperCase())}
              placeholder="Enter stock ticker (e.g., AAPL, MSFT, GOOGL)"
              className="flex-1 px-4 py-2 border border-gray-300 rounded-l-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
            <button
              onClick={handleAnalyze}
              disabled={loading}
              className="px-6 py-2 bg-blue-600 text-white rounded-r-lg hover:bg-blue-700 disabled:opacity-50"
            >
              {loading ? 'Analyzing...' : 'Analyze'}
            </button>
          </div>
          {error && <p className="mt-2 text-sm text-red-600">{error}</p>}
        </div>

        {analysisResult ? (
          <>
            {/* Signal Card */}
            <SignalCard signal={analysisResult.signal} />

            {/* Confidence Breakdown */}
            <ConfidenceBreakdown breakdown={analysisResult.confidence_breakdown} />

            {/* Analysis Details Tabs */}
            <div className="mt-8">
              <button
                onClick={() => setAnalysisResult(null)}
                className="text-sm text-gray-600 hover:text-gray-900"
              >
                ← Back to Search
              </button>
            </div>

            {/* StockTwits Sentiment Panel - Full width at bottom */}
            <SentimentPanel
              sentiment={analysisResult.signal?.stocktwits_sentiment}
              ticker={ticker}
              loading={loading}
            />
          </>
        ) : (
          <>
            {/* Default View - Market Overview and Sector Analysis */}
            <div className="grid gap-6 md:grid-cols-2">
              <MarketOverview />
              <SectorHeatmap />
            </div>

            {/* Example Stock Chart */}
            <div className="mt-8">
              <h2 className="text-xl font-semibold mb-4">Example: AAPL Chart</h2>
              <StockChart ticker="AAPL" />
            </div>
          </>
        )}
      </main>

      {/* Raw Data Display (for debugging) */}
      {analysisResult && (
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 mt-12 bg-gray-50">
          <h2 className="text-xl font-bold mb-4">Raw Analysis Data (for debugging)</h2>
          <div className="bg-white rounded-lg shadow-md p-6">
            <pre className="text-xs text-gray-600 whitespace-pre-wrap">{JSON.stringify(analysisResult, null, 2)}</pre>
          </div>
        </div>
      )}
    </div>
  );
}

export default App;