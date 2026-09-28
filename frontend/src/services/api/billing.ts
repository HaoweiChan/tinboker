import { z } from 'zod';
import { apiClient } from './client';
import { useAppStore } from '@/store/useAppStore';
import { parseResponse, BillingPlansSchema, type BillingPlans } from '@/validation/schemas';

const GatewaySchema = z.enum(['sandbox', 'production']);
const SubscriptionSchema = z.object({
  id: z.string(),
  mer_order_no: z.string(),
  status: z.enum(['pending', 'active', 'cancelling', 'cancelled', 'ended', 'failed']),
  amount: z.number().int().positive(),
  is_founding: z.boolean(),
  gateway_env: GatewaySchema,
  paid_until: z.string().datetime({ offset: true }).nullable(),
  next_auth_date: z.string().regex(/^\d{4}-\d{2}-\d{2}$/).nullable(),
});
const SubscriptionResponseSchema = z.object({ subscription: SubscriptionSchema.nullable() });
export type BillingSubscription = z.infer<typeof SubscriptionSchema>;

const gatewayUrls = {
  sandbox: 'https://ccore.newebpay.com/MPG/period',
  production: 'https://core.newebpay.com/MPG/period',
};
const CheckoutSchema = z.object({
  action: z.string().url(),
  fields: z.object({ MerchantID_: z.string().min(1), PostData_: z.string().min(1) }).strict(),
  mer_order_no: z.string().min(1),
  gateway_env: GatewaySchema,
}).refine((checkout) => checkout.action === gatewayUrls[checkout.gateway_env], 'Unexpected payment destination');

function authConfig(signal?: AbortSignal) {
  const token = useAppStore.getState().token;
  if (!token) throw new Error('Not authenticated');
  return { headers: { Authorization: `Bearer ${token}` }, signal };
}

export async function getPlans(): Promise<BillingPlans> {
  const response = await apiClient.get('/api/billing/plans');
  return parseResponse(BillingPlansSchema, response.data);
}

/** Only server-encrypted fields leave the site; the browser never handles card data. */
export async function startCheckout(): Promise<void> {
  const response = await apiClient.post('/api/billing/checkout', {}, authConfig());
  const checkout = CheckoutSchema.parse(response.data);
  const form = document.createElement('form');
  form.method = 'POST';
  form.action = checkout.action;
  form.hidden = true;
  for (const [name, value] of Object.entries(checkout.fields)) {
    const input = document.createElement('input');
    input.type = 'hidden';
    input.name = name;
    input.value = value;
    form.append(input);
  }
  document.body.append(form);
  try { form.submit(); } finally { form.remove(); }
}

export async function getSubscription(signal?: AbortSignal): Promise<BillingSubscription | null> {
  const response = await apiClient.get('/api/billing/subscription', authConfig(signal));
  return SubscriptionResponseSchema.parse(response.data).subscription;
}

export async function cancelSubscription(): Promise<BillingSubscription | null> {
  const response = await apiClient.post('/api/billing/cancel', {}, authConfig());
  return SubscriptionResponseSchema.parse(response.data).subscription;
}
