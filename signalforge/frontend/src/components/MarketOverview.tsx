import React, { useState, useEffect } from 'react';

interface MarketOverviewProps {}

const MarketOverview: React.FC<MarketOverviewProps> = () => {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchData = async () => {
      setLoading(true);
      try {
        // In a real app, this would call the backend API
        // For now, we'll simulate with mock data
        const mockData = {
          vix: {
            vix: 18.5,
            vix_change: -2.3,
            fear_greed_score: 62
          },
          yield_curve: {
            ten_year_rate: 4.25,
            two_year_rate: 4.85,
            yield_curve_spread: -0.6
          }
        };
        setData(mockData);
        setLoading(false);
      } catch (err) {
        setError('Failed to load market data');
        setLoading(false);
      }
    };

    fetchData();
  }, []);

  if (loading) return <div className="text-center py-8">Loading...</div>;
  if (error) return <div className="text-center text-red-500 py-8">{error}</div>;

  return (
    <div className="bg-white rounded-lg shadow-md p-6">
      <h2 className="text-xl font-bold mb-4">Market Overview</h2>
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        {/* VIX Card */}
        <div className="bg-blue-50 p-4 rounded-lg">
          <h3 className="font-semibold mb-2">VIX (Fear & Greed Index)</h3>
          <div className="flex items-center justify-between">
            <div>
              <p className="text-2xl font-bold">{data?.vix.vix?.toFixed(2) || '--'}</p>
              <p className={data?.vix.vix_change! >= 0 ? 'text-red-600' : 'text-green-600'}>
                {data?.vix.vix_change?.toFixed(2) || '--'}%
              </p>
            </div>
            <div className="text-center">
              <p className="text-sm">Fear/Greed</p>
              <p className="font-bold text-lg">
                {data?.vix.fear_greed_score?.toFixed(0) || '--'}/100
              </p>
            </div>
          </div>
          <p className="mt-2 text-sm text-gray-600">
            {data?.vix.vix! > 25 ? 'High Fear' : data?.vix.vix! > 20 ? 'Moderate' : 'Low Fear'}
          </p>
        </div>

        {/* Yield Curve Card */}
        <div className="bg-green-50 p-4 rounded-lg">
          <h3 className="font-semibold mb-2">Yield Curve (10Y-2Y Spread)</h3>
          <div className="flex items-center justify-between">
            <div className="space-y-2">
              <p className="text-sm">10Y Treasury</p>
              <p className="font-bold text-lg">
                {data?.yield_curve.ten_year_rate?.toFixed(2) || '--'}%
              </p>
            </div>
            <div className="text-center space-y-2">
              <p className="text-sm">2Y Treasury</p>
              <p className="font-bold text-lg">
                {data?.yield_curve.two_year_rate?.toFixed(2) || '--'}%
              </p>
            </div>
            <div className="space-y-2">
              <p className="text-sm">Spread</p>
              <p className={
                `font-bold text-lg ${data?.yield_curve.yield_curve_spread! >= 0 ? 'text-green-600' : 'text-red-600'}`
              }>
                {data?.yield_curve.yield_curve_spread?.toFixed(2) || '--'}%
              </p>
            </div>
          </div>
          <p className="mt-2 text-sm text-gray-600">
            {data?.yield_curve.yield_curve_spread! > 0 ? 'Normal (Steepener)' :
             data?.yield_curve.yield_curve_spread! < -0.5 ? 'Inverted (Recession Signal)' : 'Flat'}
          </p>
        </div>
      </div>
    </div>
  );
};

export default MarketOverview;