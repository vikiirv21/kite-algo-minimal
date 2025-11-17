/**
 * Arthayukti Dashboard - Tab Controller
 * Manages tab switching and rendering
 */

const DashboardTabs = (() => {
    // Current render functions for each tab
    const tabRenderers = {};

    /**
     * Register a tab renderer
     */
    function registerTab(tabName, renderFn) {
        tabRenderers[tabName] = renderFn;
    }

    /**
     * Switch to a tab
     */
    function switchTab(tabName) {
        // Update state store
        StateStore.switchTab(tabName);
        
        // Update tab buttons
        document.querySelectorAll('.tab-btn').forEach(btn => {
            btn.classList.remove('active');
            if (btn.dataset.tab === tabName) {
                btn.classList.add('active');
            }
        });

        // Hide all tab contents
        document.querySelectorAll('.tab-content').forEach(content => {
            content.style.display = 'none';
        });

        // Show active tab content
        const activeContent = document.getElementById(`tab-${tabName}`);
        if (activeContent) {
            activeContent.style.display = 'block';
        }

        // Render tab content
        renderTab(tabName);
    }

    /**
     * Render a specific tab
     */
    function renderTab(tabName) {
        const renderer = tabRenderers[tabName];
        if (renderer) {
            try {
                renderer(StateStore.getState());
            } catch (error) {
                console.error(`Failed to render tab ${tabName}:`, error);
            }
        }
    }

    /**
     * Initialize tabs
     */
    function init() {
        // Register all tab renderers
        registerTab('overview', renderOverview);
        registerTab('engines', renderEngines);
        registerTab('portfolio', renderPortfolio);
        registerTab('signals', renderSignals);
        registerTab('analytics', renderAnalytics);
        registerTab('system', renderSystem);

        // Setup tab button listeners
        document.querySelectorAll('.tab-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                const tabName = btn.dataset.tab;
                if (tabName) switchTab(tabName);
            });
        });

        // Subscribe to state changes
        StateStore.subscribe((key, value, state) => {
            // Re-render active tab when relevant state changes
            const activeTab = state.activeTab;
            if (shouldRerender(activeTab, key)) {
                renderTab(activeTab);
            }
        });

        // Initial render
        const activeTab = StateStore.getState().activeTab;
        switchTab(activeTab);
    }

    /**
     * Determine if tab should re-render on state change
     */
    function shouldRerender(tabName, stateKey) {
        const tabStateMap = {
            overview: ['portfolio', 'signals', 'todaySummary', 'mode', 'engines'],
            engines: ['engines', 'logs'],
            portfolio: ['portfolio', 'positionsOpen', 'orders', 'todaySummary'],
            signals: ['signals', 'strategies'],
            analytics: ['equityCurve', 'analyticsSummary'],
            system: ['config', 'health'],
        };

        const relevantKeys = tabStateMap[tabName] || [];
        return relevantKeys.includes(stateKey);
    }

    // ========== Tab Renderers ==========

    /**
     * Render Overview Tab
     */
    function renderOverview(state) {
        const { mode, engines, portfolio, signals, todaySummary } = state;

        // Mode & Status Card
        const runningEngines = (engines || []).filter(e => e.running).length;
        document.getElementById('overview-mode').textContent = mode;
        document.getElementById('overview-mode').className = `mode-badge mode-${mode.toLowerCase()}`;
        document.getElementById('overview-engines-count').textContent = runningEngines;

        // Portfolio Snapshot Card
        if (portfolio) {
            document.getElementById('overview-equity').textContent = Components.formatCurrency(portfolio.equity);
            document.getElementById('overview-pnl').textContent = Components.formatCurrency(portfolio.daily_pnl);
            document.getElementById('overview-pnl').className = `value ${Components.getValueClass(portfolio.daily_pnl)}`;
            document.getElementById('overview-exposure').textContent = Components.formatPercentage(portfolio.exposure_pct);
            document.getElementById('overview-positions').textContent = portfolio.position_count || 0;
        }

        // Today Summary Card
        if (todaySummary) {
            document.getElementById('overview-trades').textContent = todaySummary.num_trades || 0;
            document.getElementById('overview-win-rate').textContent = `${(todaySummary.win_rate || 0).toFixed(1)}%`;
            document.getElementById('overview-realized-pnl').textContent = Components.formatCurrency(todaySummary.realized_pnl);
            document.getElementById('overview-realized-pnl').className = `value ${Components.getValueClass(todaySummary.realized_pnl)}`;
        }

        // Recent Signals Card
        const signalsHtml = (signals || []).slice(0, 5).map(s => `
            <tr>
                <td>${Components.formatTime(s.ts)}</td>
                <td>${s.symbol || '—'}</td>
                <td><span class="signal-badge signal-${s.signal}">${s.signal}</span></td>
                <td>${s.strategy || '—'}</td>
            </tr>
        `).join('');
        document.getElementById('overview-signals-body').innerHTML = signalsHtml || '<tr><td colspan="4">No recent signals</td></tr>';
    }

    /**
     * Render Engines & Logs Tab
     */
    function renderEngines(state) {
        const { engines, logs } = state;

        // Engines Status Table
        const enginesHtml = (engines || []).map(e => `
            <tr>
                <td>${e.engine}</td>
                <td><span class="badge badge-${e.mode}">${e.mode}</span></td>
                <td><span class="status-indicator status-${e.running ? 'running' : 'stopped'}"></span> ${e.running ? 'Running' : 'Stopped'}</td>
                <td>${Components.formatDateTime(e.last_checkpoint_ts) || '—'}</td>
                <td>${e.checkpoint_age_seconds ? `${e.checkpoint_age_seconds.toFixed(1)}s ago` : '—'}</td>
            </tr>
        `).join('');
        document.getElementById('engines-table-body').innerHTML = enginesHtml || '<tr><td colspan="5">No engines</td></tr>';

        // Logs Table
        const logsHtml = (logs || []).slice(-100).reverse().map(log => `
            <tr class="log-${log.level?.toLowerCase() || 'info'}">
                <td class="log-time">${Components.formatTime(log.timestamp || log.ts)}</td>
                <td class="log-level"><span class="level-badge level-${log.level?.toLowerCase() || 'info'}">${log.level || 'INFO'}</span></td>
                <td class="log-source">${log.source || log.logger || '—'}</td>
                <td class="log-message">${log.message || ''}</td>
            </tr>
        `).join('');
        document.getElementById('logs-table-body').innerHTML = logsHtml || '<tr><td colspan="4">No logs</td></tr>';
    }

    /**
     * Render Portfolio Tab (LIVE REFRESH)
     */
    function renderPortfolio(state) {
        const { portfolio, positionsOpen, orders, todaySummary } = state;

        // Portfolio Summary Card
        if (portfolio) {
            document.getElementById('portfolio-equity').textContent = Components.formatCurrency(portfolio.equity);
            document.getElementById('portfolio-capital').textContent = Components.formatCurrency(portfolio.paper_capital);
            document.getElementById('portfolio-realized').textContent = Components.formatCurrency(portfolio.total_realized_pnl);
            document.getElementById('portfolio-realized').className = `value ${Components.getValueClass(portfolio.total_realized_pnl)}`;
            document.getElementById('portfolio-unrealized').textContent = Components.formatCurrency(portfolio.total_unrealized_pnl);
            document.getElementById('portfolio-unrealized').className = `value ${Components.getValueClass(portfolio.total_unrealized_pnl)}`;
            document.getElementById('portfolio-exposure').textContent = Components.formatPercentage(portfolio.exposure_pct);
        }

        // Open Positions Table
        const positionsHtml = (positionsOpen || []).map(pos => {
            const pnlPct = pos.avg_price ? ((pos.last_price - pos.avg_price) / pos.avg_price * 100) : 0;
            return `
                <tr>
                    <td>${pos.symbol}</td>
                    <td><span class="side-badge side-${pos.side?.toLowerCase()}">${pos.side}</span></td>
                    <td>${pos.quantity}</td>
                    <td>${Components.formatCurrency(pos.avg_price)}</td>
                    <td>${Components.formatCurrency(pos.last_price)}</td>
                    <td class="${Components.getValueClass(pos.unrealized_pnl)}">${Components.formatCurrency(pos.unrealized_pnl)}</td>
                    <td class="${Components.getValueClass(pnlPct)}">${pnlPct.toFixed(2)}%</td>
                </tr>
            `;
        }).join('');
        document.getElementById('positions-table-body').innerHTML = positionsHtml || '<tr><td colspan="7">No open positions</td></tr>';

        // Orders Table
        const ordersHtml = (orders || []).slice(0, 20).map(order => `
            <tr>
                <td>${Components.formatTime(order.timestamp || order.ts || order.time)}</td>
                <td>${order.symbol || '—'}</td>
                <td><span class="side-badge side-${order.side?.toLowerCase()}">${order.side || '—'}</span></td>
                <td>${order.quantity || order.qty || '—'}</td>
                <td>${Components.formatCurrency(order.price)}</td>
                <td><span class="status-badge status-${order.status?.toLowerCase()}">${order.status || '—'}</span></td>
                <td>${order.order_id || '—'}</td>
            </tr>
        `).join('');
        document.getElementById('orders-table-body').innerHTML = ordersHtml || '<tr><td colspan="7">No orders</td></tr>';

        // Today Summary
        if (todaySummary) {
            document.getElementById('portfolio-today-pnl').textContent = Components.formatCurrency(todaySummary.realized_pnl);
            document.getElementById('portfolio-today-pnl').className = `value ${Components.getValueClass(todaySummary.realized_pnl)}`;
            document.getElementById('portfolio-today-trades').textContent = todaySummary.num_trades || 0;
            document.getElementById('portfolio-today-winrate').textContent = `${(todaySummary.win_rate || 0).toFixed(1)}%`;
        }
    }

    /**
     * Render Signals & Strategies Tab
     */
    function renderSignals(state) {
        const { signals, strategies } = state;

        // Strategies Table
        const strategiesHtml = (strategies || []).map(s => `
            <tr>
                <td>${s.logical || s.strategy}</td>
                <td>${s.symbol || '—'}</td>
                <td>${s.timeframe || '—'}</td>
                <td>${s.buy_count || 0}</td>
                <td>${s.sell_count || 0}</td>
                <td>${s.exit_count || 0}</td>
                <td>${Components.formatTime(s.last_ts)}</td>
                <td><span class="signal-badge signal-${s.last_signal}">${s.last_signal || '—'}</span></td>
            </tr>
        `).join('');
        document.getElementById('strategies-table-body').innerHTML = strategiesHtml || '<tr><td colspan="8">No strategy data</td></tr>';

        // Recent Signals Table
        const signalsHtml = (signals || []).slice(0, 30).map(s => `
            <tr>
                <td>${Components.formatTime(s.ts)}</td>
                <td>${s.symbol || '—'}</td>
                <td><span class="signal-badge signal-${s.signal}">${s.signal}</span></td>
                <td>${s.strategy || '—'}</td>
                <td>${s.tf || '—'}</td>
                <td>${Components.formatCurrency(s.price)}</td>
            </tr>
        `).join('');
        document.getElementById('signals-table-body').innerHTML = signalsHtml || '<tr><td colspan="6">No signals</td></tr>';
    }

    /**
     * Render Analytics Tab
     */
    function renderAnalytics(state) {
        const { equityCurve, analyticsSummary } = state;

        // Check if we have equity data
        const chartEl = document.getElementById('analytics-equity-chart');
        if (chartEl) {
            if (!equityCurve || equityCurve.length === 0) {
                chartEl.innerHTML = '<p class="placeholder-text">No equity curve data available. The engine needs to record snapshots during trading.</p>';
            } else {
                // Render equity chart (placeholder for now - needs chart library)
                chartEl.innerHTML = `<p class="placeholder-text">Equity chart: ${equityCurve.length} data points available. Chart library integration needed.</p>`;
            }
        }

        // Analytics summary
        if (analyticsSummary && analyticsSummary.daily) {
            const daily = analyticsSummary.daily;
            const realizedEl = document.getElementById('analytics-realized-pnl');
            const tradesEl = document.getElementById('analytics-trades');
            const winrateEl = document.getElementById('analytics-winrate');
            const avgWinEl = document.getElementById('analytics-avg-win');
            const avgLossEl = document.getElementById('analytics-avg-loss');
            
            if (realizedEl) realizedEl.textContent = Components.formatCurrency(daily.realized_pnl);
            if (tradesEl) tradesEl.textContent = daily.num_trades || 0;
            if (winrateEl) winrateEl.textContent = `${(daily.win_rate || 0).toFixed(1)}%`;
            if (avgWinEl) avgWinEl.textContent = Components.formatCurrency(daily.avg_win);
            if (avgLossEl) avgLossEl.textContent = Components.formatCurrency(daily.avg_loss);
        } else {
            const placeholderEl = document.getElementById('analytics-placeholder');
            if (placeholderEl) {
                placeholderEl.innerHTML = '<p class="placeholder-text">Analytics data is being computed...</p>';
            }
        }

        // Note about missing backend features
        const notesEl = document.getElementById('analytics-notes');
        if (notesEl) {
            notesEl.innerHTML = `
                <div class="info-box">
                    <strong>Note:</strong> Advanced analytics features like NIFTY/BANKNIFTY benchmark comparison 
                    would require additional backend endpoints:
                    <ul>
                        <li><code>GET /api/perf/benchmark?symbol=NIFTY&days=1</code></li>
                        <li><code>GET /api/perf/sharpe</code> for risk-adjusted metrics</li>
                    </ul>
                </div>
            `;
        }
    }

    /**
     * Render System Tab
     */
    function renderSystem(state) {
        const { config, health, meta } = state;

        // System Info
        if (meta) {
            document.getElementById('system-time').textContent = Components.formatDateTime(meta.now_ist);
            document.getElementById('system-market-status').textContent = meta.market_status || '—';
        }

        // Config Summary
        if (config) {
            document.getElementById('config-mode').textContent = config.mode || '—';
            document.getElementById('config-universe').textContent = (config.fno_universe || []).join(', ') || '—';
            document.getElementById('config-capital').textContent = Components.formatCurrency(config.paper_capital);
            document.getElementById('config-risk-profile').textContent = config.risk_profile || '—';
            document.getElementById('config-risk-per-trade').textContent = Components.formatPercentage(config.risk_per_trade_pct);
            document.getElementById('config-max-exposure').textContent = Components.formatPercentage(config.max_exposure_pct);
        }

        // Health Info
        if (health) {
            const logHealth = health.log_health || {};
            document.getElementById('health-errors').textContent = logHealth.error_count_recent || 0;
            document.getElementById('health-warnings').textContent = logHealth.warning_count_recent || 0;
        }
    }

    // Public API
    return {
        init,
        switchTab,
        registerTab,
        renderTab,
    };
})();
