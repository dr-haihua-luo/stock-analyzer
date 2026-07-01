import React from 'react';

interface SignalCardProps {
  signal: {
    ticker: string;
    signal: 'BUY' | 'HOLD' | 'SELL';
    confidence: number;
    composite_score: number;
    timestamp: string;
  };
}

const SignalCard: React.FC<SignalCardProps> = ({ signal }) => {
  const getSignalClass = (signalType: string) => {
    switch (signalType) {
      case 'BUY': return 'bg-green-50 text-green-800';
      case 'SELL': return 'bg-red-50 text-red-800';
      default: return 'bg-yellow-50 text-yellow-800';
    }
  };

  const getSignalColor = (signalType: string) => {
    switch (signalType) {
      case 'BUY': return 'text-green-600';
      case 'SELL': return 'text-red-600';
      default: return 'text-yellow-600';
    }
  };

  const getScoreDescription = (composite: number) => {
    if (composite >= 0.3) {
      return '> 0.3 = BUY';
    } else if (composite <= -0.3) {
      return '< -0.3 = SELL';
    } else {
      return '-0.3 to 0.3 = HOLD';
    }
  };

  const getCompositeColor = (composite: number) => {
    if (composite >= 0.3) return 'text-green-600';
    if (composite <= -0.3) return 'text-red-600';
    return 'text-yellow-600';
  };

  return (
    <div className="bg-white rounded-lg shadow-md p-6 mb-6">
      <div className="flex justify-between items-start">
        <div>
          <h2 className="text-2xl font-bold">{signal.ticker}</h2>
          <p className="text-sm text-gray-500">
            {new Date(signal.timestamp).toLocaleString()}
          </p>
          <div className="mt-3">
            <p className="text-sm text-gray-600 mb-1">Composite Score</p>
            <p className={`text-xl font-bold ${getCompositeColor(signal.composite_score)}`}>
              {signal.composite_score.toFixed(4)}
            </p>
            <p className="text-xs text-gray-500 mt-1">
              {getScoreDescription(signal.composite_score)}: {signal.signal}
            </p>
          </div>
        </div>
        <div className={`text-center ${getSignalClass(signal.signal)} p-3 rounded`}>
          <p className="font-semibold text-lg">{signal.signal}</p>
          <p className="text-sm">Confidence</p>
          <p className="text-3xl font-bold">{Math.round(signal.confidence * 100)}%</p>
        </div>
      </div>
    </div>
  );
};

export default SignalCard;