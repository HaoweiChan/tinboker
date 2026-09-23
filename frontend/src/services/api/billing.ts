import { z } from 'zod';
import { apiClient } from './client';

const PlansSchema = z.object({
  list_price: z.number().int().positive(),
  founding_price: z.number().int().positive(),
  founding_remaining: z.number().int().nonnegative(),
  founding_open: z.boolean(),
  checkout_open: z.boolean(),
});
export type MembershipPlans = z.infer<typeof PlansSchema>;

export async function getMembershipPlans(): Promise<MembershipPlans> {
  const response = await apiClient.get('/api/billing/plans');
  return PlansSchema.parse(response.data);
}
