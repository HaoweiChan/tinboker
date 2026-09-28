# NewebPay membership billing

TinBoker uses NewebPay credit-card periodic payments for monthly membership. Card details are entered on NewebPay's hosted page and are not sent to TinBoker.

## Environment and merchant setup

- Development and staging use the sandbox merchant; production uses the production merchant. The environment is derived from `ENVIRONMENT`, not a client request.
- Sandbox checkout is restricted to administrators. Sandbox payments record their own paid term and do not change the shared production `users.member_until` entitlement.
- Membership-preview sessions cannot create or cancel payment mandates. Sign in again normally before testing payment.
- Development enables checkout in Compose, subject to valid sandbox credentials. Staging and production keep `NEWEBPAY_CHECKOUT_ENABLED=false`. Changing this flag does not disable callbacks or cancellation of existing mandates.
- Store `NEWEBPAY_SANDBOX_MERCHANT_ID`, `NEWEBPAY_SANDBOX_HASH_KEY`, and `NEWEBPAY_SANDBOX_HASH_IV` in Google Secret Manager, project `gen-lang-client-0901363254`. Use the corresponding names without `SANDBOX_` only for production. Never paste credential values into chat, commits, or documentation.
- The merchant must have credit-card periodic payments enabled. Credentials alone do not prove merchant approval or successful payment.
- Apply configuration and code through the normal Git/PR/CI deployment. Do not edit or restart the deployed application manually.

## API flow

1. `GET /api/billing/plans` supplies current pricing and advisory founding-member availability.
2. Authenticated `POST /api/billing/checkout` reserves a server-priced order and returns the hosted form action and encrypted fields. The frontend submits those fields to NewebPay.
3. `POST /api/billing/notify` verifies provider notifications. `POST /api/billing/return` also verifies the encrypted first-payment result before redirecting to the fixed membership page. Both paths use the same idempotent event processor.
4. Authenticated `GET /api/billing/subscription` returns only the caller's subscription in the current gateway environment, with private cache headers. The membership page uses it to show the result and refresh the signed-in user's effective access.
5. Authenticated `POST /api/billing/cancel` stops the recurring mandate at NewebPay. Already paid access remains valid until its recorded expiry.

The browser's return query is never proof of payment. A successful provider event must match the stored order, merchant, gateway environment and amount. Repeated notifications must not grant the same term twice. Provider failures must not erase an already paid term.

An unresolved checkout keeps its order and founding-price reservation. The provider's timestamp acceptance window does not prove that an already opened card/3DS page has expired, so a local timer must not release the reservation or silently create another mandate. A definitively failed first payment can be retried as a new order. If the provider never delivers a conclusive result, reconcile the order in the merchant dashboard before changing its state; do not fabricate a successful callback.

## Callback origins

| Environment | API origin | Return page |
|---|---|---|
| Development | `https://dev-api.tinboker.com` | `https://dev.tinboker.com/membership` |
| Staging | `https://staging-api.tinboker.com` | `https://staging.tinboker.com/membership` |
| Production | `https://api.tinboker.com` | `https://tinboker.com/membership` |

Each API origin uses `/api/billing/return` and `/api/billing/notify`. They must remain publicly reachable for provider POSTs; they authenticate provider content rather than requiring a browser login. Do not put the callback paths behind an interactive access challenge.

## Verification before accepting real payments

Run the billing tests, full backend suite, frontend build/lint checks, and billing frontend harness. Then use an approved sandbox merchant to verify a complete hosted checkout, callback, subscription lookup, repeated notification, and cancellation. Inspect only non-sensitive status and order references; do not log full provider payloads or card data.

Focused local checks:

```bash
cd backend
pytest tests/test_billing_flow.py tests/test_newebpay.py tests/test_billing_models.py
```

```bash
cd frontend
node scripts/validate-billing.mjs
npm run build
```

A green mocked test suite does not establish that the merchant account can charge cards. Production activation requires the production merchant setup and a separate release decision.

## Provider reference

Use the official [NewebPay API download catalog](https://www.newebpay.com/website/Page/content/download_api), credit-card periodic payment manual NDNP-1.0.8 (API version 1.5). Periodic uses AES-256-CBC encrypted payloads; it does not use the MPG `TradeSha` contract. Creation and status-alteration requests post `MerchantID_` and `PostData_`; the status-alteration response uses the lowercase `period` encrypted field. Treat first-auth and recurring payload schemas separately.
