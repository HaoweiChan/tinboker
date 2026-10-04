/**
 * API client for membership promo codes (admin). Not to be confused with
 * adminPromo.ts, which composes Threads promo posts.
 */

import { z } from 'zod';
import { apiClient } from './client';
import { useAppStore } from '@/store/useAppStore';

const PromoCodeSchema = z.object({
  code: z.string(),
  amount_off: z.number().int().positive(),
  max_uses: z.number().int().nonnegative(),
  active: z.boolean(),
  used_production: z.number().int().nonnegative(),
  used_sandbox: z.number().int().nonnegative(),
});
export type AdminPromoCode = z.infer<typeof PromoCodeSchema>;
export type AdminPromoCodeInput = Pick<AdminPromoCode, 'amount_off' | 'max_uses' | 'active'>;

const RedemptionSchema = z.object({
  code: z.string(),
  email: z.string(),
  gateway_env: z.enum(['sandbox', 'production']),
  status: z.string(),
  amount: z.number().int().nonnegative(),
  counted: z.boolean(),
  created_at: z.string(),
  paid_until: z.string().nullable(),
});
export type AdminPromoRedemption = z.infer<typeof RedemptionSchema>;

function adminAuthConfig() {
  const token = useAppStore.getState().token;
  if (!token) throw new Error('Not authenticated');
  return { headers: { Authorization: `Bearer ${token}` } };
}

export async function listPromoCodes(): Promise<AdminPromoCode[]> {
  const response = await apiClient.get('/api/admin/promo-codes', adminAuthConfig());
  return z.array(PromoCodeSchema).parse(response.data);
}

/** Latest checkouts that carried a code, both gateways, newest first. */
export async function listPromoRedemptions(): Promise<AdminPromoRedemption[]> {
  const response = await apiClient.get('/api/admin/promo-codes/redemptions', adminAuthConfig());
  return z.array(RedemptionSchema).parse(response.data);
}

/** Creates the code, or edits it when it already exists. */
export async function savePromoCode(code: string, input: AdminPromoCodeInput): Promise<AdminPromoCode> {
  const response = await apiClient.put(`/api/admin/promo-codes/${encodeURIComponent(code)}`, input, adminAuthConfig());
  return PromoCodeSchema.parse(response.data);
}
