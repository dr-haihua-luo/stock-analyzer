import React, { useState, useEffect } from 'react';

interface StockChartProps {
  ticker: string;
  height?: number;
}

const StockChart: React.FC<StockChartProps> = ({ ticker, height = 300 }) => {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchData = async () => {
      setLoading(true);
      try {
        // In a real app, this would call the backend API or a financial data API
        // For now, we'll simulate with mock chart data
        const mockData = generateMockData(ticker);
        setData(mockData);
        setLoading(false);
      } catch (err) {
        setError('Failed to load chart data');
        setLoading(false);
      }
    };

    fetchData();
  }, [ticker]);

  // Generate mock data for demonstration
  const generateMockData = (symbol: string) => {
    const data = [];
    let price = 100 + Math.random() * 50; // Random starting price between 100-150

    // Generate 30 days of data
    for (let i = 29; i >= 0; i--) {
      const date = new Date();
      date.setDate(date.getDate() - i);

      // Random walk for price
      const change = (Math.random() - 0.5) * 0.02; // -1% to +1% daily change
      price = price * (1 + change);

      const high = price * (1 + Math.random() * 0.01); // 0-1% above close
      const low = price * (1 - Math.random() * 0.01);  // 0-1% below close
      const open = price * (1 + (Math.random() - 0.5) * 0.005); // -0.25% to +0.25% from close
      const volume = Math.floor(1000000 + Math.random() * 9000000); // 1M-10M volume

      data.push({
        date: date.toISOString().split('T')[0],
        open: Number(open.toFixed(2)),
        high: Number(high.toFixed(2)),
        low: Number(low.toFixed(2)),
        close: Number(price.toFixed(2)),
        volume: volume
      });
    }

    return data;
  };

  if (loading) return <div className="text-center py-8">Loading chart...</div>;
  if (error) return <div className="text-center text-red-500 py-8">{error}</div>;
  if (!data || data.length === 0) return <div className="text-center py-8">No data available</div>;

  // Simple line chart using SVG (in a real app, you'd use Recharts or similar)
  const width = 600;
  const padding = 40;

  // Calculate scales
  const xScale = (index: number) =>
    padding + (index / (data.length - 1)) * (width - 2 * padding);

  const prices = data.map(d => d.close);
  const minPrice = Math.min(...prices);
  const maxPrice = Math.max(...prices);
  const priceRange = maxPrice - minPrice;
  const yScale = (price: number) =>
    (height - padding) - ((price - minPrice) / priceRange) * (height - 2 * padding);

  return (
    <div className="bg-white rounded-lg shadow-md p-6">
      <h2 className="text-xl font-bold mb-4">
        {ticker} Stock Chart
      </h2>
      <div className="relative h-[{height}px]">
        {/* Axes */}
        <svg className="absolute inset-0" width={width} height={height}>
          {/* X-axis (dates) */}
          <line
            x1={padding}
            y1={height - padding}
            x2={width - padding}
            y2={height - padding}
            stroke="gray-300"
            strokeWidth={1}
          />

          {/* Y-axis (price) */}
          <line
            x1={padding}
            y1={padding}
            x2={padding}
            y2={height - padding}
            stroke="gray-300"
            strokeWidth={1}
          />

          {/* Grid lines (horizontal) */}
          {[0, 0.25, 0.5, 0.75, 1].map((pct, i) => (
            <line
              key={`h-grid-${i}`}
              x1={padding}
              y1={yScale(minPrice + priceRange * pct)}
              x2={width - padding}
              y2={yScale(minPrice + priceRange * pct)}
              stroke="gray-200"
              strokeWidth={1}
              strokeDasharray="2,2"
            />
          ))}

          {/* Price line */}
          <path
            d={data.map((point, index) =>
              `${index === 0 ? 'M' : 'L'}${xScale(index)},${yScale(point.close)}`
            ).join(' ')}
            stroke="blue-500"
            strokeWidth={2}
            fill="none"
          />

          {/* Points */}
          {data.map((point, index) => (
            <circle
              key={`point-${index}`}
              cx={xScale(index)}
              cy={yScale(point.close)}
              r={3}
              fill="blue-500"
            />
          ))}
        </svg>

        {/* X-axis labels (dates) */}
        <div className="absolute bottom-0 left-0 right-0 flex justify-between px-4 pt-2">
          {data.map((point, index) =>
            index % Math.max(1, Math.floor(data.length / 5)) === 0 ? (
              <div key={'date-' + index} className="text-xs text-gray-500">
                {new Date(point.date).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}
              </div>
            ) : null
          )}
        </div>

        {/* Y-axis labels (prices) */}
        <div className="absolute top-0 left-0 flex flex-col h-full items-start p-2">
          {[0, 0.25, 0.5, 0.75, 1].map((pct, i) => (
            <div
              key={`price-label-${i}`}
              className="flex items-center text-xs text-gray-500"
              style={{ top: `${pct * 100}%` }}
            >
              <span className="w-4 h-0.5 bg-gray-300" />
              <span className="ml-1">
                {(minPrice + priceRange * pct).toFixed(2)}
              </span>
            </div>
          ))}
        </div>
      </div>

      <div className="mt-4 text-sm text-gray-500 flex justify-between">
        <span>Period: {data[0].date} to {data[data.length - 1].date}</span>
        <span>
          {((data[data.length - 1].close - data[0].close) / data[0].close * 100).toFixed(2)}%
          {(data[data.length - 1].close - data[0].close) >= 0 ? '▲' : '▼'}
        </span>
      </div>
    </div>
  );
};

export default StockChart;