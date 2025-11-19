import { Card, CardSkeleton } from '../../components/Card';
import { useRecentOrders, useTradingStatus } from '../../hooks/useApi';
import { formatTimestamp, formatCurrency, getPnlClass, getPnlPrefix } from '../../utils/format';

export function TradingPage() {
  const { data: ordersData, isLoading } = useRecentOrders(50);
  const { data: tradingStatus } = useTradingStatus();
  
  // Debug flag - set to true to see raw API data
  const DEBUG_MODE = import.meta.env.DEV || false; // Only in development
  
  const orders = ordersData?.orders || [];
  const activeOrders = orders.filter(o => 
    ['OPEN', 'PENDING', 'TRIGGER_PENDING'].includes(o.status?.toUpperCase())
  );
  const completedOrders = orders.filter(o => 
    ['FILLED', 'COMPLETE', 'CLOSED'].includes(o.status?.toUpperCase())
  );
  
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-3xl font-bold">Trading</h1>
        
        {/* Trading Status Card */}
        {tradingStatus && (
          <div className="flex items-center gap-6 bg-surface-light px-6 py-3 rounded-lg border border-border">
            <div className="flex items-center gap-2">
              <span className={`w-3 h-3 rounded-full ${tradingStatus.connected ? 'bg-positive animate-pulse' : 'bg-negative'}`}></span>
              <span className="text-sm text-text-secondary">
                {tradingStatus.connected ? 'Connected' : 'Disconnected'}
              </span>
            </div>
            <div className="border-l border-border pl-6">
              <span className="text-sm text-text-secondary mr-2">Mode:</span>
              <span className={`font-bold uppercase ${tradingStatus.mode === 'live' ? 'text-negative' : 'text-warning'}`}>
                {tradingStatus.mode}
              </span>
            </div>
            <div className="border-l border-border pl-6">
              <span className="text-sm text-text-secondary mr-2">Phase:</span>
              <span className="font-semibold">{tradingStatus.phase}</span>
            </div>
            <div className="border-l border-border pl-6">
              <span className="text-sm text-text-secondary mr-2">IST:</span>
              <span className="font-mono font-semibold">{tradingStatus.ist_time}</span>
            </div>
          </div>
        )}
      </div>
      
      {/* DEBUG: Raw API Data (Development Only) */}
      {DEBUG_MODE && ordersData && (
        <Card title="🔍 DEBUG: Orders API Response">
          <div className="text-xs font-mono space-y-2">
            <div className="text-text-secondary mb-2">
              Raw API data from <code className="bg-border px-1 rounded">/api/orders/recent?limit=50</code>
            </div>
            <div className="text-text-secondary text-[10px] mb-2">
              Total orders: {orders.length}<br/>
              Active orders: {activeOrders.length}<br/>
              Completed orders: {completedOrders.length}
            </div>
            {orders.length > 0 && (
              <>
                <div className="text-text-secondary mb-1">First order:</div>
                <pre className="bg-surface-light p-3 rounded overflow-x-auto text-[10px] leading-tight">
                  {JSON.stringify(orders[0], null, 2)}
                </pre>
              </>
            )}
            {orders.length === 0 && (
              <div className="text-warning">⚠️ No orders in response. Check if engine has placed any orders today.</div>
            )}
          </div>
        </Card>
      )}
      
      {/* Active Orders */}
      <Card title="Active Orders">
        {isLoading ? (
          <div className="space-y-2">
            <div className="h-4 bg-border rounded animate-pulse"></div>
            <div className="h-4 bg-border rounded animate-pulse"></div>
          </div>
        ) : activeOrders.length === 0 ? (
          <div className="text-center text-text-secondary py-8">No active orders</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-border text-left">
                  <th className="pb-2 text-text-secondary font-medium">Time</th>
                  <th className="pb-2 text-text-secondary font-medium">Symbol</th>
                  <th className="pb-2 text-text-secondary font-medium">Side</th>
                  <th className="pb-2 text-text-secondary font-medium text-right">Quantity</th>
                  <th className="pb-2 text-text-secondary font-medium text-right">Price</th>
                  <th className="pb-2 text-text-secondary font-medium">Status</th>
                  <th className="pb-2 text-text-secondary font-medium">Order ID</th>
                </tr>
              </thead>
              <tbody>
                {activeOrders.map((order, idx) => (
                  <tr key={idx} className="border-b border-border/50 hover:bg-surface-light">
                    <td className="py-3 text-sm">{formatTimestamp(order.timestamp)}</td>
                    <td className="py-3 font-medium">{order.symbol}</td>
                    <td className="py-3">
                      <span className={`
                        px-2 py-1 rounded text-xs font-semibold
                        ${order.side?.toUpperCase() === 'BUY' ? 'bg-positive/20 text-positive' : 'bg-negative/20 text-negative'}
                      `}>
                        {order.side}
                      </span>
                    </td>
                    <td className="py-3 text-right font-mono">{order.quantity}</td>
                    <td className="py-3 text-right font-mono">{formatCurrency(order.price)}</td>
                    <td className="py-3">
                      <span className="px-2 py-1 rounded text-xs bg-warning/20 text-warning">
                        {order.status}
                      </span>
                    </td>
                    <td className="py-3 text-sm text-text-secondary font-mono">{order.order_id || '--'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
      
      {/* Recent/Completed Orders */}
      <Card title="Recent Orders">
        {isLoading ? (
          <CardSkeleton />
        ) : completedOrders.length === 0 ? (
          <div className="text-center text-text-secondary py-8">No completed orders</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-border text-left">
                  <th className="pb-2 text-text-secondary font-medium">Time</th>
                  <th className="pb-2 text-text-secondary font-medium">Symbol</th>
                  <th className="pb-2 text-text-secondary font-medium">Side</th>
                  <th className="pb-2 text-text-secondary font-medium text-right">Quantity</th>
                  <th className="pb-2 text-text-secondary font-medium text-right">Price</th>
                  <th className="pb-2 text-text-secondary font-medium">Status</th>
                  <th className="pb-2 text-text-secondary font-medium text-right">P&L</th>
                </tr>
              </thead>
              <tbody>
                {completedOrders.map((order, idx) => (
                  <tr key={idx} className="border-b border-border/50 hover:bg-surface-light">
                    <td className="py-3 text-sm">{formatTimestamp(order.timestamp)}</td>
                    <td className="py-3 font-medium">{order.symbol}</td>
                    <td className="py-3">
                      <span className={`
                        px-2 py-1 rounded text-xs font-semibold
                        ${order.side?.toUpperCase() === 'BUY' ? 'bg-positive/20 text-positive' : 'bg-negative/20 text-negative'}
                      `}>
                        {order.side}
                      </span>
                    </td>
                    <td className="py-3 text-right font-mono">{order.quantity}</td>
                    <td className="py-3 text-right font-mono">{formatCurrency(order.price)}</td>
                    <td className="py-3">
                      <span className="px-2 py-1 rounded text-xs bg-positive/20 text-positive">
                        {order.status}
                      </span>
                    </td>
                    <td className={`py-3 text-right font-mono ${getPnlClass(order.pnl)}`}>
                      {order.pnl !== undefined ? (
                        `${getPnlPrefix(order.pnl)}${formatCurrency(order.pnl)}`
                      ) : '--'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}
