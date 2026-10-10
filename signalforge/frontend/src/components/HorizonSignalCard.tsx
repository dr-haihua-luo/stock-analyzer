import React from 'react';
import { HorizonSignal } from '../types/signal';

interface HorizonSignalCardProps {
  horizonSignal: HorizonSignal;
  showWeights?: boolean;
}

const HorizonSignalCard: React.FC<HorizonSignalCardProps> = ({ horizonSignal, showWeights }) => {
  const {
    horizon_label,
    signal,
    confidence,
    composite_score,
    status,
    disclaimer,
    earnings_warning,
    relative_valuation,
    weights,
  } = horizonSignal;

  const isExperimental = status === 'experimental';
  const isUnavailable = status === 'unavailable' || signal === null;

  // Color helpers
  const getSignalClass = (signalType: string | null) => {
    switch (signalType) {
      case 'BUY':   return 'bg-green-50 text-green-800 border-green-200';
      case 'SELL':  return 'bg-red-50 text-red-800 border-red-200';
      default:      return 'bg-yellow-50 text-yellow-800 border-yellow-200';
    }
  };

  const getScoreColor = (composite: number) => {
    if (composite >= 0.3) return 'text-green-600';
    if (composite <= -0.3) return 'text-red-600';
    return 'text-yellow-600';
  };

  return (
    <div
      className={`border rounded-lg p-4 mb-4 transition-shadow ${
        isExperimental ? 'border-purple-300 bg-purple-50/30' : 'border-gray-200 bg-white'
      } ${isExperimental ? 'shadow-purple' : 'shadow-md'}`}
    >
      {/* Header — horizon label + experimental/unavailable badges */}
      <div className="flex justify-between items-center mb-3">
        <h3 className="text-lg font-semibold text-gray-800">{horizon_label}</h3>
        <div className="flex gap-2">
          {isExperimental && (
            <span className="px-2 py-1 text-xs font-semibold bg-purple-100 text-purple-800 rounded">
              EXPERIMENTAL
            </span>
          )}
          {status === 'unavailable' && (
            <span className="px-2 py-1 text-xs font-semibold bg-gray-100 text-gray-600 rounded">
              Unavailable
            </span>
          )}
        </div>
      </div>

      {isUnavailable ? (
        /* Unavailable state */
        <div className="py-4 text-center text-gray-500">
          <p>No signal available{status === 'unavailable' && horizonSignal.reason ? `: ${horizonSignal.reason}` : ''}</p>
        </div>
      ) : (
        /* Signal display */
        <div className="flex justify-between items-start">
          <div className="flex-1">
            {composite_score !== null && (
              <div className="mb-2">
                <p className="text-xs text-gray-600 mb-1">Composite Score</p>
                <p className={`text-xl font-bold ${getScoreColor(composite_score)}`}>
                  {composite_score.toFixed(4)}
                </p>
              </div>
            )}

            {/* Earnings warning (swing horizon) */}
            {earnings_warning && (
              <div className="mt-2 p-2 bg-amber-50 border border-amber-200 rounded text-xs text-amber-800">
                ⚠️ {earnings_warning}
              </div>
            )}

            {/* Relative valuation (position horizon) */}
            {relative_valuation && (
              <div className="mt-2 p-2 bg-blue-50 border border-blue-200 rounded text-xs text-blue-800">
                <span className="font-medium">Valuation:</span>{' '}
                P/E {relative_valuation.pe_ratio.toFixed(1)} vs sector avg {relative_valuation.sector_benchmark.toFixed(1)}
                {' '}({relative_valuation.pct_vs_benchmark > 0 ? '+' : ''}{relative_valuation.pct_vs_benchmark.toFixed(1)}% — {relative_valuation.label})
              </div>
            )}

            {/* Weights legend */}
            {showWeights && weights && Object.keys(weights).length > 0 && (
              <div className="mt-3 pt-2 border-t border-gray-100">
                <p className="text-xs text-gray-500 mb-1">Weights:</p>
                <div className="flex flex-wrap gap-2">
                  {Object.entries(weights).map(([key, val]) => (
                    <span key={key} className="text-xs text-gray-600">
                      {key}: {Math.round(val * 100)}%
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* Signal + confidence box */}
          <div
            className={`text-center p-3 rounded border ${getSignalClass(signal)}`}
          >
            <p className="font-semibold text-lg">{signal}</p>
            {confidence !== null && (
              <>
                <p className="text-sm">Confidence</p>
                <p className="text-3xl font-bold">{Math.round(confidence * 100)}%</p>
              </>
            )}
          </div>
        </div>
      )}

      {/* Experimental disclaimer */}
      {isExperimental && disclaimer && (
        <div className="mt-3 pt-2 border-t border-purple-200 text-xs text-purple-800">
          <p className="font-medium mb-1">Disclaimer:</p>
          <p className="italic">{disclaimer}</p>
        </div>
      )}
    </div>
  );
};

export default HorizonSignalCard;