export interface StockTwitsSentiment {
  ticker: string;
  source: 'public_stream' | 'unavailable';
  bullish_pct: number | null;
  bearish_pct: number | null;
  neutral_pct: number | null;
  sentiment_label: 'BULLISH' | 'BEARISH' | 'NEUTRAL' | null;
  message_volume_label: string | null;
  message_volume_24h: number | null;
  participation_score: number | null;
  total_messages_sampled: number | null;
  labeled_messages: number | null;
  fetched_at: string;
  disclaimer: string;
}

export interface FinvizSnapshot {
  pe_ratio: number | null;
  forward_pe: number | null;
  peg_ratio: number | null;
  profit_margin_pct: number | null;
  roe_pct: number | null;
  debt_to_equity: number | null;
  insider_own_pct: number | null;
  net_insider_sentiment: number | null;
  insider_buys_90d: number | null;
  insider_sells_90d: number | null;
  eps_next_5y_pct: number | null;
  market_cap_billions: number | null;
  beta: number | null;
  recent_analyst_actions: Array<{
    date: string;
    status: string;
    firm: string;
    target: string;
  }>;
  source: string;
}

export interface TipRanksSnapshot {
  analyst_consensus: string | null;
  price_target_mean: number | null;
  price_target_high: number | null;
  price_target_low: number | null;
  number_of_analysts: number | null;
  buy_pct: number | null;
  hold_pct: number | null;
  sell_pct: number | null;
  buy_count: number | null;
  hold_count: number | null;
  sell_count: number | null;
  smart_score: number | null;
  upside_to_target_pct: number | null;
  source: string;
}

export interface FundamentalsDisplay {
  ticker: string;
  fundamental_score: number;
  score_components: Record<string, any>;
  finviz: FinvizSnapshot | null;
  tipranks: TipRanksSnapshot | null;
  disclaimer: string;
}

export interface SignalOutput {
  ticker: string;
  signal: 'BUY' | 'HOLD' | 'SELL';
  confidence: number;
  timestamp: string;
  stocktwits_sentiment?: StockTwitsSentiment | null;
  fundamentals?: FundamentalsDisplay | null;
  market_narrative?: string | null;
  sector_narrative?: string | null;
  stock_narrative?: string | null;
  news_sentiment_narrative?: string | null;
}

export interface ConfidenceBreakdown {
  market_contribution: number;
  sector_contribution: number;
  technical_contribution: number;
  fundamental_contribution: number;
}

export interface AnalysisResponse {
  signal: SignalOutput;
  confidence_breakdown: ConfidenceBreakdown;
  analysis_details: Record<string, any>;
}

export interface AnalysisRequest {
  ticker: string;
  force_refresh?: boolean;
  skip_tipranks?: boolean;
}