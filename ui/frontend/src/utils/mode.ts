import type { EngineStatus } from '../types/api';

export type Mode = 'LIVE' | 'PAPER' | 'IDLE';

/**
 * Derive the overall mode from engine statuses.
 * - If any engine is running in LIVE mode: LIVE
 * - If any engine is running in PAPER mode: PAPER
 * - Otherwise: IDLE
 */
export function deriveModeFromEngines(engines: EngineStatus[] | undefined): Mode {
  if (!engines || engines.length === 0) {
    return 'IDLE';
  }

  // Check if any engine is running in LIVE mode
  const hasLiveRunning = engines.some(
    (engine) => engine.running && engine.mode?.toUpperCase() === 'LIVE'
  );
  if (hasLiveRunning) {
    return 'LIVE';
  }

  // Check if any engine is running in PAPER mode
  const hasPaperRunning = engines.some(
    (engine) => engine.running && engine.mode?.toUpperCase() === 'PAPER'
  );
  if (hasPaperRunning) {
    return 'PAPER';
  }

  // No engines running
  return 'IDLE';
}

/**
 * Get CSS classes for mode badge
 */
export function getModeBadgeClass(mode: Mode): string {
  switch (mode) {
    case 'LIVE':
      return 'bg-negative text-white animate-pulse-slow';
    case 'PAPER':
      return 'bg-warning text-black';
    case 'IDLE':
    default:
      return 'bg-muted text-white';
  }
}
