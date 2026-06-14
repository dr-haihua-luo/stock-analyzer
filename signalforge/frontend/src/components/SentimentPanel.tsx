import { StockTwitsSentiment } from '../types/signal';

interface Props {
  sentiment: StockTwitsSentiment | null | undefined;
  ticker: string;
  loading: boolean;
}

export default function SentimentPanel({ sentiment, ticker, loading }: Props) {
  if (loading) {
    return (
      <div className="w-full border border-gray-700 rounded-xl p-5 bg-gray-900 mt-6">
        <div className="flex items-center gap-2 mb-4">
          <span className="text-lg font-semibold text-gray-300">
            StockTwits Social Sentiment
          </span>
          <span className="text-xs text-gray-500 bg-gray-800 px-2 py-0.5 rounded">
            INFORMATIONAL
          </span>
        </div>
        <div className="animate-pulse h-20 bg-gray-800 rounded-lg" />
      </div>
    );
  }

  const unavailable =
    !sentiment || sentiment.source === 'unavailable';

  const sourceLabel =
    sentiment?.source === 'firestream'
      ? 'Firestream v2 (24h aggregate)'
      : sentiment?.source === 'public_stream'
      ? `Public stream (last ${sentiment.total_messages_sampled ?? '?'} posts)`
      : null;

  const bullish = sentiment?.bullish_pct ?? 0;
  const bearish = sentiment?.bearish_pct ?? 0;
  const neutral = sentiment?.neutral_pct ?? 0;

  const labelColor =
    sentiment?.sentiment_label === 'BULLISH'
      ? 'text-green-400 bg-green-900/30 border-green-700'
      : sentiment?.sentiment_label === 'BEARISH'
      ? 'text-red-400 bg-red-900/30 border-red-700'
      : 'text-gray-400 bg-gray-800 border-gray-600';

  return (
    <div className="w-full border border-gray-700 rounded-xl p-5 bg-gray-900 mt-6">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3 mb-5">
        <div className="flex items-center gap-2">
          <span className="text-lg font-semibold text-gray-200">
            StockTwits Social Sentiment
          </span>
          <span className="text-xs font-medium text-yellow-400 bg-yellow-900/30
                           border border-yellow-700 px-2 py-0.5 rounded">
            INFORMATIONAL ONLY
          </span>
        </div>
        {sourceLabel && (
          <span className="text-xs text-gray-500">
            Source: {sourceLabel}
          </span>
        )}
      </div>

      {unavailable ? (
        <div className="text-center py-6 text-gray-500 text-sm">
          StockTwits sentiment data unavailable for {ticker}.
          <br />
          Check STOCKTWITS_USERNAME / STOCKTWITS_PASSWORD in .env,
          or the ticker may have low social activity.
        </div>
      ) : (
        <>
          {/* Sentiment label badge + score */}
          <div className="flex flex-wrap items-center gap-4 mb-5">
            <span
              className={`text-base font-bold px-3 py-1 rounded-lg border ${labelColor}`}
            >
              {sentiment?.sentiment_label ?? 'NEUTRAL'}
            </span>
            {sentiment?.sentiment_score != null && (
              <span className="text-sm text-gray-400">
                Sentiment score:{' '}
                <span className="text-white font-medium">
                  {sentiment.sentiment_score.toFixed(1)} / 100
                </span>
              </span>
            )}
          </div>

          {/* Three-bar percentage breakdown */}
          <div className="space-y-3 mb-5">
            {/* Bullish bar */}
            <div>
              <div className="flex justify-between text-xs text-gray-400 mb-1">
                <span>Bullish</span>
                <span className="text-green-400 font-semibold">
                  {bullish.toFixed(1)}%
                </span>
              </div>
              <div className="w-full h-3 bg-gray-800 rounded-full overflow-hidden">
                <div
                  className="h-full bg-green-500 rounded-full transition-all duration-700"
                  style={{ width: `${bullish}%` }}
                />
              </div>
            </div>

            {/* Neutral bar */}
            <div>
              <div className="flex justify-between text-xs text-gray-400 mb-1">
                <span>Neutral / Unlabeled</span>
                <span className="text-gray-300 font-semibold">
                  {neutral.toFixed(1)}%
                </span>
              </div>
              <div className="w-full h-3 bg-gray-800 rounded-full overflow-hidden">
                <div
                  className="h-full bg-gray-500 rounded-full transition-all duration-700"
                  style={{ width: `${neutral}%` }}
                />
              </div>
            </div>

            {/* Bearish bar */}
            <div>
              <div className="flex justify-between text-xs text-gray-400 mb-1">
                <span>Bearish</span>
                <span className="text-red-400 font-semibold">
                  {bearish.toFixed(1)}%
                </span>
              </div>
              <div className="w-full h-3 bg-gray-800 rounded-full overflow-hidden">
                <div
                  className="h-full bg-red-500 rounded-full transition-all duration-700"
                  style={{ width: `${bearish}%` }}
                />
              </div>
            </div>
          </div>

          {/* Stacked bar — visual summary */}
          <div className="w-full h-4 rounded-full overflow-hidden flex mb-4">
            <div
              className="h-full bg-green-500 transition-all duration-700"
              style={{ width: `${bullish}%` }}
            />
            <div
              className="h-full bg-gray-600 transition-all duration-700"
              style={{ width: `${neutral}%` }}
            />
            <div
              className="h-full bg-red-500 transition-all duration-700"
              style={{ width: `${bearish}%` }}
            />
          </div>

          {/* Metadata row */}
          <div className="flex flex-wrap gap-x-6 gap-y-1 text-xs text-gray-500 mb-4">
            {sentiment?.message_volume_label && (
              <span>
                Message volume (24h):{' '}
                <span className="text-gray-300">
                  {sentiment.message_volume_label}
                </span>
              </span>
            )}
            {sentiment?.participation_score != null && (
              <span>
                Participation score:{' '}
                <span className="text-gray-300">
                  {sentiment.participation_score.toFixed(1)}
                </span>
              </span>
            )}
            {sentiment?.labeled_messages != null && sentiment?.total_messages_sampled != null && (
              <span>
                Tagged posts:{' '}
                <span className="text-gray-300">
                  {sentiment.labeled_messages} / {sentiment.total_messages_sampled}
                </span>
              </span>
            )}
            {sentiment?.fetched_at && (
              <span>
                Fetched:{' '}
                <span className="text-gray-300">
                  {new Date(sentiment.fetched_at).toLocaleTimeString()}
                </span>
              </span>
            )}
          </div>
        </>
      )}

      {/* Disclaimer — always shown */}
      <p className="text-xs text-gray-600 border-t border-gray-800 pt-3 mt-1">
        ⚠️ {sentiment?.disclaimer ??
          'Social sentiment is informational only and does not affect the BUY/HOLD/SELL signal or confidence score.'}
      </p>
    </div>
  );
}