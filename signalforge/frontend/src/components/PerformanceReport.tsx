import {
  ComposedChart, Line, Scatter, XAxis, YAxis, CartesianGrid,
  Tooltip, ReferenceLine, ResponsiveContainer, Legend,
} from 'recharts';
import type { PerformanceReport, SignalDataPoint } from '../types/signal';

interface Props {
  report: PerformanceReport | null;
  loading: boolean;
  error: string | null;
  onClose: () => void;
}

// Color per signal type
const SIGNAL_COLOR: Record<string, string> = {
  BUY: '#22c55e',
  SELL: '#ef4444',
  HOLD: '#94a3b8',
};

// Shape per outcome
function SignalDot(props: any) {
  const { cx, cy, payload } = props;
  const color = SIGNAL_COLOR[payload.signal] ?? '#94a3b8';
  const correct = payload.outcome === 'correct';
  const wrong = payload.outcome === 'incorrect';
  return (
    <g>
      <circle cx={cx} cy={cy} r={8} fill={color}
              stroke={wrong ? '#fbbf24' : 'transparent'} strokeWidth={2} />
      {correct && (
        <text x={cx} y={cy + 4} textAnchor="middle"
              fontSize={9} fill="#fff" fontWeight="bold">✓</text>
      )}
      {wrong && (
        <text x={cx} y={cy + 4} textAnchor="middle"
              fontSize={9} fill="#fff" fontWeight="bold">✗</text>
      )}
    </g>
  );
}

function CustomTooltip({ active, payload }: any) {
  if (!active || !payload?.length) return null;
  const d: SignalDataPoint = payload[0]?.payload;
  if (!d) return null;
  return (
    <div className="bg-gray-900 border border-gray-700 rounded-lg
                    p-3 text-xs shadow-xl min-w-48">
      <p className="font-bold mb-1">
        {new Date(d.date).toLocaleDateString('en-US', {
          month: 'short', day: 'numeric', year: 'numeric'
        })}
      </p>
      <p>
        Signal:{' '}
        <span className="font-bold" style={{ color: SIGNAL_COLOR[d.signal] }}>
          {d.signal}
        </span>
        {' '}({(d.confidence * 100).toFixed(0)}% conf.)
      </p>
      <p>Price at signal: <span className="text-white">
        {d.price_at_signal != null ? `$${d.price_at_signal.toFixed(2)}` : 'N/A'}
      </span></p>
      <p>Current price: <span className="text-white">
        {d.current_price != null ? `$${d.current_price.toFixed(2)}` : 'N/A'}
      </span></p>
      {d.pct_change != null && (
        <p>Change: <span className={
          d.pct_change >= 0 ? 'text-green-400' : 'text-red-400'
        }>{d.pct_change >= 0 ? '+' : ''}{d.pct_change.toFixed(2)}%</span></p>
      )}
      <p>Composite: <span className="text-white">
        {d.composite_score != null
          ? `${d.composite_score >= 0 ? '+' : ''}${d.composite_score.toFixed(4)}`
          : 'N/A'}
      </span></p>
      <p>Outcome: <span className={
        d.outcome === 'correct' ? 'text-green-400' :
        d.outcome === 'incorrect' ? 'text-yellow-400' : 'text-gray-400'
      }>{d.outcome}</span></p>
    </div>
  );
}

