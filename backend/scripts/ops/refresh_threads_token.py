#!/usr/bin/env python3
"""Refresh the long-lived Threads access token in GCP Secret Manager.

Threads long-lived tokens expire after 60 days, but can be refreshed once they are
at least 24h old — each refresh extends validity another 60 days. Run on a schedule
(monthly) so the token never lapses. Reads + writes the GSM secret
``THREADS_ACCESS_TOKEN``; the new token value is never printed.

The backend reads the token at startup, so a refreshed token takes effect on the
next deploy/restart. The companion workflow restarts the prod backend after a
successful refresh so it's effective immediately.

Exit codes: 0 = refreshed or nothing-to-do (don't fail the schedule on a too-new /
unset token); 1 = a real error (can't read the secret, write failed).

Facebook Page tokens derived from a long-lived user token do NOT expire, so there
is nothing to refresh for Facebook here.
"""
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

from google.api_core import exceptions as gcp_exceptions
from google.cloud import secretmanager

PROJECT = os.environ.get("GCP_PROJECT_ID", "gen-lang-client-0901363254")
SECRET = "THREADS_ACCESS_TOKEN"
REFRESH_URL = "https://graph.threads.net/refresh_access_token"


def _set_output(key: str, value: str) -> None:
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as f:
            f.write(f"{key}={value}\n")


def main() -> int:
    client = secretmanager.SecretManagerServiceClient()
    name = f"projects/{PROJECT}/secrets/{SECRET}/versions/latest"
    try:
        token = client.access_secret_version(request={"name": name}).payload.data.decode("utf-8").strip()
    except gcp_exceptions.NotFound:
        print(f"::warning::{SECRET} does not exist yet — create it with the long-lived token first; nothing to refresh")
        return 0
    except Exception as e:  # noqa: BLE001
        print(f"::error::cannot read {SECRET}: {e}")
        return 1
    if not token:
        print(f"::warning::{SECRET} is unset — add the long-lived token first; nothing to refresh")
        return 0

    query = urllib.parse.urlencode({"grant_type": "th_refresh_token", "access_token": token})
    try:
        with urllib.request.urlopen(f"{REFRESH_URL}?{query}", timeout=30) as resp:
            data = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        # 400 is typically "token too new to refresh (<24h)" or "expired" — log, don't
        # hard-fail the monthly schedule (a fresh deploy resets the 24h clock).
        print(f"::warning::Threads refresh returned HTTP {e.code}: {body}")
        return 0 if e.code == 400 else 1
    except Exception as e:  # noqa: BLE001
        print(f"::error::Threads refresh request failed: {e}")
        return 1

    new_token = data.get("access_token")
    expires_in = data.get("expires_in")
    if not new_token:
        print(f"::warning::refresh response had no access_token: {data}")
        return 0
    if new_token == token:
        print(f"token unchanged (expires_in={expires_in}s); nothing to write")
        return 0

    try:
        client.add_secret_version(request={
            "parent": f"projects/{PROJECT}/secrets/{SECRET}",
            "payload": {"data": new_token.encode("utf-8")},
        })
    except Exception as e:  # noqa: BLE001
        print(f"::error::failed to write new {SECRET} version: {e}")
        return 1

    days = int(expires_in) // 86400 if expires_in else "?"
    print(f"✓ refreshed {SECRET} (expires_in={expires_in}s ≈ {days}d)")
    _set_output("changed", "true")
    return 0


if __name__ == "__main__":
    sys.exit(main())
