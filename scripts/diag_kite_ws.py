# scripts/diag_kite_ws.py
"""
Diagnose Kite WebSocket connection health.

Connects to the WebSocket, subscribes to nothing, and waits 5 seconds
to see if the connection is stable. Prints profile info on success.

Usage:
    python -m scripts.diag_kite_ws
"""
import logging
import sys
import time
import threading

from kiteconnect import KiteTicker

# Add project root to path to allow absolute imports
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.kite_env import make_kite_client_from_files, read_api_creds, read_tokens

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("diag_kite_ws")

def main():
    log.info("Starting Kite WebSocket diagnostic tool...")
    try:
        api_key, _ = read_api_creds()
        access_token, _, _, token_api_key = read_tokens()
    except Exception as e:
        log.error("Failed to read API credentials or tokens from /secrets/: %s", e)
        log.error("Please ensure /secrets/kite.env and /secrets/kite_tokens.env are correctly set up.")
        return

    if not access_token:
        log.error("KITE_ACCESS_TOKEN not found in /secrets/kite_tokens.env. Please login first.")
        return

    log.info(f"Using API Key: {api_key}")
    if token_api_key:
        log.info(f"Token was generated for API Key: {token_api_key}")
        if api_key != token_api_key:
            log.warning("Mismatch between current API key and token's API key!")

    # Use a separate client to fetch profile to confirm REST API works
    try:
        kite_rest = make_kite_client_from_files()
        profile = kite_rest.profile()
        log.info("Successfully fetched profile via REST API:")
        log.info(f"  User: {profile.get('user_id')} ({profile.get('user_name')})")
        log.info(f"  Email: {profile.get('email')}")
        log.info(f"  Broker: {profile.get('broker')}")
    except Exception as e:
        log.error("Failed to fetch profile using REST client: %s", e)
        log.error("The access token might be invalid or expired.")
        return

    # Now, test the WebSocket connection
    kws = KiteTicker(api_key, access_token)
    connection_closed = threading.Event()

    def on_connect(ws, response):
        log.info("WebSocket connection established.")
        log.info("Will wait for 5 seconds to check stability...")

    def on_close(ws, code, reason):
        log.info(f"WebSocket connection closed. Code: {code}, Reason: {reason}")
        connection_closed.set()

    def on_error(ws, code, reason):
        log.error(f"WebSocket error. Code: {code}, Reason: {reason}")

    def on_ticks(ws, ticks):
        # We don't subscribe, but good to have a handler
        log.info(f"Received {len(ticks)} ticks (unexpected, as we subscribed to none).")

    kws.on_connect = on_connect
    kws.on_close = on_close
    kws.on_error = on_error
    kws.on_ticks = on_ticks

    log.info("Connecting to WebSocket...")
    kws.connect(threaded=True)

    # Wait for connection to be established
    time.sleep(2)
    if not kws.is_connected():
        log.error("Failed to establish WebSocket connection after 2 seconds.")
        connection_closed.set()
    else:
        time.sleep(5) # The main wait
        log.info("5-second wait complete. Closing connection.")

    kws.stop()
    connection_closed.wait(timeout=5) # Wait for graceful close
    log.info("Diagnostic finished.")


if __name__ == "__main__":
    main()
