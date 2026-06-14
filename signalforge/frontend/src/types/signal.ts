export interface StockTwitsSentiment {
  ticker: string;
  source: 'firestream' | 'public_stream' | 'unavailable';
  bullish_pct: number | null;
  bearish_pct: number | null;
  neutral_pct: number | null;
  sentiment_label: 'BULLISH' | 'BEARISH' | 'NEUTRAL' | null;
  sentiment_score: number | null;
  message_volume_label: string | null;
  message_volume_24h: number | null;
  participation_score: number | null;
  total_messages_sampled: number | null;
  labeled_messages: number | null;
  fetched_at: string;
  disclaimer: string;
}

export interface SignalOutput {
  ticker: string;
  signal: 'BUY' | 'HOLD' | 'SELL';
  confidence: number;
  timestamp: string;
  stocktwits_sentiment?: StockTwitsSentiment | null;
}

export interface ConfidenceBreakdown {
  market_factor: number;
  sector_factor: number;
  stock_factor: number;
  total_confidence: number;
}

export interface AnalysisResponse {
  signal: SignalOutput;
  confidence_breakdown: ConfidenceBreakdown;
  analysis_details: Record<string, any>;
}

export interface AnalysisRequest {
  ticker: string;
  force_refresh?: boolean;
}