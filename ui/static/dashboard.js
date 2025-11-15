async function fetchJSON(url) {
  const res = await fetch(url, { cache: "no-store" });
  if (!res.ok) {
    throw new Error(res.status + " " + res.statusText);
  }
  return res.json();
}

function formatMoney(v) {
  const value = Number(v);
  if (Number.isNaN(value)) return "\u20b90";
  const sign = value < 0 ? "-" : "";
  const num = Math.abs(value).toFixed(0);
  return sign + "\u20b9" + Number(num).toLocaleString("en-IN");
}

function formatPct(v, decimals = 1) {
  if (v === null || v === undefined || Number.isNaN(Number(v))) return "0.0%";
  return Number(v).toFixed(decimals) + "%";
}

function kpiClassForValue(v) {
  if (v > 0) return "kpi-main pos";
  if (v < 0) return "kpi-main neg";
  return "kpi-main";
}

const LOG_TAB_KINDS = {
  engine: "engine",
  trades: "trades",
  signals: "signals",
  system: "system",
};

const LOG_LEVEL_META = {
  INFO: { icon: "ℹ️", cls: "log-info" },
  WARN: { icon: "⚠️", cls: "log-warn" },
  ERROR: { icon: "❗", cls: "log-error" },
  DEBUG: { icon: "🐞", cls: "log-debug" },
};

let activeLogTab = "engine";
let followLogTail = true;
let logRefreshTimer = null;
let serverClockOffsetMs = null;
let logClockTimer = null;
let serverClockPollTimer = null;

