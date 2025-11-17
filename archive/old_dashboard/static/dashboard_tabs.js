/**
 * Arthayukti Dashboard - Tabbed Layout with Auto-Detection
 * 
 * Features:
 * - Auto-detects PAPER/LIVE mode from engines status API
 * - Polls server time, engines, portfolio, signals, logs
 * - Implements tabs: Overview, Engines & Logs, Portfolio, Signals & Strategies, System
 * - Logs with severity filter and auto-scroll behavior
 * - Dark theme with loading/error states per card
 * 
 * Backend APIs used:
 * - /api/meta (server time, market status)
 * - /api/engines/status (mode detection, engine status)
 * - /api/portfolio/summary (portfolio snapshot)
 * - /api/positions/open (open positions)
 * - /api/orders/recent (recent orders)
 * - /api/signals/recent (recent signals)
 * - /api/stats/strategies (strategy stats)
 * - /api/logs (logs with filters)
 * - /api/config/summary (config summary)
 * - /api/scanner/universe (scanner data)
 */

// State management
const state = {
    currentTab: 'overview',
    mode: 'IDLE',
    logFollow: true,
    logSeverityFilter: '',
    logsData: [],
    lastLogScroll: 0,
};

// Polling intervals
let timeInterval = null;
let enginesInterval = null;
let portfolioInterval = null;
let signalsInterval = null;
let logsInterval = null;

// Initialize dashboard
document.addEventListener('DOMContentLoaded', () => {
    initTabs();
    initLogControls();
    startPolling();
    
    // Initial load
    fetchServerTime();
    fetchEnginesStatus();
    fetchPortfolioSummary();
    fetchSignals();
    fetchLogs();
    fetchConfigSummary();
});

// Tab switching
function initTabs() {
    const tabs = document.querySelectorAll('.tab');
    const tabContents = document.querySelectorAll('.tab-content');
    
    tabs.forEach(tab => {
        tab.addEventListener('click', () => {
            const tabName = tab.dataset.tab;
            
            // Update active tab
            tabs.forEach(t => t.classList.remove('active'));
            tab.classList.add('active');
            
            // Update active content
            tabContents.forEach(content => {
                if (content.id === `tab-${tabName}`) {
                    content.classList.add('active');
                } else {
                    content.classList.remove('active');
                }
            });
            
            state.currentTab = tabName;
            
            // Load tab-specific data if needed
            loadTabData(tabName);
        });
    });
}

// Load tab-specific data on demand
function loadTabData(tabName) {
    switch (tabName) {
        case 'overview':
            fetchEnginesStatus();
            fetchPortfolioSummary();
            fetchSignals();
            break;
        case 'engines':
            fetchEnginesStatus();
            fetchLogs();
            break;
        case 'portfolio':
            fetchPortfolioSummary();
            fetchPositions();
            fetchOrders();
            break;
        case 'signals':
            fetchStrategies();
            fetchSignals();
            fetchScanner();
            break;
        case 'system':
            fetchConfigSummary();
            fetchSystemInfo();
            break;
    }
}

// Log controls
function initLogControls() {
    const severityFilter = document.getElementById('log-severity-filter');
    const followCheckbox = document.getElementById('log-follow');
    const logsContainer = document.getElementById('logs-container');
    
    severityFilter.addEventListener('change', (e) => {
        state.logSeverityFilter = e.target.value;
        renderLogs();
    });
    
    followCheckbox.addEventListener('change', (e) => {
        state.logFollow = e.target.checked;
        if (state.logFollow) {
            scrollLogsToBottom();
        }
    });
    
    // Detect manual scroll to disable follow
    logsContainer.addEventListener('scroll', () => {
        const container = logsContainer;
        const isNearBottom = container.scrollHeight - container.scrollTop - container.clientHeight < 50;
        
        if (!isNearBottom && state.logFollow) {
            state.logFollow = false;
            followCheckbox.checked = false;
        }
    });
}

// Start polling
function startPolling() {
    // Server time: 1s
    timeInterval = setInterval(fetchServerTime, 1000);
    
    // Engines status: 5s
    enginesInterval = setInterval(fetchEnginesStatus, 5000);
    
    // Portfolio: 5s
    portfolioInterval = setInterval(() => {
        fetchPortfolioSummary();
        if (state.currentTab === 'portfolio') {
            fetchPositions();
            fetchOrders();
        }
    }, 5000);
    
    // Signals: 5s
    signalsInterval = setInterval(() => {
        fetchSignals();
        if (state.currentTab === 'signals') {
            fetchStrategies();
        }
    }, 5000);
    
    // Logs: 3s
    logsInterval = setInterval(fetchLogs, 3000);
}

