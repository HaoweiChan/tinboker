#!/usr/bin/env bash
# Mint the Threads / Facebook publishing secrets into GCP Secret Manager from the
# app credentials already in GSM (APP_ID, APP_SECRET, THREADS_APP_ID,
# THREADS_APP_SECRET). Access tokens are never printed — they go straight into GSM.
#
# The two OAuth handoffs (a Threads authorization `code`, an FB short-lived user
# token) require a one-time browser approval by the BRAND account; this script does
# the exchange + storage around them.
#
# Usage:
#   mint_social_tokens.sh social-token
#   mint_social_tokens.sh threads-url   <redirect_uri>
#   mint_social_tokens.sh threads       <code> <redirect_uri>
#   mint_social_tokens.sh facebook      <short_lived_user_token>
set -euo pipefail

PROJ="${GCP_PROJECT_ID:-gen-lang-client-0901363254}"
sec() { gcloud secrets versions access latest --secret="$1" --project="$PROJ"; }
jval() { python3 -c 'import sys,json;print(json.load(sys.stdin).get(sys.argv[1],""))' "$1"; }

put() {  # put SECRET_NAME  (value on stdin) — create-or-add-version, no echo of value
  local name="$1"
  if gcloud secrets describe "$name" --project="$PROJ" >/dev/null 2>&1; then
    gcloud secrets versions add "$name" --data-file=- --project="$PROJ" >/dev/null
  else
    gcloud secrets create "$name" --data-file=- --project="$PROJ" >/dev/null
  fi
  echo "  ✓ wrote $name"
}

# Given any FB user token: exchange to a long-lived user token, find the Page
# (matching FACEBOOK_PAGE_ID if already set, else the first), write the permanent
# Page token + id to GSM. Tokens are never printed.
_fb_pages_to_gsm() {
  local utok="$1" app_id app_secret long luser pages want pid ptok
  app_id="$(sec APP_ID)"; app_secret="$(sec APP_SECRET)"
  long="$(curl -s "https://graph.facebook.com/v21.0/oauth/access_token?grant_type=fb_exchange_token&client_id=${app_id}&client_secret=${app_secret}&fb_exchange_token=${utok}")"
  luser="$(printf '%s' "$long" | jval access_token)"
  [ -n "$luser" ] || { echo "fb_exchange_token failed: $long" >&2; exit 1; }
  pages="$(curl -s "https://graph.facebook.com/v21.0/me/accounts?access_token=${luser}")"
  want="$(sec FACEBOOK_PAGE_ID 2>/dev/null || true)"
  read -r pid ptok < <(printf '%s' "$pages" | python3 -c '
import sys, json
data = (json.load(sys.stdin) or {}).get("data") or []
want = sys.argv[1].strip()
pick = next((p for p in data if str(p.get("id")) == want), None) or (data[0] if data else None)
print((pick or {}).get("id",""), (pick or {}).get("access_token",""))
' "$want")
  [ -n "$ptok" ] || { echo "no page token in /me/accounts: $pages" >&2; exit 1; }
  printf '%s' "$pid"  | put FACEBOOK_PAGE_ID
  printf '%s' "$ptok" | put FACEBOOK_PAGE_ACCESS_TOKEN
  echo "  → FACEBOOK_PAGE_ID=${pid}"
}

cmd="${1:-}"
case "$cmd" in
  social-token)
    # Our own shared service token (not from Meta): lets the pipeline call the
    # publish endpoint without a JWT. Same value also goes in the pipeline env.
    openssl rand -hex 32 | tr -d '\n' | put TINBOKER_SOCIAL_TOKEN
    ;;

  threads-url)
    redirect="${2:?usage: threads-url <redirect_uri>}"
    app_id="$(sec THREADS_APP_ID)"
    echo "https://threads.net/oauth/authorize?client_id=${app_id}&redirect_uri=${redirect}&scope=threads_basic,threads_content_publish&response_type=code"
    ;;

  threads)
    code="${2:?usage: threads <code> <redirect_uri>}"
    redirect="${3:?usage: threads <code> <redirect_uri>}"
    app_id="$(sec THREADS_APP_ID)"; app_secret="$(sec THREADS_APP_SECRET)"
    short="$(curl -s -X POST https://graph.threads.net/oauth/access_token \
      -d client_id="$app_id" -d client_secret="$app_secret" \
      -d grant_type=authorization_code -d redirect_uri="$redirect" --data-urlencode "code=${code}")"
    stok="$(printf '%s' "$short" | jval access_token)"
    uid="$(printf '%s'  "$short" | jval user_id)"
    [ -n "$stok" ] || { echo "code→token exchange failed: $short" >&2; exit 1; }
    long="$(curl -s "https://graph.threads.net/access_token?grant_type=th_exchange_token&client_secret=${app_secret}&access_token=${stok}")"
    ltok="$(printf '%s' "$long" | jval access_token)"
    [ -n "$ltok" ] || { echo "long-lived exchange failed: $long" >&2; exit 1; }
    printf '%s' "$ltok" | put THREADS_ACCESS_TOKEN
    printf '%s' "$uid"  | put THREADS_USER_ID
    echo "  → THREADS_USER_ID=${uid}"
    ;;

  facebook)
    _fb_pages_to_gsm "${2:?usage: facebook <short_lived_user_token>}"
    ;;

  facebook-code)
    code="${2:?usage: facebook-code <code> <redirect_uri>}"
    redirect="${3:?usage: facebook-code <code> <redirect_uri>}"
    app_id="$(sec APP_ID)"; app_secret="$(sec APP_SECRET)"
    resp="$(curl -s "https://graph.facebook.com/v21.0/oauth/access_token?client_id=${app_id}&client_secret=${app_secret}&redirect_uri=${redirect}&code=${code}")"
    utok="$(printf '%s' "$resp" | jval access_token)"
    [ -n "$utok" ] || { echo "fb code→token exchange failed: $resp" >&2; exit 1; }
    _fb_pages_to_gsm "$utok"
    ;;

  *)
    echo "usage: $0 {social-token | threads-url <redirect_uri> | threads <code> <redirect_uri> | facebook <short_user_token> | facebook-code <code> <redirect_uri>}" >&2
    exit 2
    ;;
esac
