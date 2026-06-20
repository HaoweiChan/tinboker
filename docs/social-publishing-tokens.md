# Social Publishing Tokens — Minting Threads & Facebook Credentials

How we obtained the credentials that let the platform auto-publish episode summaries
to **Threads** and a **Facebook Page**, stored as secrets in GCP Secret Manager (GSM).
This is the runbook to **re-mint** them (e.g. a token lapses, the account changes, or a
new environment needs them). Written after the first successful mint on **2026-06-19**.

> **Golden rule:** access tokens and app secrets are **never** printed to a terminal,
> pasted into chat, or committed. The helper script writes them straight into GSM. Only
> public identifiers (app IDs, Page ID, Threads user ID) appear in this doc.

---

## 1. What we need — the five secrets

All live in GSM, project `gen-lang-client-0901363254`. The backend maps each **GSM secret
name = the pydantic field name UPPERCASED** and reads them **at startup**.

| GSM secret | What it is | Expiry | Obtained by |
|---|---|---|---|
| `THREADS_ACCESS_TOKEN` | Long-lived Threads Graph API token for `@tinboker` | **60 days** (auto-refreshed) | Threads OAuth code flow → `th_exchange_token` |
| `THREADS_USER_ID` | Numeric Threads user id (`27097276223297129`) | — | returned by the code exchange / `/me` |
| `FACEBOOK_PAGE_ID` | Numeric Page id (`925882133951199`) | — | `/me/accounts` |
| `FACEBOOK_PAGE_ACCESS_TOKEN` | Page token with `pages_manage_posts` | **does not expire** | long-lived user token → `/me/accounts` |
| `TINBOKER_SOCIAL_TOKEN` | Our own shared secret so the pipeline can call the publish endpoint without a JWT | — | `openssl rand` |

**Consumers:**
- **Backend** (publishing): uses only the access tokens + IDs above. It calls the
  Graph APIs directly with `THREADS_ACCESS_TOKEN` / `FACEBOOK_PAGE_ACCESS_TOKEN`.
- **Pipeline** (`pipelines/.../social_publish.py`): calls `POST /api/admin/threads/publish`
  authenticated with `TINBOKER_SOCIAL_TOKEN`.
- **Refresh** (`.github/workflows/refresh-social-tokens.yml`): refreshes only
  `THREADS_ACCESS_TOKEN`.

---

## 2. The Meta app topology (important — this is what trips people up)

There are **two** Meta apps, one nested in the other:

| App | App ID | Used for |
|---|---|---|
| **Tinboker** (parent, "Facebook" type) | `2682941075440578` | Facebook Page publishing (`pages_*` scopes) |
| **Threads app** (nested under Tinboker) | `4336105959996578` | Threads publishing (`threads_*` scopes) |

- Brand account: **@tinboker** (Threads user id `27097276223297129`).
- The Threads app **redirects/authorizes under the parent app** but has its **own app ID
  and own app secret** — you must use the Threads app ID `4336105959996578` (not the
  parent `2682941075440578`) for Threads OAuth.
- Registered OAuth redirect URI (both apps): **`https://tinboker.com/oauth/callback`**
  (and `tinboker.com` added under **App Domains**). `tinboker.com` is a SPA with no real
  `/oauth/callback` route — it just loads the homepage; we read the `code` from the
  network log (see §6).

### App credentials (only needed for minting)

Minting needs four more GSM secrets that hold the **app** credentials:

| GSM secret | Where to find it in the Meta dashboard |
|---|---|
| `APP_ID` | parent app → App settings → Basic → "App ID" (`2682941075440578`) |
| `APP_SECRET` | parent app → App settings → Basic → "App secret" → **Show** (re-enter password) |
| `THREADS_APP_ID` | Threads app → App settings → Basic → "App ID" (`4336105959996578`) |
| `THREADS_APP_SECRET` | Threads app → App settings → Basic → "App secret" → **Show** |

> These four are used **only** by the minting script — not by the backend at runtime and
> not by the refresh job. After a successful mint they were **disabled** in GSM (2026-06-19)
> to shrink the secret surface. To re-mint, re-create or re-enable them from the dashboard
> values above:
> ```bash
> # re-enable a disabled version …
> gcloud secrets versions enable 1 --secret=THREADS_APP_SECRET --project=gen-lang-client-0901363254
> # … or set a fresh value
> printf '%s' '<value-from-dashboard>' | gcloud secrets versions add THREADS_APP_SECRET \
>   --data-file=- --project=gen-lang-client-0901363254
> ```

---

## 3. ⚠️ The two gotchas that cost us hours

**Gotcha #1 — Threads Tester role ≠ OAuth consent.** The `threads_basic` /
`threads_content_publish` scopes only work in dev/standard mode if the authorizing
account is an **accepted Threads Tester**. This is set at:

> Tinboker app → **App roles → Roles → Threads Testers** → add `@tinboker` → the account
> must **accept** the invite (it then shows as a "Threads Tester" row).

This is **not** the same as the "Website permissions / Active: Tinboker" entry on the
Threads profile — that is just the OAuth consent grant. Without the *tester role*, the
`th_exchange_token` (short → long-lived) step fails with:

```
requires the threads_basic permission. You must submit for app review,
or your user must be in the list of Threads testers.
```

**Gotcha #2 — the Graph API Explorer's "Generate Threads Access Token" gives the wrong
token.** With the Meta App set to **Tinboker** (the parent), that button mints a token
against the **parent FB app** with `pages_*` scopes — it is a Facebook token, not a
Threads token. On `graph.threads.net` it fails with `Cannot parse access token` (code 190).
You can confirm what a token actually is with `debug_token` (see §7) — look at `app_id`
and `scopes`. **Do not** use the Explorer for Threads; use the OAuth code flow in §6.

Two more sharp edges:
- The SPA **strips `?code=` from the address bar** on redirect — capture it from the
  browser **Network** tab (the `…/oauth/callback?code=` document request), not the URL bar.
- Authorization `code`s are **single-use and expire in minutes** — run the exchange
  immediately after capturing one.

---

## 4. The helper script

`backend/scripts/ops/mint_social_tokens.sh` does every exchange and writes results to GSM
without printing tokens. It reads the app creds (`APP_ID`, `APP_SECRET`, `THREADS_APP_ID`,
`THREADS_APP_SECRET`) from GSM.

```
mint_social_tokens.sh social-token                       # → TINBOKER_SOCIAL_TOKEN
mint_social_tokens.sh threads-url   <redirect_uri>        # prints the Threads authorize URL
mint_social_tokens.sh threads       <code> <redirect_uri> # → THREADS_ACCESS_TOKEN + THREADS_USER_ID
mint_social_tokens.sh facebook      <short_lived_user_token>     # → FACEBOOK_PAGE_ID + ..._ACCESS_TOKEN
mint_social_tokens.sh facebook-code <code> <redirect_uri>       # same, from an OAuth code
```

Each section below also lists the **raw API calls** the script runs, so the procedure
works with or without the script.

---

## 5. Procedure A — `TINBOKER_SOCIAL_TOKEN` (the easy one)

This is our own shared secret, not from Meta. It lets the pipeline authenticate to the
publish endpoint. The **same value** must also be set in the pipeline's VPS env.

```bash
bash backend/scripts/ops/mint_social_tokens.sh social-token
# equivalent: openssl rand -hex 32 | gcloud secrets versions add TINBOKER_SOCIAL_TOKEN --data-file=-
```

---

## 6. Procedure B — Threads (`THREADS_ACCESS_TOKEN` + `THREADS_USER_ID`)