// API Fetch Functions

async function fetchServerTime() {
    try {
        const response = await fetch('/api/meta');
        const data = await response.json();
        
        if (data.now_ist) {
            const date = new Date(data.now_ist);
            const timeStr = date.toLocaleTimeString('en-IN', { 
                hour: '2-digit', 
                minute: '2-digit', 
                second: '2-digit',
                timeZone: 'Asia/Kolkata'
            });
            document.getElementById('server-time').textContent = timeStr;
        }
    } catch (error) {
        console.error('Failed to fetch server time:', error);
    }
}

async function fetchEnginesStatus() {
    try {
        const response = await fetch('/api/engines/status');
        const data = await response.json();
        
        // Auto-detect mode from engines
        const engines = data.engines || [];
        let detectedMode = 'IDLE';
        
        if (engines.some(e => e.mode === 'live' && e.running)) {
            detectedMode = 'LIVE';
        } else if (engines.some(e => e.mode === 'paper' && e.running)) {
            detectedMode = 'PAPER';
        }
        
        state.mode = detectedMode;
        updateModeBadge(detectedMode);
        
        // Render engines status
        renderEnginesStatus(engines);
        renderOverviewModeStatus(engines, detectedMode);
    } catch (error) {
        console.error('Failed to fetch engines status:', error);
        document.getElementById('engines-status').innerHTML = '<div class="error">Failed to load engines status</div>';
    }
}

function updateModeBadge(mode) {
    const badge = document.getElementById('mode-badge');
    badge.textContent = mode;
    badge.className = 'mode-badge ' + mode.toLowerCase();
}

function renderEnginesStatus(engines) {
    const container = document.getElementById('engines-status');
    
    if (engines.length === 0) {
        container.innerHTML = '<div class="text-muted">No engines configured</div>';
        return;
    }
    
    const html = `
        <table>
            <thead>
                <tr>
                    <th>Engine</th>
                    <th>Type</th>
                    <th>Status</th>
                    <th>Last Update</th>
                </tr>
            </thead>
            <tbody>
                ${engines.map(engine => `
                    <tr>
                        <td>${engine.engine || 'Unknown'}</td>
                        <td><span class="badge info">${(engine.mode || 'paper').toUpperCase()}</span></td>
                        <td>
                            <span class="badge ${engine.running ? 'success' : 'error'}">
                                ${engine.running ? 'RUNNING' : 'STOPPED'}
                            </span>
                        </td>
                        <td class="text-muted">${formatTimestamp(engine.last_checkpoint_ts)}</td>
                    </tr>
                `).join('')}
            </tbody>
        </table>
    `;
    
    container.innerHTML = html;
}

function renderOverviewModeStatus(engines, mode) {
    const container = document.getElementById('overview-mode-status');
    
    const runningEngines = engines.filter(e => e.running).length;
    const totalEngines = engines.length;
    
    const html = `
        <div class="stats-grid">
            <div class="stat-item">
                <div class="stat-label">Current Mode</div>
                <div class="stat-value">
                    <span class="badge ${mode === 'LIVE' ? 'error' : mode === 'PAPER' ? 'info' : 'warning'}">
                        ${mode}
                    </span>
                </div>
            </div>
            <div class="stat-item">
                <div class="stat-label">Engines</div>
                <div class="stat-value">${runningEngines} / ${totalEngines}</div>
            </div>
        </div>
    `;
    
    container.innerHTML = html;
}

async function fetchPortfolioSummary() {
    try {
        const response = await fetch('/api/portfolio/summary');
        const data = await response.json();
        
        renderPortfolioSummary(data);
        renderOverviewPortfolio(data);
    } catch (error) {
        console.error('Failed to fetch portfolio summary:', error);
        document.getElementById('portfolio-summary').innerHTML = '<div class="error">Failed to load portfolio</div>';
    }
}

