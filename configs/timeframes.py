from __future__ import annotations

from typing import Iterable, List, Mapping, MutableMapping, Optional


MULTI_TF_CONFIG: List[dict[str, str]] = [
    {"timeframe": "5m", "mode": "SCALP"},
    {"timeframe": "15m", "mode": "INTRADAY"},
    {"timeframe": "60m", "mode": "SWING"},
    {"timeframe": "1D", "mode": "CONTEXT"},
    {"timeframe": "1W", "mode": "CONTEXT"},
]


def resolve_multi_tf_config(
    overrides: Optional[Iterable[Mapping[str, object] | MutableMapping[str, object]]] = None,
) -> List[dict[str, str]]:
    """
    Normalize a custom multi-timeframe configuration (if provided) or fall back to MULTI_TF_CONFIG.
    """

    def _normalize(entry: Mapping[str, object] | MutableMapping[str, object]) -> Optional[dict[str, str]]:
        timeframe = str(entry.get("timeframe") or "").strip()
        mode = str(entry.get("mode") or "").strip().upper()
        if not timeframe:
            return None
        return {
            "timeframe": timeframe,
            "mode": mode or "CONTEXT",
        }

    if overrides:
        normalized: List[dict[str, str]] = []
        for raw in overrides:
            normalized_entry = _normalize(raw)
            if normalized_entry:
                normalized.append(normalized_entry)
        if normalized:
            return normalized

    # fall back to defaults
    return [cfg.copy() for cfg in MULTI_TF_CONFIG]
