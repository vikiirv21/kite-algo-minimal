# Arthayukti HFT Dashboard - Visual Guide

## Dashboard Preview

The Arthayukti dashboard is a modern, dark-themed HFT control panel designed for professional traders. Here's what you can expect:

## 🎨 Design Highlights

### Color Scheme
The dashboard uses a carefully crafted dark theme optimized for extended viewing:
- **Deep Navy Background** (#0a0e1a) - Easy on the eyes during long trading sessions
- **Card Surfaces** (#121825) - Subtle elevation with borders
- **Status Colors**:
  - 🟢 Green (#10b981) - Positive P&L, running engines, connected status
  - 🔴 Red (#ef4444) - Negative P&L, stopped engines, errors
  - 🔵 Blue (#3b82f6) - Primary actions, active states
  - 🟠 Orange (#f59e0b) - Warnings, approaching limits

### Layout Structure

```
┌─────────────────────────────────────────────────────────────┐
│  ARTHAYUKTI                  │  Overview  │ 🟢 OPEN │ 15:30 │
│  HFT Control Panel           │            │         │  IST  │
├──────────────┬───────────────────────────────────────────────┤
│              │                                                │
│ 📊 Overview  │   ┌────────────┐ ┌────────────┐              │
│ 💹 Trading   │   │ Engines    │ │ Portfolio  │              │
│ 💼 Portfolio │   │ Status     │ │ Summary    │              │
│ 📡 Signals   │   └────────────┘ └────────────┘              │
│ 📈 Analytics │                                                │
│ 🛡️ Risk      │   ┌─────────────────────────────┐            │
│ ⚙️ System    │   │ Recent Signals              │            │
│ 📝 Logs      │   │ Time  Symbol  Direction     │            │
│              │   │ 15:30 NIFTY   🟢 BUY        │            │
│              │   └─────────────────────────────┘            │
└──────────────┴───────────────────────────────────────────────┘
```

## 📄 Page-by-Page Features

### 1. Overview Page
**Purpose:** Quick glance at system health and recent activity

**Layout:**
```
┌─────────────┬─────────────┬─────────────┬─────────────┐
│ Engines     │ Portfolio   │ Today's     │ Risk        │
│ Status      │ Snapshot    │ Trading     │ Budget      │
│             │             │             │             │
│ Mode: PAPER │ Equity:     │ Realized:   │ Max Loss:   │
│ Status: 🟢  │ ₹1,00,000   │ +₹2,500     │ [========>] │
│ Running     │ Daily P&L:  │ Trades: 12  │ ₹500/₹3000  │
│             │ +₹1,200     │ Win: 75%    │             │
└─────────────┴─────────────┴─────────────┴─────────────┘

┌──────────────────────────────────────────────────────────┐
│ Recent Signals                                           │
├──────────┬────────┬────────────┬──────────┬─────────────┤
│ Time     │ Symbol │ Direction  │ Strategy │ Price       │
├──────────┼────────┼────────────┼──────────┼─────────────┤
│ 15:30:45 │ NIFTY  │ 🟢 BUY     │ EMA      │ ₹19,500.00  │
│ 15:25:30 │ BANK   │ 🔴 SELL    │ RSI      │ ₹45,000.00  │
└──────────┴────────┴────────────┴──────────┴─────────────┘
```

### 2. Trading Page
**Purpose:** Monitor and manage orders

**Features:**
- Active orders table (real-time updates every 3s)
- Recent orders with execution status
- Color-coded side badges (BUY/SELL)
- P&L display for completed orders

### 3. Portfolio Page
**Purpose:** Track positions and overall P&L

**Sections:**
- Portfolio Summary (4-column grid)
  - Equity, Daily P&L, Realized P&L, Unrealized P&L
  - Total Notional, Free Margin, Exposure %, Position Count
- Open Positions Table
  - Symbol, Side, Quantity, Avg Price, LTP, P&L, P&L %
  - Live updates every 3s
  - Color-coded P&L

### 4. Signals Page
**Purpose:** Monitor signal generation and strategies

**Sections:**
- **Active Strategies Table**
  ```
  Strategy    Symbol  TF   Mode    Signals  Win Rate  Last
  EMA Cross   NIFTY   5m   PAPER   15       65.5%     🟢 BUY
  RSI         BANK    15m  LIVE    8        72.3%     🔴 SELL
  ```

- **Strategy Lab** (Placeholder)
  - Enable/Disable toggle buttons
  - Parameter adjustment sliders
  - Backtest runner
  - *Expected APIs documented in code*

- **Signal Stream** (Scrollable)
  - Real-time signal feed
  - Filterable by strategy/symbol
  - Timestamps in IST

### 5. Analytics Page
**Purpose:** Performance visualization and analysis

**Charts:**
```
Equity Curve
₹
│    /\  /\
│   /  \/  \___
│  /           \
│ /             \___
└────────────────────> Time
  Equity  Realized  Unrealized
```

**Placeholders:**
- Benchmarks (vs NIFTY/BANKNIFTY)
- Per-Strategy Performance Metrics
- Drawdown Analysis
- *Expected API shapes documented*

### 6. Risk Dashboard (NEW)
**Purpose:** Real-time risk monitoring

**Risk Gauges:**
```
┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
│ Daily Loss      │  │ Exposure        │  │ Positions       │
│                 │  │                 │  │                 │
│  ₹500          │  │  45%            │  │  3 / 5          │
│  of ₹3,000     │  │  of 100%        │  │  Open           │
│                 │  │                 │  │                 │
│ [=====>    ]    │  │ [=======>  ]    │  │ [====>     ]    │
│ 🟢 Safe         │  │ 🟠 Moderate     │  │ 🟢 Safe         │
└─────────────────┘  └─────────────────┘  └─────────────────┘
```

**Advanced Metrics** (Placeholder):
- VaR calculations (95%, 99%)
- Correlation-adjusted exposure
- Per-symbol position limits
- Max drawdown tracking

### 7. System Page
**Purpose:** System configuration and status

**Sections:**
- System Info: Mode, Risk Profile, Auth Status, User ID
- Config Summary: FNO Universe, Capital, Risk Settings
- Raw JSON: Collapsible debug view

### 8. Logs Page (NEW)
**Purpose:** Real-time engine log monitoring

**Features:**
```
Level: [ALL ▼]                    [● Follow Logs]

┌────────────────────────────────────────────────────────┐
│ 15:30:45 INFO   [engine]  Market opened               │
│ 15:30:46 INFO   [trader]  Signal received: BUY NIFTY  │
│ 15:30:47 WARN   [risk]    Approaching exposure limit  │
│ 15:30:48 ERROR  [order]   Order placement failed      │
│                 ↓ Auto-scroll enabled                  │
└────────────────────────────────────────────────────────┘
```

**Features:**
- Level filter (DEBUG/INFO/WARN/ERROR)
- Auto-follow toggle
- Color-coded severity
- Monospace formatting
- Smart scroll detection

## 🎯 Key UI Features

### Connection Status Indicator
```
Top Bar: [🟢 Connected]  or  [🔴 Disconnected]
         ↑ Pulsing       ↑ Solid
```
- Monitors API health every 2s
- Green pulsing = connected
- Red solid = no API response for 15s

### Loading States
All components show elegant skeletons while loading:
```
┌─────────────────┐
│ Loading...      │
│ ▓▓▓▓▓▓░░░░░░░  │ ← Animated
│ ▓▓▓░░░░░░░░░░  │ ← Shimmer effect
└─────────────────┘
```

### Error States
Errors are displayed without breaking the layout:
```
┌─────────────────────────────┐
│ ⚠ Failed to load data       │
│                              │
│ API error: Connection timeout│
└─────────────────────────────┘
```

### Empty States
Friendly messages for no data:
```
┌─────────────────────────────┐
│         No signals yet       │
│                              │
│  Signals will appear once    │
│  trading begins              │
└─────────────────────────────┘
```

## 🚀 Interactive Elements

### Navigation
- Click any sidebar tab to navigate
- Active tab highlighted with blue accent
- URL updates for bookmarkable pages

### Tables
- Hover rows for highlight
- Sticky headers for long lists
- Horizontal scroll on small screens
- Right-aligned numbers

### Auto-scroll Logs
- Toggle "Follow Logs" button
- Automatically scrolls to new logs
- Pauses on manual scroll up
- Shows "Auto-follow paused" warning

### Real-time Updates
- Portfolio: every 3s
- Orders: every 3s
- Signals: every 2s
- Logs: every 2s
- Market status: every 2s

## 📱 Responsive Design

**Desktop (>1024px):**
- Full sidebar visible
- 4-column grid layouts
- Wide tables with all columns

**Tablet (768-1024px):**
- Full sidebar
- 2-3 column grids
- Horizontal scroll for tables

**Mobile (<768px):**
- Collapsible sidebar
- Single column layouts
- Stacked cards
- Touch-friendly targets

## 🎨 Component Showcase

### Cards
```
┌──────────────────────┐
│ Card Title   [Action]│  ← Optional action button
├──────────────────────┤
│                      │
│  Card content here   │
│                      │
└──────────────────────┘
```

### Badges
```
🟢 BUY    🔴 SELL    🔵 INFO    🟠 WARNING
```

### Progress Bars
```
[=========>     ]  60%  (color changes with value)
[=============> ]  85%  🟠 Warning
[===============]  100% 🔴 Limit reached
```

### P&L Display
```
+₹2,500.00  (green, with + prefix)
-₹1,200.00  (red, with - prefix)
 ₹0.00      (neutral)
```

## 💻 Technical Stack Visible to Users

The dashboard is built with modern web technologies, resulting in:
- ⚡ Fast page loads
- 🔄 Real-time updates
- 📱 Mobile-friendly
- 🌙 Dark theme by default
- ♿ Accessible
- 🎯 Type-safe

## 🔮 Coming Soon Indicators

Throughout the dashboard, placeholder features are clearly marked:
```
┌────────────────────────────────────┐
│ Strategy Lab (Coming Soon)         │
│                                     │
│ 🎚️ Enable/Disable strategies       │
│ ⚙️ Adjust parameters                │
│ 📊 Run backtests                    │
│                                     │
│ // Expected API:                    │
│ POST /api/strategies/{id}/enable   │
└────────────────────────────────────┘
```

This ensures users know what's planned and developers know what to build next!