function renderPortfolioSummary(data) {
    const container = document.getElementById('portfolio-summary');
    
    const equity = data.equity || 0;
    const paperCapital = data.paper_capital || 0;
    const realizedPnl = data.total_realized_pnl || 0;
    const unrealizedPnl = data.total_unrealized_pnl || 0;
    const freeNotional = data.free_notional || 0;
    const exposurePct = data.exposure_pct ? (data.exposure_pct * 100).toFixed(1) : 0;
    const dailyPnl = data.daily_pnl || 0;
    
    const html = `
        <div class="stats-grid">
            <div class="stat-item">
                <div class="stat-label">Equity</div>
                <div class="stat-value">₹${formatNumber(equity)}</div>
            </div>
            <div class="stat-item">
                <div class="stat-label">Capital</div>
                <div class="stat-value">₹${formatNumber(paperCapital)}</div>
            </div>
            <div class="stat-item">
                <div class="stat-label">Realized P&L</div>
                <div class="stat-value ${realizedPnl >= 0 ? 'positive' : 'negative'}">
                    ₹${formatNumber(realizedPnl)}
                </div>
            </div>
            <div class="stat-item">
                <div class="stat-label">Unrealized P&L</div>
                <div class="stat-value ${unrealizedPnl >= 0 ? 'positive' : 'negative'}">
                    ₹${formatNumber(unrealizedPnl)}
                </div>
            </div>
            <div class="stat-item">
                <div class="stat-label">Daily P&L</div>
                <div class="stat-value ${dailyPnl >= 0 ? 'positive' : 'negative'}">
                    ₹${formatNumber(dailyPnl)}
                </div>
            </div>
            <div class="stat-item">
                <div class="stat-label">Free Margin</div>
                <div class="stat-value">₹${formatNumber(freeNotional)}</div>
            </div>
            <div class="stat-item">
                <div class="stat-label">Exposure</div>
                <div class="stat-value">${exposurePct}%</div>
            </div>
        </div>
    `;
    
    container.innerHTML = html;
}

function renderOverviewPortfolio(data) {
    const container = document.getElementById('overview-portfolio');
    
    const equity = data.equity || 0;
    const freeNotional = data.free_notional || 0;
    const dailyPnl = data.daily_pnl || 0;
    
    const html = `
        <div class="stats-grid">
            <div class="stat-item">
                <div class="stat-label">Equity</div>
                <div class="stat-value">₹${formatNumber(equity)}</div>
            </div>
            <div class="stat-item">
                <div class="stat-label">Free Margin</div>
                <div class="stat-value">₹${formatNumber(freeNotional)}</div>
            </div>
            <div class="stat-item">
                <div class="stat-label">Day P&L</div>
                <div class="stat-value ${dailyPnl >= 0 ? 'positive' : 'negative'}">
                    ₹${formatNumber(dailyPnl)}
                </div>
            </div>
        </div>
    `;
    
    container.innerHTML = html;
}

async function fetchPositions() {
    try {
        const response = await fetch('/api/positions/open');
        const positions = await response.json();
        
        renderPositions(positions);
    } catch (error) {
        console.error('Failed to fetch positions:', error);
        document.getElementById('portfolio-positions').innerHTML = '<div class="error">Failed to load positions</div>';
    }
}

function renderPositions(positions) {
    const container = document.getElementById('portfolio-positions');
    
    if (!positions || positions.length === 0) {
        container.innerHTML = '<div class="text-muted">No open positions</div>';
        return;
    }
    
    const html = `
        <table>
            <thead>
                <tr>
                    <th>Symbol</th>
                    <th>Side</th>
                    <th>Qty</th>
                    <th>Avg Price</th>
                    <th>LTP</th>
                    <th>P&L</th>
                    <th>% P&L</th>
                </tr>
            </thead>
            <tbody>
                ${positions.map(pos => {
                    const pnl = pos.unrealized_pnl || 0;
                    const pnlPct = pos.avg_price ? ((pos.last_price - pos.avg_price) / pos.avg_price * 100).toFixed(2) : 0;
                    return `
                        <tr>
                            <td>${pos.symbol}</td>
                            <td><span class="badge ${pos.side === 'LONG' ? 'success' : 'error'}">${pos.side}</span></td>
                            <td>${pos.quantity}</td>
                            <td>₹${formatNumber(pos.avg_price)}</td>
                            <td>₹${formatNumber(pos.last_price)}</td>
                            <td class="${pnl >= 0 ? 'text-success' : 'text-error'}">₹${formatNumber(pnl)}</td>
                            <td class="${pnl >= 0 ? 'text-success' : 'text-error'}">${pnlPct}%</td>
                        </tr>
                    `;
                }).join('')}
            </tbody>
        </table>
    `;
    
    container.innerHTML = html;
}

