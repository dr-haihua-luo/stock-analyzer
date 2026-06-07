import React, { useState, useEffect } from 'react';

interface SectorHeatmapProps {}

const SectorHeatmap: React.FC<SectorHeatmapProps> = () => {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Sector ETFs and their names
  const sectorEtfs = {
    XLK: "Technology",
    XLF: "Financial",
    XLE: "Energy",
    XLV: "Healthcare",
    XLI: "Industrial",
    XLY: "Consumer Discretionary",
    XLP: "Consumer Staples",
    XLB: "Materials",
    XLU: "Utilities",
    XLRE: "Real Estate",
    XLC: "Communication Services"
  };

  useEffect(() => {
    const fetchData = async () => {
      setLoading(true);
      try {
        // In a real app, this would call the backend API
        // For now, we'll simulate with mock data
        const mockData = {};
        Object.keys(sectorEtfs).forEach((symbol) => {
          // Generate random performance data for demonstration
          const change = (Math.random() - 0.5) * 4; // -2% to +2%
          mockData[symbol] = {
            name: sectorEtfs[symbol],
            "1m_return": change.toFixed(2),
            "3m_return": ((Math.random() - 0.5) * 8).toFixed(2), // -4% to +4%
            "ytd_return": ((Math.random() - 0.5) * 15).toFixed(2) // -7.5% to +7.5%
          };
        });
        setData(mockData);
        setLoading(false);
      } catch (err) {
        setError('Failed to load sector data');
        setLoading(false);
      }
    };

    fetchData();
  }, []);

  if (loading) return <div className="text-center py-8">Loading...</div>;
  if (error) return <div className="text-center text-red-500 py-8">{error}</div>;

  // Convert data to array for sorting
  const sectorArray = Object.entries(data || {}).map(([symbol, info]) => ({
    symbol,
    ...info
  }));

  // Sort by 1-month return (descending)
  const sortedSectors = sectorArray.sort(
    (a, b) => parseFloat(b["1m_return"]) - parseFloat(a["1m_return"])
  );

  return (
    <div className="bg-white rounded-lg shadow-md p-6">
      <h2 className="text-xl font-bold mb-4">Sector Rotation Heatmap</h2>
      <p className="mb-4 text-sm text-gray-600">
        1-Month Performance Ranking (ETF Proxies)
      </p>

      <div className="overflow-x-auto">
        <table className="min-w-full divide-y divide-gray-200">
          <thead className="bg-gray-50">
            <tr>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Rank
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Sector
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                1M Return
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                3M Return
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                YTD Return
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-200">
            {sortedSectors.map((sector, index) => {
              const return1M = parseFloat(sector["1m_return"]);
              const getReturnClass = (returnVal: number) => {
                if (returnVal > 2) return "bg-green-50 text-green-800";
                if (returnVal > 0) return "bg-green-50 text-green-600";
                if (returnVal > -2) return "bg-yellow-50 text-yellow-600";
                return "bg-red-50 text-red-600";
              };

              return (
                <tr key={sector.symbol} className="hover:bg-gray-50">
                  <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900">
                    {index + 1}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-700">
                    {sector.name} ({sector.symbol})
                  </td>
                  <td className={`px-6 py-4 whitespace-nowrap text-sm ${getReturnClass(return1M)}`}>
                    {sector["1m_return"]}%
                  </td>
                  <td className={`px-6 py-4 whitespace-nowrap text-sm ${getReturnClass(parseFloat(sector["3m_return"]))}`}>
                    {sector["3m_return"]}%
                  </td>
                  <td className={`px-6 py-4 whitespace-nowrap text-sm ${getReturnClass(parseFloat(sector["ytd_return"]))}`}>
                    {sector["ytd_return"]}%
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Rotation Signals */}
      <div className="mt-6 p-4 bg-blue-50 rounded-lg">
        <h3 className="font-semibold mb-2">Rotation Signals</h3>
        <p className="text-sm text-gray-600">
          Strongest: {sortedSectors[0]?.name || '--'} ({sortedSectors[0]?.symbol || '--'}) |
          Weakest: {sortedSectors[sortedSectors.length - 1]?.name || '--'} ({sortedSectors[sortedSectors.length - 1]?.symbol || '--'})
        </p>
      </div>
    </div>
  );
};

export default SectorHeatmap;