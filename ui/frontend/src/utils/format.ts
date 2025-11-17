// Format timestamp to readable string
export function formatTimestamp(ts: string | null | undefined): string {
  if (!ts) return '--';
  
  try {
    const date = new Date(ts);
    if (isNaN(date.getTime())) return '--';
    
    return new Intl.DateTimeFormat('en-IN', {
      timeZone: 'Asia/Kolkata',
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: false,
    }).format(date);
  } catch {
    return '--';
  }
}

// Format timestamp to time only
export function formatTime(ts: string | null | undefined): string {
  if (!ts) return '--:--:--';
  
  try {
    const date = new Date(ts);
    if (isNaN(date.getTime())) return '--:--:--';
    
    return new Intl.DateTimeFormat('en-IN', {
      timeZone: 'Asia/Kolkata',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: false,
    }).format(date);
  } catch {
    return '--:--:--';
  }
}

// Format number as currency
export function formatCurrency(value: number | null | undefined): string {
  if (value === null || value === undefined) return '₹--';
  
  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value);
}

// Format number with fixed decimals
export function formatNumber(value: number | null | undefined, decimals = 2): string {
  if (value === null || value === undefined) return '--';
  
  return value.toFixed(decimals);
}

// Format percentage
export function formatPercent(value: number | null | undefined): string {
  if (value === null || value === undefined) return '--';
  
  return `${value.toFixed(2)}%`;
}

// Get P&L color class
export function getPnlClass(value: number | null | undefined): string {
  if (value === null || value === undefined || value === 0) return '';
  return value > 0 ? 'pnl-positive' : 'pnl-negative';
}

// Get P&L sign prefix
export function getPnlPrefix(value: number | null | undefined): string {
  if (value === null || value === undefined || value === 0) return '';
  return value > 0 ? '+' : '';
}