async function fetchOrders() {
    try {
        const response = await fetch('/api/orders/recent?limit=20');
        const data = await response.json();
        const orders = data.orders || data;
        
        renderOrders(orders);
    } catch (error) {
        console.error('Failed to fetch orders:', error);
        document.getElementById('portfolio-orders').innerHTML = '<div class="error">Failed to load orders</div>';
    }
}

function renderOrders(orders) {
    const container = document.getElementById('portfolio-orders');
    
    if (!orders || orders.length === 0) {
        container.innerHTML = '<div class="text-muted">No recent orders</div>';
        return;
    }
    
    const html = `
        <table>
            <thead>
                <tr>
                    <th>Time</th>
                    <th>Symbol</th>
                    <th>Side</th>
                    <th>Qty</th>
                    <th>Price</th>
                    <th>Status</th>
                </tr>
            </thead>
            <tbody>
                ${orders.map(order => `
                    <tr>
                        <td class="text-muted">${formatTimestamp(order.timestamp || order.ts)}</td>
                        <td>${order.symbol || order.tradingsymbol || '-'}</td>
                        <td><span class="badge ${order.side === 'BUY' ? 'success' : 'error'}">${order.side || '-'}</span></td>
                        <td>${order.quantity || order.qty || '-'}</td>
                        <td>₹${formatNumber(order.price || order.average_price || 0)}</td>
                        <td><span class="badge info">${order.status || '-'}</span></td>
                    </tr>
                `).join('')}
            </tbody>
        </table>
    `;
    
    container.innerHTML = html;
}

async function fetchSignals() {
    try {
        const response = await fetch('/api/signals/recent?limit=5');
        const signals = await response.json();
        
        renderSignalsTable(signals);
        renderOverviewSignals(signals);
    } catch (error) {
        console.error('Failed to fetch signals:', error);
        document.getElementById('signals-table').innerHTML = '<div class="error">Failed to load signals</div>';
    }
}

function renderOverviewSignals(signals) {
    const container = document.getElementById('overview-signals');
    
    if (!signals || signals.length === 0) {
        container.innerHTML = '<div class="text-muted">No recent signals</div>';
        return;
    }
    
    const html = `
        <table>
            <thead>
                <tr>
                    <th>Time</th>
                    <th>Symbol</th>
                    <th>Signal</th>
                    <th>Strategy</th>
                </tr>
            </thead>
            <tbody>
                ${signals.slice(0, 5).map(sig => `
                    <tr>
                        <td class="text-muted">${formatTimestamp(sig.ts)}</td>
                        <td>${sig.symbol || sig.logical || '-'}</td>
                        <td><span class="badge ${sig.signal === 'BUY' ? 'success' : sig.signal === 'SELL' ? 'error' : 'warning'}">${sig.signal}</span></td>
                        <td class="text-muted">${sig.strategy || '-'}</td>
                    </tr>
                `).join('')}
            </tbody>
        </table>
    `;
    
    container.innerHTML = html;
}

function renderSignalsTable(signals) {
    const container = document.getElementById('signals-table');
    
    if (!signals || signals.length === 0) {
        container.innerHTML = '<div class="text-muted">No recent signals</div>';
        return;
    }
    
    const html = `
        <table>
            <thead>
                <tr>
                    <th>Time</th>
                    <th>Symbol</th>
                    <th>Signal</th>
                    <th>Strategy</th>
                    <th>Price</th>
                    <th>TF</th>
                </tr>
            </thead>
            <tbody>
                ${signals.map(sig => `
                    <tr>
                        <td class="text-muted">${formatTimestamp(sig.ts)}</td>
                        <td>${sig.symbol || sig.logical || '-'}</td>
                        <td><span class="badge ${sig.signal === 'BUY' ? 'success' : sig.signal === 'SELL' ? 'error' : 'warning'}">${sig.signal}</span></td>
                        <td class="text-muted">${sig.strategy || '-'}</td>
                        <td>${sig.price ? '₹' + formatNumber(sig.price) : '-'}</td>
                        <td class="text-muted">${sig.tf || '-'}</td>
                    </tr>
                `).join('')}
            </tbody>
        </table>
    `;
    
    container.innerHTML = html;
}

