import React from 'react';

interface Props {
  longTrend: 'up' | 'down' | null | undefined;
  mediumTrend: 'up' | 'down' | null | undefined;
  shortTrend: 'up' | 'down' | null | undefined;
  loading: boolean;
}

function Badge({ label, trend }: { label: string; trend: 'up' | 'down' | null | undefined }) {
  if (!trend) {
    return (
      <div className="flex-1 bg-gray-800 rounded-lg px-3 py-2 text-center
                      border border-gray-700">
        <p className="text-xs text-gray-600 mb-1">{label}</p>
        <p className="text-sm text-gray-600">N/A</p>
      </div>
    );
  }
  const isUp = trend === 'up';
  return (
    <div className={`flex-1 rounded-lg px-3 py-2 text-center border ${
      isUp ? 'bg-green-900/20 border-green-700' : 'bg-red-900/20 border-red-700'
    }`}>
      <p className="text-xs text-gray-500 mb-1">{label}</p>
      <p className={`text-sm font-bold flex items-center justify-center gap-1 ${
        isUp ? 'text-green-400' : 'text-red-400'
      }`}>
        {isUp ? '▲' : '▼'} {trend.toUpperCase()}
      </p>
    </div>
  );
}

export default function MATrendBadges({
  longTrend, mediumTrend, shortTrend, loading,
}: Props) {
  if (loading) {
    return (
      <div className="flex gap-2 mt-3">
        {[...Array(3)].map((_, i) => (
          <div key={i} className="flex-1 h-14 bg-gray-800 rounded-lg animate-pulse" />
        ))}
      </div>
    );
  }

  // Highlight alignment: all three same direction = strong signal
  const aligned = longTrend && mediumTrend && shortTrend &&
    longTrend === mediumTrend && mediumTrend === shortTrend;

  return (
    <div>
      <div className="flex gap-2 mt-3">
        <Badge label="Long (12mo)"   trend={longTrend} />
        <Badge label="Medium (2mo)"  trend={mediumTrend} />
        <Badge label="Short (2wk)"   trend={shortTrend} />
      </div>
      {aligned && (
        <p className="text-xs text-center mt-2 text-gray-500">
          All timeframes aligned {longTrend === 'up' ? '📈' : '📉'}
        </p>
      )}
    </div>
  );
}
