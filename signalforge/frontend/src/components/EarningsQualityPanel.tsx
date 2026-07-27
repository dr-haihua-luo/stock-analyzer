import {
  BarChart, Bar, LineChart, Line, XAxis, YAxis,
  Tooltip, ResponsiveContainer, ReferenceLine,
} from 'recharts';

interface QuarterlyPoint  { period: string; value: number | null }
interface SurpriseRecord  {
  period: string; eps_estimate: number | null;
  eps_actual: number | null; surprise_pct: number | null;
}
interface EpsRevision {
  window: string; up_count: number | null;
  down_count: number | null; direction: string | null;
}
interface EarningsQuality {
  ticker: string;
  revenue_qtrs: QuarterlyPoint[];
  revenue_yoy_pct: number | null;
  revenue_trend: string | null;
  gross_margin_pct: number | null;
  operating_margin_pct: number | null;
  net_margin_pct: number | null;
  gross_margin_qtrs: QuarterlyPoint[];
  operating_margin_qtrs: QuarterlyPoint[];
  margin_trend: string | null;
  fcf_qtrs: QuarterlyPoint[];
  fcf_margin_pct: number | null;
  fcf_to_net_income: number | null;
  fcf_trend: string | null;
  cash_billions: number | null;
  total_debt_billions: number | null;
  net_cash_billions: number | null;
  current_ratio: number | null;
  debt_to_equity: number | null;
  cash_trend: string | null;
  surprise_history: SurpriseRecord[];
  avg_surprise_pct: number | null;
  beat_streak: number | null;
  next_earnings_date: string | null;
  guidance_signal: string | null;
  earnings_quality_score: number | null;
  quality_components: Record<string, any>;
  disclaimer: string;
}

interface Props {
  data: EarningsQuality | null | undefined;
  ticker: string;
  loading: boolean;
}

const TREND_BADGE: Record<string, string> = {
  accelerating: "text-green-400  bg-green-900/30  border-green-700",
  improving:    "text-green-400  bg-green-900/30  border-green-700",
  expanding:    "text-green-400  bg-green-900/30  border-green-700",
  growing:      "text-green-400  bg-green-900/30  border-green-700",
  raised:       "text-green-400  bg-green-900/30  border-green-700",
  stable:       "text-gray-400   bg-gray-800      border-gray-600",
  neutral:      "text-gray-400   bg-gray-800      border-gray-600",
  decelerating: "text-yellow-400 bg-yellow-900/30 border-yellow-700",
  contracting:  "text-red-400    bg-red-900/30    border-red-700",
  deteriorating:"text-red-400    bg-red-900/30    border-red-700",
  shrinking:    "text-red-400    bg-red-900/30    border-red-700",
  cut:          "text-red-400    bg-red-900/30    border-red-700",
};

function TrendBadge({ label }: { label: string | null | undefined }) {
  if (!label) return null;
  const cls = TREND_BADGE[label] ?? "text-gray-400 bg-gray-800 border-gray-600";
  return (
    <span className={`text-xs font-medium px-2 py-0.5 rounded border ${cls}`}>
      {label}
    </span>
  );
}

function MiniBarChart({
  data, unit = "B", color = "#60a5fa",
}: {
  data: QuarterlyPoint[]; unit?: string; color?: string;
}) {
  if (!data?.length) return <p className="text-xs text-gray-600">No data</p>;
  return (
    <ResponsiveContainer width="100%" height={80}>
      <BarChart data={data} margin={{ top: 4, right: 4, left: -20, bottom: 0 }}>
        <XAxis dataKey="period" tick={{ fontSize: 9, fill: "#6b7280" }}
               tickLine={false} axisLine={false} />
        <YAxis tick={{ fontSize: 9, fill: "#6b7280" }}
               tickLine={false} axisLine={false}
               tickFormatter={(v) => `${v}${unit}`} />
        <Tooltip
          formatter={(v: number) => [`${v}${unit}`, ""]}
          contentStyle={{
            background: "#111827", border: "1px solid #374151",
            fontSize: 11, borderRadius: 6,
          }}
        />
        <ReferenceLine y={0} stroke="#374151" />
        <Bar dataKey="value" fill={color} radius={[2, 2, 0, 0]} />
      </BarChart>
    </ResponsiveContainer>
  );
}

