/**
 * Arthayukti Dashboard - API Client
 * Centralized API calls with error handling and retry logic
 */

const ApiClient = (() => {
    // Configuration
    const config = {
        baseURL: '',
        maxRetries: 2,
        retryDelay: 1000,
        timeout: 10000,
    };

    /**
     * Sleep utility for retry delays
     */
    const sleep = (ms) => new Promise(resolve => setTimeout(resolve, ms));

    /**
     * Core fetch with retry and timeout
     */
    async function fetchWithRetry(endpoint, options = {}) {
        const url = `${config.baseURL}${endpoint}`;
        let lastError = null;

        for (let attempt = 1; attempt <= config.maxRetries; attempt++) {
            try {
                const controller = new AbortController();
                const timeoutId = setTimeout(() => controller.abort(), config.timeout);

                const response = await fetch(url, {
                    ...options,
                    signal: controller.signal,
                });

                clearTimeout(timeoutId);

                if (!response.ok) {
                    throw new Error(`HTTP ${response.status}: ${endpoint}`);
                }

                return await response.json();
            } catch (error) {
                lastError = error;
                
                if (error.name === 'AbortError') {
                    console.warn(`API timeout: ${endpoint}`);
                    break;
                }

                if (attempt < config.maxRetries) {
                    const delay = config.retryDelay * Math.pow(2, attempt - 1);
                    await sleep(delay);
                } else {
                    console.error(`API failed: ${endpoint}`, error);
                }
            }
        }

        throw lastError || new Error(`API call failed: ${endpoint}`);
    }

    /**
     * GET request
     */
    async function get(endpoint, params = {}) {
        const queryString = new URLSearchParams(params).toString();
        const url = queryString ? `${endpoint}?${queryString}` : endpoint;
        return await fetchWithRetry(url, { method: 'GET' });
    }

    /**
     * POST request
     */
    async function post(endpoint, data = {}) {
        return await fetchWithRetry(endpoint, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data),
        });
    }

    // ========== System & Meta ==========

    async function getSystemTime() {
        return await get('/api/system/time');
    }

    async function getMeta() {
        return await get('/api/meta');
    }

    async function getHealth() {
        return await get('/api/health');
    }

    async function getConfigSummary() {
        return await get('/api/config/summary');
    }

    // ========== Engines ==========

    async function getEnginesStatus() {
        return await get('/api/engines/status');
    }

    async function getState() {
        return await get('/api/state');
    }

    async function getAuthStatus() {
        return await get('/api/auth/status');
    }

    // ========== Portfolio & Positions ==========

    async function getPortfolioSummary() {
        return await get('/api/portfolio/summary');
    }

    async function getPositionsOpen() {
        return await get('/api/positions/open');
    }

    async function getPositionsNormalized() {
        return await get('/api/positions_normalized');
    }

    async function getRiskSummary() {
        return await get('/api/risk/summary');
    }

    async function getMargins() {
        return await get('/api/margins');
    }

    // ========== Orders & Trades ==========

    async function getOrders(params = {}) {
        return await get('/api/orders', params);
    }

    async function getOrdersRecent(limit = 50) {
        return await get('/api/orders/recent', { limit });
    }

    async function getSummaryToday() {
        return await get('/api/summary/today');
    }

    // ========== Signals & Strategies ==========

    async function getSignals(params = {}) {
        return await get('/api/signals', params);
    }

    async function getSignalsRecent(limit = 50) {
        return await get('/api/signals/recent', { limit });
    }

    async function getStatsStrategies(days = 1) {
        return await get('/api/stats/strategies', { days });
    }

    async function getStrategyPerformance() {
        return await get('/api/strategy_performance');
    }

    async function getQualitySummary() {
        return await get('/api/quality/summary');
    }

    // ========== Logs & Monitoring ==========

    async function getLogs(params = {}) {
        return await get('/api/logs', params);
    }

    async function getLogsRecent(params = {}) {
        const defaults = { limit: 200 };
        return await get('/api/logs/recent', { ...defaults, ...params });
    }

    async function getTradeFlow() {
        return await get('/api/trade_flow');
    }

    async function getMonitorTradeFlow() {
        return await get('/api/monitor/trade_flow');
    }

    // ========== Analytics & Performance ==========

    async function getStatsEquity(days = 1) {
        return await get('/api/stats/equity', { days });
    }

    async function getAnalyticsSummary() {
        return await get('/api/analytics/summary');
    }

    async function getAnalyticsEquityCurve(filters = {}) {
        return await get('/api/analytics/equity_curve', filters);
    }

    // ========== Market Data ==========

    async function getQuotes(keys = null) {
        const params = keys ? { keys } : {};
        return await get('/api/quotes', params);
    }

    async function getScannerUniverse() {
        return await get('/api/scanner/universe');
    }

    async function getMarketDataWindow(symbol, timeframe = '5m', limit = 50) {
        return await get('/api/market_data/window', { symbol, timeframe, limit });
    }

    // ========== Backtests ==========

    async function getBacktests() {
        return await get('/api/backtests');
    }

    async function getBacktestSummary(runId) {
        return await get(`/api/backtests/${runId}/summary`);
    }

    async function getBacktestEquityCurve(runId) {
        return await get(`/api/backtests/${runId}/equity_curve`);
    }

    // ========== Actions ==========

    async function postResync() {
        return await post('/api/resync');
    }

    // Public API
    return {
        // System & Meta
        getSystemTime,
        getMeta,
        getHealth,
        getConfigSummary,
        
        // Engines
        getEnginesStatus,
        getState,
        getAuthStatus,
        
        // Portfolio & Positions
        getPortfolioSummary,
        getPositionsOpen,
        getPositionsNormalized,
        getRiskSummary,
        getMargins,
        
        // Orders & Trades
        getOrders,
        getOrdersRecent,
        getSummaryToday,
        
        // Signals & Strategies
        getSignals,
        getSignalsRecent,
        getStatsStrategies,
        getStrategyPerformance,
        getQualitySummary,
        
        // Logs & Monitoring
        getLogs,
        getLogsRecent,
        getTradeFlow,
        getMonitorTradeFlow,
        
        // Analytics & Performance
        getStatsEquity,
        getAnalyticsSummary,
        getAnalyticsEquityCurve,
        
        // Market Data
        getQuotes,
        getScannerUniverse,
        getMarketDataWindow,
        
        // Backtests
        getBacktests,
        getBacktestSummary,
        getBacktestEquityCurve,
        
        // Actions
        postResync,
    };
})();
