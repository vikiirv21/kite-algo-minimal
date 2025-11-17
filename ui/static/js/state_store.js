/**
 * Arthayukti Dashboard - State Store
 * Global state management and polling lifecycle
 */

const StateStore = (() => {
    // Global state
    const state = {
        // Active tab
        activeTab: 'overview',
        
        // System & Meta
        serverTime: null,
        meta: null,
        health: null,
        config: null,
        mode: 'IDLE', // Derived from engines
        
        // Engines
        engines: [],
        authStatus: null,
        
        // Portfolio
        portfolio: null,
        positionsOpen: [],
        orders: [],
        todaySummary: null,
        
        // Signals & Strategies
        signals: [],
        strategies: [],
        
        // Logs & Monitoring
        logs: [],
        tradeFlow: null,
        
        // Analytics
        equityCurve: [],
        analyticsSummary: null,
        
        // Market Data
        quotes: {},
    };

    // Active polling intervals
    const intervals = {};

    // Subscribers for state changes
    const subscribers = [];

    /**
     * Get current state (read-only)
     */
    function getState() {
        return { ...state };
    }

    /**
     * Update state and notify subscribers
     */
    function setState(key, value) {
        state[key] = value;
        notifySubscribers(key, value);
    }

    /**
     * Update multiple state keys at once
     */
    function setStateMultiple(updates) {
        Object.entries(updates).forEach(([key, value]) => {
            state[key] = value;
        });
        notifySubscribers();
    }

    /**
     * Subscribe to state changes
     */
    function subscribe(callback) {
        subscribers.push(callback);
        return () => {
            const index = subscribers.indexOf(callback);
            if (index > -1) subscribers.splice(index, 1);
        };
    }

    /**
     * Notify all subscribers
     */
    function notifySubscribers(key = null, value = null) {
        subscribers.forEach(callback => {
            try {
                callback(key, value, state);
            } catch (error) {
                console.error('Subscriber error:', error);
            }
        });
    }

    /**
     * Detect mode from engines
     */
    function detectMode(engines) {
        if (!engines || !Array.isArray(engines)) return 'IDLE';
        
        const hasLive = engines.some(e => e.running && e.mode === 'live');
        const hasPaper = engines.some(e => e.running && e.mode === 'paper');
        
        if (hasLive) return 'LIVE';
        if (hasPaper) return 'PAPER';
        return 'IDLE';
    }

    /**
     * Start polling with interval
     */
    function startInterval(key, intervalMs, fetchFn) {
        if (intervals[key]) {
            clearInterval(intervals[key]);
        }
        
        // Fetch immediately
        fetchFn().catch(err => console.error(`Failed to fetch ${key}:`, err));
        
        // Then poll at interval
        intervals[key] = setInterval(() => {
            fetchFn().catch(err => console.error(`Failed to fetch ${key}:`, err));
        }, intervalMs);
    }

    /**
     * Stop polling for a specific key
     */
    function stopInterval(key) {
        if (intervals[key]) {
            clearInterval(intervals[key]);
            delete intervals[key];
        }
    }

    /**
     * Stop all polling
     */
    function stopAllIntervals() {
        Object.keys(intervals).forEach(key => stopInterval(key));
    }

    /**
     * Initialize common polling (always active)
     */
    function initCommonPolling() {
        // Server time - 1 second
        startInterval('serverTime', 1000, async () => {
            const data = await ApiClient.getSystemTime();
            setState('serverTime', data.utc);
        });

        // Meta - 5 seconds
        startInterval('meta', 5000, async () => {
            const data = await ApiClient.getMeta();
            setState('meta', data);
        });

        // Engines - 10 seconds (also updates mode)
        startInterval('engines', 10000, async () => {
            const data = await ApiClient.getEnginesStatus();
            const engines = data.engines || [];
            setState('engines', engines);
            
            // Derive and update mode
            const mode = detectMode(engines);
            setState('mode', mode);
        });
    }

    /**
     * Initialize tab-specific polling
     */
    function initTabPolling(tabName) {
        // Stop previous tab polling (except common)
        const commonKeys = ['serverTime', 'meta', 'engines'];
        Object.keys(intervals).forEach(key => {
            if (!commonKeys.includes(key)) {
                stopInterval(key);
            }
        });

        // Start new tab polling
        switch (tabName) {
            case 'overview':
                startOverviewPolling();
                break;
            case 'engines':
                startEnginesPolling();
                break;
            case 'portfolio':
                startPortfolioPolling();
                break;
            case 'signals':
                startSignalsPolling();
                break;
            case 'analytics':
                startAnalyticsPolling();
                break;
            case 'system':
                startSystemPolling();
                break;
        }
    }

    /**
     * Overview tab polling
     */
    function startOverviewPolling() {
        // Portfolio summary - 3 seconds
        startInterval('portfolio', 3000, async () => {
            const data = await ApiClient.getPortfolioSummary();
            setState('portfolio', data);
        });

        // Recent signals - 10 seconds
        startInterval('signals', 10000, async () => {
            const data = await ApiClient.getSignalsRecent(10);
            setState('signals', data);
        });

        // Today summary - 10 seconds
        startInterval('todaySummary', 10000, async () => {
            const data = await ApiClient.getSummaryToday();
            setState('todaySummary', data);
        });
    }

    /**
     * Engines & Logs tab polling
     */
    function startEnginesPolling() {
        // Logs - 3 seconds
        startInterval('logs', 3000, async () => {
            const data = await ApiClient.getLogsRecent({ limit: 200 });
            setState('logs', data.logs || data.entries || []);
        });
    }

    /**
     * Portfolio tab polling (LIVE REFRESH)
     */
    function startPortfolioPolling() {
        // Portfolio summary - 3 seconds
        startInterval('portfolio', 3000, async () => {
            const data = await ApiClient.getPortfolioSummary();
            setState('portfolio', data);
        });

        // Open positions - 3 seconds
        startInterval('positionsOpen', 3000, async () => {
            const data = await ApiClient.getPositionsOpen();
            setState('positionsOpen', data);
        });

        // Orders - 3 seconds
        startInterval('orders', 3000, async () => {
            const data = await ApiClient.getOrdersRecent(50);
            setState('orders', data.orders || data);
        });

        // Today summary - 5 seconds
        startInterval('todaySummary', 5000, async () => {
            const data = await ApiClient.getSummaryToday();
            setState('todaySummary', data);
        });
    }

    /**
     * Signals & Strategies tab polling
     */
    function startSignalsPolling() {
        // Recent signals - 5 seconds
        startInterval('signals', 5000, async () => {
            const data = await ApiClient.getSignalsRecent(50);
            setState('signals', data);
        });

        // Strategy stats - 10 seconds
        startInterval('strategies', 10000, async () => {
            const data = await ApiClient.getStatsStrategies(1);
            setState('strategies', data);
        });
    }

    /**
     * Analytics tab polling
     */
    function startAnalyticsPolling() {
        // Equity curve - 10 seconds
        startInterval('equityCurve', 10000, async () => {
            const data = await ApiClient.getStatsEquity(1);
            setState('equityCurve', data);
        });

        // Analytics summary - 10 seconds
        startInterval('analyticsSummary', 10000, async () => {
            const data = await ApiClient.getAnalyticsSummary();
            setState('analyticsSummary', data);
        });
    }

    /**
     * System tab polling
     */
    function startSystemPolling() {
        // Config - 30 seconds
        startInterval('config', 30000, async () => {
            const data = await ApiClient.getConfigSummary();
            setState('config', data);
        });

        // Health - 30 seconds
        startInterval('health', 30000, async () => {
            const data = await ApiClient.getHealth();
            setState('health', data);
        });
    }

    /**
     * Initialize state store
     */
    async function init() {
        console.log('Initializing state store...');
        
        // Load initial data
        try {
            const [meta, engines, portfolio] = await Promise.all([
                ApiClient.getMeta(),
                ApiClient.getEnginesStatus(),
                ApiClient.getPortfolioSummary(),
            ]);

            setState('meta', meta);
            setState('engines', engines.engines || []);
            setState('portfolio', portfolio);
            setState('mode', detectMode(engines.engines || []));
        } catch (error) {
            console.error('Failed to load initial data:', error);
        }

        // Start common polling
        initCommonPolling();
        
        // Start polling for default tab
        initTabPolling(state.activeTab);
        
        console.log('State store initialized');
    }

    /**
     * Switch to a different tab
     */
    function switchTab(tabName) {
        if (state.activeTab === tabName) return;
        
        console.log(`Switching tab: ${state.activeTab} -> ${tabName}`);
        state.activeTab = tabName;
        initTabPolling(tabName);
        notifySubscribers('activeTab', tabName);
    }

    // Public API
    return {
        getState,
        setState,
        setStateMultiple,
        subscribe,
        init,
        switchTab,
        stopAllIntervals,
        detectMode,
    };
})();