export default function PerformanceReportPanel({ report, loading, error, onClose }: Props) {
  if (!loading && !report && !error) return null;

  // Build chart data — one point per signal, x = date index, y = price_at_signal
  const chartData = (report?.signals ?? []).map((s, i) => ({
    ...s,
    index: i,
    dateLabel: new Date(s.date).toLocaleDateString('en-US', {
      month: 'short', day: 'numeric',
    }),
  }));

  const currentPrice = report?.current_price;
  const { summary } = report ?? {};

  const accuracy = (correct: number, total: number) =>
    total > 0 ? `${Math.round(correct / total * 100)}%` : 'N/A';

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center
                    bg-black/70 backdrop-blur-sm p-4">
      <div className="bg-gray-900 border border-gray-700 rounded-2xl
                      w-full max-w-5xl max-h-[90vh] overflow-y-auto
                      shadow-2xl">

        {/* Header */}
        <div className="flex items-center justify-between p-5
                        border-b border-gray-800">
          <div>
            <h2 className="text-xl font-bold text-white">
              Signal Performance Report
              {report && (
                <span className="ml-2 text-blue-400">{report.ticker}</span>
              )}
            </h2>
            <p className="text-xs text-gray-500 mt-0.5">
              Past 12 months · Current price vs price at signal
            </p>
          </div>
          <button onClick={onClose}
                  className="text-gray-400 hover:text-white text-2xl
                             leading-none px-2">
            ×
          </button>
        </div>

        {/* Body */}
        <div className="p-5">

          {loading && (
            <div className="flex items-center justify-center h-64">
              <div className="text-gray-400 text-sm animate-pulse">
                Loading performance data...
              </div>
            </div>
          )}

          {error && (
            <div className="text-red-400 text-sm text-center py-10">
              {error}
            </div>
          )}

          {report && !loading && (
            <>
              {/* Summary stats */}
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
                {[
                  {
                    label: 'Total Signals',
                    value: report.total_signals,
                    color: 'text-white',
                  },
                  {
                    label: 'BUY Accuracy',
                    value: accuracy(summary?.buy_correct ?? 0,
                                   summary?.buy_signals ?? 0),
                    sub: `${summary?.buy_signals ?? 0} signals`,
                    color: 'text-green-400',
                  },
                  {
                    label: 'SELL Accuracy',
                    value: accuracy(summary?.sell_correct ?? 0,
                                   summary?.sell_signals ?? 0),
                    sub: `${summary?.sell_signals ?? 0} signals`,
                    color: 'text-red-400',
                  },
                  {
                    label: 'Current Price',
                    value: currentPrice != null
                      ? `$${currentPrice.toFixed(2)}` : 'N/A',
                    color: 'text-blue-400',
                  },
                ].map(({ label, value, sub, color }) => (
                  <div key={label}
                       className="bg-gray-800 rounded-xl p-4 text-center">
                    <p className="text-xs text-gray-500 mb-1">{label}</p>
                    <p className={`text-2xl font-black ${color}`}>{value}</p>
                    {sub && <p className="text-xs text-gray-600 mt-0.5">{sub}</p>}
                  </div>
                ))}
              </div>

              {/* Average returns */}
              {(summary?.buy_avg_return_pct != null ||
                summary?.sell_avg_return_pct != null) && (
                <div className="flex gap-3 mb-6">
                  {summary?.buy_avg_return_pct != null && (
                    <div className="flex-1 bg-green-900/20 border
                                    border-green-800 rounded-xl p-3 text-center">
                      <p className="text-xs text-gray-400 mb-1">
                        Avg return after BUY signal
                      </p>
                      <p className={`text-lg font-bold ${
                        summary.buy_avg_return_pct >= 0
                          ? 'text-green-400' : 'text-red-400'
                      }`}>
                        {summary.buy_avg_return_pct >= 0 ? '+' : ''}
                        {summary.buy_avg_return_pct.toFixed(2)}%
                      </p>
                      <p className="text-xs text-gray-600 mt-0.5">
                        vs current price
                      </p>
                    </div>
                  )}
                  {summary?.sell_avg_return_pct != null && (
                    <div className="flex-1 bg-red-900/20 border
                                    border-red-800 rounded-xl p-3 text-center">
                      <p className="text-xs text-gray-400 mb-1">
                        Avg return after SELL signal
                      </p>
                      <p className={`text-lg font-bold ${
                        summary.sell_avg_return_pct <= 0
                          ? 'text-green-400' : 'text-red-400'
                      }`}>
                        {summary.sell_avg_return_pct >= 0 ? '+' : ''}
                        {summary.sell_avg_return_pct.toFixed(2)}%
                      </p>
                      <p className="text-xs text-gray-600 mt-0.5">
                        vs current price (negative = SELL was right)
                      </p>
                    </div>
                  )}
                </div>
              )}

              {/* Price chart */}
              {chartData.length === 0 ? (
                <div className="text-center text-gray-500 text-sm py-16
                                border border-gray-800 rounded-xl">
                  No signals recorded for {report.ticker} in the past 12 months.
                  <br />
                  Run an analysis to start tracking performance.
                </div>
              ) : (
                <div className="border border-gray-800 rounded-xl p-4 mb-6">
                  <h3 className="text-sm font-medium text-gray-400
                                 uppercase tracking-wide mb-4">
                    Price at Signal vs Current Price
                  </h3>
                  <ResponsiveContainer width="100%" height={320}>
                    <ComposedChart
                      data={chartData}
                      margin={{ top: 10, right: 20, left: 10, bottom: 10 }}
                    >
                      <CartesianGrid strokeDasharray="3 3"
                                     stroke="#374151" />
                      <XAxis
                        dataKey="dateLabel"
                        tick={{ fill: '#9ca3af', fontSize: 11 }}
                        tickLine={false}
                      />
                      <YAxis
                        tick={{ fill: '#9ca3af', fontSize: 11 }}
                        tickLine={false}
                        tickFormatter={(v) => `$${v.toFixed(0)}`}
                        domain={['auto', 'auto']}
                      />
                      <Tooltip content={<CustomTooltip />} />
                      <Legend
                        wrapperStyle={{ fontSize: 11, color: '#9ca3af' }}
                      />
                      {/* Current price reference line */}
                      {currentPrice != null && (
                        <ReferenceLine
                          y={currentPrice}
                          stroke="#60a5fa"
                          strokeDasharray="6 3"
                          label={{
                            value: `Current $${currentPrice.toFixed(2)}`,
                            fill: '#60a5fa',
                            fontSize: 11,
                            position: 'insideTopRight',
                          }}
                        />
                      )}
                      {/* Signal dots colored by BUY/SELL/HOLD */}
                      <Scatter
                        name="Signal price"
                        dataKey="price_at_signal"
                        shape={<SignalDot />}
                      />
                      {/* Line connecting signal prices over time */}
                      <Line
                        type="monotone"
                        dataKey="price_at_signal"
                        stroke="#475569"
                        strokeWidth={1}
                        dot={false}
                        name="Price at signal"
                      />
                    </ComposedChart>
                  </ResponsiveContainer>

                  {/* Legend for signal colours */}
                  <div className="flex gap-4 mt-3 justify-center text-xs
                                  text-gray-500">
                    {['BUY', 'HOLD', 'SELL'].map(s => (
                      <span key={s} className="flex items-center gap-1.5">
                        <span className="inline-block w-3 h-3 rounded-full"
                              style={{ background: SIGNAL_COLOR[s] }} />
                        {s}
                      </span>
                    ))}
                    <span className="flex items-center gap-1.5">
                      <span className="inline-block w-3 h-3 rounded-full
                                       border-2 border-yellow-400 bg-transparent" />
                      Incorrect
                    </span>
                    <span className="text-blue-400">
                      — — Current price
                    </span>
                  </div>
                </div>
              )}

              {/* Signal history table */}
              {chartData.length > 0 && (
                <div>
                  <h3 className="text-sm font-medium text-gray-400
                                 uppercase tracking-wide mb-3">
                    Signal History
                  </h3>
                  <div className="overflow-x-auto">
                    <table className="w-full text-xs text-gray-400">
                      <thead>
                        <tr className="border-b border-gray-800
                                       text-gray-500 uppercase tracking-wide">
                          <th className="text-left py-2 pr-4">Date</th>
                          <th className="text-left py-2 pr-4">Signal</th>
                          <th className="text-right py-2 pr-4">Confidence</th>
                          <th className="text-right py-2 pr-4">Price then</th>
                          <th className="text-right py-2 pr-4">Price now</th>
                          <th className="text-right py-2 pr-4">Change</th>
                          <th className="text-right py-2 pr-4">Composite</th>
                          <th className="text-left py-2">Outcome</th>
                        </tr>
                      </thead>
                      <tbody>
                        {[...chartData].reverse().map((d) => (
                          <tr key={d.id}
                              className="border-b border-gray-800/50
                                         hover:bg-gray-800/30">
                            <td className="py-2 pr-4 whitespace-nowrap">
                              {new Date(d.date).toLocaleDateString('en-US', {
                                month: 'short', day: 'numeric',
                                year: 'numeric',
                              })}
                            </td>
                            <td className="py-2 pr-4">
                              <span className="font-bold"
                                    style={{ color: SIGNAL_COLOR[d.signal] }}>
                                {d.signal}
                              </span>
                            </td>
                            <td className="py-2 pr-4 text-right">
                              {(d.confidence * 100).toFixed(0)}%
                            </td>
                            <td className="py-2 pr-4 text-right text-white">
                              {d.price_at_signal != null
                                ? `$${d.price_at_signal.toFixed(2)}` : '—'}
                            </td>
                            <td className="py-2 pr-4 text-right text-blue-400">
                              {d.current_price != null
                                ? `$${d.current_price.toFixed(2)}` : '—'}
                            </td>
                            <td className={`py-2 pr-4 text-right font-medium ${
                              d.pct_change == null ? 'text-gray-600' :
                              d.pct_change >= 0 ? 'text-green-400'
                                                    : 'text-red-400'
                            }`}>
                              {d.pct_change != null
                                ? `${d.pct_change >= 0 ? '+' : ''}${d.pct_change.toFixed(2)}%`
                                : '—'}
                            </td>
                            <td className={`py-2 pr-4 text-right ${
                              d.composite_score == null ? 'text-gray-600' :
                              d.composite_score >= 0 ? 'text-green-400'
                                                        : 'text-red-400'
                            }`}>
                              {d.composite_score != null
                                ? `${d.composite_score >= 0 ? '+' : ''}${d.composite_score.toFixed(4)}`
                                : '—'}
                            </td>
                            <td className={`py-2 ${
                              d.outcome === 'correct' ? 'text-green-400' :
                              d.outcome === 'incorrect' ? 'text-yellow-400' :
                              d.outcome === 'neutral' ? 'text-gray-500'
                                                        : 'text-gray-600'
                            }`}>
                              {d.outcome}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}