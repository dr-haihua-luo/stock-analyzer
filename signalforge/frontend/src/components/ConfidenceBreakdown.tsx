import React from 'react';

interface ConfidenceBreakdown {
  market_contribution: number;
  sector_contribution: number;
  technical_contribution: number;
  fundamental_contribution: number;
}

interface Props {
  breakdown: ConfidenceBreakdown | null | undefined;
  market_narrative?: string | null;
  sector_narrative?: string | null;
  stock_narrative?: string | null;
  // Additional market LLM fields
  market_sentiment?: string | null;
  market_rate_implications?: string | null;
  market_volatility_expectation?: string | null;
  market_outlook?: string | null;
  // Additional sector LLM fields
  sector_rotation_momentum?: string | null;
  sector_economic_implications?: string | null;
  sector_momentum_assessment?: string | null;
  sector_outlook?: string | null;
}

/**
 * Render stock narrative with section-aware parsing.
 * The stock narrative uses a 5-label template with TECHNICAL:/SETUP:/FUNDAMENTALS:/ANALYST VIEW:/SENTIMENT:
 * Each section is rendered in its own colored block for readability.
 * Handles multi-line narratives with the "s" flag for regex.
 */
function renderStockNarrative(narrative: string | null | undefined) {
  if (!narrative) return (
    <p className="text-xs text-gray-700 italic mt-1">No analysis available</p>
  );

  const LABELS = ["TECHNICAL", "SETUP", "FUNDAMENTALS", "ANALYST VIEW", "SENTIMENT"];
  const sections: { label: string; text: string }[] = [];

  // Escape special regex characters in labels (like SPACE in "ANALYST VIEW")
  const escapeRegex = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

  LABELS.forEach((label, i) => {
    // Build lookahead pattern: match until next label followed by : or end of string
    const nextLabelsPattern = LABELS.slice(i + 1).map(escapeRegex).join(":\\s*|\\s*");
    const pattern = new RegExp(
      `${escapeRegex(label)}:\\s*([\\s\\S]+?)(?:${nextLabelsPattern}:|$)`,
      "i" // case-insensitive, handles variations
    );
    const match = narrative.match(pattern);
    if (match?.[1]?.trim()) {
      sections.push({ label, text: match[1].trim() });
    }
  });

  // If parsing found structured sections, render them individually
  if (sections.length >= 1) {
    return (
      <div className="mt-1 space-y-1.5">
        {sections.map(({ label, text }) => (
          <div key={label}
               className="bg-gray-800/50 rounded px-2.5 py-1.5
                          border-l-2 border-amber-700">
            <span className="text-xs font-semibold text-amber-500
                             uppercase tracking-wide mr-1.5">
              {label}:
            </span>
            <span className="text-xs text-gray-300 leading-relaxed">
              {text}
            </span>
          </div>
        ))}
      </div>
    );
  }

  // Fallback: render as pre-wrap paragraph if no sections parsed
  // This ensures even long unstructured narratives display
  return (
    <p className="text-xs text-gray-300 leading-relaxed
                  bg-gray-800/50 rounded-lg px-3 py-2
                  border-l-2 border-gray-600 mt-1
                  whitespace-pre-wrap break-words">
      {narrative}
    </p>
  );
}

