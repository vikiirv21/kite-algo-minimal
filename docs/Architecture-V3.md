# Architecture V3 – Service-Oriented, Event-Driven Trading System

> **Status**: Skeleton implementation (2025-11-17)  
> **Supersedes**: Architecture v2 (threaded, single-process)

This document describes the Architecture v3 evolution of the kite-algo-minimal system, introducing a **service-oriented, event-driven** design that maintains compatibility with the existing v2 threaded engine while laying the foundation for distributed, scalable trading operations.

---

## Overview

Architecture v3 introduces a fundamental shift from a monolithic, threaded architecture to a loosely-coupled, service-based system where independent services communicate via an event bus. This enables:

- **Horizontal scalability**: Services can be distributed across multiple processes or machines
- **Independent deployment**: Each service can be updated without affecting others
- **Better fault isolation**: Service failures don't cascade to the entire system
- **Technology flexibility**: Services can use different languages or frameworks
- **Easier testing**: Services can be tested in isolation with mock event streams

---

## Core Principles

### 1. Event-Driven Communication
All inter-service communication happens through an **EventBus** abstraction. Services publish events to topics and subscribe to topics of interest. No service directly calls another service's methods.

### 2. Service Independence
Each service is a standalone component with:
- Its own lifecycle (start/stop)
- Private state management
- Clear responsibilities (single purpose)
- Configuration via dataclasses

### 3. Non-Breaking Evolution
The v3 architecture is **additive only**. Existing v2 components (threaded engines, scripts, dashboard) continue to work unchanged. New v3 services run independently and can be gradually integrated.

### 4. Local-First Development
Development uses an **InMemoryEventBus** (threads + queues) for fast iteration. Production can swap to **RedisEventBus** for distributed deployment without code changes.

---

## Service Catalog

### Core Services

#### 1. **MarketData Service** (`services/marketdata/`)
- **Purpose**: Fetch and distribute real-time market data (LTP, OHLC, order book)
- **Publishes**: `marketdata.tick`, `marketdata.quote`, `marketdata.ohlc`
- **Subscribes**: `control.start`, `control.stop`
- **Responsibilities**:
  - Connect to Kite WebSocket or REST APIs
  - Normalize and validate incoming data
  - Broadcast market updates to subscribers

#### 2. **Strategy Service** (`services/strategy/`)
- **Purpose**: Generate trading signals based on market data and indicators
- **Publishes**: `strategy.signal`
- **Subscribes**: `marketdata.tick`, `marketdata.ohlc`
- **Responsibilities**:
  - Compute indicators (ATR, EMA, RSI, etc.)
  - Apply strategy logic (trend following, mean reversion, etc.)
  - Emit BUY/SELL/HOLD signals with confidence scores

#### 3. **Risk & Portfolio Service** (`services/risk_portfolio/`)
- **Purpose**: Validate signals against risk rules and portfolio constraints
- **Publishes**: `risk.approved`, `risk.blocked`
- **Subscribes**: `strategy.signal`, `execution.fill`
- **Responsibilities**:
  - Enforce position sizing limits
  - Check daily loss limits
  - Validate margin requirements
  - Track open positions and P&L

#### 4. **Execution Service** (`services/execution/`)
- **Purpose**: Execute approved orders with broker APIs
- **Publishes**: `execution.order_placed`, `execution.fill`, `execution.reject`
- **Subscribes**: `risk.approved`
- **Responsibilities**:
  - Place orders via Kite API
  - Monitor order status
  - Handle partial fills and rejections
  - Retry transient failures

#### 5. **Journal Service** (`services/journal/`)
- **Purpose**: Log all trading events and decisions for auditing and analysis
- **Publishes**: (none, terminal sink)
- **Subscribes**: `*` (all events)
- **Responsibilities**:
  - Write events to CSV, JSON, or database
  - Support real-time querying and debugging
  - Generate daily reports

### Trading Domain Services

#### 6. **FnO Trader Service** (`services/trader_fno/`)
- **Purpose**: Manage FnO futures trading strategies
- **Publishes**: `trader_fno.signal`
- **Subscribes**: `marketdata.tick`, `execution.fill`

#### 7. **Options Trader Service** (`services/trader_options/`)
- **Purpose**: Manage options trading strategies (iron condors, straddles, etc.)
- **Publishes**: `trader_options.signal`
- **Subscribes**: `marketdata.tick`, `execution.fill`

#### 8. **Equity Trader Service** (`services/trader_equity/`)
- **Purpose**: Manage equity cash trading strategies
- **Publishes**: `trader_equity.signal`
- **Subscribes**: `marketdata.tick`, `execution.fill`

---

## Event Bus Specification

### Event Structure
```python
@dataclass
class Event:
    event_id: str           # Unique identifier (UUID)
    ts: datetime | str      # Timestamp of event
    type: str               # Event type (e.g., "marketdata.tick")
    source: str             # Service that generated the event
    payload: dict           # Event-specific data
```

### EventBus Interface
```python
class EventBus(ABC):
    @abstractmethod
    def publish(self, topic: str, payload: dict) -> None:
        """Publish an event to a topic"""
        
    @abstractmethod
    def subscribe(self, topic: str, handler: Callable[[Event], None]) -> None:
        """Subscribe a handler to a topic"""
        
    @abstractmethod
    def start(self) -> None:
        """Start the event bus (background threads/connections)"""
        
    @abstractmethod
    def stop(self) -> None:
        """Stop the event bus and release resources"""
```

