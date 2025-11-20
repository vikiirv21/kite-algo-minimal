// API Response Types

export interface MetaResponse {
  now_ist: string;
  market_open: boolean;
  market_status: string;
  status_payload: {
    status: string;
    message: string;
    ist_timestamp: string;
    label: string;
    phase: string;
  };
  regime: string;
  regime_snapshot: Record<string, unknown>;
}

export interface ConfigSummary {
  config_path: string;
  mode: string;
  fno_universe: string[];
  paper_capital: number;
  risk_per_trade_pct: number;
  max_daily_loss: number;
  max_exposure_pct: number;
  max_positions: number | null;  // null = unlimited positions
  risk_profile: string;
  meta_enabled: boolean;
}

export interface EngineStatus {
  engine: string;
  running: boolean;
  last_checkpoint_ts: string | null;
  checkpoint_age_seconds: number | null;
  market_open: boolean;
  mode: string;
  error: string | null;
  checkpoint_path: string | null;
}

export interface EnginesStatusResponse {
  engines: EngineStatus[];
}

export interface PortfolioSummary {
  paper_capital: number | null;
  total_realized_pnl: number | null;
  total_unrealized_pnl: number | null;
  equity: number | null;
  total_notional: number | null;
  free_notional: number | null;
  exposure_pct: number | null;
  daily_pnl: number | null;
  has_positions: boolean;
  position_count: number;
  position_limit: number | null;  // null = unlimited positions
  open_positions: number;
  position_used_pct: number;
  note: string;
}

export interface Signal {
  ts: string;
  symbol: string;
  logical: string;
  signal: string;
  tf: string;
  price: number | null;
  profile: string;
  strategy: string;
}

export interface Order {
  timestamp: string;
  symbol: string;
  side: string;
  quantity: number;
  price: number;
  status: string;
  order_id?: string;
  pnl?: number;
}

export interface Position {
  symbol: string;
  side: string;
  quantity: number;
  avg_price: number;
  last_price: number;
  notional?: number;
  unrealized_pnl: number;
  pnl_pct?: number;
}

export interface Portfolio {
  starting_capital: number;
  equity: number;
  realized_pnl: number;
  unrealized_pnl: number;
  total_notional: number;
  free_margin: number;
  margin_used: number;
  positions: Position[];
  error?: string;
}

export interface LogEntry {
  timestamp?: string;
  ts?: string;
  level: string;
  source?: string;
  logger?: string;
  message?: string;
  raw?: string;
}

export interface LogsResponse {
  logs: LogEntry[];
  entries: LogEntry[];
}

export interface StrategyStats {
  key: string;
  logical: string;
  symbol: string;
  strategy: string;
  last_ts: string;
  last_signal: string;
  last_price: number | null;
  timeframe: string;
  buy_count: number;
  sell_count: number;
  exit_count: number;
  hold_count: number;
  mode: string;
  trades_today: number;
  winrate_20: number;
  avg_r_20: number;
  avg_signal_score: number;
  veto_count_today: number;
}

export interface EquityCurvePoint {
  ts: string;
  equity: number;
  paper_capital: number;
  realized: number;
  unrealized: number;
}

export interface TodaySummary {
  date: string;
  realized_pnl: number;
  num_trades: number;
  win_trades: number;
  loss_trades: number;
  win_rate: number;
  largest_win: number;
  largest_loss: number;
  avg_r: number;
  note?: string;
}

export interface AuthStatus {
  is_logged_in: boolean;
  user_id: string | null;
  login_ts: string | null;
  login_age_minutes: number | null;
  token_valid: boolean;
  error: string | null;
}