export default function ConfidenceBreakdown({
  breakdown,
  market_narrative,
  sector_narrative,
  stock_narrative,
  // Market LLM fields
  market_sentiment,
  market_rate_implications,
  market_volatility_expectation,
  market_outlook,
  // Sector LLM fields
  sector_rotation_momentum,
  sector_economic_implications,
  sector_momentum_assessment,
  sector_outlook,
}: Props) {

  if (!breakdown) {
    return (
      <div className="border border-gray-700 rounded-xl p-4 bg-gray-900">
        <h3 className="text-sm font-semibold text-gray-400 uppercase tracking-wide mb-3">
          Confidence Breakdown
        </h3>
        <p className="text-gray-600 text-xs text-center py-4">
          Run an analysis to see breakdown
        </p>
      </div>
    );
  }

  // Combine technical + fundamental into a single "Stock" bar for display.
  // The two sub-components are shown as a split annotation beneath.
  const techContrib = breakdown.technical_contribution ?? 0;
  const fundContrib = breakdown.fundamental_contribution ?? 0;
  const stockContrib = techContrib + fundContrib;

  const areas = [
    {
      label:       "Market",
      value:       breakdown.market_contribution ?? 0,
      narrative:   market_narrative,
      barColor:    "bg-blue-500",
      textColor:   "text-blue-400",
      subtext:     null,
      // Additional market LLM fields
      llm_fields: {
        sentiment: market_sentiment,
        rate_implications: market_rate_implications,
        volatility_expectation: market_volatility_expectation,
        outlook: market_outlook,
      },
    },
    {
      label:       "Sector",
      value:       breakdown.sector_contribution ?? 0,
      narrative:   sector_narrative,
      barColor:    "bg-purple-500",
      textColor:   "text-purple-400",
      subtext:     null,
      // Additional sector LLM fields
      llm_fields: {
        rotation_momentum: sector_rotation_momentum,
        economic_implications: sector_economic_implications,
        momentum_assessment: sector_momentum_assessment,
        outlook: sector_outlook,
      },
    },
    {
      label:       "Stock",
      value:       stockContrib,
      narrative:   stock_narrative,
      barColor:    "bg-amber-500",
      textColor:   "text-amber-400",
      subtext:     `Technical ${(techContrib * 100).toFixed(1)}% · Fundamental ${(fundContrib * 100).toFixed(1)}%`,
      llm_fields: null,
    },
  ];

  // Normalise bar widths: scale so the largest bar fills 100% of the bar track.
  // This makes small differences visible rather than showing near-empty bars.
  const maxAbs = Math.max(...areas.map(a => Math.abs(a.value)), 0.01);

  const formatContrib = (v: number) =>
    `${v >= 0 ? "+" : ""}${(v * 100).toFixed(1)}%`;

  return (
    <div className="border border-gray-700 rounded-xl p-4 bg-gray-900">
      <h3 className="text-sm font-semibold text-gray-400 uppercase tracking-wide mb-4">
        Confidence Breakdown
      </h3>

      <div className="space-y-5">
        {areas.map((area) => {
          const isPositive  = area.value >= 0;
          const barWidthPct = (Math.abs(area.value) / maxAbs) * 100;

          return (
            <div key={area.label}>
              {/* Label row */}
              <div className="flex items-center justify-between mb-1">
                <span className="text-xs font-medium text-gray-300">
                  {area.label}
                </span>
                <span className={`text-xs font-bold ${
                  isPositive ? "text-green-400" : "text-red-400"
                }`}>
                  {formatContrib(area.value)}
                </span>
              </div>

              {/* Score bar */}
              <div className="w-full h-2 bg-gray-800 rounded-full overflow-hidden mb-1">
                <div
                  className={`h-full rounded-full transition-all duration-700 ${
                    isPositive ? area.barColor : "bg-red-500"
                  }`}
                  style={{ width: `${barWidthPct}%` }}
                />
              </div>

              {/* Sub-component annotation (Stock only) */}
              {area.subtext && (
                <p className="text-xs text-gray-600 mb-2">{area.subtext}</p>
              )}

              {/* LLM narrative and detailed fields — shown if available */}
              {area.label === "Stock" ? (
                // Stock: use section-aware renderer for multi-line narrative
                renderStockNarrative(area.narrative)
              ) : (
                // Market and Sector: show both narrative AND detailed LLM fields
                <div className="space-y-2">
                  {/* Detailed LLM fields (market/sector analysis) */}
                  {Object.values(area.llm_fields).some(v => v) && (
                    <div className="text-xs text-gray-400 leading-relaxed
                                   bg-gray-800/50 rounded-lg px-3 py-2
                                   border-l-2 border-gray-600 mt-1 space-y-1">
                      {area.llm_fields.sentiment && (
                        <p><span className="text-gray-500">Sentiment:</span> {area.llm_fields.sentiment}</p>
                      )}
                      {area.llm_fields.rate_implications && (
                        <p><span className="text-gray-500">Rate Implications:</span> {area.llm_fields.rate_implications}</p>
                      )}
                      {area.llm_fields.volatility_expectation && (
                        <p><span className="text-gray-500">Volatility Expectation:</span> {area.llm_fields.volatility_expectation}</p>
                      )}
                      {area.llm_fields.outlook && (
                        <p><span className="text-gray-500">Outlook:</span> {area.llm_fields.outlook}</p>
                      )}
                      {area.llm_fields.rotation_momentum && (
                        <p><span className="text-gray-500">Rotation Momentum:</span> {area.llm_fields.rotation_momentum}</p>
                      )}
                      {area.llm_fields.economic_implications && (
                        <p><span className="text-gray-500">Economic Implications:</span> {area.llm_fields.economic_implications}</p>
                      )}
                      {area.llm_fields.momentum_assessment && (
                        <p><span className="text-gray-500">Momentum Assessment:</span> {area.llm_fields.momentum_assessment}</p>
                      )}
                    </div>
                  )}
                  {/* Narrative (shown alongside detailed fields if available) */}
                  {area.narrative && (
                    <p className="text-xs text-gray-300 leading-relaxed
                              bg-gray-800/50 rounded-lg px-3 py-2
                              border-l-2 border-gray-600 mt-1
                              whitespace-pre-wrap break-words">
                      {area.narrative}
                    </p>
                  )}
                  {/* No data fallback */}
                  {!Object.values(area.llm_fields).some(v => v) && !area.narrative && (
                    <p className="text-xs text-gray-700 italic mt-1">
                      No analysis available
                    </p>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Weight legend */}
      <div className="mt-4 pt-3 border-t border-gray-800 flex justify-between
                      text-xs text-gray-600">
        <span>Market 25%</span>
        <span>Sector 25%</span>
        <span>Stock 50%</span>
      </div>
    </div>
  );
}