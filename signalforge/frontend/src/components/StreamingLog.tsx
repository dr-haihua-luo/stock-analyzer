import React, { useState, useEffect } from 'react';

interface StreamingLogProps {
  ticker: string;
}

const StreamingLog: React.FC<StreamingLogProps> = ({ ticker }) => {
  const [logs, setLogs] = useState<Array<{id: number; message: string; timestamp: string; type: 'info' | 'success' | 'warning' | 'error'}>>([]);
  const [isConnected, setIsConnected] = useState(false);

  useEffect(() => {
    // Simulate WebSocket connection for demo purposes
    const simulateConnection = () => {
      setIsConnected(true);
      addLog('Connecting to analysis stream...', 'info');

      setTimeout(() => {
        addLog('Connected to real-time analysis stream', 'success');

        // Simulate periodic updates
        const interval = setInterval(() => {
          const timestamps = [
            new Date(Date.now() - Math.random() * 300000), // Last 5 minutes
            new Date(Date.now() - Math.random() * 300000),
            new Date(Date.now() - Math.random() * 300000)
          ];

          const messages = [
            `Market data updated for ${ticker}`,
            `Sector rotation signals detected`,
            `Technical indicators recalculated`,
            `News sentiment analyzed`
          ];

          const types = ['info', 'success', 'warning', 'info'];

          const randomIndex = Math.floor(Math.random() * messages.length);
          addLog(
            messages[randomIndex],
            types[randomIndex],
            timestamps[randomIndex].toISOString()
          );
        }, 5000 + Math.random() * 5000); // Random interval between 5-10 seconds

        return () => clearInterval(interval);
      }, 2000);
    };

    simulateConnection();

    return () => {
      // Cleanup on unmount
      setIsConnected(false);
    };
  }, [ticker]);

  const addLog = (message: string, type: 'info' | 'success' | 'warning' | 'error' = 'info', timestamp: string = new Date().toISOString()) => {
    setLogs(prev => [
      ...prev.slice(0, 99), // Keep only last 100 logs
      { id: Date.now(), message, timestamp, type }
    ]);
  };

  if (logs.length === 0) {
    return <div className="text-center py-4 text-gray-500">Waiting for analysis stream...</div>;
  }

  return (
    <div className="bg-white rounded-lg shadow-md p-6">
      <div className="flex justify-between items-start mb-4">
        <h2 className="text-xl font-bold">Analysis Stream</h2>
        <div className="flex items-center space-x-2">
          <div className={`w-2 h-2 rounded-full ${isConnected ? 'bg-green-500' : 'bg-red-500'}`} />
          <span className="text-sm text-gray-600">{isConnected ? 'LIVE' : 'OFFLINE'}</span>
        </div>
      </div>

      <div className="h-96 overflow-y-auto space-y-2">
        {logs.map(log => (
          <div key={log.id} className={`p-3 rounded-lg border-l-4
            ${log.type === 'info' ? 'border-blue-500 bg-blue-50' : ''}
            ${log.type === 'success' ? 'border-green-500 bg-green-50' : ''}
            ${log.type === 'warning' ? 'border-yellow-500 bg-yellow-50' : ''}
            ${log.type === 'error' ? 'border-red-500 bg-red-50' : ''}
          `}>
            <div className="flex justify-between items-start mb-1">
              <span className="font-medium">{log.message}</span>
              <span className="text-xs text-gray-400">
                {new Date(log.timestamp).toLocaleTimeString()}
              </span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};

export default StreamingLog;