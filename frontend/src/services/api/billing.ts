import { apiClient } from './client';
import { parseResponse, BillingPlansSchema, type BillingPlans } from '../../validation/schemas';

/** Public plan info for the /membership page — price, founding-seat availability,
 * and whether checkout is open yet. PR 3a ships no checkout endpoint at all. */
export async function getPlans(): Promise<BillingPlans> {
  const response = await apiClient.get('/api/billing/plans');
  return parseResponse(BillingPlansSchema, response.data);
}

/** PR 3b implements the real NewebPay checkout redirect. Kept here (rather than
 * inlined in MembershipPage) so the page's button always calls the same function,
 * whether or not checkout is wired up yet. */
export async function startCheckout(): Promise<never> {
  throw new Error('checkout not implemented');
}