async function fetchStrategies() {
    try {
        const response = await fetch('/api/stats/strategies');
        const strategies = await response.json();
        
        renderStrategies(strategies);
    } catch (error) {
        console.error('Failed to fetch strategies:', error);
        document.getElementById('strategies-table').innerHTML = '<div class="error">Failed to load strategies</div>';
    }
}

function renderStrategies(strategies) {
    const container = document.getElementById('strategies-table');
    
    if (!strategies || strategies.length === 0) {
        container.innerHTML = '<div class="text-muted">No strategies available</div>';
        return;
    }
    
    const html = `
        <table>
            <thead>
                <tr>
                    <th>Strategy</th>
                    <th>Symbol</th>
                    <th>Mode</th>
                    <th>TF</th>
                    <th>Buy</th>
                    <th>Sell</th>
                    <th>Exit</th>
                    <th>Last Signal</th>
                </tr>
            </thead>
            <tbody>
                ${strategies.map(strat => `
                    <tr>
                        <td>${strat.strategy || strat.logical || '-'}</td>
                        <td>${strat.symbol || '-'}</td>
                        <td><span class="badge info">${(strat.mode || 'PAPER').toUpperCase()}</span></td>
                        <td class="text-muted">${strat.timeframe || '-'}</td>
                        <td>${strat.buy_count || 0}</td>
                        <td>${strat.sell_count || 0}</td>
                        <td>${strat.exit_count || 0}</td>
                        <td class="text-muted">${formatTimestamp(strat.last_ts)}</td>
                    </tr>
                `).join('')}
            </tbody>
        </table>
    `;
    
    container.innerHTML = html;
}

async function fetchScanner() {
    try {
        const response = await fetch('/api/scanner/universe');
        const data = await response.json();
        
        renderScanner(data);
    } catch (error) {
        console.error('Failed to fetch scanner:', error);
        document.getElementById('scanner-snapshot').innerHTML = '<div class="text-muted">Scanner data not available</div>';
    }
}

function renderScanner(data) {
    const container = document.getElementById('scanner-snapshot');
    
    if (!data || Object.keys(data).length === 0) {
        container.innerHTML = '<div class="text-muted">No scanner data available</div>';
        return;
    }
    
    const symbols = Object.keys(data).slice(0, 10);
    
    const html = `
        <table>
            <thead>
                <tr>
                    <th>Symbol</th>
                    <th>Token</th>
                </tr>
            </thead>
            <tbody>
                ${symbols.map(symbol => `
                    <tr>
                        <td>${symbol}</td>
                        <td class="text-muted">${data[symbol]}</td>
                    </tr>
                `).join('')}
            </tbody>
        </table>
    `;
    
    container.innerHTML = html;
}

async function fetchLogs() {
    try {
        const params = new URLSearchParams({ limit: 100 });
        if (state.logSeverityFilter) {
            params.append('level', state.logSeverityFilter);
        }
        
        const response = await fetch(`/api/logs?${params}`);
        const data = await response.json();
        
        state.logsData = data.logs || data.entries || [];
        renderLogs();
    } catch (error) {
        console.error('Failed to fetch logs:', error);
        document.getElementById('logs-container').innerHTML = '<div class="error">Failed to load logs</div>';
    }
}

function renderLogs() {
    const container = document.getElementById('logs-container');
    const logs = state.logsData;
    
    if (!logs || logs.length === 0) {
        container.innerHTML = '<div class="text-muted">No logs available</div>';
        return;
    }
    
    const html = logs.map(log => {
        const timestamp = log.timestamp || log.ts || '';
        const level = log.level || 'INFO';
        const source = log.logger || log.source || '';
        const message = log.message || '';
        
        return `
            <div class="log-entry">
                <span class="timestamp">${formatTimestamp(timestamp)}</span>
                <span class="level ${level}">[${level}]</span>
                <span class="source">${source}</span>
                <span class="message">${message}</span>
            </div>
        `;
    }).join('');
    
    container.innerHTML = html;
    
    // Auto-scroll if follow is enabled
    if (state.logFollow) {
        scrollLogsToBottom();
    }
}

