// Dashboard V2 - JavaScript for page navigation and HTMX updates

// Current active page
let currentPage = 'overview';

// Polling intervals storage
let pollingIntervals = {};

/**
 * Load a specific page into the content area
 */
function loadPage(pageName) {
    // Clear any existing polling intervals
    clearAllPollingIntervals();
    
    // Update sidebar active state
    document.querySelectorAll('.sidebar-item').forEach(item => {
        item.classList.remove('active');
        if (item.dataset.page === pageName) {
            item.classList.add('active');
        }
    });
    
    // Load the page content
    currentPage = pageName;
    const contentArea = document.getElementById('page-content');
    
    if (contentArea) {
        // Show loading state
        contentArea.innerHTML = '<div class="loading">Loading...</div>';
        
        // Fetch the page content
        fetch(`/api/pages/${pageName}`)
            .then(response => {
                if (!response.ok) {
                    // If API endpoint doesn't exist, load static template
                    return fetch(`/pages/${pageName}`);
                }
                return response;
            })
            .then(response => response.text())
            .then(html => {
                contentArea.innerHTML = html;
                // Re-initialize HTMX for the new content
                if (typeof htmx !== 'undefined') {
                    htmx.process(contentArea);
                }
            })
            .catch(error => {
                console.error('Error loading page:', error);
                contentArea.innerHTML = `<div class="error">Failed to load page: ${pageName}</div>`;
            });
    }
}

/**
 * Clear all polling intervals
 */
function clearAllPollingIntervals() {
    Object.keys(pollingIntervals).forEach(key => {
        clearInterval(pollingIntervals[key]);
    });
    pollingIntervals = {};
}

/**
 * Update server time display
 */
function updateServerTime() {
    fetch('/api/system/time')
        .then(response => response.json())
        .then(data => {
            const serverTimeEl = document.getElementById('server-time');
            if (serverTimeEl && data.utc) {
                const date = new Date(data.utc);
                const istTime = date.toLocaleTimeString('en-IN', {
                    timeZone: 'Asia/Kolkata',
                    hour12: false
                });
                serverTimeEl.textContent = istTime;
            }
        })
        .catch(error => console.error('Error fetching server time:', error));
}

/**
 * Update market status
 */
function updateMarketStatus() {
    fetch('/api/meta')
        .then(response => response.json())
        .then(data => {
            const statusEl = document.getElementById('market-status');
            if (statusEl) {
                const isOpen = data.market_open || false;
                statusEl.textContent = isOpen ? 'OPEN' : 'CLOSED';
                statusEl.className = `badge badge-${isOpen ? 'success' : 'closed'}`;
            }
        })
        .catch(error => console.error('Error fetching market status:', error));
}

/**
 * Update mode indicator (PAPER/LIVE)
 */
function updateModeIndicator() {
    fetch('/api/config/summary')
        .then(response => response.json())
        .then(data => {
            const modeEl = document.getElementById('mode-badge');
            if (modeEl && data.mode) {
                const mode = data.mode.toUpperCase();
                modeEl.textContent = mode;
                modeEl.className = `badge badge-${mode === 'PAPER' ? 'paper' : 'live'}`;
            }
        })
        .catch(error => console.error('Error fetching mode:', error));
}

/**
 * Initialize dashboard on page load
 */
document.addEventListener('DOMContentLoaded', function() {
    // Load the default page (overview)
    loadPage('overview');
    
    // Start polling for topbar updates
    updateServerTime();
    updateMarketStatus();
    updateModeIndicator();
    
    // Set up polling intervals
    pollingIntervals.serverTime = setInterval(updateServerTime, 1000);
    pollingIntervals.marketStatus = setInterval(updateMarketStatus, 5000);
    pollingIntervals.modeIndicator = setInterval(updateModeIndicator, 15000);
});

/**
 * Handle HTMX events
 */
document.body.addEventListener('htmx:configRequest', function(evt) {
    // Add any custom headers or configuration here
    console.log('HTMX request:', evt.detail.path);
});

document.body.addEventListener('htmx:beforeRequest', function(evt) {
    // Show loading indicator if needed
    const target = evt.detail.target;
    if (target && !target.classList.contains('topbar-item')) {
        // Don't show loading for topbar items
        const originalContent = target.innerHTML;
        target.setAttribute('data-original-content', originalContent);
    }
});

document.body.addEventListener('htmx:afterRequest', function(evt) {
    // Handle errors
    if (evt.detail.failed) {
        console.error('HTMX request failed:', evt.detail);
        const target = evt.detail.target;
        if (target) {
            target.innerHTML = '<div class="error">Failed to load data. Retrying...</div>';
        }
    }
});

document.body.addEventListener('htmx:responseError', function(evt) {
    console.error('HTMX response error:', evt.detail);
});

/**
 * Utility function to format currency
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
 * Utility function to format percentage
 */
function formatPercentage(value) {
    return `${(value * 100).toFixed(2)}%`;
}

/**
 * Utility function to format timestamp
 */
function formatTimestamp(timestamp) {
    const date = new Date(timestamp);
    return date.toLocaleString('en-IN', {
        timeZone: 'Asia/Kolkata',
        hour12: false
    });
}

// Export functions for use in templates
window.dashboardV2 = {
    loadPage,
    formatCurrency,
    formatPercentage,
    formatTimestamp,
    updateServerTime,
    updateMarketStatus,
    updateModeIndicator
};
