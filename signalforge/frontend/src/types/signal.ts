export interface SignalOutput {
  ticker: string;
  signal: 'BUY' | 'HOLD' | 'SELL';
  confidence: number;
  timestamp: string;
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