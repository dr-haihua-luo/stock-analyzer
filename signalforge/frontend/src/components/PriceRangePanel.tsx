import { PriceRangeProjection } from '../types/signal';

interface Props {
  data: PriceRangeProjection | null | undefined;
  currentPrice: number | null | undefined;
  loading: boolean;
}

function RangeBar({
  low, high, current, confLabel,
}: {
  low: number;
  high: number;
  current: number;
  confLabel: string;
}) {
  const span = high - low;
  const pctLow = span > 0 ? ((current - low) / span) * 100 : 50;
  const clampedPct = Math.min(100, Math.max(0, pctLow));

  return (
    <div className="mb-3">
      <div className="flex justify-between text-xs text-gray-500 mb-1">
        <span>${low.toFixed(2)}</span>
        <span className="text-gray-400 font-medium">{confLabel} range</span>
        <span>${high.toFixed(2)}</span>
      </div>
      <div className="relative w-full h-2.5 bg-gray-800 rounded-full">
        <div className="absolute inset-0 rounded-full bg-gradient-to-r from-red-900/40 via-gray-700/40 to-green-900/40" />
        <div
          className="absolute top-1/2 -translate-y-1/2 w-1 h-4 bg-blue-400 rounded-full shadow-lg"
          style={{ left: `calc(${clampedPct}% - 2px)` }}
          title={`Current: $${current.toFixed(2)}`}
        />
      </div>
    </div>
  );
}

export default function PriceRangePanel({ data, currentPrice, loading }: Props) {
  if (loading) {
    return (
      <div className="w-full border border-gray-700 rounded-xl p-5 bg-gray-900 mt-4 animate-pulse">
        <div className="h-5 w-56 bg-gray-800 rounded mb-4" />
        <div className="h-32 bg-gray-800 rounded-lg" />
      </div>
    );
  }

  if (!data || !currentPrice) return null;

  const twoDay = data['2_day'];
  const oneWeek = data['1_week'];
  const twoWeek = data['2_week'];
  const oneMonth = data['1_month'];

  return (
    <div className="w-full border border-gray-700 rounded-xl p-5 bg-gray-900 mt-4">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-3">
          <h2 className="text-lg font-semibold text-gray-200">
            Statistical Price Range
          </h2>
          <span className="text-xs font-medium text-gray-500 bg-gray-800 border border-gray-700 px-2 py-0.5 rounded">
            VOLATILITY-BASED PROJECTION
          </span>
        </div>
        <div className="flex items-center gap-4 text-xs text-gray-500">
          <span>
            Current:{' '}
            <span className="text-blue-400 font-medium">${currentPrice.toFixed(2)}</span>
          </span>
          {data.daily_volatility_pct != null && (
            <span>
              Annualized volatility:{' '}
              <span className="text-gray-300 font-medium">
                {data.daily_volatility_pct.toFixed(1)}%
              </span>
              {data.vix_adjustment_applied && data.vix_multiplier != null && (
                <span className="text-amber-400 ml-1">
                  (VIX-adjusted ×{data.vix_multiplier.toFixed(2)})
                </span>
              )}
            </span>
          )}
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-6">
        {/* 2-day horizon */}
        <div>
          <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-3">
            2-Day Range
          </h3>
          {twoDay && (
            <>
              <RangeBar
                low={twoDay['90pct'].low}
                high={twoDay['90pct'].high}
                current={currentPrice}
                confLabel="90%"
              />
              <RangeBar
                low={twoDay['68pct'].low}
                high={twoDay['68pct'].high}
                current={currentPrice}
                confLabel="68%"
              />
            </>
          )}
        </div>

        {/* 1-week horizon */}
        <div>
          <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-3">
            1-Week Range
          </h3>
          {oneWeek && (
            <>
              <RangeBar
                low={oneWeek['90pct'].low}
                high={oneWeek['90pct'].high}
                current={currentPrice}
                confLabel="90%"
              />
              <RangeBar
                low={oneWeek['68pct'].low}
                high={oneWeek['68pct'].high}
                current={currentPrice}
                confLabel="68%"
              />
            </>
          )}
        </div>

        {/* 2-week horizon */}
        <div>
          <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-3">
            2-Week Range
          </h3>
          {twoWeek && (
            <>
              <RangeBar
                low={twoWeek['90pct'].low}
                high={twoWeek['90pct'].high}
                current={currentPrice}
                confLabel="90%"
              />
              <RangeBar
                low={twoWeek['68pct'].low}
                high={twoWeek['68pct'].high}
                current={currentPrice}
                confLabel="68%"
              />
            </>
          )}
        </div>

        {/* 1-month horizon */}
        <div>
          <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-3">
            1-Month Range
          </h3>
          {oneMonth && (
            <>
              <RangeBar
                low={oneMonth['90pct'].low}
                high={oneMonth['90pct'].high}
                current={currentPrice}
                confLabel="90%"
              />
              <RangeBar
                low={oneMonth['68pct'].low}
                high={oneMonth['68pct'].high}
                current={currentPrice}
                confLabel="68%"
              />
            </>
          )}
        </div>
      </div>

      <p className="text-xs text-gray-600 border-t border-gray-800 pt-3 mt-4">
        ⚠️ Statistical projection based on historical volatility, not a price
        prediction. Assumes a log-normal random walk. Ranges are centered on the
        current price and say nothing about direction — actual outcomes depend on
        unforeseeable news, earnings, and market events. 90% range means the price
        is expected to stay within these bounds 9 times out of 10, historically.
      </p>
    </div>
  );
}
