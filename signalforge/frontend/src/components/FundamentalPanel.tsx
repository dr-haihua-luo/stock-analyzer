import { FundamentalsDisplay } from '../types/signal';

interface Props {
  fundamentals: FundamentalsDisplay | null | undefined;
  ticker: string;
  loading: boolean;
}

export default function FundamentalPanel({ fundamentals, ticker, loading }: Props) {

  // Render a KPI tile: label + value + optional color coding
  const KpiTile = ({
    label, value, unit = "", positive_threshold, negative_threshold, invert = false
  }: {
    label: string; value: number | string | null | undefined;
    unit?: string; positive_threshold?: number; negative_threshold?: number;
    invert?: boolean;
  }) => {
    const displayVal = value == null ? "—" : `${value}${unit}`;
    let colorClass = "text-gray-300";
    if (typeof value === "number" && positive_threshold !== undefined && negative_threshold !== undefined) {
      if (invert) {
        colorClass = value <= negative_threshold ? "text-green-400"
                   : value >= positive_threshold ? "text-red-400" : "text-yellow-400";
      } else {
        colorClass = value >= positive_threshold ? "text-green-400"
                   : value <= negative_threshold ? "text-red-400" : "text-yellow-400";
      }
    }
    return (
      <div className="bg-gray-800 rounded-lg p-3 flex flex-col gap-1">
        <span className="text-xs text-gray-500 uppercase tracking-wide">{label}</span>
        <span className={`text-base font-semibold ${colorClass}`}>{displayVal}</span>
      </div>
    );
  };

  // Analyst consensus badge color
  const consensusColor = (c: string | null | undefined) => {
    if (!c) return "text-gray-400 bg-gray-800 border-gray-600";
    if (c.includes("Strong Buy")) return "text-green-300 bg-green-900/40 border-green-600";
    if (c.includes("Buy"))        return "text-green-400 bg-green-900/30 border-green-700";
    if (c.includes("Hold"))       return "text-yellow-400 bg-yellow-900/30 border-yellow-700";
    if (c.includes("Sell"))       return "text-red-400 bg-red-900/30 border-red-700";
    return "text-gray-400 bg-gray-800 border-gray-600";
  };

  // Smart Score color
  const smartScoreColor = (s: number | null | undefined) => {
    if (!s) return "text-gray-400";
    if (s >= 8) return "text-green-400";
    if (s >= 6) return "text-yellow-400";
    return "text-red-400";
  };

  if (loading) {
    return (
      <div className="w-full border border-gray-700 rounded-xl p-5 bg-gray-900 mt-4">
        <div className="h-5 w-48 bg-gray-800 rounded animate-pulse mb-4" />
        <div className="grid grid-cols-4 gap-3">
          {[...Array(8)].map((_, i) => (
            <div key={i} className="h-16 bg-gray-800 rounded-lg animate-pulse" />
          ))}
        </div>
      </div>
    );
  }

  const fv = fundamentals?.finviz;
  const tr = fundamentals?.tipranks;
  const noData = !fv && !tr;

  return (
    <div className="w-full border border-gray-700 rounded-xl p-5 bg-gray-900 mt-4">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3 mb-5">
        <div className="flex items-center gap-3">
          <h2 className="text-lg font-semibold text-gray-200">
            Fundamental Analysis
          </h2>
          <span className="text-xs font-medium text-blue-400 bg-blue-900/30
                           border border-blue-700 px-2 py-0.5 rounded">
            FEEDS SIGNAL SCORE
          </span>
        </div>
        <div className="flex gap-2">
          {fv && (
            <span className="text-xs text-gray-500 bg-gray-800 px-2 py-0.5 rounded">
              FinViz
            </span>
          )}
          {tr && (
            <span className="text-xs text-gray-500 bg-gray-800 px-2 py-0.5 rounded">
              TipRanks
            </span>
          )}
        </div>
      </div>

      {noData ? (
        <p className="text-gray-500 text-sm text-center py-6">
          Fundamental data unavailable for {ticker}.
        </p>
      ) : (
        <div className="space-y-5">

          {/* TipRanks analyst consensus row */}
          {tr && (
            <div className="border border-gray-700/50 rounded-xl p-4 bg-gray-800/30">
              <h3 className="text-sm font-medium text-gray-400 mb-3 uppercase tracking-wide">
                Wall Street Analyst Consensus — TipRanks
              </h3>
              <div className="flex flex-wrap items-center gap-4 mb-3">
                {tr.analyst_consensus && (
                  <span className={`text-sm font-bold px-3 py-1 rounded-lg border
                                   ${consensusColor(tr.analyst_consensus)}`}>
                    {tr.analyst_consensus}
                  </span>
                )}
                {tr.smart_score != null && (
                  <div className="flex items-center gap-1">
                    <span className="text-xs text-gray-500">Smart Score:</span>
                    <span className={`text-xl font-black ${smartScoreColor(tr.smart_score)}`}>
                      {tr.smart_score}
                      <span className="text-sm font-normal text-gray-500">/10</span>
                    </span>
                  </div>
                )}
                {tr.number_of_analysts && (
                  <span className="text-xs text-gray-500">
                    Based on {tr.number_of_analysts} analyst{tr.number_of_analysts !== 1 ? "s" : ""}
                  </span>
                )}
              </div>

              {/* Buy/Hold/Sell bar */}
              {(tr.buy_pct != null || tr.hold_pct != null || tr.sell_pct != null) && (
                <div className="space-y-1.5 mb-3">
                  <div className="w-full h-3 rounded-full overflow-hidden flex">
                    <div className="h-full bg-green-500" style={{ width: `${tr.buy_pct ?? 0}%` }} />
                    <div className="h-full bg-yellow-500" style={{ width: `${tr.hold_pct ?? 0}%` }} />
                    <div className="h-full bg-red-500" style={{ width: `${tr.sell_pct ?? 0}%` }} />
                  </div>
                  <div className="flex gap-x-6 text-xs text-gray-500">
                    <span><span className="text-green-400">{tr.buy_pct?.toFixed(0)}%</span> Buy ({tr.buy_count ?? 0})</span>
                    <span><span className="text-yellow-400">{tr.hold_pct?.toFixed(0)}%</span> Hold ({tr.hold_count ?? 0})</span>
                    <span><span className="text-red-400">{tr.sell_pct?.toFixed(0)}%</span> Sell ({tr.sell_count ?? 0})</span>
                  </div>
                </div>
              )}

              {/* Price targets */}
              {tr.price_target_mean && (
                <div className="flex flex-wrap gap-x-6 gap-y-1 text-sm">
                  <span>
                    Avg target:{" "}
                    <span className="text-white font-semibold">
                      ${tr.price_target_mean.toFixed(2)}
                    </span>
                    {tr.upside_to_target_pct != null && (
                      <span className={`ml-1 text-xs ${tr.upside_to_target_pct >= 0 ? "text-green-400" : "text-red-400"}`}>
                        ({tr.upside_to_target_pct >= 0 ? "+" : ""}{tr.upside_to_target_pct.toFixed(1)}%)
                      </span>
                    )}
                  </span>
                  {tr.price_target_high && (
                    <span className="text-gray-500 text-xs">
                      High: <span className="text-gray-300">${tr.price_target_high.toFixed(2)}</span>
                    </span>
                  )}
                  {tr.price_target_low && (
                    <span className="text-gray-500 text-xs">
                      Low: <span className="text-gray-300">${tr.price_target_low.toFixed(2)}</span>
                    </span>
                  )}
                </div>
              )}
            </div>
          )}

          {/* FinViz KPI grid */}
          {fv && (
            <div>
              <h3 className="text-sm font-medium text-gray-300 mb-3 uppercase tracking-wide border-b border-gray-700 pb-2">
                Financial Ratios & KPIs — FinViz
              </h3>
              <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-3">
                <KpiTile label="P/E Ratio" value={fv.pe_ratio}
                  positive_threshold={0} negative_threshold={50} invert />
                <KpiTile label="Forward P/E" value={fv.forward_pe}
                  positive_threshold={0} negative_threshold={40} invert />
                <KpiTile label="PEG Ratio" value={fv.peg_ratio}
                  positive_threshold={0} negative_threshold={2} invert />
                <KpiTile label="Profit Margin" value={fv.profit_margin_pct} unit="%"
                  positive_threshold={15} negative_threshold={0} />
                <KpiTile label="ROE" value={fv.roe_pct} unit="%"
                  positive_threshold={15} negative_threshold={5} />
                <KpiTile label="ROA" value={fv.roa_pct} unit="%"
                  positive_threshold={10} negative_threshold={3} />
                <KpiTile label="Debt/Equity" value={fv.debt_to_equity}
                  positive_threshold={0} negative_threshold={1.5} invert />
                <KpiTile label="EPS Next 5Y" value={fv.eps_next_5y_pct} unit="%"
                  positive_threshold={15} negative_threshold={0} />
                <KpiTile label="Beta" value={fv.beta} />
                <KpiTile label="Market Cap" value={fv.market_cap_billions?.toFixed(1)} unit="B" />
              </div>
            </div>
          )}

          {/* Insider activity */}
          {fv && (fv.net_insider_sentiment != null || fv.insider_own_pct != null) && (
            <div className="border border-gray-700/50 rounded-xl p-4 bg-gray-800/30">
              <h3 className="text-sm font-medium text-gray-400 mb-3 uppercase tracking-wide">
                Insider Activity — FinViz
              </h3>
              <div className="flex flex-wrap gap-x-6 gap-y-2 text-sm">
                {fv.insider_own_pct != null && (
                  <span className="text-white grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-3">
                    Insider ownership:{" "}
                    <span className="text-white font-semibold">{fv.insider_own_pct.toFixed(1)}%</span>
                  </span>
                )}
                {fv.net_insider_sentiment != null && (
                  <span>
                    90-day net sentiment:{" "}
                    <span className={`font-semibold ${
                      fv.net_insider_sentiment > 0.2 ? "text-green-400" :
                      fv.net_insider_sentiment < -0.2 ? "text-red-400" : "text-gray-300"
                    }`}>
                      {fv.net_insider_sentiment > 0 ? "+" : ""}
                      {(fv.net_insider_sentiment * 100).toFixed(0)}%
                    </span>
                    {" "}
                    <span className="text-gray-500 text-xs">
                      ({fv.insider_buys_90d ?? 0} buy / {fv.insider_sells_90d ?? 0} sell)
                    </span>
                  </span>
                )}
              </div>
            </div>
          )}

          {/* Recent analyst actions from FinViz */}
          {fv && fv.recent_analyst_actions && fv.recent_analyst_actions.length > 0 && (
            <div>
              <h3 className="text-sm font-medium text-gray-400 mb-2 uppercase tracking-wide">
                Recent Analyst Actions — FinViz
              </h3>
              <div className="space-y-1">
                {fv.recent_analyst_actions.map((a, i) => (
                  <div key={i} className="flex flex-wrap gap-x-3 text-xs text-gray-400
                                          bg-gray-800/40 rounded px-3 py-1.5">
                    <span className="text-gray-500">{a.date}</span>
                    <span className={
                      a.status?.toLowerCase().includes("upgrade") ? "text-green-400" :
                      a.status?.toLowerCase().includes("downgrade") ? "text-red-400" :
                      "text-gray-300"
                    }>{a.status}</span>
                    <span className="text-gray-300">{a.firm}</span>
                    {a.target && a.target !== "—" && (
                      <span className="text-gray-500">→ {a.target}</span>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Fundamental score summary */}
          {fundamentals?.fundamental_score != null && (
            <div className="flex items-center gap-3 pt-2 border-t border-gray-800">
              <span className="text-xs text-gray-500">Fundamental score (feeds signal):</span>
              <span className={`text-sm font-bold ${
                fundamentals.fundamental_score > 0.2 ? "text-green-400" :
                fundamentals.fundamental_score < -0.2 ? "text-red-400" : "text-yellow-400"
              }`}>
                {fundamentals.fundamental_score > 0 ? "+" : ""}
                {fundamentals.fundamental_score.toFixed(3)}
              </span>
              <span className="text-xs text-gray-600">
                (coverage: {((fundamentals.score_components?._total_weight_coverage ?? 0) * 100).toFixed(0)}% of weights)
              </span>
            </div>
          )}
        </div>
      )}

      <p className="text-xs text-gray-600 border-t border-gray-800 pt-3 mt-4">
        {fundamentals?.disclaimer ??
          "Fundamental data feeds the signal score with 50% weight on the stock component."}
      </p>
    </div>
  );
}