**Pre-req:** `@tinboker` is an **accepted Threads Tester** (§3, Gotcha #1).

**Step 1 — get the authorize URL** (uses the *Threads* app ID + the `threads_*` scopes):

```bash
bash backend/scripts/ops/mint_social_tokens.sh threads-url "https://tinboker.com/oauth/callback"
```
Produces:
```
https://threads.net/oauth/authorize?client_id=4336105959996578&redirect_uri=https://tinboker.com/oauth/callback&scope=threads_basic,threads_content_publish&response_type=code
```

**Step 2 — authorize in a browser, signed in as the brand account.** Open the URL. On the
consent screen ("Tinboker is requesting access to … Create and share posts on Threads
profile") click **Continue As tinboker**. Keep the *Optional* "Create and share posts"
permission enabled — that is `threads_content_publish`, required to post.

**Step 3 — capture the `code`.** The browser redirects to
`https://tinboker.com/oauth/callback?code=AQ…` and the SPA immediately rewrites the URL to
`/`. Open DevTools → **Network** **before** the redirect completes (or re-run the authorize
URL with Network already open) and copy the full `code` from the
`…/oauth/callback?code=AQ…` request. Drop any trailing `#_` fragment.

**Step 4 — exchange + store** (do this immediately; codes expire fast):

```bash
bash backend/scripts/ops/mint_social_tokens.sh threads "AQ…<code>…" "https://tinboker.com/oauth/callback"
```

Under the hood:
```bash
# code → short-lived token + user_id
curl -s -X POST https://graph.threads.net/oauth/access_token \
  -d client_id="$THREADS_APP_ID" -d client_secret="$THREADS_APP_SECRET" \
  -d grant_type=authorization_code -d redirect_uri="https://tinboker.com/oauth/callback" \
  --data-urlencode "code=AQ…"
# short-lived → long-lived (60-day)
curl -s "https://graph.threads.net/access_token?grant_type=th_exchange_token&client_secret=$THREADS_APP_SECRET&access_token=<short_token>"
```
The script writes `THREADS_ACCESS_TOKEN` (the long-lived token) and `THREADS_USER_ID`
(the `user_id` from the first response).

**Step 5 — verify:**
```bash
TOK=$(gcloud secrets versions access latest --secret=THREADS_ACCESS_TOKEN --project=gen-lang-client-0901363254)
curl -s "https://graph.threads.net/v1.0/me?fields=id,username&access_token=$TOK"
# → {"id":"27097276223297129","username":"tinboker"}
```

---

## 7. Procedure C — Facebook Page (`FACEBOOK_PAGE_ID` + `FACEBOOK_PAGE_ACCESS_TOKEN`)

The goal is a **permanent Page token**. The reliable path is: start from a **long-lived
USER token** with Page scopes, then read `/me/accounts` — a Page token derived from a
**long-lived** user token does not expire.

**Step 1 — get a short-lived USER token** (NOT a Page token). Use the Graph API Explorer
(`developers.facebook.com/tools/explorer`) with:
- **Meta App:** Tinboker (`2682941075440578`)
- **User or Page:** *User Token*
- **Permissions:** `pages_show_list`, `pages_read_engagement`, `pages_manage_posts`
- click **Generate Access Token**, approve, copy the token.

(Or do a normal Facebook Login OAuth and capture the `code`, then use `facebook-code`.)

**Step 2 — exchange + pick the Page + store:**
```bash
bash backend/scripts/ops/mint_social_tokens.sh facebook "<short_lived_user_token>"
# or from an OAuth code:
bash backend/scripts/ops/mint_social_tokens.sh facebook-code "<code>" "https://tinboker.com/oauth/callback"
```
Under the hood:
```bash
# short-lived user → long-lived user token
curl -s "https://graph.facebook.com/v21.0/oauth/access_token?grant_type=fb_exchange_token&client_id=$APP_ID&client_secret=$APP_SECRET&fb_exchange_token=<short_user_token>"
# list pages; pick the one matching FACEBOOK_PAGE_ID (or the first) → its access_token is permanent
curl -s "https://graph.facebook.com/v21.0/me/accounts?access_token=<long_user_token>"
```
The script writes `FACEBOOK_PAGE_ID` and `FACEBOOK_PAGE_ACCESS_TOKEN`.

**Step 3 — verify it's a non-expiring Page token:**
```bash
PT=$(gcloud secrets versions access latest --secret=FACEBOOK_PAGE_ACCESS_TOKEN --project=gen-lang-client-0901363254)
curl -s "https://graph.facebook.com/v21.0/debug_token?input_token=$PT&access_token=$APP_ID|$APP_SECRET"
# expect: "type":"PAGE", "is_valid":true, "expires_at":0, scopes include "pages_manage_posts"
```

> Pitfall: if `debug_token` shows `"type":"USER"` with `pages_*` scopes, you stored the
> *user* token — re-run, the script already picks the Page token out of `/me/accounts`.
> If it shows `expires_at` ≠ 0, you started from a *short-lived* user token — exchange to
> long-lived first (the script does this for you).

---

## 8. Activation (after any mint)

1. **Backend restart/redeploy.** The backend reads GSM **at startup**, so a backend that
   was already running before the secret existed will treat that platform as unconfigured
   and force every publish into dry-run. Trigger a redeploy:
   - merge to `develop` → dev, merge to `main` → staging, `v*` tag → prod
   (any deploy re-pulls the secrets — see [deploy-flow](workflows/deploy-flow.md)).
2. **Pipeline env.** Set `TINBOKER_SOCIAL_TOKEN` in the podcast service's VPS env so
   post-ingest auto-publish can authenticate.
3. **Dry-run test** (after redeploy):
   ```bash
   curl -s -X POST "https://api.tinboker.com/api/admin/threads/publish?dry_run=true&platforms=threads,facebook" \
     -H "Authorization: Bearer $TINBOKER_SOCIAL_TOKEN"
   ```
   Both platforms should report `configured` (no longer forced-dry) and show the composed
   thread + Facebook album.

---

## 9. Token lifecycle / refresh

- **Threads** — long-lived tokens last **60 days** and can be refreshed once they're ≥24h
  old; each refresh extends another 60 days. `.github/workflows/refresh-social-tokens.yml`
  runs `backend/scripts/ops/refresh_threads_token.py` monthly (and on demand). It calls
  `GET https://graph.threads.net/refresh_access_token?grant_type=th_refresh_token&access_token=…`
  — **no app secret needed** — and writes a new `THREADS_ACCESS_TOKEN` version. The
  refreshed token takes effect on the **next backend deploy** (which happens well within
  60 days on a normal cadence). The CI service account needs `secretmanager.versions.add`
  on `THREADS_ACCESS_TOKEN`.
- **Facebook** — the Page token derived from a long-lived user token **does not expire**,
  so there is nothing to refresh. If it is ever invalidated (password change, app
  permission revoke), re-run Procedure C.

---

## 10. Security notes

- Tokens / app secrets are **never** printed or committed — `mint_social_tokens.sh` writes
  them straight into GSM.
- The four app-cred secrets (`APP_ID`, `APP_SECRET`, `THREADS_APP_ID`,
  `THREADS_APP_SECRET`) are **disabled in GSM** after minting; re-enable/re-create from the
  Meta dashboard (§2) only when re-minting.
- Public, non-secret identifiers (safe to keep in this doc): parent app `2682941075440578`,
  Threads app `4336105959996578`, Threads user `27097276223297129`, Page `925882133951199`.
- Card images for the Threads carousel / FB album must be world-readable (pipeline sets
  `public=True` on upload) or Meta's image fetch 403s.
