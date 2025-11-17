/**
 * Dashboard V2 - Tab Management Module
 * Handles page navigation, polling intervals, and cleanup
 */

const TabManager = (() => {
    // State
    let currentPage = 'overview';
    let pollingIntervals = {};
    let activeTimers = new Set();

    /**
     * Clear all polling intervals and timers
     */
    function clearAllPolling() {
        // Clear all intervals
        Object.values(pollingIntervals).forEach(intervalId => {
            clearInterval(intervalId);
        });
        pollingIntervals = {};

        // Clear all timers
        activeTimers.forEach(timerId => {
            clearTimeout(timerId);
        });
        activeTimers.clear();

        console.log('✓ Cleared all polling intervals');
    }

    /**
     * Register a polling interval
     * @param {string} key - Unique identifier for this interval
     * @param {Function} callback - Function to call repeatedly
     * @param {number} intervalMs - Interval in milliseconds
     */
    function registerPolling(key, callback, intervalMs) {
        // Clear existing interval with same key
        if (pollingIntervals[key]) {
            clearInterval(pollingIntervals[key]);
        }

        // Execute immediately
        callback().catch(err => {
            console.error(`Polling callback error (${key}):`, err);
        });

        // Set up interval
        pollingIntervals[key] = setInterval(async () => {
            try {
                await callback();
            } catch (err) {
                console.error(`Polling callback error (${key}):`, err);
            }
        }, intervalMs);

        console.log(`✓ Registered polling: ${key} (${intervalMs}ms)`);
    }

    /**
     * Register a delayed timer
     * @param {Function} callback - Function to call
     * @param {number} delayMs - Delay in milliseconds
     */
    function registerTimer(callback, delayMs) {
        const timerId = setTimeout(callback, delayMs);
        activeTimers.add(timerId);
        return timerId;
    }

    /**
     * Update sidebar active state
     * @param {string} pageName - Name of the active page
     */
    function updateSidebarState(pageName) {
        document.querySelectorAll('.sidebar-item').forEach(item => {
            item.classList.remove('active');
            if (item.dataset.page === pageName) {
                item.classList.add('active');
            }
        });
    }

    /**
     * Load a page into the content area
     * @param {string} pageName - Name of the page to load
     */
    async function loadPage(pageName) {
        // Clear existing polling
        clearAllPolling();

        // Update state
        currentPage = pageName;
        updateSidebarState(pageName);

        // Get content area
        const contentArea = document.getElementById('page-content');
        if (!contentArea) {
            console.error('Content area not found');
            return;
        }

        // Show loading state
        contentArea.innerHTML = '<div class="loading">Loading page...</div>';

        try {
            // Fetch page content
            const response = await fetch(`/pages/${pageName}`);
            
            if (!response.ok) {
                throw new Error(`Failed to load page: ${response.status}`);
            }

            const html = await response.text();
            contentArea.innerHTML = html;

            // Re-initialize HTMX if available
            if (typeof htmx !== 'undefined') {
                htmx.process(contentArea);
            }

            // Initialize page-specific polling
            initializePagePolling(pageName);

            console.log(`✓ Loaded page: ${pageName}`);
        } catch (error) {
            console.error('Error loading page:', error);
            contentArea.innerHTML = `
                <div class="error">
                    Failed to load page: ${pageName}
                    <br><small>${error.message}</small>
                </div>
            `;
        }
    }

    /**
     * Initialize page-specific polling based on the current page
     * @param {string} pageName - Name of the current page
     */
    function initializePagePolling(pageName) {
        // Each page can have its own polling logic
        switch (pageName) {
            case 'overview':
                // Fast polling for overview data
                registerPolling('portfolio', () => API.get('/api/portfolio/summary'), 5000);
                registerPolling('today_summary', () => API.get('/api/summary/today'), 5000);
                registerPolling('engines', () => API.get('/api/engines/status'), 3000);
                break;

            case 'portfolio':
                registerPolling('portfolio_detail', () => API.get('/api/portfolio/summary'), 5000);
                registerPolling('positions', () => API.get('/api/positions/open'), 3000);
                break;

            case 'orders':
                registerPolling('orders', () => API.get('/api/orders/recent', { limit: 50 }), 3000);
                break;

            case 'signals':
                registerPolling('signals', () => API.get('/api/signals/recent', { limit: 50 }), 3000);
                break;

            case 'logs':
                registerPolling('logs', () => API.get('/api/logs/recent', { limit: 150, kind: 'engine' }), 2000);
                break;

            case 'trade_flow':
                registerPolling('trade_flow', () => API.get('/api/monitor/trade_flow'), 5000);
                break;

            case 'engines':
                registerPolling('engine_status', () => API.get('/api/engines/status'), 3000);
                break;

            case 'strategies':
                registerPolling('strategy_stats', () => API.get('/api/stats/strategies'), 10000);
                break;

            case 'system_health':
                registerPolling('health', () => API.get('/api/health'), 15000);
                break;

            default:
                console.log(`No specific polling for page: ${pageName}`);
        }
    }

    /**
     * Get current page name
     */
    function getCurrentPage() {
        return currentPage;
    }

    // Public API
    return {
        loadPage,
        clearAllPolling,
        registerPolling,
        registerTimer,
        getCurrentPage,
    };
})();

// Export for ES6 modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = TabManager;
}

// Make available globally
window.TabManager = TabManager;