let backtestRunsIndex = [];
let backtestRunsByStrategy = new Map();
let backtestSelectedStrategy = "";
let backtestSelectedPath = "";
let backtestCurrentData = null;

    /* ---------- Header pills ---------- */

    function setPill(pillId, dotId, status, labelValue) {
      const pill = document.getElementById(pillId);
      const dot  = document.getElementById(dotId);
      const valueEl = pill?.querySelector(".pill-value");
      if (!pill || !dot || !valueEl) return;

      let color = "amber";
      if (status === "ok" || status === "open" || status === "running") color = "green";
      if (status === "bad" || status === "closed") color = "red";

      dot.className = "pill-dot " + color;
      valueEl.textContent = labelValue;
    }

    async function updateHeaderPills() {
      try {
        const [eng, auth] = await Promise.all([
          fetchJSON("/api/engines/status"),
          fetchJSON("/api/auth/status"),
        ]);

        const e = (eng.engines || [])[0] || {};
        setPill("pill-engine", "pill-engine-dot", e.running ? "running" : "bad", e.running ? "Running" : "Offline");

        const marketOpen = !!e.market_open;
        setPill("pill-market", "pill-market-dot", marketOpen ? "open" : "closed", marketOpen ? "Open" : "Closed");

        const goodAuth = !!auth.is_logged_in && auth.token_valid;
        setPill("pill-auth", "pill-auth-dot", goodAuth ? "ok" : "bad", goodAuth ? (auth.user_id || "OK") : "Login");
      } catch (err) {
        setPill("pill-engine", "pill-engine-dot", "bad", "Error");
        setPill("pill-market", "pill-market-dot", "bad", "Error");
        setPill("pill-auth", "pill-auth-dot", "bad", "Error");
      }
    }

    /* ---------- Top KPIs ---------- */

    async function renderTopKpis() {
      const eqEl  = document.getElementById("kpi-equity-body");
      const pnlEl = document.getElementById("kpi-daypnl-body");
      const trEl  = document.getElementById("kpi-trades-body");
      const riskEl = document.getElementById("kpi-risk-body");

      try {
        const [today, port, cfg] = await Promise.all([
          fetchJSON("/api/summary/today"),
          fetchJSON("/api/portfolio/summary"),
          fetchJSON("/api/config/summary"),
        ]);

        const realized = today.realized_pnl ?? 0;
        const unreal = port.total_unrealized_pnl ?? 0;
        const dayPnl = (realized || 0) + (unreal || 0);
        const winRate = today.win_rate ?? today.winRate ?? 0;

        // Equity
        const equity = port.equity ?? (port.paper_capital || 0);
        eqEl.innerHTML = `
          <div class="${kpiClassForValue(equity - (port.paper_capital || 0))}">
            ${formatMoney(equity)}
          </div>
          <div class="kpi-label">Starting: ${formatMoney(port.paper_capital || 0)}</div>
          <div class="kpi-extra">
            <span>Realized: <strong>${formatMoney(port.total_realized_pnl || 0)}</strong></span>
            <span>Unrealized: <strong>${formatMoney(port.total_unrealized_pnl || 0)}</strong></span>
          </div>
        `;

        // Day PnL
        pnlEl.innerHTML = `
          <div class="${kpiClassForValue(dayPnl)}">
            ${formatMoney(dayPnl)}
          </div>
          <div class="kpi-label">Today</div>
          <div class="kpi-extra">
            <span>Realized: <strong>${formatMoney(realized || 0)}</strong></span>
            <span>Unrealized: <strong>${formatMoney(unreal || 0)}</strong></span>
          </div>
        `;

        // Trades
        const trades = today.num_trades ?? today.trades ?? 0;
        trEl.innerHTML = `
          <div class="kpi-main">${trades}</div>
          <div class="kpi-label">Filled orders</div>
          <div class="kpi-extra">
            <span>Win: <strong>${today.win_trades ?? 0}</strong></span>
            <span>Loss: <strong>${today.loss_trades ?? 0}</strong></span>
            <span>Win rate: <strong>${formatPct(winRate, 1)}</strong></span>
          </div>
        `;

        // Risk
        const r = cfg || {};
        const riskPct = (r.risk_per_trade_pct ?? 0) * 100;
        const maxExp = (r.max_exposure_pct ?? 0) * 100;
        const expPct = port.exposure_pct != null ? port.exposure_pct * 100 : null;
        riskEl.innerHTML = `
          <div class="kpi-main">${(r.risk_profile || "Default")}</div>
          <div class="kpi-label">Risk mode</div>
          <div class="kpi-extra">
            <span>Risk / trade: <strong>${riskPct.toFixed(2)}%</strong></span>
            <span>Max exposure: <strong>${maxExp.toFixed(1)}%</strong></span>
            <span>Current exposure: <strong>${expPct != null ? expPct.toFixed(1) + "%" : "—"}</strong></span>
          </div>
        `;
      } catch (err) {
        const html = `<div class="error">Failed to load KPIs</div>`;
        eqEl.innerHTML = pnlEl.innerHTML = trEl.innerHTML = riskEl.innerHTML = html;
      }
    }

    /* ---------- Equity curve ---------- */

    async function renderEquity() {
      const canvas = document.getElementById("equity-canvas");
      const left = document.getElementById("equity-summary-left");
      const right = document.getElementById("equity-summary-right");
      if (!canvas) return;

      const ctx = canvas.getContext("2d");

      function resize() {
        const rect = canvas.getBoundingClientRect();
        canvas.width = rect.width * window.devicePixelRatio;
        canvas.height = rect.height * window.devicePixelRatio;
        ctx.setTransform(window.devicePixelRatio, 0, 0, window.devicePixelRatio, 0, 0);
      }
      resize();

      try {
        const data = await fetchJSON("/api/stats/equity?days=1");
        if (!Array.isArray(data) || data.length === 0) {
          ctx.clearRect(0, 0, canvas.width, canvas.height);
          ctx.fillStyle = "#6b7280";
          ctx.font = "11px " + getComputedStyle(document.body).fontFamily;
          ctx.fillText("No equity snapshots yet.", 12, 20);
          left.textContent = "";
          right.textContent = "";
          return;
        }

        const points = data
          .map(d => ({
            ts: new Date(d.ts),
            equity: Number(d.equity ?? d.equity_curve ?? d.equityCurve ?? 0),
          }))
          .filter(p => !isNaN(p.equity));

        if (!points.length) {
          ctx.clearRect(0, 0, canvas.width, canvas.height);
          ctx.fillStyle = "#6b7280";
          ctx.font = "11px " + getComputedStyle(document.body).fontFamily;
          ctx.fillText("No equity data.", 12, 20);
          left.textContent = "";
          right.textContent = "";
          return;
        }

        const w = canvas.width / window.devicePixelRatio;
        const h = canvas.height / window.devicePixelRatio;
        const padding = 18;
        const x0 = padding;
        const x1 = w - padding;
        const y0 = h - padding;
        const y1 = padding;

        const minEq = Math.min(...points.map(p => p.equity));
        const maxEq = Math.max(...points.map(p => p.equity));
        const t0 = points[0].ts.getTime();
        const t1 = points[points.length - 1].ts.getTime() || t0 + 1;
        const eqMin = minEq === maxEq ? minEq - 1 : minEq;
        const eqMax = minEq === maxEq ? maxEq + 1 : maxEq;

        function xs(t) {
          if (t1 === t0) return (x0 + x1) / 2;
          return x0 + (x1 - x0) * ((t - t0) / (t1 - t0));
        }
        function ys(eq) {
          if (eqMax === eqMin) return (y0 + y1) / 2;
          return y0 - (y0 - y1) * ((eq - eqMin) / (eqMax - eqMin));
        }

        ctx.clearRect(0, 0, w, h);

        // axes
        ctx.strokeStyle = "rgba(148, 163, 184, 0.5)";
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(x0, y1);
        ctx.lineTo(x0, y0);
        ctx.lineTo(x1, y0);
        ctx.stroke();

        // equity line
        ctx.beginPath();
        ctx.strokeStyle = "#38bdf8";
        ctx.lineWidth = 1.8;
        points.forEach((p, i) => {
          const x = xs(p.ts.getTime());
          const y = ys(p.equity);
          if (i === 0) ctx.moveTo(x, y);
          else ctx.lineTo(x, y);
        });
        ctx.stroke();

        // fill under curve
        const gradient = ctx.createLinearGradient(0, y1, 0, y0);
        gradient.addColorStop(0, "rgba(56, 189, 248, 0.35)");
        gradient.addColorStop(1, "rgba(15, 23, 42, 0)");
        ctx.fillStyle = gradient;
        ctx.lineTo(xs(points[points.length - 1].ts.getTime()), y0);
        ctx.lineTo(xs(points[0].ts.getTime()), y0);
        ctx.closePath();
        ctx.fill();

        const firstEq = points[0].equity;
        const lastEq = points[points.length - 1].equity || firstEq;
        const delta = lastEq - firstEq;
        const deltaPct = firstEq ? (delta / firstEq) * 100 : 0;

        left.textContent =
          "Points: " + points.length +
          " · Start: " + formatMoney(firstEq) +
          " · End: " + formatMoney(lastEq);
        right.textContent =
          "Δ: " + formatMoney(delta) +
          " (" + deltaPct.toFixed(2) + "%)";
      } catch (err) {
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        ctx.fillStyle = "#f97373";
        ctx.font = "11px " + getComputedStyle(document.body).fontFamily;
        ctx.fillText("Failed to load equity curve.", 12, 20);
        left.textContent = "";
        right.textContent = "";
      }
    }

    /* ---------- Trade flow ---------- */

    async function renderTradeFlow() {
      const el = document.getElementById("tradeflow-body");
      try {
        const snap = await fetchJSON("/api/monitor/trade_flow");
        const tf = snap.trade_flow || {};
        const funnel = snap.funnel || [];

        const stagesHtml = funnel.map(f => `
          <tr>
            <td>${f.label}</td>
            <td>${f.count ?? 0}</td>
            <td class="muted">${f.last_ts ?? "—"}</td>
          </tr>
        `).join("");

        el.innerHTML = `
          <table>
            <thead>
              <tr>
                <th>Stage</th>
                <th>Count</th>
                <th>Last event</th>
              </tr>
            </thead>
            <tbody>
              ${stagesHtml || `<tr><td colspan="3" class="muted">No trade activity yet.</td></tr>`}
            </tbody>
          </table>
          <div class="muted" style="margin-top:4px;">
            Risk blocks: ${tf.risk_blocks ?? 0} · Time blocks: ${tf.time_blocks ?? 0} ·
            Stops: ${tf.stop_hits ?? 0} · Targets: ${tf.target_hits ?? 0}
          </div>
        `;
      } catch (err) {
        el.innerHTML = `<div class="error">Failed to load trade pipe.</div>`;
      }
    }

    /* ---------- Engine & Config/Auth ---------- */

    async function renderEngine() {
      const el = document.getElementById("engine-body");
      try {
        const data = await fetchJSON("/api/engines/status");
        const e = (data.engines || [])[0] || {};

        const status = e.running ? "Running" : "Offline";
        el.innerHTML = `
          <div class="stat-list">
            <div>
              <div class="stat-label">Engine</div>
              <div class="stat-value">${e.engine || "fno_paper"}</div>
            </div>
            <div>
              <div class="stat-label">Status</div>
              <div class="stat-value">${status}</div>
            </div>
            <div>
              <div class="stat-label">Market</div>
              <div class="stat-value">${e.market_open ? "Open" : "Closed"}</div>
            </div>
            <div>
              <div class="stat-label">Checkpoint age</div>
              <div class="stat-value">${(e.checkpoint_age_seconds ?? 0).toFixed(0)}s</div>
            </div>
          </div>
          <div class="muted" style="margin-top:4px;">
            Checkpoint: ${e.last_checkpoint_ts || "—"}
          </div>
        `;
      } catch (err) {
        el.innerHTML = `<div class="error">Failed to load engine state.</div>`;
      }
    }

    async function renderConfigAuth() {
      const el = document.getElementById("config-body");
      try {
        const [cfg, auth] = await Promise.all([
          fetchJSON("/api/config/summary"),
          fetchJSON("/api/auth/status"),
        ]);

        const uni = (cfg.fno_universe || []).join(", ") || "—";
        el.innerHTML = `
          <div class="stat-list">
            <div>
              <div class="stat-label">Mode</div>
              <div class="stat-value">${(cfg.mode || "").toUpperCase()}</div>
            </div>
            <div>
              <div class="stat-label">Paper capital</div>
              <div class="stat-value">${formatMoney(cfg.paper_capital || 0)}</div>
            </div>
            <div>
              <div class="stat-label">Universe</div>
              <div class="stat-value">${uni}</div>
            </div>
            <div>
              <div class="stat-label">User / Token</div>
              <div class="stat-value">
                ${auth.user_id || "—"}
                <span class="pill-small" style="margin-left:4px;">
                  <strong>${auth.token_valid ? "TOKEN OK" : "LOGIN"}</strong>
                </span>
              </div>
            </div>
          </div>
          <div class="muted" style="margin-top:4px;">
            Last login: ${auth.login_ts || "—"}
          </div>
        `;
      } catch (err) {
        el.innerHTML = `<div class="error">Failed to load config/auth.</div>`;
      }
    }

    /* ---------- Signals ---------- */

    function badgeForSignal(sig) {
      const s = (sig || "").toUpperCase();
      if (!s) return "";
      const cls = "badge-signal-" + s;
      return `<span class="badge ${cls}">${s}</span>`;
    }

    async function renderSignals() {
      const el = document.getElementById("signals-body");
      try {
        const rows = await fetchJSON("/api/signals/recent?limit=40");
        if (!Array.isArray(rows) || !rows.length) {
          el.innerHTML = `<div class="muted">No recent signals.</div>`;
          return;
        }
        const htmlRows = rows.slice(-40).reverse().map(r => {
          const ts = r.ts || r.timestamp || "";
          const sym = r.symbol || "";
          const tf = r.tf || r.timeframe || "";
          const strat = r.strategy || "";
          const price = r.price != null ? Number(r.price).toFixed(2) : "—";
          const sig = (r.signal || "").toUpperCase();
          return `
            <tr>
              <td class="mono">${ts.slice(11, 19)}</td>
              <td>${sym}</td>
              <td>${tf}</td>
              <td>${strat}</td>
              <td>${badgeForSignal(sig)}</td>
              <td class="mono">${price}</td>
            </tr>
          `;
        }).join("");
        el.innerHTML = `
          <table class="row-striped">
            <thead>
              <tr>
                <th>Time</th>
                <th>Symbol</th>
                <th>TF</th>
                <th>Strategy</th>
                <th>Signal</th>
                <th>Price</th>
              </tr>
            </thead>
            <tbody>
              ${htmlRows}
            </tbody>
          </table>
        `;
      } catch (err) {
        el.innerHTML = `<div class="error">Failed to load signals.</div>`;
      }
    }

    /* ---------- Orders ---------- */

    function badgeForStatus(status) {
      const s = (status || "").toUpperCase();
      if (!s) return "";
      const cls = "badge-status-" + s;
      return `<span class="badge ${cls}">${s}</span>`;
    }

    async function renderOrders() {
      const el = document.getElementById("orders-body");
      try {
        const rows = await fetchJSON("/api/orders/recent?limit=40");
        if (!Array.isArray(rows) || !rows.length) {
          el.innerHTML = `<div class="muted">No recent orders.</div>`;
          return;
        }
        const htmlRows = rows.slice(-40).reverse().map(r => {
          const ts = r.ts || r.timestamp || "";
          const sym = r.symbol || "";
          const side = (r.side || r.transaction_type || "").toUpperCase();
          const qty = r.quantity ?? r.qty ?? r.filled_quantity ?? 0;
          const price = r.price != null ? Number(r.price).toFixed(2) :
                        (r.avg_price != null ? Number(r.avg_price).toFixed(2) : "—");
          const status = (r.status || "").toUpperCase();
          const strat = r.strategy || "";
          return `
            <tr>
              <td class="mono">${ts.slice(11, 19)}</td>
              <td>${sym}</td>
              <td>${side}</td>
              <td>${qty}</td>
              <td class="mono">${price}</td>
              <td>${badgeForStatus(status)}</td>
              <td>${strat}</td>
            </tr>
          `;
        }).join("");
        el.innerHTML = `
          <table class="row-striped">
            <thead>
              <tr>
                <th>Time</th>
                <th>Symbol</th>
                <th>Side</th>
                <th>Qty</th>
                <th>Price</th>
                <th>Status</th>
                <th>Strategy</th>
              </tr>
            </thead>
            <tbody>
              ${htmlRows}
            </tbody>
          </table>
        `;
      } catch (err) {
        el.innerHTML = `<div class="error">Failed to load orders.</div>`;
      }
    }

    /* ---------- Logs ---------- */

    function formatLogTimestamp(ts) {
      if (!ts) {
        return "--:--:--";
      }
      const date = new Date(ts);
      if (Number.isNaN(date.getTime())) {
        return ts;
      }
      const hh = String(date.getHours()).padStart(2, "0");
      const mm = String(date.getMinutes()).padStart(2, "0");
      const ss = String(date.getSeconds()).padStart(2, "0");
      return `${hh}:${mm}:${ss}`;
    }

    function updateLogsClockDisplay() {
      const clock = document.getElementById("logs-clock");
      if (!clock) return;
      const now = serverClockOffsetMs == null
        ? new Date()
        : new Date(Date.now() - serverClockOffsetMs);
      const hh = String(now.getHours()).padStart(2, "0");
      const mm = String(now.getMinutes()).padStart(2, "0");
      const ss = String(now.getSeconds()).padStart(2, "0");
      clock.textContent = `${hh}:${mm}:${ss}`;
    }

    async function pollServerTime() {
      try {
        const data = await fetchJSON("/api/system/time");
        const utc = data?.utc;
        if (utc) {
          const ts = Date.parse(utc);
          if (!Number.isNaN(ts)) {
            serverClockOffsetMs = Date.now() - ts;
          }
        }
      } catch (err) {
        serverClockOffsetMs = null;
      } finally {
        updateLogsClockDisplay();
      }
    }

    function startServerClock() {
      if (!logClockTimer) {
        logClockTimer = setInterval(updateLogsClockDisplay, 1_000);
      }
      if (!serverClockPollTimer) {
        pollServerTime();
        serverClockPollTimer = setInterval(pollServerTime, 5_000);
      }
    }

    function setActiveLogTab(tabName, force = false) {
      const target = tabName || "engine";
      if (!force && target === activeLogTab) {
        return;
      }
      activeLogTab = target;
      document.querySelectorAll(".log-tab").forEach((btn) => {
        btn.classList.toggle("active", btn.dataset.logTab === target);
      });
      fetchLogStream();
      scheduleLogRefresh();
    }

    function renderLogEntries(entries) {
      const viewer = document.getElementById("log-viewer");
      if (!viewer) return;
      if (!Array.isArray(entries) || entries.length === 0) {
        viewer.innerHTML = `<div class="muted">No log entries yet.</div>`;
        return;
      }

      const lines = entries
        .map((entry) => {
          const level = (entry.level || "INFO").toUpperCase();
          const meta = LOG_LEVEL_META[level] || LOG_LEVEL_META.INFO;
          const loggerName = entry.logger || "engine";
          const message = entry.message || "";
          const time = formatLogTimestamp(entry.ts);
          return `
            <div class="log-line ${meta.cls}">
              <span class="log-time">[${time}]</span>
              <span class="log-level">${meta.icon} ${level}</span>
              <span class="log-message"><span class="log-source">${loggerName}:</span> ${message}</span>
            </div>
          `;
        })
        .join("");

      viewer.innerHTML = lines;
      if (followLogTail) {
        viewer.scrollTop = viewer.scrollHeight;
      }
    }

    async function fetchLogStream() {
      const viewer = document.getElementById("log-viewer");
      if (!viewer) return;
      const params = new URLSearchParams({ limit: "150" });
      const kind = LOG_TAB_KINDS[activeLogTab];
      if (kind) {
        params.set("kind", kind);
      }
      const endpoint = `/api/logs?${params.toString()}`;
      try {
        const payload = await fetchJSON(endpoint);
        const entries = payload.logs || payload.entries || [];
        renderLogEntries(entries);
      } catch (err) {
        viewer.innerHTML = `<div class="error">Failed to load logs.</div>`;
      }
    }

    function scheduleLogRefresh() {
      if (logRefreshTimer) {
        clearInterval(logRefreshTimer);
      }
      logRefreshTimer = setInterval(fetchLogStream, 5_000);
    }

    function bindLogScrollControls() {
      const viewer = document.getElementById("log-viewer");
      const followToggle = document.getElementById("log-follow");
      if (!viewer) return;

      viewer.addEventListener("scroll", () => {
        const nearBottom = viewer.scrollHeight - viewer.scrollTop - viewer.clientHeight < 18;
        if (!nearBottom && followLogTail) {
          followLogTail = false;
          if (followToggle) {
            followToggle.checked = false;
          }
        } else if (nearBottom && followToggle && followToggle.checked) {
          followLogTail = true;
        }
      });

      if (followToggle) {
        followToggle.checked = true;
        followToggle.addEventListener("change", (event) => {
          followLogTail = !!event.target.checked;
          if (followLogTail) {
            viewer.scrollTop = viewer.scrollHeight;
          }
        });
      }
    }

    function initLogConsole() {
      const viewer = document.getElementById("log-viewer");
      const tabs = document.querySelectorAll(".log-tab");
      if (!viewer || !tabs.length) {
        return;
      }

      tabs.forEach((btn) => {
        btn.addEventListener("click", () => {
          const target = btn.dataset.logTab || "engine";
          setActiveLogTab(target);
        });
      });

      bindLogScrollControls();
      setActiveLogTab(activeLogTab, true);
      startServerClock();
    }

    /* ---------- Strategy Performance ---------- */

    async function renderStrategies() {
      const el = document.getElementById("strategies-body");
      try {
        const data = await fetchJSON("/api/strategy_performance");
        const perStrat = data.per_strategy || [];
        if (!perStrat.length) {
          el.innerHTML = `<div class="muted">No strategy performance yet (backend may not be writing trades).</div>`;
          return;
        }

        const rows = perStrat.map(s => {
          const pnl = Number(s.realized_pnl || 0);
          const pnlCls = pnl > 0 ? "kpi-main pos" : (pnl < 0 ? "kpi-main neg" : "kpi-main");
          return `
            <tr>
              <td>${s.strategy}</td>
              <td>${s.round_trips ?? 0}</td>
              <td>${s.num_orders ?? 0}</td>
              <td class="mono">${formatMoney(s.total_notional || 0)}</td>
              <td class="${pnlCls}" style="font-size:11px;">${formatMoney(pnl)}</td>
            </tr>
          `;
        }).join("");

        el.innerHTML = `
          <table class="row-striped">
            <thead>
              <tr>
                <th>Strategy</th>
                <th>Round trips</th>
                <th>Orders</th>
                <th>Notional</th>
                <th>Realized PnL</th>
              </tr>
            </thead>
            <tbody>
              ${rows}
            </tbody>
          </table>
          <div class="muted" style="margin-top:4px;">
            Data from /api/strategy_performance
            ${perStrat.length ? "" : "(backend wiring pending)"}
          </div>
        `;
      } catch (err) {
        el.innerHTML = `<div class="error">Failed to load strategy performance (is /api/strategy_performance implemented?).</div>`;
      }
    }

    /* ---------- Backtests ---------- */

    async function refreshBacktestRuns() {
      try {
        const payload = await fetchJSON("/api/backtests/list");
        backtestRunsIndex = Array.isArray(payload.runs) ? payload.runs : [];
        backtestRunsByStrategy = new Map();
        backtestRunsIndex.forEach((run) => {
          if (!run || !run.strategy) return;
          const bucket = backtestRunsByStrategy.get(run.strategy) || [];
          bucket.push(run);
          backtestRunsByStrategy.set(run.strategy, bucket);
        });
        backtestRunsByStrategy.forEach((runs) => runs.sort((a, b) => b.run.localeCompare(a.run)));
        populateBacktestStrategies();
      } catch (err) {
        const summaryEl = document.getElementById("backtest-summary");
        if (summaryEl) {
          summaryEl.innerHTML = `<div class="error">Failed to load backtest runs: ${err.message || err}</div>`;
        }
      }
    }

    function populateBacktestStrategies() {
      const select = document.getElementById("backtest-strategy");
      const runSelect = document.getElementById("backtest-run");
      const summaryEl = document.getElementById("backtest-summary");
      if (!select || !runSelect || !summaryEl) return;

      const strategies = Array.from(backtestRunsByStrategy.keys());
      select.innerHTML = `<option value="">Select strategy</option>`;
      strategies.forEach((strategy) => {
        const opt = document.createElement("option");
        opt.value = strategy;
        opt.textContent = strategy;
        if (strategy === backtestSelectedStrategy) {
          opt.selected = true;
        }
        select.appendChild(opt);
      });

      if (!strategies.length) {
        runSelect.innerHTML = `<option value="">Select run</option>`;
        runSelect.disabled = true;
        resetBacktestSections("No backtest runs available.");
        updateBacktestDownload(null);
        return;
      }

      if (!strategies.includes(backtestSelectedStrategy)) {
        backtestSelectedStrategy = "";
        if (strategies.length === 1) {
          backtestSelectedStrategy = strategies[0];
          select.value = backtestSelectedStrategy;
        }
      }
      populateBacktestRuns();
    }

    function populateBacktestRuns() {
      const runSelect = document.getElementById("backtest-run");
      if (!runSelect) return;
      runSelect.innerHTML = `<option value="">Select run</option>`;
      if (!backtestSelectedStrategy) {
        runSelect.disabled = true;
        resetBacktestSections("Select a strategy to view runs.");
        updateBacktestDownload(null);
        return;
      }
      const runs = backtestRunsByStrategy.get(backtestSelectedStrategy) || [];
      runs.forEach((run) => {
        const opt = document.createElement("option");
        opt.value = run.path;
        opt.textContent = run.run;
        if (run.path === backtestSelectedPath) {
          opt.selected = true;
        }
        runSelect.appendChild(opt);
      });
      runSelect.disabled = runs.length === 0;
      if (!runs.length) {
        resetBacktestSections("No runs found for this strategy.");
        updateBacktestDownload(null);
        return;
      }
      if (!runs.find((run) => run.path === backtestSelectedPath)) {
        backtestSelectedPath = "";
        runSelect.value = "";
        resetBacktestSections("Select a backtest run to view details.");
        updateBacktestDownload(null);
      } else if (backtestSelectedPath) {
        loadBacktestResult(backtestSelectedPath);
      }
    }

    function resetBacktestSections(message) {
      const summaryEl = document.getElementById("backtest-summary");
      const tradesEl = document.getElementById("backtest-trades");
      const canvas = document.getElementById("backtest-equity");
      if (summaryEl) {
        summaryEl.innerHTML = `<div class="muted">${message}</div>`;
      }
      if (tradesEl) {
        tradesEl.innerHTML = `<div class="muted">${message}</div>`;
      }
      if (canvas) {
        const ctx = canvas.getContext("2d");
        if (ctx) {
          ctx.clearRect(0, 0, canvas.width, canvas.height);
          ctx.fillStyle = "#94a3b8";
          ctx.font = "12px Inter, system-ui, sans-serif";
          ctx.fillText("No equity data.", 12, 20);
        }
      }
    }

    function updateBacktestDownload(path) {
      const button = document.getElementById("backtest-download");
      if (!button) return;
      if (path) {
        button.disabled = false;
        button.dataset.path = path;
      } else {
        button.disabled = true;
        button.dataset.path = "";
      }
    }

    async function loadBacktestResult(path) {
      const summaryEl = document.getElementById("backtest-summary");
      const tradesEl = document.getElementById("backtest-trades");
      if (!summaryEl || !tradesEl) return;
      if (!path) {
        resetBacktestSections("Select a backtest run to view details.");
        return;
      }
      summaryEl.innerHTML = `<div class="muted">Loading backtest summary...</div>`;
      tradesEl.innerHTML = `<div class="muted">Loading trades...</div>`;
      try {
        const data = await fetchJSON(`/api/backtests/result?path=${encodeURIComponent(path)}`);
        backtestSelectedPath = path;
        backtestCurrentData = data;
        renderBacktestSummary(data);
        renderBacktestEquityCurve(data);
        renderBacktestTrades(data);
        updateBacktestDownload(path);
      } catch (err) {
        summaryEl.innerHTML = `<div class="error">Failed to load backtest summary: ${err.message || err}</div>`;
        tradesEl.innerHTML = `<div class="error">Failed to load trades.</div>`;
        backtestCurrentData = null;
        updateBacktestDownload(null);
      }
    }

    function renderBacktestSummary(data) {
      const summaryEl = document.getElementById("backtest-summary");
      if (!summaryEl) return;
      const summary = data.summary || {};
      const rows = [
        { label: "Total PnL", value: summary.total_pnl || 0, formatter: formatMoney },
        { label: "Win Rate", value: summary.win_rate || 0, formatter: (v) => formatPct(v, 1) },
        { label: "Trades", value: summary.total_trades || 0, formatter: (v) => Number(v).toLocaleString("en-IN") },
        { label: "Wins", value: summary.wins || 0, formatter: (v) => Number(v).toLocaleString("en-IN") },
        { label: "Losses", value: summary.losses || 0, formatter: (v) => Number(v).toLocaleString("en-IN") },
        { label: "Max Drawdown", value: summary.max_drawdown || 0, formatter: formatMoney },
        { label: "Max Drawdown %", value: summary.max_drawdown_pct || 0, formatter: (v) => formatPct(v, 1) },
      ];

      summaryEl.innerHTML = `
        <div class="backtest-summary-grid">
          ${rows
            .map(
              (row) => `
              <div class="backtest-summary-item">
                <div class="backtest-summary-label">${row.label}</div>
                <div class="backtest-summary-value ${kpiClassForValue(Number(row.value || 0))}">
                  ${row.formatter(row.value || 0)}
                </div>
              </div>
            `
            )
            .join("")}
        </div>
      `;
    }

    function renderBacktestEquityCurve(data) {
      const canvas = document.getElementById("backtest-equity");
      if (!canvas) return;
      const ctx = canvas.getContext("2d");
      if (!ctx) return;

      const rect = canvas.getBoundingClientRect();
      canvas.width = rect.width * window.devicePixelRatio;
      canvas.height = rect.height * window.devicePixelRatio;
      ctx.setTransform(window.devicePixelRatio, 0, 0, window.devicePixelRatio, 0, 0);

      const rawPoints = Array.isArray(data.equity_curve) ? data.equity_curve : [];
      const points = rawPoints
        .map((entry) => ({
          ts: new Date(entry[0]),
          equity: Number(entry[1]),
        }))
        .filter((p) => Number.isFinite(p.equity) && !Number.isNaN(p.ts.getTime()));

      ctx.clearRect(0, 0, canvas.width, canvas.height);

      if (!points.length) {
        ctx.fillStyle = "#94a3b8";
        ctx.font = "12px Inter, system-ui, sans-serif";
        ctx.fillText("No equity data.", 12, 20);
        return;
      }

      const minEq = Math.min(...points.map((p) => p.equity));
      const maxEq = Math.max(...points.map((p) => p.equity));
      const w = canvas.width / window.devicePixelRatio;
      const h = canvas.height / window.devicePixelRatio;
      const padding = 16;
      const x0 = padding;
      const x1 = w - padding;
      const y0 = h - padding;
      const y1 = padding;
      const tsStart = points[0].ts.getTime();
      const tsEnd = points[points.length - 1].ts.getTime() || tsStart + 1;
      const eqMin = minEq === maxEq ? minEq - 1 : minEq;
      const eqMax = minEq === maxEq ? maxEq + 1 : maxEq;

      const xScale = (t) => {
        if (tsEnd === tsStart) return (x0 + x1) / 2;
        return x0 + ((t - tsStart) / (tsEnd - tsStart)) * (x1 - x0);
      };
      const yScale = (eq) => {
        if (eqMax === eqMin) return (y0 + y1) / 2;
        return y0 - ((eq - eqMin) / (eqMax - eqMin)) * (y0 - y1);
      };

      ctx.strokeStyle = "rgba(148, 163, 184, 0.35)";
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(x0, y1);
      ctx.lineTo(x0, y0);
      ctx.lineTo(x1, y0);
      ctx.stroke();

      ctx.strokeStyle = "#38bdf8";
      ctx.lineWidth = 1.8;
      ctx.beginPath();
      points.forEach((point, idx) => {
        const x = xScale(point.ts.getTime());
        const y = yScale(point.equity);
        if (idx === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      });
      ctx.stroke();
    }

    function renderBacktestTrades(data) {
      const tradesEl = document.getElementById("backtest-trades");
      if (!tradesEl) return;
      const trades = Array.isArray(data.trades) ? data.trades : [];
      if (!trades.length) {
        tradesEl.innerHTML = `<div class="muted">No trades recorded for this run.</div>`;
        return;
      }
      const rows = trades
        .map((trade) => {
          const ts = trade.timestamp ? new Date(trade.timestamp).toLocaleString() : "-";
          const pnlCls = kpiClassForValue(Number(trade.pnl || 0));
          return `
            <tr>
              <td>${ts}</td>
              <td>${trade.symbol || "-"}</td>
              <td>${trade.side || "-"}</td>
              <td>${trade.qty || trade.quantity || 0}</td>
              <td>${Number(trade.entry_price || 0).toFixed(2)}</td>
              <td>${Number(trade.exit_price || 0).toFixed(2)}</td>
              <td class="${pnlCls}">${formatMoney(trade.pnl || 0)}</td>
              <td>${trade.holding_time || "-"}</td>
            </tr>
          `;
        })
        .join("");
      tradesEl.innerHTML = `
        <div class="table-scroll">
          <table class="row-striped">
            <thead>
              <tr>
                <th>Timestamp</th>
                <th>Symbol</th>
                <th>Side</th>
                <th>Qty</th>
                <th>Entry</th>
                <th>Exit</th>
                <th>PnL</th>
                <th>Holding</th>
              </tr>
            </thead>
            <tbody>${rows}</tbody>
          </table>
        </div>
      `;
    }

    function initBacktestCard() {
      const strategySelect = document.getElementById("backtest-strategy");
      const runSelect = document.getElementById("backtest-run");
      const downloadBtn = document.getElementById("backtest-download");
      if (!strategySelect || !runSelect || !downloadBtn) {
        return;
      }

      strategySelect.addEventListener("change", (event) => {
        backtestSelectedStrategy = event.target.value || "";
        backtestSelectedPath = "";
        populateBacktestRuns();
      });

      runSelect.addEventListener("change", (event) => {
        backtestSelectedPath = event.target.value || "";
        loadBacktestResult(backtestSelectedPath);
      });

      downloadBtn.addEventListener("click", () => {
        const path = downloadBtn.dataset.path;
        if (!path) return;
        window.open(`/api/backtests/result?path=${encodeURIComponent(path)}`, "_blank");
      });

      refreshBacktestRuns();
    }

    /* ---------- Init ---------- */

function initDashboard() {
  updateHeaderPills();
  renderTopKpis();
  renderEquity();
  renderTradeFlow();
      renderEngine();
      renderConfigAuth();
      renderSignals();
      renderOrders();
  initLogConsole();
  renderStrategies();
  initBacktestCard();

  setInterval(updateHeaderPills, 15_000);
  setInterval(renderTopKpis, 15_000);
  setInterval(renderEquity, 25_000);
      setInterval(renderTradeFlow, 20_000);
      setInterval(renderEngine, 20_000);
  setInterval(renderConfigAuth, 40_000);
  setInterval(renderSignals, 15_000);
  setInterval(renderOrders, 15_000);
  setInterval(renderStrategies, 30_000);

  window.addEventListener("resize", () => {
    renderEquity();
    if (backtestCurrentData) {
      renderBacktestEquityCurve(backtestCurrentData);
    }
  });
}

    document.addEventListener("DOMContentLoaded", initDashboard);
