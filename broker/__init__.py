"""
Broker abstractions:

- kite_client: real KiteConnect client for live trading and data.
- paper_broker: in-memory paper broker (no real orders).
- execution_router: chooses between live and paper broker based on config.
"""
