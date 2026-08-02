import React from 'react';

interface Props {
  narrative: string | null | undefined;
  signal: 'BUY' | 'HOLD' | 'SELL' | null | undefined;
  loading: boolean;
}

function parseSections(text: string): Record<string, string> {
  const labels = ["VERDICT", "REASONING", "WATCH"];
  const result: Record<string, string> = {};
  labels.forEach((label, i) => {
    const rest = labels.slice(i + 1).map((l) => `${l}:`);
    const alternation = rest.length ? rest.join("|") + "|" : "";
    const pattern = new RegExp(
      `${label}:\\s*(.+?)(?=${alternation}$)`, "s"
    );
    const match = text.match(pattern);
    if (match?.[1]) result[label] = match[1].trim();
  });
  return result;
}

const SIGNAL_STYLE: Record<string, { bg: string; border: string; text: string }> = {
  BUY:  { bg: "bg-green-950/40", border: "border-green-600", text: "text-green-400" },
  SELL: { bg: "bg-red-950/40",   border: "border-red-600",   text: "text-red-400"   },
  HOLD: { bg: "bg-gray-800/60",  border: "border-gray-600",  text: "text-gray-300"  },
};

export default function OverallAnalysisPanel({ narrative, signal, loading }: Props) {
  if (loading) {
    return (
      <div className="w-full border border-gray-700 rounded-xl p-5
                      bg-gray-900 mb-4 animate-pulse">
        <div className="h-5 w-72 bg-gray-800 rounded mb-4" />
        <div className="h-20 bg-gray-800 rounded-lg" />
      </div>
    );
  }

  if (!narrative) return null;

  const sections = parseSections(narrative);
  const verdictText = sections.VERDICT || "";
  const detectedSignal = (["BUY", "SELL", "HOLD"] as const).find(
    s => verdictText.toUpperCase().includes(s)
  ) ?? signal ?? "HOLD";

  const style = SIGNAL_STYLE[detectedSignal] ?? SIGNAL_STYLE.HOLD;

  return (
    <div className={`w-full rounded-xl p-5 mb-4 border-2 ${style.bg} ${style.border}`}>
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-3">
          <span className="text-2xl">🎯</span>
          <h2 className="text-lg font-bold text-gray-100">
            AI Overall Verdict
          </h2>
          <span className="text-xs font-medium text-gray-500
                           bg-gray-800/80 border border-gray-700
                           px-2 py-0.5 rounded">
            6-MONTH OUTLOOK
          </span>
        </div>
        <span className={`text-xl font-black uppercase ${style.text}`}>
          {detectedSignal}
        </span>
      </div>

      {sections.REASONING && (
        <p className="text-sm text-gray-200 leading-relaxed mb-2">
          {sections.REASONING}
        </p>
      )}

      {sections.WATCH && (
        <div className="flex items-start gap-2 mt-3 pt-3 border-t
                        border-gray-700/50">
          <span className="text-amber-400 text-sm">⚠</span>
          <p className="text-xs text-gray-400 leading-relaxed">
            <span className="font-semibold text-gray-300">Watch: </span>
            {sections.WATCH}
          </p>
        </div>
      )}

      {!sections.REASONING && !sections.WATCH && (
        <p className="text-sm text-gray-300 leading-relaxed
                      whitespace-pre-wrap">
          {narrative}
        </p>
      )}
    </div>
  );
}