### Implementations

#### InMemoryEventBus (Development)
- Uses Python `threading` and `queue.Queue`
- Single-process only
- Fast, no external dependencies
- Suitable for development and testing

#### RedisEventBus (Production, Future)
- Uses Redis Pub/Sub or Streams
- Multi-process, multi-machine support
- Persistent event history (with Streams)
- Requires Redis server

---

## Service Lifecycle

Each service follows a standard lifecycle:

1. **Configuration**: Load ServiceConfig (name, enabled flag, etc.)
2. **Initialization**: Connect to EventBus, subscribe to topics
3. **Running**: Process events in `run_forever()` loop
4. **Shutdown**: Unsubscribe, release resources, stop gracefully

### Example Service Stub
```python
@dataclass
class ServiceConfig:
    name: str
    enabled: bool = True

class ServiceBase:
    def __init__(self, event_bus: EventBus, config: ServiceConfig):
        self.event_bus = event_bus
        self.config = config
    
    def run_forever(self) -> None:
        logger.info(f"Service {self.config.name} starting...")
        while True:
            time.sleep(1)  # Placeholder
```

---

## Deployment Models

### Development (Current)
```
Single Process:
  - InMemoryEventBus (threads)
  - All services in same Python process
  - Fast iteration, easy debugging
```

### Production (Future)
```
Multi-Process:
  - RedisEventBus (networked)
  - Each service in separate process/container
  - Horizontal scaling, fault isolation
  
Example:
  docker-compose up
    - service-marketdata (1 instance)
    - service-strategy (3 instances, sharded by symbol)
    - service-risk (1 instance)
    - service-execution (2 instances, active-passive)
    - service-journal (1 instance)
```

---

## Migration Strategy

### Phase 1: Skeleton (Current)
- ✅ Create service package structure
- ✅ Implement EventBus abstraction
- ✅ Add service stubs with minimal logic
- ✅ Build `run_service.py` launcher
- ⚠️ No integration with v2 engines yet

### Phase 2: Gradual Integration
- Wire MarketData service to Kite APIs
- Connect Strategy service to existing strategy logic
- Integrate Risk service with existing RiskEngine
- Run v2 and v3 in parallel (dual write events)

### Phase 3: Feature Parity
- Migrate all v2 engine logic to v3 services
- Switch primary execution path to v3
- Keep v2 as fallback

### Phase 4: Full Transition
- Remove v2 engines
- Optimize v3 services
- Deploy distributed architecture

---

## Compatibility Guarantees

- **v2 scripts remain unchanged**: `scripts/run_day.py`, `scripts/run_trader.py`
- **v2 dashboard works**: `uvicorn apps.dashboard:app`
- **v2 engines unmodified**: `engine/*.py` files untouched
- **v3 services are opt-in**: Must explicitly run with `apps/run_service.py`

---

## Running Services

### Launch Individual Service
```bash
# Start market data service
python -m apps.run_service marketdata

# Start strategy service
python -m apps.run_service strategy

# Start risk/portfolio service
python -m apps.run_service risk_portfolio
```

### Future: Orchestration
```bash
# Future: Run all services via docker-compose
docker-compose -f docker-compose.v3.yml up

# Future: Run via Kubernetes
kubectl apply -f k8s/services/
```

---

## Benefits of v3 Architecture

### For Developers
- **Easier debugging**: Isolate and test individual services
- **Faster iteration**: Restart only the service you're working on
- **Clear boundaries**: Each service has a single responsibility

### For Operations
- **Independent scaling**: Scale strategy computation separately from execution
- **Gradual rollout**: Deploy new services without downtime
- **Better monitoring**: Per-service metrics and logging

### For Trading
- **Lower latency**: Optimize critical path (execution) separately
- **Higher reliability**: Service failures don't crash entire system
- **More strategies**: Add new strategy services without modifying core system

---

## Future Extensions

### Short-Term
- [ ] Implement RedisEventBus for distributed deployment
- [ ] Add service health checks and heartbeats
- [ ] Build dashboard UI for v3 service monitoring
- [ ] Implement event replay for testing and debugging

### Long-Term
- [ ] Add API Gateway service for external integrations
- [ ] Implement distributed tracing (OpenTelemetry)
- [ ] Add service mesh (Istio) for advanced routing and security
- [ ] Build machine learning service for adaptive strategies

---

## Summary

Architecture v3 represents a strategic evolution toward a scalable, maintainable trading system. The skeleton implementation provides the foundation for incremental migration while preserving all existing v2 functionality. Services can be developed, tested, and deployed independently, enabling faster innovation and more reliable operations.

The event-driven approach decouples components, making the system more flexible and easier to reason about. As the system matures, v3 will enable horizontal scaling, multi-region deployment, and advanced features like real-time strategy optimization and risk management.

---

**Next Steps**:
1. Implement business logic in service stubs (starting with MarketData)
2. Add comprehensive unit tests for EventBus and services
3. Build integration tests with mock event streams
4. Document event schemas and service contracts
5. Plan v2-to-v3 migration milestones
