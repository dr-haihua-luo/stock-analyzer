import React from 'react';

interface SignalCardProps {
  signal: {
    ticker: string;
    signal: 'BUY' | 'HOLD' | 'SELL';
    confidence: number;
    timestamp: string;
  };
}

const SignalCard: React.FC<SignalCardProps> = ({ signal }) => {
  const getSignalClass = (signal: string) => {
    switch (signal) {
      case 'BUY': return 'bg-green-50 text-green-800';
      case 'SELL': return 'bg-red-50 text-red-800';
      default: return 'bg-yellow-50 text-yellow-800';
    }
  };

  const getSignalColor = (signal: string) => {
    switch (signal) {
      case 'BUY': return 'text-green-600';
      case 'SELL': return 'text-red-600';
      default: return 'text-yellow-600';
    }
  };

  return (
    <div className="bg-white rounded-lg shadow-md p-6 mb-6">
      <div className="flex justify-between items-start">
        <div>
          <h2 className="text-2xl font-bold">{signal.ticker}</h2>
          <p className="text-sm text-gray-500">
            {new Date(signal.timestamp).toLocaleString()}
          </p>
        </div>
        <div className={`text-center ${getSignalClass(signal.signal)} p-3 rounded`}>
          <p className="font-semibold">{signal.signal}</p>
          <p className="text-sm">Confidence</p>
          <p className="text-2xl font-bold">{Math.round(signal.confidence * 100)}%</p>
        </div>
      </div>
    </div>
  );
};

export default SignalCard;