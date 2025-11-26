"""
Debug Kite authentication and margins fetch.

Usage:
    python -m scripts.debug_kite_auth

This script never places orders. It exercises the shared auth helpers
to validate profile and margins() responses.
"""

from __future__ import annotations

import sys
import traceback

from broker.auth import make_kite_client_from_env, token_is_valid


def main() -> int:
    profile_ok = False
    margins_ok = False
    profile_msg = ""
    margins_msg = ""
    api_source = "env/secrets"
    token_source = "env/secrets"

    try:
     kite = make_kite_client_from_env()
    except Exception as exc:  # noqa: BLE001
        print("Failed to construct Kite client from env/secrets: %s" % exc)
        return 0

    # Profile
    try:
        if token_is_valid(kite):
            prof = kite.profile()
            user_id = prof.get("user_id") or prof.get("USER_ID") or "unknown"
            user_name = prof.get("user_name") or prof.get("USER_NAME") or ""
            profile_ok = True
            profile_msg = f"Profile OK: user_id={user_id}, user_name={user_name}"
        else:
            profile_msg = "Profile ERROR: token invalid (profile() failed)"
    except Exception as exc:  # noqa: BLE001
        profile_msg = f"Profile ERROR: {exc!r}"

    # Margins
    if profile_ok:
        try:
            margins = kite.margins("equity")
            eq = margins.get("equity") if isinstance(margins, dict) and "equity" in margins else margins
            avail = eq.get("available", {}) if isinstance(eq, dict) else {}
            net = eq.get("net") if isinstance(eq, dict) else None
            cash = avail.get("cash")
            intraday = avail.get("intraday_payin") or avail.get("intradayPayin")
            margins_ok = True
            margins_msg = (
                f"Margins OK: net={net}, available.cash={cash}, intraday_payin={intraday}"
            )
        except Exception as exc:  # noqa: BLE001
            margins_msg = f"Margins ERROR: {exc!r}"
    else:
        margins_msg = "Margins SKIPPED due to profile error"

    print("=" * 60)
    print("KITE AUTH DEBUG SUMMARY")
    print("=" * 60)
    print(f"API key source      : {api_source}")
    print(f"Access token source : {token_source}")
    print(f"Profile             : {profile_msg}")
    print(f"Margins (equity)    : {margins_msg}")
    if not profile_ok or not margins_ok:
        print("HINT                : Run `python scripts/login_kite.py` to refresh token.")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        traceback.print_exc()
        sys.exit(1)