function MiniLineChart({
  data, unit = "%", color = "#a78bfa",
}: {
  data: QuarterlyPoint[]; unit?: string; color?: string;
}) {
  if (!data?.length) return <p className="text-xs text-gray-600">No data</p>;
  return (
    <ResponsiveContainer width="100%" height={80}>
      <LineChart data={data} margin={{ top: 4, right: 4, left: -20, bottom: 0 }}>
        <XAxis dataKey="period" tick={{ fontSize: 9, fill: "#6b7280" }}
               tickLine={false} axisLine={false} />
        <YAxis tick={{ fontSize: 9, fill: "#6b7280" }}
               tickLine={false} axisLine={false}
               tickFormatter={(v) => `${v}${unit}`} />
        <Tooltip
          formatter={(v: number) => [`${v.toFixed(1)}${unit}`, ""]}
          contentStyle={{
            background: "#111827", border: "1px solid #374151",
            fontSize: 11, borderRadius: 6,
          }}
        />
        <Line type="monotone" dataKey="value" stroke={color}
              strokeWidth={2} dot={{ r: 3 }} />
      </LineChart>
    </ResponsiveContainer>
  );
}

export default function EarningsQualityPanel({ data, ticker, loading }: Props) {
  if (loading) {
    return (
      <div className="w-full border border-gray-700 rounded-xl p-5
                      bg-gray-900 mt-4">
        <div className="h-5 w-56 bg-gray-800 rounded animate-pulse mb-4" />
        <div className="grid grid-cols-3 gap-3">
          {[...Array(6)].map((_, i) => (
            <div key={i} className="h-28 bg-gray-800 rounded-lg animate-pulse" />
          ))}
        </div>
      </div>
    );
  }

  if (!data) return null;

  // Check if any meaningful data was returned
  const hasAnyData = data && (
    (data.revenue_qtrs?.length ?? 0) > 0 ||
    data.revenue_yoy_pct != null ||
    data.gross_margin_pct != null ||
    data.fcf_margin_pct != null ||
    data.cash_billions != null ||
    (data.surprise_history?.length ?? 0) > 0 ||
    data.earnings_quality_score != null
  );

  if (!hasAnyData) {
    return (
      <div className="w-full border border-gray-700 rounded-xl p-5
                      bg-gray-900 mt-4">
        <div className="flex items-center gap-3 mb-2">
          <h2 className="text-lg font-semibold text-gray-200">
            Earnings Quality
          </h2>
          <span className="text-xs text-gray-500 bg-gray-800 border
                           border-gray-700 px-2 py-0.5 rounded">
            INFORMATIONAL
          </span>
        </div>
        <p className="text-sm text-gray-500 text-center py-8">
          Earnings quality data unavailable for {ticker}.
          Yahoo Finance may not have quarterly financial statements
          for this ticker. Try a major US exchange-listed stock.
        </p>
      </div>
    );
  }

  const score      = data.earnings_quality_score;
  const scoreColor = score == null ? "text-gray-500"
    : score > 0.3  ? "text-green-400"
    : score < -0.3 ? "text-red-400"
    : "text-yellow-400";

  const guidanceColor = {
    raised:       "text-green-400",
    neutral:      "text-gray-400",
    cut:          "text-red-400",
    unavailable:  "text-gray-600",
  }[data.guidance_signal ?? "unavailable"] ?? "text-gray-400";

  const beatStreakColor = !data.beat_streak ? "text-gray-400"
    : data.beat_streak >= 3  ? "text-green-400"
    : data.beat_streak >= 1  ? "text-green-300"
    : data.beat_streak <= -2 ? "text-red-400"
    : "text-yellow-400";

  return (
    <div className="w-full border border-gray-700 rounded-xl p-5
                    bg-gray-900 mt-4">

      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3 mb-5">
        <div className="flex items-center gap-3">
          <h2 className="text-lg font-semibold text-gray-200">
            Earnings Quality
          </h2>
          <span className="text-xs font-medium text-gray-500
                           bg-gray-800 border border-gray-700
                           px-2 py-0.5 rounded">
            INFORMATIONAL
          </span>
        </div>
        <div className="flex items-center gap-3">
          {data.next_earnings_date && (
            <span className="text-xs text-gray-500">
              Next earnings:{" "}
              <span className="text-gray-300">{data.next_earnings_date}</span>
            </span>
          )}
          {score != null && (
            <span className={`text-sm font-bold ${scoreColor}`}>
              Quality score: {score >= 0 ? "+" : ""}{score.toFixed(3)}
            </span>
          )}
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">

        {/* Revenue — only render if data exists */}
        {(data.revenue_qtrs.length > 0 || data.revenue_yoy_pct != null) && (
          <div className="bg-gray-800/40 rounded-xl p-4 border border-gray-700/50">
            <div className="flex items-center justify-between mb-2">
              <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wide">
                Revenue (Quarterly, $B)
              </h3>
              <TrendBadge label={data.revenue_trend} />
            </div>
            <MiniBarChart data={data.revenue_qtrs} unit="B" color="#60a5fa" />
            {data.revenue_yoy_pct != null && (
              <p className="text-xs text-gray-500 mt-1">
                YoY growth:{" "}
                <span className={data.revenue_yoy_pct >= 0
                  ? "text-green-400 font-medium" : "text-red-400 font-medium"}>
                  {data.revenue_yoy_pct >= 0 ? "+" : ""}{data.revenue_yoy_pct.toFixed(1)}%
                </span>
              </p>
            )}
          </div>
        )}

        {/* Margins — only render if data exists */}
        {(data.gross_margin_qtrs.length > 0 || data.gross_margin_pct != null) && (
          <div className="bg-gray-800/40 rounded-xl p-4 border border-gray-700/50">
            <div className="flex items-center justify-between mb-2">
              <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wide">
                Gross Margin Trend
              </h3>
              <TrendBadge label={data.margin_trend} />
            </div>
            <MiniLineChart data={data.gross_margin_qtrs} unit="%" color="#a78bfa" />
            <div className="flex gap-3 mt-1 text-xs text-gray-500">
              {data.gross_margin_pct != null && (
                <span>Gross: <span className="text-white">
                  {data.gross_margin_pct.toFixed(1)}%
                </span></span>
              )}
              {data.operating_margin_pct != null && (
                <span>Oper: <span className="text-white">
                  {data.operating_margin_pct.toFixed(1)}%
                </span></span>
              )}
              {data.net_margin_pct != null && (
                <span>Net: <span className="text-white">
                  {data.net_margin_pct.toFixed(1)}%
                </span></span>
              )}
            </div>
          </div>
        )}

        {/* Free Cash Flow — only render if data exists */}
        {(data.fcf_qtrs.length > 0 || data.fcf_margin_pct != null) && (
          <div className="bg-gray-800/40 rounded-xl p-4 border border-gray-700/50">
            <div className="flex items-center justify-between mb-2">
              <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wide">
                Free Cash Flow ($B)
              </h3>
              <TrendBadge label={data.fcf_trend} />
            </div>
            <MiniBarChart
              data={data.fcf_qtrs} unit="B"
              color="#34d399"
            />
            <div className="flex gap-3 mt-1 text-xs text-gray-500">
              {data.fcf_margin_pct != null && (
                <span>FCF margin: <span className="text-white">
                  {data.fcf_margin_pct.toFixed(1)}%
                </span></span>
              )}
              {data.fcf_to_net_income != null && (
                <span>
                  FCF/NI:{" "}
                  <span className={data.fcf_to_net_income > 1
                    ? "text-green-400" : "text-yellow-400"}>
                    {data.fcf_to_net_income.toFixed(2)}x
                  </span>
                </span>
              )}
            </div>
          </div>
        )}

        {/* Balance Sheet — only render if data exists */}
        {(data.cash_billions != null || data.current_ratio != null) && (
          <div className="bg-gray-800/40 rounded-xl p-4 border border-gray-700/50">
            <div className="flex items-center justify-between mb-2">
              <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wide">
                Balance Sheet
              </h3>
              <TrendBadge label={data.cash_trend} />
            </div>
            <div className="space-y-1.5 mt-2">
              {[
                {
                  label: "Net cash",
                  value: data.net_cash_billions != null
                    ? `${data.net_cash_billions >= 0 ? "+" : ""}$${data.net_cash_billions.toFixed(1)}B`
                    : "N/A",
                  color: data.net_cash_billions == null ? "text-gray-500"
                    : data.net_cash_billions >= 0 ? "text-green-400" : "text-red-400",
                },
                {
                  label: "Cash",
                  value: data.cash_billions != null
                    ? `$${data.cash_billions.toFixed(1)}B` : "N/A",
                  color: "text-gray-300",
                },
                {
                  label: "Total debt",
                  value: data.total_debt_billions != null
                    ? `$${data.total_debt_billions.toFixed(1)}B` : "N/A",
                  color: "text-gray-300",
                },
                {
                  label: "Current ratio",
                  value: data.current_ratio?.toFixed(2) ?? "N/A",
                  color: data.current_ratio == null ? "text-gray-500"
                    : data.current_ratio >= 1.5 ? "text-green-400"
                    : data.current_ratio >= 1.0 ? "text-yellow-400"
                    : "text-red-400",
                },
                {
                  label: "Debt/Equity",
                  value: data.debt_to_equity?.toFixed(2) ?? "N/A",
                  color: data.debt_to_equity == null ? "text-gray-500"
                    : data.debt_to_equity < 0.5 ? "text-green-400"
                    : data.debt_to_equity < 1.5 ? "text-yellow-400"
                    : "text-red-400",
                },
              ].map(({ label, value, color }) => (
                <div key={label}
                     className="flex justify-between text-xs">
                  <span className="text-gray-500">{label}</span>
                  <span className={`font-medium ${color}`}>{value}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Earnings Surprises — only render if data exists */}
        {data.surprise_history.length > 0 && (
          <div className="bg-gray-800/40 rounded-xl p-4 border border-gray-700/50">
            <div className="flex items-center justify-between mb-2">
              <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wide">
                EPS Surprise History
              </h3>
              {data.beat_streak != null && (
                <span className={`text-xs font-bold ${beatStreakColor}`}>
                  {data.beat_streak > 0
                    ? `${data.beat_streak}Q beat streak`
                    : data.beat_streak < 0
                    ? `${Math.abs(data.beat_streak)}Q miss streak`
                    : "Mixed"}
                </span>
              )}
            </div>
            <div className="space-y-1.5 mt-1">
              {data.surprise_history.map((s) => (
                <div key={s.period}
                     className="flex justify-between items-center text-xs">
                  <span className="text-gray-600">{s.period}</span>
                  <div className="flex items-center gap-2">
                    {s.eps_estimate != null && (
                      <span className="text-gray-500">
                        est ${s.eps_estimate.toFixed(2)}
                      </span>
                    )}
                    {s.eps_actual != null && (
                      <span className="text-gray-300 font-medium">
                        act ${s.eps_actual.toFixed(2)}
                      </span>
                    )}
                    {s.surprise_pct != null && (
                      <span className={`font-bold ${
                        s.surprise_pct >= 0 ? "text-green-400" : "text-red-400"
                      }`}>
                        {s.surprise_pct >= 0 ? "+" : ""}
                        {s.surprise_pct.toFixed(1)}%
                      </span>
                    )}
                  </div>
                </div>
              ))}
            </div>
            {data.avg_surprise_pct != null && (
              <p className="text-xs text-gray-500 mt-2 pt-2 border-t border-gray-800">
                Avg surprise:{" "}
                <span className={data.avg_surprise_pct >= 0
                  ? "text-green-400 font-medium" : "text-red-400 font-medium"}>
                  {data.avg_surprise_pct >= 0 ? "+" : ""}
                  {data.avg_surprise_pct.toFixed(1)}%
                </span>
              </p>
            )}
          </div>
        )}

        {/* Guidance Signal — only render if data exists */}
        {data.guidance_signal != null && data.guidance_signal !== "unavailable" && (
          <div className="bg-gray-800/40 rounded-xl p-4 border border-gray-700/50">
            <h3 className="text-xs font-semibold text-gray-400 uppercase
                           tracking-wide mb-3">
              Guidance Signal
            </h3>
            <div className="flex items-center gap-2 mb-4">
              <span className={`text-2xl font-black uppercase ${guidanceColor}`}>
                {data.guidance_signal ?? "N/A"}
              </span>
              <span className="text-xs text-gray-600">
                (via EPS estimate revisions)
              </span>
            </div>
            <p className="text-xs text-gray-600 leading-relaxed">
              {data.guidance_signal === "raised"
                ? "Analysts are raising EPS estimates, typically reflecting positive management guidance or improved outlook."
                : data.guidance_signal === "cut"
                ? "Analysts are cutting EPS estimates, often reflecting disappointing guidance or deteriorating outlook."
                : data.guidance_signal === "neutral"
                ? "EPS estimate revisions are balanced with no clear directional bias."
                : "Insufficient revision data to determine guidance direction."}
            </p>
          </div>
        )}
      </div>

      <p className="text-xs text-gray-600 border-t border-gray-800 pt-3 mt-4">
        ⚠️ {data.disclaimer}
      </p>
    </div>
  );
}