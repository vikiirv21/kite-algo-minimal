import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Sidebar } from './components/Sidebar';
import { TopBar } from './components/TopBar';
import { OverviewPage } from './features/overview/OverviewPage';
import { TradingPage } from './features/trading/TradingPage';
import { PortfolioPage } from './features/portfolio/PortfolioPage';
import { SignalsPage } from './features/signals/SignalsPage';
import { AnalyticsPage } from './features/analytics/AnalyticsPage';
import { SystemPage } from './features/system/SystemPage';
import { LogsPage } from './features/logs/LogsPage';
import { RiskPage } from './features/risk/RiskPage';

// Create a client
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      retry: 1,
      staleTime: 1000,
    },
  },
});

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <div className="h-full flex">
          <Sidebar />
          <div className="flex-1 flex flex-col overflow-hidden">
            <TopBar />
            <main className="flex-1 overflow-y-auto bg-background p-6">
              <Routes>
                <Route path="/" element={<OverviewPage />} />
                <Route path="/trading" element={<TradingPage />} />
                <Route path="/portfolio" element={<PortfolioPage />} />
                <Route path="/signals" element={<SignalsPage />} />
                <Route path="/analytics" element={<AnalyticsPage />} />
                <Route path="/risk" element={<RiskPage />} />
                <Route path="/system" element={<SystemPage />} />
                <Route path="/logs" element={<LogsPage />} />
              </Routes>
            </main>
          </div>
        </div>
      </BrowserRouter>
    </QueryClientProvider>
  );
}

export default App;