function scrollLogsToBottom() {
    const container = document.getElementById('logs-container');
    container.scrollTop = container.scrollHeight;
}

async function fetchConfigSummary() {
    try {
        const response = await fetch('/api/config/summary');
        const data = await response.json();
        
        renderConfigSummary(data);
    } catch (error) {
        console.error('Failed to fetch config summary:', error);
        document.getElementById('config-summary').innerHTML = '<div class="error">Failed to load config</div>';
    }
}

function renderConfigSummary(data) {
    const container = document.getElementById('config-summary');
    
    const html = `
        <div class="stats-grid">
            <div class="stat-item">
                <div class="stat-label">Mode</div>
                <div class="stat-value">${(data.mode || 'PAPER').toUpperCase()}</div>
            </div>
            <div class="stat-item">
                <div class="stat-label">Paper Capital</div>
                <div class="stat-value">₹${formatNumber(data.paper_capital || 0)}</div>
            </div>
            <div class="stat-item">
                <div class="stat-label">Risk Per Trade</div>
                <div class="stat-value">${((data.risk_per_trade_pct || 0) * 100).toFixed(2)}%</div>
            </div>
            <div class="stat-item">
                <div class="stat-label">Max Daily Loss</div>
                <div class="stat-value">₹${formatNumber(data.max_daily_loss || 0)}</div>
            </div>
            <div class="stat-item">
                <div class="stat-label">Max Exposure</div>
                <div class="stat-value">${((data.max_exposure_pct || 0) * 100).toFixed(0)}%</div>
            </div>
            <div class="stat-item">
                <div class="stat-label">Risk Profile</div>
                <div class="stat-value">${data.risk_profile || 'Default'}</div>
            </div>
        </div>
        <div style="margin-top: var(--spacing-md);">
            <div class="text-muted" style="font-size: 12px;">
                Universe: ${(data.fno_universe || []).join(', ') || 'None'}
            </div>
        </div>
    `;
    
    container.innerHTML = html;
}

async function fetchSystemInfo() {
    const container = document.getElementById('system-info');
    
    // For now, show basic info
    const html = `
        <div class="stats-grid">
            <div class="stat-item">
                <div class="stat-label">Environment</div>
                <div class="stat-value">Production</div>
            </div>
            <div class="stat-item">
                <div class="stat-label">Version</div>
                <div class="stat-value">v1.0.0</div>
            </div>
        </div>
    `;
    
    container.innerHTML = html;
}

// Debug JSON toggle
document.getElementById('toggle-debug')?.addEventListener('click', async () => {
    const debugContainer = document.getElementById('debug-json');
    const button = document.getElementById('toggle-debug');
    
    if (debugContainer.style.display === 'none') {
        // Fetch and show debug data
        try {
            const [meta, config, engines, portfolio] = await Promise.all([
                fetch('/api/meta').then(r => r.json()),
                fetch('/api/config/summary').then(r => r.json()),
                fetch('/api/engines/status').then(r => r.json()),
                fetch('/api/portfolio/summary').then(r => r.json()),
            ]);
            
            const debugData = { meta, config, engines, portfolio };
            debugContainer.querySelector('pre').textContent = JSON.stringify(debugData, null, 2);
            debugContainer.style.display = 'block';
            button.textContent = 'Hide';
        } catch (error) {
            debugContainer.querySelector('pre').textContent = 'Failed to load debug data';
            debugContainer.style.display = 'block';
            button.textContent = 'Hide';
        }
    } else {
        debugContainer.style.display = 'none';
        button.textContent = 'Show';
    }
});

// Utility functions

function formatNumber(num) {
    if (num === null || num === undefined) return '0';
    return Number(num).toLocaleString('en-IN', { maximumFractionDigits: 2 });
}

function formatTimestamp(ts) {
    if (!ts) return '-';
    
    try {
        const date = new Date(ts);
        return date.toLocaleTimeString('en-IN', { 
            hour: '2-digit', 
            minute: '2-digit',
            second: '2-digit',
            timeZone: 'Asia/Kolkata'
        });
    } catch (error) {
        return ts.toString().substring(0, 19);
    }
}

// Cleanup on page unload
window.addEventListener('beforeunload', () => {
    clearInterval(timeInterval);
    clearInterval(enginesInterval);
    clearInterval(portfolioInterval);
    clearInterval(signalsInterval);
    clearInterval(logsInterval);
});
