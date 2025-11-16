"""
ReconciliationEngine - Order and Position Reconciliation for ExecutionEngine V3

This module provides robust reconciliation for LIVE and PAPER trading:
- Polls execution_engine.poll_orders() for broker state
- Compares with local order objects
- Resolves discrepancies automatically
- Updates order state and publishes events
- Synchronizes positions with broker (LIVE mode only)

Key Features:
- Configurable reconciliation intervals (2s for LIVE, 5s for PAPER)
- Never crashes - all exceptions are caught and logged
- No impact on existing execution flow
- Zero breakage for paper trading
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from core.execution_engine_v3 import EventBus, EventType, ExecutionEngine, Order, OrderStatus

logger = logging.getLogger(__name__)


class ReconciliationEngine:
    """
    Reconciliation engine for order and position synchronization.
    
    Responsibilities:
    - Poll orders from execution engine
    - Compare with local state
    - Resolve discrepancies using predefined rules
    - Update StateStore positions
    - Publish reconciliation events to EventBus
    - Rebuild positions from broker data (LIVE mode only)
    """
    
    def __init__(
        self,
        execution_engine: ExecutionEngine,
        state_store: Any,
        event_bus: Optional[EventBus] = None,
        kite_broker: Optional[Any] = None,
        config: Optional[Dict[str, Any]] = None,
        mode: str = "PAPER",
        logger_instance: Optional[logging.Logger] = None
    ):
        """
        Initialize ReconciliationEngine.
        
        Args:
            execution_engine: ExecutionEngine instance (Paper or Live)
            state_store: StateStore instance for persistence
            event_bus: Optional EventBus instance for event publishing
            kite_broker: Optional KiteBroker instance (required for LIVE position reconciliation)
            config: Configuration dict
            mode: Trading mode ("PAPER" or "LIVE")
            logger_instance: Optional logger instance
        """
        self.execution_engine = execution_engine
        self.state_store = state_store
        self.event_bus = event_bus or EventBus()
        self.kite_broker = kite_broker
        self.config = config or {}
        self.mode = mode.upper()
        self.logger = logger_instance or logger
        
        # Extract reconciliation config
        reconciliation_config = self.config.get("reconciliation", {})
        
        # Default intervals: 2s for LIVE, 5s for PAPER
        default_interval = 2.0 if self.mode == "LIVE" else 5.0
        self.interval_seconds = reconciliation_config.get("interval_seconds", default_interval)
        self.enabled = reconciliation_config.get("enabled", True)
        
        # Track local order state for comparison
        self.local_orders: Dict[str, Order] = {}
        
        # Reconciliation statistics
        self.reconciliation_count = 0
        self.discrepancy_count = 0
        self.last_reconciliation_time: Optional[datetime] = None
        
        self.logger.info(
            "ReconciliationEngine initialized: mode=%s, interval=%.1fs, enabled=%s",
            self.mode,
            self.interval_seconds,
            self.enabled
        )
    
    async def reconcile_orders(self):
        """
        Reconcile orders between execution engine and local state.
        
        Workflow:
        1. Poll execution_engine.poll_orders() to get latest broker state
        2. Compare with local order objects
        3. Resolve discrepancies using predefined rules
        4. Update order state
        5. Publish events to EventBus
        6. Update StateStore positions if fills occurred
        
        Discrepancy Resolution Rules:
        - If broker says OPEN but local is SUBMITTED/PENDING → local → OPEN
        - If broker says FILLED but local is OPEN/PLACED → apply fill event
        - If broker says CANCELLED → local → CANCELLED
        - If broker says REJECTED → local → REJECTED + publish risk alert
        - If broker missing order → mark "unknown" and retry next cycle
        - If fills differ → append missing fills
        """
        try:
            # Poll orders from execution engine
            broker_orders = await self.execution_engine.poll_orders()
            
            # Track reconciliation
            self.reconciliation_count += 1
            self.last_reconciliation_time = datetime.now(timezone.utc)
            
            # Build broker order map
            broker_order_map = {order.order_id: order for order in broker_orders}
            
            # Reconcile each local order
            for order_id, local_order in list(self.local_orders.items()):
                broker_order = broker_order_map.get(order_id)
                
                if broker_order is None:
                    # Broker missing order - log and retry next cycle
                    self.logger.warning(
                        "Order %s not found in broker state (local status: %s) - will retry",
                        order_id,
                        local_order.status
                    )
                    await self._publish_discrepancy_event(
                        order_id=order_id,
                        reason="Order not found in broker state",
                        local_status=local_order.status,
                        broker_status="MISSING"
                    )
                    continue
                
                # Check for discrepancies
                await self._resolve_order_discrepancy(local_order, broker_order)
            
            # Check for new orders from broker not in local state
            for order_id, broker_order in broker_order_map.items():
                if order_id not in self.local_orders:
                    self.logger.info(
                        "New order %s detected in broker state (status: %s)",
                        order_id,
                        broker_order.status
                    )
                    # Add to local tracking
                    self.local_orders[order_id] = broker_order
                    
        except Exception as exc:
            self.logger.error(
                "Order reconciliation failed: %s",
                exc,
                exc_info=True
            )
    
    async def reconcile_positions(self):
        """
        Reconcile positions with broker (LIVE mode only).
        
        Workflow:
        1. Fetch broker positions via kite_bridge
        2. Compare with local StateStore positions
        3. Rebuild local positions if mismatch detected
        4. Publish reconciliation alert event
        
        This is only executed in LIVE mode to ensure broker positions
        match our local state.
        """
        if self.mode != "LIVE":
            # Skip position reconciliation for PAPER mode
            return
        
        if self.kite_broker is None:
            self.logger.warning("Position reconciliation skipped - no kite_broker provided")
            return
        
        try:
            # Fetch broker positions
            broker_positions_raw = self.kite_broker.kite.positions()
            broker_positions = self._normalize_broker_positions(broker_positions_raw)
            
            # Load local positions from StateStore
            state = self.state_store.load()
            local_positions = state.get("positions", [])
            
            # Compare positions
            mismatch_detected = self._detect_position_mismatch(local_positions, broker_positions)
            
            if mismatch_detected:
                self.logger.warning(
                    "Position mismatch detected - rebuilding local positions from broker"
                )
                
                # Rebuild local positions
                state["positions"] = broker_positions
                self.state_store.save(state)
                
                # Publish reconciliation alert
                await self.event_bus.publish(EventType.POSITION_SYNCED, {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "positions_count": len(broker_positions),
                    "mismatch_detected": True,
                    "action": "rebuilt_from_broker"
                })
                
                self.logger.info(
                    "✅ Positions reconciled: %d positions synced from broker",
                    len(broker_positions)
                )
            else:
                self.logger.debug("Position reconciliation: no mismatches detected")
                
        except Exception as exc:
            self.logger.error(
                "Position reconciliation failed: %s",
                exc,
                exc_info=True
            )
    
    async def start_reconciliation_loop(self):
        """
        Start background reconciliation loop.
        
        This loop runs continuously and performs both order and position
        reconciliation at the configured interval.
        
        Features:
        - Never crashes - all exceptions are caught
        - Logs discrepancies but doesn't halt trading
        - Runs in parallel with execution engine
        """
        if not self.enabled:
            self.logger.info("Reconciliation loop disabled by configuration")
            return
        
        self.logger.info(
            "Starting reconciliation loop (interval=%.1fs, mode=%s)",
            self.interval_seconds,
            self.mode
        )
        
        while True:
            try:
                await asyncio.sleep(self.interval_seconds)
                
                # Reconcile orders
                await self.reconcile_orders()
                
                # Reconcile positions (LIVE mode only)
                await self.reconcile_positions()
                
            except Exception as exc:
                # Catch all exceptions to prevent loop crash
                self.logger.error(
                    "Reconciliation loop error: %s",
                    exc,
                    exc_info=True
                )
                # Continue loop after error
                await asyncio.sleep(1.0)
    
    async def register_order(self, order: Order):
        """
        Register an order for reconciliation tracking.
        
        Args:
            order: Order to track
        """
        self.local_orders[order.order_id] = order
        self.logger.debug("Order %s registered for reconciliation", order.order_id)
    
    async def _resolve_order_discrepancy(self, local_order: Order, broker_order: Order):
        """
        Resolve discrepancies between local and broker order state.
        
        Args:
            local_order: Local order object
            broker_order: Broker order object
        """
        # Check for status match AND fill quantity match
        if local_order.status == broker_order.status:
            # Even if status matches, check for fill quantity discrepancies
            if local_order.status in [OrderStatus.PARTIAL, OrderStatus.FILLED]:
                if local_order.filled_qty != broker_order.filled_qty:
                    # Fill quantity mismatch - need to reconcile
                    pass  # Continue to reconciliation logic
                else:
                    # No discrepancy - states and fills match
                    return
            else:
                # No discrepancy - states match
                return
        
        # Discrepancy detected
        self.discrepancy_count += 1
        old_status = local_order.status
        new_status = broker_order.status
        
        self.logger.info(
            "Order %s status discrepancy: local=%s, broker=%s",
            local_order.order_id,
            old_status,
            new_status
        )
        
        # Apply resolution rules
        if new_status in [OrderStatus.PLACED, "OPEN", "SUBMITTED"]:
            # Rule: If broker says OPEN/PLACED but local is SUBMITTED/PENDING → update local
            if old_status in [OrderStatus.PENDING, "SUBMITTED"]:
                local_order.status = OrderStatus.PLACED
                local_order.updated_at = datetime.now(timezone.utc)
                
                await self._publish_order_updated_event(local_order, old_status)
                self.logger.info(
                    "✅ Order %s reconciled: %s → %s",
                    local_order.order_id,
                    old_status,
                    OrderStatus.PLACED
                )
        
        elif new_status == OrderStatus.FILLED:
            # Rule: If broker says FILLED but local is OPEN/PLACED → apply fill
            if old_status in [OrderStatus.PLACED, OrderStatus.PENDING, "OPEN", "SUBMITTED"]:
                local_order.status = OrderStatus.FILLED
                local_order.filled_qty = broker_order.filled_qty
                local_order.avg_price = broker_order.avg_price
                local_order.updated_at = datetime.now(timezone.utc)
                
                # Publish fill event
                await self.event_bus.publish(EventType.ORDER_FILLED, {
                    "order_id": local_order.order_id,
                    "symbol": local_order.symbol,
                    "side": local_order.side,
                    "qty": local_order.filled_qty,
                    "price": local_order.avg_price,
                    "reconciled": True
                })
                
                # Update position in StateStore
                self._update_position(local_order)
                
                # Write checkpoint after fill
                self._write_checkpoint()
                
                self.logger.info(
                    "✅ Order %s reconciled FILL: %s %d x %s @ %.2f",
                    local_order.order_id,
                    local_order.side,
                    local_order.filled_qty,
                    local_order.symbol,
                    local_order.avg_price or 0.0
                )
        
        elif new_status == OrderStatus.PARTIAL:
            # Rule: If fills differ → update local
            if local_order.filled_qty != broker_order.filled_qty:
                old_filled_qty = local_order.filled_qty
                local_order.status = OrderStatus.PARTIAL
                local_order.filled_qty = broker_order.filled_qty
                local_order.avg_price = broker_order.avg_price
                local_order.updated_at = datetime.now(timezone.utc)
                
                # Calculate incremental fill
                incremental_qty = broker_order.filled_qty - old_filled_qty
                
                if incremental_qty > 0:
                    # Publish partial fill event
                    await self.event_bus.publish(EventType.ORDER_FILLED, {
                        "order_id": local_order.order_id,
                        "symbol": local_order.symbol,
                        "side": local_order.side,
                        "qty": incremental_qty,
                        "price": local_order.avg_price,
                        "partial": True,
                        "reconciled": True
                    })
                    
                    # Update position
                    self._update_position(local_order)
                    
                    self.logger.info(
                        "✅ Order %s reconciled PARTIAL: filled %d → %d",
                        local_order.order_id,
                        old_filled_qty,
                        broker_order.filled_qty
                    )
        
        elif new_status == OrderStatus.CANCELLED:
            # Rule: If broker says CANCELLED → update local
            local_order.status = OrderStatus.CANCELLED
            local_order.message = "Cancelled (reconciled from broker)"
            local_order.updated_at = datetime.now(timezone.utc)
            
            await self.event_bus.publish(EventType.ORDER_CANCELLED, {
                "order_id": local_order.order_id,
                "symbol": local_order.symbol,
                "reconciled": True
            })
            
            self.logger.info(
                "✅ Order %s reconciled: %s → CANCELLED",
                local_order.order_id,
                old_status
            )
        
        elif new_status == OrderStatus.REJECTED:
            # Rule: If broker says REJECTED → update local + publish risk alert
            local_order.status = OrderStatus.REJECTED
            local_order.message = broker_order.message or "Rejected (reconciled from broker)"
            local_order.updated_at = datetime.now(timezone.utc)
            
            await self.event_bus.publish(EventType.ORDER_REJECTED, {
                "order_id": local_order.order_id,
                "symbol": local_order.symbol,
                "reason": local_order.message,
                "reconciled": True
            })
            
            # Publish reconciliation discrepancy event for risk monitoring
            await self._publish_discrepancy_event(
                order_id=local_order.order_id,
                reason=f"Order rejected by broker: {local_order.message}",
                local_status=old_status,
                broker_status=new_status
            )
            
            self.logger.warning(
                "⚠️  Order %s reconciled REJECTION: %s → REJECTED (reason: %s)",
                local_order.order_id,
                old_status,
                local_order.message
            )
        
        # Publish general discrepancy event
        await self._publish_discrepancy_event(
            order_id=local_order.order_id,
            reason=f"Status mismatch resolved: {old_status} → {new_status}",
            local_status=old_status,
            broker_status=new_status
        )
    
    async def _publish_order_updated_event(self, order: Order, old_status: str):
        """
        Publish order_updated event.
        
        Args:
            order: Updated order
            old_status: Previous order status
        """
        await self.event_bus.publish(EventType.ORDER_UPDATED, {
            "order_id": order.order_id,
            "symbol": order.symbol,
            "old_status": old_status,
            "new_status": order.status,
            "reconciled": True
        })
    
    async def _publish_discrepancy_event(
        self,
        order_id: str,
        reason: str,
        local_status: str,
        broker_status: str
    ):
        """
        Publish reconciliation_discrepancy event.
        
        Args:
            order_id: Order ID
            reason: Discrepancy reason
            local_status: Local order status
            broker_status: Broker order status
        """
        await self.event_bus.publish(EventType.RECONCILIATION_DISCREPANCY, {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "order_id": order_id,
            "reason": reason,
            "local_status": local_status,
            "broker_status": broker_status,
            "reconciliation_count": self.reconciliation_count,
            "discrepancy_count": self.discrepancy_count
        })
    
    def _update_position(self, order: Order):
        """
        Update position in StateStore after fill.
        
        Args:
            order: Filled order
        """
        try:
            state = self.state_store.load()
            if not state:
                return
            
            positions = state.get("positions", [])
            
            # Find existing position
            position = None
            for pos in positions:
                if pos.get("symbol") == order.symbol:
                    position = pos
                    break
            
            # Calculate position change (only for newly filled quantity)
            # For reconciliation, we use filled_qty as the total filled
            qty_change = order.filled_qty if order.side == "BUY" else -order.filled_qty
            
            if position:
                # Update existing position
                current_qty = position.get("qty", 0)
                new_qty = current_qty + qty_change
                
                if new_qty == 0:
                    positions.remove(position)
                else:
                    position["qty"] = new_qty
                    position["avg_price"] = order.avg_price
            else:
                # Create new position
                if qty_change != 0:
                    positions.append({
                        "symbol": order.symbol,
                        "qty": qty_change,
                        "avg_price": order.avg_price,
                        "entry_time": order.created_at.isoformat(),
                    })
            
            state["positions"] = positions
            self.state_store.save(state)
            
            # Publish position update event
            asyncio.create_task(self.event_bus.publish(EventType.POSITION_UPDATED, {
                "symbol": order.symbol,
                "qty": qty_change,
                "price": order.avg_price,
                "reconciled": True
            }))
            
        except Exception as exc:
            self.logger.error(
                "Error updating position for order %s: %s",
                order.order_id,
                exc,
                exc_info=True
            )
    
    def _write_checkpoint(self):
        """
        Write fresh checkpoint to StateStore after reconciliation.
        """
        try:
            state = self.state_store.load()
            if state:
                # Update last reconciliation timestamp
                state["last_reconciliation_ts"] = datetime.now(timezone.utc).isoformat()
                self.state_store.save(state)
        except Exception as exc:
            self.logger.error(
                "Error writing checkpoint: %s",
                exc,
                exc_info=True
            )
    
    def _normalize_broker_positions(self, broker_positions_raw: Any) -> List[Dict[str, Any]]:
        """
        Normalize broker positions to standard format.
        
        Args:
            broker_positions_raw: Raw positions from broker
            
        Returns:
            List of normalized position dicts
        """
        entries: List[Dict[str, Any]] = []
        
        if isinstance(broker_positions_raw, dict):
            entries = broker_positions_raw.get("net", []) or broker_positions_raw.get("day", [])
        elif isinstance(broker_positions_raw, list):
            entries = broker_positions_raw
        
        positions: List[Dict[str, Any]] = []
        
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            
            symbol = entry.get("tradingsymbol") or entry.get("symbol")
            if not symbol:
                continue
            
            qty = self._safe_float(entry.get("quantity") or entry.get("net_quantity") or 0.0)
            
            # Skip zero positions
            if qty == 0:
                continue
            
            positions.append({
                "symbol": symbol,
                "qty": int(qty),
                "avg_price": self._safe_float(entry.get("average_price") or 0.0),
                "entry_time": datetime.now(timezone.utc).isoformat(),
            })
        
        return positions
    
    def _detect_position_mismatch(
        self,
        local_positions: List[Dict[str, Any]],
        broker_positions: List[Dict[str, Any]]
    ) -> bool:
        """
        Detect if there's a mismatch between local and broker positions.
        
        Args:
            local_positions: Local positions from StateStore
            broker_positions: Broker positions
            
        Returns:
            True if mismatch detected, False otherwise
        """
        # Build position maps for comparison
        local_map = {pos["symbol"]: pos["qty"] for pos in local_positions}
        broker_map = {pos["symbol"]: pos["qty"] for pos in broker_positions}
        
        # Check for mismatches
        all_symbols = set(local_map.keys()) | set(broker_map.keys())
        
        for symbol in all_symbols:
            local_qty = local_map.get(symbol, 0)
            broker_qty = broker_map.get(symbol, 0)
            
            if local_qty != broker_qty:
                self.logger.warning(
                    "Position mismatch for %s: local=%d, broker=%d",
                    symbol,
                    local_qty,
                    broker_qty
                )
                return True
        
        return False
    
    @staticmethod
    def _safe_float(value: Any, default: float = 0.0) -> float:
        """
        Safely convert value to float.
        
        Args:
            value: Value to convert
            default: Default value if conversion fails
            
        Returns:
            Float value or default
        """
        try:
            return float(value)
        except (TypeError, ValueError):
            return default
