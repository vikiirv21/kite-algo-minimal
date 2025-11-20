import { useEffect, useState } from 'react';

interface LastUpdatedProps {
  timestamp?: number | null;
  className?: string;
}

/**
 * Display "Last updated" timestamp that counts up from the given timestamp.
 * 
 * Usage:
 *   const { dataUpdatedAt } = useQuery(...);
 *   <LastUpdated timestamp={dataUpdatedAt} />
 */
export function LastUpdated({ timestamp, className = '' }: LastUpdatedProps) {
  const [now, setNow] = useState(Date.now());
  
  // Update every second to show live "X seconds ago"
  useEffect(() => {
    const interval = setInterval(() => {
      setNow(Date.now());
    }, 1000);
    
    return () => clearInterval(interval);
  }, []);
  
  if (!timestamp || timestamp === 0) {
    return <span className={`text-xs text-text-secondary ${className}`}>Never updated</span>;
  }
  
  const secondsAgo = Math.floor((now - timestamp) / 1000);
  
  let timeStr: string;
  if (secondsAgo < 60) {
    timeStr = `${secondsAgo}s ago`;
  } else if (secondsAgo < 3600) {
    const minutes = Math.floor(secondsAgo / 60);
    timeStr = `${minutes}m ago`;
  } else {
    const hours = Math.floor(secondsAgo / 3600);
    timeStr = `${hours}h ago`;
  }
  
  // Show exact time on hover
  const exactTime = new Date(timestamp).toLocaleTimeString('en-IN', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    timeZone: 'Asia/Kolkata',
  });
  
  return (
    <span 
      className={`text-xs text-text-secondary ${className}`}
      title={`Last updated: ${exactTime} IST`}
    >
      ⟳ {timeStr}
    </span>
  );
}
