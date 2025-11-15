# scripts/login_kite.py
from __future__ import annotations

import argparse
import sys
import webbrowser
from typing import Optional, Tuple

from kiteconnect import KiteConnect, exceptions as kite_exceptions

from core.kite_env import (
    read_api_creds,
    write_token,
    print_loaded_paths,
)

BANNER = """
=== Kite Interactive Login ===
1) This will print a login URL.
2) Open it in your browser and complete login/2FA.
3) You'll be redirected to your app's redirect URL with a `request_token` query parameter.
4) Paste that `request_token` back here.
"""

def _get_client() -> Tuple[KiteConnect, str, str]:
    api_key, api_secret = read_api_creds()
    kite = KiteConnect(api_key=api_key, timeout=10)
    return kite, api_key, api_secret

def interactive_login_once(open_browser: bool = True, request_token: Optional[str] = None) -> None:
    kite, api_key, api_secret = _get_client()

    login_url = kite.login_url()
    print_loaded_paths()
    print(BANNER)
    print(f"Login URL:\n  {login_url}\n")

    if open_browser:
        try:
            webbrowser.open(login_url, new=2, autoraise=True)
        except Exception:
            pass

    if not request_token:
        request_token = input("Enter request_token from redirected URL: ").strip()

    if not request_token:
        print("No request_token provided. Aborting.")
        sys.exit(2)

    try:
        data = kite.generate_session(request_token, api_secret)
        access_token = data.get("access_token")
        public_token = data.get("public_token")
        if not access_token:
            print("Login failed: no access_token in response.")
            sys.exit(1)
        write_token(access_token, public_token)
        print("\n✅ Login successful.")
        print("Access token saved to /secrets/kite_tokens.env")
    except kite_exceptions.TokenException as exc:
        print(f"\n❌ TokenException: {exc}")
        sys.exit(1)
    except Exception as exc:
        print(f"\n❌ Login failed: {exc}")
        sys.exit(1)


# Back-compat entry used by other scripts
def interactive_login_files() -> None:
    interactive_login_once(open_browser=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Interactive Zerodha Kite login")
    parser.add_argument("--no-open", action="store_true", help="Do not auto-open the browser")
    parser.add_argument("--request-token", help="Provide request_token non-interactively")
    args = parser.parse_args()

    interactive_login_once(open_browser=not args.no_open, request_token=args.request_token)


if __name__ == "__main__":
    main()
