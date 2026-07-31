interface Props {
  narrative: string | null | undefined;
  ticker: string;
  loading: boolean;
}

// Extract everything after the NEWS: label (includes sentiment and outlook)
function parseNarrative(text: string): Record<string, string> {
  const result: Record<string, string> = {};
  const match = text.match(/NEWS:\s*(.+)/s);
  if (match) result["NEWS"] = match[1].trim();
  return result;
}

const LABEL_META: Record<string, { icon: string; color: string }> = {
  NEWS:      { icon: "📰", color: "border-blue-700 bg-blue-900/20"    },
};

export default function NewsSentimentPanel({
  narrative,
  ticker,
  loading,
}: Props) {
  if (loading) {
    return (
      <div className="w-full border border-gray-700 rounded-xl p-5
                      bg-gray-900 mt-4">
        <div className="h-5 w-64 bg-gray-800 rounded animate-pulse mb-4" />
        <div className="space-y-3">
          {[...Array(1)].map((_, i) => (
            <div key={i}
                 className="h-20 bg-gray-800 rounded-lg animate-pulse" />
          ))}
        </div>
      </div>
    );
  }

  const hasNarrative = narrative && narrative.trim().length > 0;
  const sections     = hasNarrative ? parseNarrative(narrative!) : {};

  return (
    <div className="w-full border border-gray-700 rounded-xl p-5
                    bg-gray-900 mt-4">
      {/* Header */}
      <div className="flex items-center gap-3 mb-4">
        <h2 className="text-lg font-semibold text-gray-200">
          News & Sentiment Analysis
        </h2>
        <span className="text-xs font-medium text-indigo-400
                         bg-indigo-900/30 border border-indigo-700
                         px-2 py-0.5 rounded">
          AI SYNTHESIS
        </span>
        <span className="text-xs text-gray-500 ml-auto">
          Alpaca news · StockTwits
        </span>
      </div>

      {!hasNarrative ? (
        <p className="text-gray-500 text-sm text-center py-6">
          News & sentiment analysis unavailable for {ticker}.
        </p>
      ) : sections["NEWS"] ? (
        // Has NEWS label - render the news narrative
        <div className="space-y-3">
          {["NEWS"].map((label) => {
            const text = sections[label];
            const meta = LABEL_META[label];
            if (!text) return null;
            return (
              <div
                key={label}
                className={`rounded-lg border px-4 py-3 ${meta.color}`}
              >
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-base">{meta.icon}</span>
                  <span className="text-xs font-semibold text-gray-400
                                 uppercase tracking-wider">
                    {label}
                  </span>
                </div>
                <p className="text-sm text-gray-200 leading-relaxed">
                  {text}
                </p>
              </div>
            );
          })}
        </div>
      ) : (
        // Raw LLM response - render as plain text
        <div className="rounded-lg border border-blue-700 bg-blue-900/20 px-4 py-3">
          <p className="text-sm text-gray-200 leading-relaxed whitespace-pre-wrap">
            {narrative}
          </p>
        </div>
      )}

      <p className="text-xs text-gray-600 border-t border-gray-800
                    pt-3 mt-4">
        Synthesised from Alpaca news (past 10 days, up to 15 articles)
        and StockTwits social posts. Informational only.
      </p>
    </div>
  );
}