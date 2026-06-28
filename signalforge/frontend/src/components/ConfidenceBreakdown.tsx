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
}

export default function ConfidenceBreakdown({
  breakdown,
  market_narrative,
  sector_narrative,
  stock_narrative,
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
    },
    {
      label:       "Sector",
      value:       breakdown.sector_contribution ?? 0,
      narrative:   sector_narrative,
      barColor:    "bg-purple-500",
      textColor:   "text-purple-400",
      subtext:     null,
    },
    {
      label:       "Stock",
      value:       stockContrib,
      narrative:   stock_narrative,
      barColor:    "bg-amber-500",
      textColor:   "text-amber-400",
      subtext:     `Technical ${(techContrib * 100).toFixed(1)}% · Fundamental ${(fundContrib * 100).toFixed(1)}%`,
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

              {/* LLM narrative — shown if available */}
              {area.narrative ? (
                <p className="text-xs text-gray-400 leading-relaxed
                               bg-gray-800/50 rounded-lg px-3 py-2
                               border-l-2 border-gray-600 mt-1">
                  {area.narrative}
                </p>
              ) : (
                <p className="text-xs text-gray-700 italic mt-1">
                  No analysis available
                </p>
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