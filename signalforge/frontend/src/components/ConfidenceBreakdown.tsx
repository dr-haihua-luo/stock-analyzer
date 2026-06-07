import React from 'react';

interface ConfidenceBreakdownProps {
  breakdown: {
    market_factor: number;
    sector_factor: number;
    stock_factor: number;
    total_confidence: number;
  };
}

const ConfidenceBreakdown: React.FC<ConfidenceBreakdownProps> = ({ breakdown }) => {
  const getFactorColor = (factor: number) => {
    if (factor >= 0.8) return 'bg-green-100 text-green-800';
    if (factor >= 0.6) return 'bg-blue-100 text-blue-800';
    if (factor >= 0.4) return 'bg-yellow-100 text-yellow-800';
    return 'bg-red-100 text-red-800';
  };

  return (
    <div className="bg-white rounded-lg shadow-md p-6 mb-6">
      <h2 className="text-xl font-bold mb-4">Confidence Breakdown</h2>
      <p className="mb-4 text-sm text-gray-600">
        Factors contributing to the final signal confidence
      </p>

      <div className="space-y-4">
        <div className={`p-4 rounded-lg ${getFactorColor(breakdown.market_factor)}`}>
          <h3 className="font-semibold mb-2">Market Analysis</h3>
          <p className="text-sm text-gray-600">
            {Math.round(breakdown.market_factor * 100)}%
          </p>
          <p className="text-xs text-gray-500">
            Based on VIX, yield curve, and overall market conditions
          </p>
        </div>

        <div className={`p-4 rounded-lg ${getFactorColor(breakdown.sector_factor)}`}>
          <h3 className="font-semibold mb-2">Sector Analysis</h3>
          <p className="text-sm text-gray-600">
            {Math.round(breakdown.sector_factor * 100)}%
          </p>
          <p className="text-xs text-gray-500">
            Based on sector rotation and relative strength
          </p>
        </div>

        <div className={`p-4 rounded-lg ${getFactorColor(breakdown.stock_factor)}`}>
          <h3 className="font-semibold mb-2">Stock Analysis</h3>
          <p className="text-sm text-gray-600">
            {Math.round(breakdown.stock_factor * 100)}%
          </p>
          <p className="text-xs text-gray-500">
            Based on technical indicators and fundamentals
          </p>
        </div>
      </div>

      <div className="mt-6 p-4 bg-indigo-50 rounded-lg">
        <h3 className="font-semibold mb-2">Overall Confidence</h3>
        <p className="text-3xl font-bold text-indigo-600">
          {Math.round(breakdown.total_confidence * 100)}%
        </p>
        <p className="text-sm text-gray-600">
          Weighted average of all analysis factors
        </p>
      </div>
    </div>
  );
};

export default ConfidenceBreakdown;