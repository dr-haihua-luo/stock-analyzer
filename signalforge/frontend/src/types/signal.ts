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
  ps_ratio: number | null;
  pb_ratio: number | null;
  profit_margin_pct: number | null;
  roa_pct: number | null;
  roe_pct: number | null;
  roi_pct: number | null;
  gross_margin_pct: number | null;
  oper_margin_pct: number | null;
  debt_to_equity: number | null;
  insider_own_pct: number | null;
  inst_own_pct: number | null;
  inst_trans_pct: number | null;
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

export interface QuarterlyDataPoint {
  period: string;
  value: number | null;
}

export interface EarningsQualityDisplay {
  ticker: string;
  revenue_qtrs: QuarterlyDataPoint[];
  revenue_yoy_pct: number | null;
  revenue_trend: string | null;
  gross_margin_pct: number | null;
  operating_margin_pct: number | null;
  net_margin_pct: number | null;
  gross_margin_qtrs: QuarterlyDataPoint[];
  operating_margin_qtrs: QuarterlyDataPoint[];
  margin_trend: string | null;
  fcf_qtrs: QuarterlyDataPoint[];
  fcf_margin_pct: number | null;
  fcf_to_net_income: number | null;
  fcf_trend: string | null;
  cash_billions: number | null;
  total_debt_billions: number | null;
  net_cash_billions: number | null;
  current_ratio: number | null;
  debt_to_equity: number | null;
  cash_trend: string | null;
  earnings_quality_score: number | null;
  quality_components: Record<string, any>;
  disclaimer: string;
}

export interface FundamentalsDisplay {
  ticker: string;
  fundamental_score: number;
  score_components: Record<string, any>;
  finviz: FinvizSnapshot | null;
  tipranks: TipRanksSnapshot | null;
  disclaimer: string;
}

export interface StockContextDisplay {
  ticker: string;
  current_price?: number | null;
  rsi_14?: number | null;
  macd_signal?: string | null;
  bb_position?: string | null;
  volume_trend?: string | null;
  price_vs_52w_high?: number | null;
  news_sentiment?: number | null;
  technical_score?: number | null;
  fundamental_score?: number | null;
  long_term_ma_trend?: 'up' | 'down' | null;
  long_term_ma_value?: number | null;
  medium_term_ma_trend?: 'up' | 'down' | null;
  medium_term_ma_value?: number | null;
  short_term_ma_trend?: 'up' | 'down' | null;
  short_term_ma_value?: number | null;
  disclaimer?: string;
}

export interface PriceRangeLevel {
  low: number;
  high: number;
}

export interface PriceRangeHorizon {
  '68pct': PriceRangeLevel;
  '90pct': PriceRangeLevel;
  '95pct': PriceRangeLevel;
}

export interface PriceRangeProjection {
  daily_volatility_pct: number | null;
  vix_adjustment_applied: boolean;
  vix_multiplier: number | null;
  '2_week': PriceRangeHorizon | null;
  '1_month': PriceRangeHorizon | null;
}

export interface SignalOutput {
  ticker: string;
  signal: 'BUY' | 'HOLD' | 'SELL';
  confidence: number;
  composite_score: number;
  timestamp: string;
  price_at_signal?: number | null;
  stocktwits_sentiment?: StockTwitsSentiment | null;
  fundamentals?: FundamentalsDisplay | null;
  earnings_quality?: EarningsQualityDisplay | null;
  stock_context?: StockContextDisplay | null;
  market_narrative?: string | null;
  sector_narrative?: string | null;
  stock_narrative?: string | null;
  news_sentiment_narrative?: string | null;
  overall_analysis_narrative?: string | null;
  // Additional market LLM fields
  market_macro?: string | null;
  market_rates_fx?: string | null;
  market_regime?: string | null;
  // Additional sector LLM fields
  sector_rotation_momentum?: string | null;
  sector_economic_implications?: string | null;
  sector_momentum_assessment?: string | null;
  sector_outlook?: string | null;
  price_range_projection?: PriceRangeProjection | null;
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

export interface SignalDataPoint {
  id: string;
  date: string;
  signal: 'BUY' | 'HOLD' | 'SELL';
  confidence: number;
  price_at_signal: number | null;
  composite_score: number | null;
  current_price: number | null;
  pct_change: number | null;
  outcome: 'correct' | 'incorrect' | 'neutral' | 'pending';
}

export interface PerformanceSummary {
  buy_signals: number;
  buy_correct: number;
  buy_avg_return_pct: number | null;
  sell_signals: number;
  sell_correct: number;
  sell_avg_return_pct: number | null;
}

export interface PerformanceReport {
  ticker: string;
  current_price: number | null;
  period: string;
  total_signals: number;
  summary: PerformanceSummary;
  signals: SignalDataPoint[];
}