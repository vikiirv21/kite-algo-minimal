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
  regime_snapshot: Record<string, any>;
}

export interface ConfigSummary {
  config_path: string;
  mode: string;
  fno_universe: string[];
  paper_capital: number;
  risk_per_trade_pct: number;
  max_daily_loss: number;
  max_exposure_pct: number;
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
  unrealized_pnl: number;
}

export interface LogEntry {
  timestamp: string;
  level: string;
  source: string;
  message: string;
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
