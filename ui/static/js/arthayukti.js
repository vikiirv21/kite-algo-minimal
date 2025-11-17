/**
 * Arthayukti HFT Dashboard - Main Controller
 * Handles all UI updates and API polling
 */

// Configuration
const CONFIG = {
    POLL_INTERVALS: {
        serverTime: 1000,        // 1 second
        meta: 5000,              // 5 seconds
        engines: 10000,          // 10 seconds
        portfolio: 10000,        // 10 seconds
        logs: 5000,              // 5 seconds
        signals: 10000,          // 10 seconds
        health: 30000,           // 30 seconds
    },
    LOG_LIMIT: 200,
};

// State
let intervals = {};
let currentLogFilter = '';

// ===== Utility Functions =====

async function apiGet(endpoint) {
    try {
        const response = await fetch(endpoint);
        if (!response.ok) {
            throw new Error(`API error: ${response.status}`);
        }
        return await response.json();
    } catch (error) {
        console.error(`Failed to fetch ${endpoint}:`, error);
        return null;
    }
}

function formatCurrency(value) {
    if (value === null || value === undefined) return '—';
    const num = parseFloat(value);
    if (isNaN(num)) return '—';
    return `₹${num.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function formatPercentage(value) {
    if (value === null || value === undefined) return '—';
    const num = parseFloat(value);
    if (isNaN(num)) return '—';
    return `${(num * 100).toFixed(2)}%`;
}

function formatTime(isoString) {
    if (!isoString) return '—';
    try {
        const date = new Date(isoString);
        return date.toLocaleTimeString('en-IN', { hour12: false });
    } catch {
        return '—';
    }
}

function formatDateTime(isoString) {
    if (!isoString) return '—';
    try {
        const date = new Date(isoString);
        return date.toLocaleString('en-IN', { 
            hour12: false,
            year: 'numeric',
            month: 'short',
            day: 'numeric',
            hour: '2-digit',
            minute: '2-digit',
        });
    } catch {
        return '—';
    }
}

function getValueClass(value) {
    if (value === null || value === undefined) return '';
    const num = parseFloat(value);
    if (isNaN(num)) return '';
    return num >= 0 ? 'positive' : 'negative';
}

// ===== Server Time =====

async function updateServerTime() {
    const data = await apiGet('/api/system/time');
    if (!data || !data.utc) return;
    
    try {
        const date = new Date(data.utc);
        const istTime = date.toLocaleTimeString('en-IN', {
            timeZone: 'Asia/Kolkata',
            hour12: false
        });
        document.getElementById('server-time').textContent = istTime;
    } catch (error) {
        console.error('Error formatting time:', error);
    }
}

// ===== Meta & Market Status =====

async function updateMeta() {
    const data = await apiGet('/api/meta');
    if (!data) return;
    
    // Market status
    const marketPill = document.getElementById('market-status-pill');
    if (marketPill) {
        const isOpen = data.market_open === true;
        const status = data.market_status || (isOpen ? 'OPEN' : 'CLOSED');
        marketPill.textContent = `MARKET ${status}`;
        marketPill.className = `status-pill ${isOpen ? 'market-open' : 'market-closed'}`;
    }
}

// ===== Mode Detection from Engines =====

async function detectModeFromEngines(enginesData) {
    if (!enginesData || !enginesData.engines) return 'UNKNOWN';
    
    const engines = enginesData.engines;
    let hasLiveRunning = false;
    let hasPaperRunning = false;
    
    for (const engine of engines) {
        if (engine.running) {
            if (engine.mode === 'live') {
                hasLiveRunning = true;
            } else if (engine.mode === 'paper') {
                hasPaperRunning = true;
            }
        }
    }
    
    if (hasLiveRunning) return 'LIVE';
    if (hasPaperRunning) return 'PAPER';
    return 'IDLE';
}

// ===== Engines Panel =====

async function updateEnginesPanel() {
    const data = await apiGet('/api/engines/status');
    const panelBody = document.getElementById('engines-panel-body');
    const badge = document.getElementById('engines-badge');
    const modeBadge = document.getElementById('mode-badge');
    
    if (!data || !panelBody) return;
    
    const engines = data.engines || [];
    const mode = await detectModeFromEngines(data);
    
    // Update mode badge
    if (modeBadge) {
        modeBadge.textContent = mode;
        modeBadge.className = `mode-badge mode-${mode.toLowerCase()}`;
    }
    
    // Update engines badge
    const runningCount = engines.filter(e => e.running).length;
    if (badge) {
        badge.textContent = `${runningCount}/${engines.length} running`;
        badge.className = runningCount > 0 ? 'badge badge-success' : 'badge';
    }
    
    // Render engine list
    if (engines.length === 0) {
        panelBody.innerHTML = '<div class="no-data">No engines configured</div>';
        return;
    }
    
    let html = '<div class="engine-list">';
    for (const engine of engines) {
        const statusText = engine.running ? 'Running' : 'Stopped';
        const statusClass = engine.running ? 'running' : '';
        const lastCheckpoint = engine.last_checkpoint_ts ? formatDateTime(engine.last_checkpoint_ts) : 'Never';
        const ageText = engine.checkpoint_age_seconds !== null 
            ? `(${Math.round(engine.checkpoint_age_seconds)}s ago)` 
            : '';
        
        html += `
            <div class="engine-item">
                <div>
                    <div class="engine-name">${engine.engine || 'Unknown Engine'}</div>
                    <div class="text-muted" style="font-size: 0.75rem;">
                        Last: ${lastCheckpoint} ${ageText}
                    </div>
                </div>
                <div class="engine-status">
                    <span class="engine-dot ${statusClass}"></span>
                    <span class="badge badge-${engine.running ? 'success' : 'muted'}">${statusText}</span>
                    <span class="badge badge-${engine.mode === 'paper' ? 'paper' : 'live'}">${(engine.mode || 'paper').toUpperCase()}</span>
                </div>
            </div>
        `;
    }
    html += '</div>';
    
    // Add mode-specific warning for live mode
    if (mode === 'LIVE') {
        html += `
            <div class="mt-md" style="padding: var(--spacing-md); background-color: rgba(239, 68, 68, 0.1); border: 1px solid var(--accent-danger); border-radius: var(--radius-md);">
                <strong style="color: var(--accent-danger);">⚠️ LIVE MODE ACTIVE</strong>
                <div style="font-size: 0.875rem; color: var(--text-secondary); margin-top: var(--spacing-xs);">
                    Real orders may be sent to the broker. Verify all settings before making changes.
                </div>
            </div>
        `;
    }
    
    panelBody.innerHTML = html;
}

// ===== Portfolio Panel =====

async function updatePortfolioPanel() {
    const summaryData = await apiGet('/api/portfolio/summary');
    const positionsData = await apiGet('/api/positions/open');
    const panelBody = document.getElementById('portfolio-panel-body');
    const badge = document.getElementById('portfolio-badge');
    
    if (!summaryData || !panelBody) return;
    
    // Update badge
    const posCount = summaryData.position_count || 0;
    if (badge) {
        badge.textContent = `${posCount} positions`;
        badge.className = posCount > 0 ? 'badge badge-success' : 'badge';
    }
    
    // Build portfolio summary
    let html = '<div class="metric-grid">';
    
    const metrics = [
        { label: 'Equity', value: formatCurrency(summaryData.equity) },
        { label: 'Realized P&L', value: formatCurrency(summaryData.total_realized_pnl), class: getValueClass(summaryData.total_realized_pnl) },
        { label: 'Unrealized P&L', value: formatCurrency(summaryData.total_unrealized_pnl), class: getValueClass(summaryData.total_unrealized_pnl) },
        { label: 'Daily P&L', value: formatCurrency(summaryData.daily_pnl), class: getValueClass(summaryData.daily_pnl) },
        { label: 'Total Notional', value: formatCurrency(summaryData.total_notional) },
        { label: 'Exposure', value: formatPercentage(summaryData.exposure_pct) },
    ];
    
    for (const metric of metrics) {
        html += `
            <div class="metric-item">
                <span class="metric-label">${metric.label}</span>
                <span class="metric-value ${metric.class || ''}">${metric.value}</span>
            </div>
        `;
    }
    
    html += '</div>';
    
    // Add positions table
    if (positionsData && Array.isArray(positionsData) && positionsData.length > 0) {
        html += `
            <div class="mt-lg">
                <h3 style="font-size: 0.875rem; color: var(--text-secondary); margin-bottom: var(--spacing-sm); text-transform: uppercase;">
                    Open Positions
                </h3>
                <table class="data-table">
                    <thead>
                        <tr>
                            <th>Symbol</th>
                            <th>Side</th>
                            <th>Qty</th>
                            <th>Avg</th>
                            <th>LTP</th>
                            <th>P&L</th>
                        </tr>
                    </thead>
                    <tbody>
        `;
        
        for (const pos of positionsData.slice(0, 10)) {
            const pnlClass = getValueClass(pos.unrealized_pnl);
            html += `
                <tr>
                    <td>${pos.symbol || '—'}</td>
                    <td><span class="badge badge-${pos.side === 'LONG' ? 'success' : 'danger'}">${pos.side || '—'}</span></td>
                    <td>${pos.quantity || 0}</td>
                    <td>${formatCurrency(pos.avg_price)}</td>
                    <td>${formatCurrency(pos.last_price)}</td>
                    <td class="${pnlClass}">${formatCurrency(pos.unrealized_pnl)}</td>
                </tr>
            `;
        }
        
        html += `
                    </tbody>
                </table>
            </div>
        `;
    }
    
    panelBody.innerHTML = html;
}

// ===== Logs Panel =====

async function updateLogsPanel() {
    const kind = currentLogFilter || null;
    const params = new URLSearchParams({ limit: CONFIG.LOG_LIMIT });
    if (kind) params.append('kind', kind);
    
    const data = await apiGet(`/api/logs?${params}`);
    const logsView = document.getElementById('logs-view');
    
    if (!data || !logsView) return;
    
    const logs = data.logs || data.entries || [];
    
    if (logs.length === 0) {
        logsView.textContent = 'No logs available.';
        return;
    }
    
    let html = '';
    for (const log of logs.slice(-100).reverse()) {
        const ts = log.ts || log.timestamp || '';
        const level = (log.level || 'INFO').toUpperCase();
        const source = log.logger || log.source || '';
        const message = log.message || '';
        
        html += `<span class="log-line">`;
        html += `<span class="log-timestamp">${formatTime(ts)}</span> `;
        html += `<span class="log-level-${level}">[${level}]</span> `;
        if (source) html += `<span class="text-muted">${source}</span> `;
        html += `<span class="log-message">${message}</span>`;
        html += `</span>\n`;
    }
    
    logsView.innerHTML = html;
    
    // Auto-scroll to bottom
    logsView.scrollTop = logsView.scrollHeight;
}

// ===== Signals Panel =====

async function updateSignalsPanel() {
    const signalsData = await apiGet('/api/signals/recent?limit=50');
    const strategiesData = await apiGet('/api/stats/strategies?days=1');
    const panelBody = document.getElementById('signals-panel-body');
    const badge = document.getElementById('signals-count-badge');
    
    if (!panelBody) return;
    
    const signals = signalsData || [];
    const strategies = strategiesData || [];
    
    // Update badge
    if (badge) {
        badge.textContent = `${signals.length} signals`;
    }
    
    let html = '';
    
    // Strategies section
    if (strategies.length > 0) {
        html += `
            <div class="mb-lg">
                <h3 style="font-size: 0.875rem; color: var(--text-secondary); margin-bottom: var(--spacing-sm); text-transform: uppercase;">
                    Active Strategies
                </h3>
                <table class="data-table">
                    <thead>
                        <tr>
                            <th>Strategy</th>
                            <th>Symbol</th>
                            <th>Last Signal</th>
                            <th>TF</th>
                            <th>B/S/X/H</th>
                        </tr>
                    </thead>
                    <tbody>
        `;
        
        for (const strat of strategies.slice(0, 10)) {
            const counts = `${strat.buy_count || 0}/${strat.sell_count || 0}/${strat.exit_count || 0}/${strat.hold_count || 0}`;
            html += `
                <tr>
                    <td>${strat.logical || strat.strategy || '—'}</td>
                    <td>${strat.symbol || '—'}</td>
                    <td><span class="badge badge-${strat.last_signal === 'BUY' ? 'success' : strat.last_signal === 'SELL' ? 'danger' : 'muted'}">${strat.last_signal || '—'}</span></td>
                    <td>${strat.timeframe || '—'}</td>
                    <td>${counts}</td>
                </tr>
            `;
        }
        
        html += `
                    </tbody>
                </table>
            </div>
        `;
    }
    
    // Recent signals section
    if (signals.length > 0) {
        html += `
            <div>
                <h3 style="font-size: 0.875rem; color: var(--text-secondary); margin-bottom: var(--spacing-sm); text-transform: uppercase;">
                    Recent Signals
                </h3>
                <table class="data-table">
                    <thead>
                        <tr>
                            <th>Time</th>
                            <th>Symbol</th>
                            <th>Signal</th>
                            <th>TF</th>
                            <th>Price</th>
                            <th>Strategy</th>
                        </tr>
                    </thead>
                    <tbody>
        `;
        
        for (const sig of signals.slice(0, 20)) {
            html += `
                <tr>
                    <td>${formatTime(sig.ts)}</td>
                    <td>${sig.symbol || '—'}</td>
                    <td><span class="badge badge-${sig.signal === 'BUY' ? 'success' : sig.signal === 'SELL' ? 'danger' : 'muted'}">${sig.signal || '—'}</span></td>
                    <td>${sig.tf || '—'}</td>
                    <td>${formatCurrency(sig.price)}</td>
                    <td class="text-muted">${sig.strategy || '—'}</td>
                </tr>
            `;
        }
        
        html += `
                    </tbody>
                </table>
            </div>
        `;
    }
    
    if (strategies.length === 0 && signals.length === 0) {
        html = '<div class="no-data">No strategies or signals yet.</div>';
    }
    
    panelBody.innerHTML = html;
}

// ===== Health & Meta Panel =====

async function updateMetaPanel() {
    const healthData = await apiGet('/api/health');
    const configData = await apiGet('/api/config/summary');
    const todayData = await apiGet('/api/summary/today');
    const panelBody = document.getElementById('meta-panel-body');
    const badge = document.getElementById('health-badge');
    
    if (!panelBody) return;
    
    let html = '';
    
    // Config section
    if (configData) {
        html += `
            <div class="mb-lg">
                <h3 style="font-size: 0.875rem; color: var(--text-secondary); margin-bottom: var(--spacing-sm); text-transform: uppercase;">
                    Configuration
                </h3>
                <div class="metric-grid">
                    <div class="metric-item">
                        <span class="metric-label">Mode</span>
                        <span class="metric-value">${(configData.mode || 'paper').toUpperCase()}</span>
                    </div>
                    <div class="metric-item">
                        <span class="metric-label">Universe</span>
                        <span class="metric-value" style="font-size: 1rem;">${(configData.fno_universe || []).join(', ') || '—'}</span>
                    </div>
                    <div class="metric-item">
                        <span class="metric-label">Paper Capital</span>
                        <span class="metric-value">${formatCurrency(configData.paper_capital)}</span>
                    </div>
                    <div class="metric-item">
                        <span class="metric-label">Risk Profile</span>
                        <span class="badge badge-${configData.risk_profile === 'Aggressive' ? 'danger' : configData.risk_profile === 'Conservative' ? 'success' : 'muted'}">${configData.risk_profile || 'Default'}</span>
                    </div>
                </div>
            </div>
        `;
    }
    
    // Today's summary
    if (todayData) {
        html += `
            <div class="mb-lg">
                <h3 style="font-size: 0.875rem; color: var(--text-secondary); margin-bottom: var(--spacing-sm); text-transform: uppercase;">
                    Today's Summary
                </h3>
                <div class="metric-grid">
                    <div class="metric-item">
                        <span class="metric-label">Realized P&L</span>
                        <span class="metric-value ${getValueClass(todayData.realized_pnl)}">${formatCurrency(todayData.realized_pnl)}</span>
                    </div>
                    <div class="metric-item">
                        <span class="metric-label">Trades</span>
                        <span class="metric-value">${todayData.num_trades || 0}</span>
                    </div>
                    <div class="metric-item">
                        <span class="metric-label">Win Rate</span>
                        <span class="metric-value">${(todayData.win_rate || 0).toFixed(1)}%</span>
                    </div>
                    <div class="metric-item">
                        <span class="metric-label">Avg R</span>
                        <span class="metric-value">${(todayData.avg_r || 0).toFixed(2)}R</span>
                    </div>
                </div>
            </div>
        `;
    }
    
    // Health section
    if (healthData) {
        const logHealth = healthData.log_health || {};
        const marketStatus = healthData.market_status || {};
        
        if (badge) {
            const errorCount = logHealth.error_count_recent || 0;
            badge.textContent = errorCount > 0 ? `${errorCount} errors` : 'Healthy';
            badge.className = errorCount > 0 ? 'badge badge-danger' : 'badge badge-success';
        }
        
        html += `
            <div>
                <h3 style="font-size: 0.875rem; color: var(--text-secondary); margin-bottom: var(--spacing-sm); text-transform: uppercase;">
                    System Health
                </h3>
                <div class="metric-grid">
                    <div class="metric-item">
                        <span class="metric-label">Market Status</span>
                        <span class="badge badge-${marketStatus.status === 'OPEN' ? 'success' : 'muted'}">${marketStatus.status || 'UNKNOWN'}</span>
                    </div>
                    <div class="metric-item">
                        <span class="metric-label">Recent Errors</span>
                        <span class="metric-value ${logHealth.error_count_recent > 0 ? 'negative' : ''}">${logHealth.error_count_recent || 0}</span>
                    </div>
                    <div class="metric-item">
                        <span class="metric-label">Recent Warnings</span>
                        <span class="metric-value">${logHealth.warning_count_recent || 0}</span>
                    </div>
                    <div class="metric-item">
                        <span class="metric-label">Last Log</span>
                        <span class="metric-value" style="font-size: 0.875rem;">${formatTime(logHealth.last_log_ts)}</span>
                    </div>
                </div>
            </div>
        `;
    }
    
    panelBody.innerHTML = html;
}

// ===== Polling Management =====

function startPolling() {
    // Clear any existing intervals
    stopPolling();
    
    // Start all polling intervals
    intervals.serverTime = setInterval(updateServerTime, CONFIG.POLL_INTERVALS.serverTime);
    intervals.meta = setInterval(updateMeta, CONFIG.POLL_INTERVALS.meta);
    intervals.engines = setInterval(updateEnginesPanel, CONFIG.POLL_INTERVALS.engines);
    intervals.portfolio = setInterval(updatePortfolioPanel, CONFIG.POLL_INTERVALS.portfolio);
    intervals.logs = setInterval(updateLogsPanel, CONFIG.POLL_INTERVALS.logs);
    intervals.signals = setInterval(updateSignalsPanel, CONFIG.POLL_INTERVALS.signals);
    intervals.health = setInterval(updateMetaPanel, CONFIG.POLL_INTERVALS.health);
    
    console.log('✓ Dashboard polling started');
}

function stopPolling() {
    Object.values(intervals).forEach(id => clearInterval(id));
    intervals = {};
}

// ===== Event Handlers =====

function setupEventHandlers() {
    // Log filter
    const logFilter = document.getElementById('log-filter');
    if (logFilter) {
        logFilter.addEventListener('change', (e) => {
            currentLogFilter = e.target.value;
            updateLogsPanel();
        });
    }
    
    // Logs refresh button
    const logsRefresh = document.getElementById('logs-refresh');
    if (logsRefresh) {
        logsRefresh.addEventListener('click', () => {
            updateLogsPanel();
        });
    }
    
    // Cleanup on page unload
    window.addEventListener('beforeunload', () => {
        stopPolling();
    });
}

// ===== Initialization =====

async function init() {
    console.log('Initializing Arthayukti Dashboard...');
    
    // Setup event handlers
    setupEventHandlers();
    
    // Load all data immediately
    await Promise.all([
        updateServerTime(),
        updateMeta(),
        updateEnginesPanel(),
        updatePortfolioPanel(),
        updateLogsPanel(),
        updateSignalsPanel(),
        updateMetaPanel(),
    ]);
    
    // Start polling
    startPolling();
    
    console.log('✓ Dashboard initialized successfully');
}

// Start when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
} else {
    init();
}
