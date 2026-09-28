-- Applied idempotently by create_all_tables during normal API startup.
-- Pending reservations must be reconciled before adding this index to a database
-- that already contains multiple pending mandates per user and environment.
BEGIN;
ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS paid_until TIMESTAMPTZ;
CREATE UNIQUE INDEX IF NOT EXISTS uq_one_open_sub_per_user_env
ON subscriptions (user_id, gateway_env)
WHERE status IN ('pending', 'active', 'cancelling');
DROP INDEX IF EXISTS uq_one_active_sub_per_user;
COMMIT;
