/**
 * Dashboard V2 - Main Dashboard Controller
 * Requires: api.js, tabs.js
 */

// Global state for topbar polling
let topbarIntervals = {};

/**
 * Update server time display
 */
async function updateServerTime() {
    try {
        const data = await API.get('/api/system/time');
        const serverTimeEl = document.getElementById('server-time');
        
        if (serverTimeEl && data.utc) {
            const date = new Date(data.utc);
            const istTime = date.toLocaleTimeString('en-IN', {
                timeZone: 'Asia/Kolkata',
                hour12: false
            });
            serverTimeEl.textContent = istTime;
        }
    } catch (error) {
        console.error('Error updating server time:', error);
        const serverTimeEl = document.getElementById('server-time');
        if (serverTimeEl) {
            serverTimeEl.textContent = '--:--:--';
        }
    }
}

/**
 * Update market status
 */
async function updateMarketStatus() {
    try {
        const data = await API.get('/api/meta');
        const statusEl = document.getElementById('market-status');
        
        if (statusEl) {
            const isOpen = data.market_open || false;
            const status = data.market_status || (isOpen ? 'OPEN' : 'CLOSED');
            statusEl.textContent = status;
            statusEl.className = `badge badge-${isOpen ? 'success' : 'closed'}`;
        }
    } catch (error) {
        console.error('Error updating market status:', error);
        const statusEl = document.getElementById('market-status');
        if (statusEl) {
            statusEl.textContent = 'UNKNOWN';
            statusEl.className = 'badge badge-neutral';
        }
    }
}

/**
 * Update mode indicator (PAPER/LIVE)
 */
async function updateModeIndicator() {
    try {
        const data = await API.get('/api/config/summary');
        const modeEl = document.getElementById('mode-badge');
        
        if (modeEl && data.mode) {
            const mode = data.mode.toUpperCase();
            modeEl.textContent = mode;
            modeEl.className = `badge badge-mode badge-${mode === 'PAPER' ? 'paper' : 'live'}`;
        }
    } catch (error) {
        console.error('Error updating mode:', error);
        const modeEl = document.getElementById('mode-badge');
        if (modeEl) {
            modeEl.textContent = 'UNKNOWN';
            modeEl.className = 'badge badge-mode badge-neutral';
        }
    }
}

/**
 * Initialize topbar polling (independent of page changes)
 */
function initializeTopbarPolling() {
    // Clear existing intervals
    Object.values(topbarIntervals).forEach(id => clearInterval(id));
    topbarIntervals = {};

    // Update immediately
    updateServerTime();
    updateMarketStatus();
    updateModeIndicator();

    // Set up intervals
    topbarIntervals.serverTime = setInterval(updateServerTime, 1000);
    topbarIntervals.marketStatus = setInterval(updateMarketStatus, 5000);
    topbarIntervals.modeIndicator = setInterval(updateModeIndicator, 15000);

    console.log('✓ Topbar polling initialized');
}

/**
 * Global loadPage function for sidebar clicks
 * @param {string} pageName - Name of page to load
 */
function loadPage(pageName) {
    TabManager.loadPage(pageName);
}

/**
 * Utility: Format currency
 */
function formatCurrency(value) {
    return new Intl.NumberFormat('en-IN', {
        style: 'currency',
        currency: 'INR',
        minimumFractionDigits: 2,
        maximumFractionDigits: 2
    }).format(value);
}

/**
 * Utility: Format percentage
 */
function formatPercentage(value, decimals = 2) {
    return `${(value * 100).toFixed(decimals)}%`;
}

/**
 * Utility: Format timestamp to IST
 */
function formatTimestamp(timestamp) {
    const date = new Date(timestamp);
    return date.toLocaleString('en-IN', {
        timeZone: 'Asia/Kolkata',
        hour12: false
    });
}

/**
 * Utility: Format relative time
 */
function formatRelativeTime(timestamp) {
    const date = new Date(timestamp);
    const now = new Date();
    const seconds = Math.floor((now - date) / 1000);
    
    if (seconds < 60) return `${seconds}s ago`;
    if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
    if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
    return `${Math.floor(seconds / 86400)}d ago`;
}

/**
 * Initialize dashboard on page load
 */
document.addEventListener('DOMContentLoaded', function() {
    console.log('Dashboard V2 - Dark Theme Initializing...');

    // Initialize topbar polling
    initializeTopbarPolling();

    // Load default page
    loadPage('overview');

    console.log('✓ Dashboard V2 initialized');
});

/**
 * HTMX Event Handlers
 */
document.body.addEventListener('htmx:configRequest', function(evt) {
    // Add custom headers if needed
    // evt.detail.headers['X-Custom-Header'] = 'value';
});

document.body.addEventListener('htmx:beforeRequest', function(evt) {
    // Show loading state for non-topbar elements
    const target = evt.detail.target;
    if (target && !target.closest('.topbar-item')) {
        target.classList.add('loading');
    }
});

document.body.addEventListener('htmx:afterRequest', function(evt) {
    // Remove loading state
    const target = evt.detail.target;
    if (target) {
        target.classList.remove('loading');
    }

    // Handle errors
    if (evt.detail.failed) {
        console.error('HTMX request failed:', evt.detail);
        if (target) {
            target.innerHTML = '<div class="error">Failed to load data</div>';
        }
    }
});

document.body.addEventListener('htmx:responseError', function(evt) {
    console.error('HTMX response error:', evt.detail);
});

/**
 * Keyboard shortcuts
 */
document.addEventListener('keydown', function(evt) {
    // Alt + 1-9 to switch tabs
    if (evt.altKey && evt.key >= '1' && evt.key <= '9') {
        const pages = [
            'overview', 'portfolio', 'engines', 'strategies',
            'orders', 'signals', 'pnl_analytics', 'logs', 'trade_flow'
        ];
        const index = parseInt(evt.key) - 1;
        if (index < pages.length) {
            evt.preventDefault();
            loadPage(pages[index]);
        }
    }

    // Alt + R to refresh current page
    if (evt.altKey && evt.key === 'r') {
        evt.preventDefault();
        loadPage(TabManager.getCurrentPage());
        }
});

// Export utilities to global scope
window.dashboardV2 = {
    loadPage,
    formatCurrency,
    formatPercentage,
    formatTimestamp,
    formatRelativeTime,
    updateServerTime,
    updateMarketStatus,
    updateModeIndicator,
};

// Expose API and TabManager globally (already done in their modules)
console.log('✓ Dashboard V2 modules loaded');