export interface AnalyticsSummary {
  asof: string | null;
  status: 'ok' | 'stale' | 'empty';
  mode: string;
  equity: {
    starting_capital: number;
    current_equity: number;
    realized_pnl: number;
    unrealized_pnl: number;
    total_notional: number;
    max_drawdown: number;
    max_equity: number;
    min_equity: number;
  };
  overall: {
    total_trades: number;
    win_trades: number;
    loss_trades: number;
    breakeven_trades: number;
    win_rate: number;
    gross_profit: number;
    gross_loss: number;
    net_pnl: number;
    profit_factor: number;
    avg_win: number;
    avg_loss: number;
    avg_r_multiple: number;
    biggest_win: number;
    biggest_loss: number;
  };
  per_strategy: Record<string, {
    trades: number;
    win_trades: number;
    loss_trades: number;
    gross_profit: number;
    gross_loss: number;
    net_pnl: number;
    win_rate: number;
    profit_factor: number;
    avg_win: number;
    avg_loss: number;
  }>;
  per_symbol: Record<string, {
    trades: number;
    win_trades: number;
    loss_trades: number;
    gross_profit: number;
    gross_loss: number;
    net_pnl: number;
    win_rate: number;
    profit_factor: number;
  }>;
}

export interface EquityCurveData {
  equity_curve: Array<{
    timestamp: string;
    equity: number;
    pnl: number;
  }>;
  drawdown: {
    max_drawdown: number;
    drawdown_series: Array<{
      timestamp: string;
      drawdown: number;
    }>;
  };
  filters: {
    strategy: string | null;
    symbol: string | null;
  };
}

export interface RiskSummary {
  mode: string;
  per_trade_risk_pct: number | null;
  max_daily_loss_abs: number | null;
  max_daily_loss_pct: number | null;
  trading_halted: boolean;
  halt_reason: string | null;
  current_day_pnl: number | null;
  current_exposure: number | null;
}

export interface RuntimeMetrics {
  asof: string | null;
  mode: string;
  equity: {
    starting_capital: number;
    current_equity: number;
    realized_pnl: number;
    unrealized_pnl: number;
    max_drawdown: number;
    max_equity: number;
    min_equity: number;
  };
  overall: {
    total_trades: number;
    win_trades: number;
    loss_trades: number;
    breakeven_trades: number;
    win_rate: number;
    gross_profit: number;
    gross_loss: number;
    net_pnl: number;
    profit_factor: number;
    avg_win: number;
    avg_loss: number;
    avg_r_multiple: number;
    biggest_win: number;
    biggest_loss: number;
  };
  per_strategy: Record<string, any>;
  per_symbol: Record<string, any>;
}

export interface TradingStatus {
  connected: boolean;
  mode: 'paper' | 'live';
  phase: 'IDLE' | 'SCANNING' | 'TRADING' | 'UNKNOWN';
  ist_time: string;
}

export interface EngineLogsTailResponse {
  engine: string;
  lines: string[];
  count: number;
  file: string;
  exists: boolean;
  warning: string | null;
}

// Strategy Lab API Types
export interface StrategyDetail {
  id: string;
  name: string;
  strategy_code: string;
  engine: string;
  timeframe: string;
  mode: string;
  enabled: boolean;
  params: Record<string, any>;
  tags: string[];
}

export interface BacktestRequest {
  symbol: string;
  engine: string;
  timeframe: string;
  from_date: string;
  to_date: string;
  params_override?: Record<string, any>;
}

export interface BacktestResult {
  summary: {
    trades: number;
    win_rate: number;
    total_pnl: number;
    max_drawdown_pct: number;
    avg_pnl_per_trade?: number;
  };
  equity_curve?: Array<[string, number]>;
}

// Advanced Risk API Types
export interface RiskLimits {
  max_daily_loss_rupees: number;
  max_daily_drawdown_pct: number;
  max_trades_per_day: number;
  max_trades_per_symbol_per_day: number;
  max_loss_streak: number;
  metadata?: {
    updated_at?: string;
    source?: {
      base_config: string;
      overrides: string;
    };
  };
}

export interface RiskBreach {
  code: string;
  severity: string;
  message: string;
  metric: {
    current: number;
    limit: number;
    unit: string;
  };
  symbol?: string | null;
  since?: string | null;
}

export interface VaRResponse {
  horizon_days: number;
  confidence: number;
  method: string;
  var_rupees: number;
  var_pct: number;
  sample_size: number;
}
