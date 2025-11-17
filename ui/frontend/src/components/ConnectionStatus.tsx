import { useQueryClient } from '@tanstack/react-query';
import { useEffect, useState, useRef } from 'react';

export function ConnectionStatus() {
  const queryClient = useQueryClient();
  const [isConnected, setIsConnected] = useState(true);
  const lastSuccessfulFetchRef = useRef<number>(0);
  
  useEffect(() => {
    // Initialize on mount
    lastSuccessfulFetchRef.current = Date.now();
    
    // Check query states to determine connection status
    const checkConnection = () => {
      const queries = queryClient.getQueryCache().getAll();
      const recentQueries = queries.filter(q => 
        q.state.dataUpdatedAt > Date.now() - 10000 // Last 10 seconds
      );
      
      if (recentQueries.length > 0) {
        setIsConnected(true);
        lastSuccessfulFetchRef.current = Date.now();
      } else if (Date.now() - lastSuccessfulFetchRef.current > 15000) {
        // No successful fetch in 15 seconds
        setIsConnected(false);
      }
    };
    
    const interval = setInterval(checkConnection, 2000);
    return () => clearInterval(interval);
  }, [queryClient]);
  
  return (
    <div className="flex items-center gap-2">
      <div className={`w-2 h-2 rounded-full ${isConnected ? 'bg-positive animate-pulse-slow' : 'bg-negative'}`} />
      <span className="text-xs text-text-secondary">
        {isConnected ? 'Connected' : 'Disconnected'}
      </span>
    </div>
  );
}
