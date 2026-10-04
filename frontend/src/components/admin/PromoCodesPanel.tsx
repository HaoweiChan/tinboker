/**
 * Membership promo codes: create, edit the limit, switch on/off, and see how many
 * times each has been used. Codes live in the one shared database, so a code made
 * here works on production; use counts are shown per payment gateway.
 */

import React, { useCallback, useEffect, useState } from 'react';
import { isAxiosError } from 'axios';
import { Ticket } from 'lucide-react';
import { getPlans } from '@/services/api/billing';
import {
    listPromoCodes, listPromoRedemptions, savePromoCode,
    type AdminPromoCode, type AdminPromoRedemption,
} from '@/services/api/adminPromoCodes';

const inputClass = 'min-h-9 rounded-md border border-border bg-background px-2 text-base text-foreground outline-none focus-visible:ring-2 focus-visible:ring-primary';

export const PromoCodesPanel: React.FC = () => {
    const [codes, setCodes] = useState<AdminPromoCode[] | null>(null);
    const [redemptions, setRedemptions] = useState<AdminPromoRedemption[] | null>(null);
    const [listPrice, setListPrice] = useState<number | null>(null);
    const [error, setError] = useState('');
    const [saving, setSaving] = useState(false);
    const [code, setCode] = useState('');
    const [amountOff, setAmountOff] = useState('');
    const [maxUses, setMaxUses] = useState('');

    const load = useCallback(async () => {
        try {
            const [nextCodes, nextRedemptions] = await Promise.all([listPromoCodes(), listPromoRedemptions()]);
            setCodes(nextCodes);
            setRedemptions(nextRedemptions);
        } catch {
            setError('Failed to load promo codes');
        }
    }, []);

    useEffect(() => {
        void load();
        getPlans().then((plans) => setListPrice(plans.list_price)).catch(() => {});
    }, [load]);

    const save = async (target: string, input: { amount_off: number; max_uses: number; active: boolean }) => {
        setSaving(true);
        setError('');
        try {
            await savePromoCode(target, input);
            await load();
            return true;
        } catch (err) {
            setError(isAxiosError(err) && err.response?.status === 422
                ? 'Code must be 1-32 letters or digits; amount off must be above 0'
                : 'Failed to save promo code');
            return false;
        } finally {
            setSaving(false);
        }
    };

    const submit = async (event: React.FormEvent) => {
        event.preventDefault();
        const off = Number(amountOff);
        const uses = Number(maxUses);
        if (!code.trim() || !Number.isInteger(off) || off <= 0 || !Number.isInteger(uses) || uses < 0) {
            setError('Enter a code, a whole amount off above 0, and a whole number of uses');
            return;
        }
        if (await save(code.trim().toUpperCase(), { amount_off: off, max_uses: uses, active: true })) {
            setCode('');
            setAmountOff('');
            setMaxUses('');
        }
    };

    const describe = (off: number) => listPrice === null ? `−NT$${off}`
        : off >= listPrice ? 'Free (12 months, no payment)' : `NT$${listPrice - off} / month`;

    return (
        <div className="mb-8 rounded-lg border border-border bg-card p-4">
            <div className="mb-4 flex items-center gap-2">
                <Ticket className="h-5 w-5 text-muted-foreground" />
                <h2 className="text-xl font-semibold text-foreground">Membership promo codes</h2>
            </div>
            <p className="mb-4 text-base text-muted-foreground">
                One use per account. A code worth the list price or more grants 12 months with no payment.
                Codes are shared with production; uses are counted per gateway.
            </p>

            {error && <p role="alert" className="mb-3 text-base text-destructive">{error}</p>}

            <div className="overflow-x-auto">
                <table className="w-full text-left text-base">
                    <thead className="text-muted-foreground">
                        <tr className="border-b border-border">
                            <th className="py-2 pr-4 font-medium">Code</th>
                            <th className="py-2 pr-4 font-medium">Off</th>
                            <th className="py-2 pr-4 font-medium">Member pays</th>
                            <th className="py-2 pr-4 font-medium">Used (prod)</th>
                            <th className="py-2 pr-4 font-medium">Used (sandbox)</th>
                            <th className="py-2 pr-4 font-medium">Max uses</th>
                            <th className="py-2 font-medium">Status</th>
                        </tr>
                    </thead>
                    <tbody>
                        {codes === null && !error && <tr><td colSpan={7} className="py-3 text-muted-foreground">Loading…</td></tr>}
                        {codes?.length === 0 && <tr><td colSpan={7} className="py-3 text-muted-foreground">No promo codes yet.</td></tr>}
                        {codes?.map((row) => (
                            <tr key={row.code} className="border-b border-border last:border-0">
                                <td className="py-2 pr-4 font-mono text-foreground">{row.code}</td>
                                <td className="py-2 pr-4 font-mono tabular-nums">NT${row.amount_off}</td>
                                <td className="py-2 pr-4">{describe(row.amount_off)}</td>
                                <td className="py-2 pr-4 font-mono tabular-nums">{row.used_production}</td>
                                <td className="py-2 pr-4 font-mono tabular-nums">{row.used_sandbox}</td>
                                <td className="py-2 pr-4 font-mono tabular-nums">{row.max_uses}</td>
                                <td className="py-2">
                                    <button
                                        type="button"
                                        disabled={saving}
                                        onClick={() => { void save(row.code, { amount_off: row.amount_off, max_uses: row.max_uses, active: !row.active }); }}
                                        className="rounded-md border border-border px-2 py-1 text-sm hover:bg-muted disabled:opacity-50"
                                        title={row.active ? 'Stop new redemptions' : 'Allow redemptions again'}
                                    >
                                        {row.active ? 'Active — disable' : 'Disabled — enable'}
                                    </button>
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>

            <h3 className="mb-2 mt-6 text-base font-semibold text-foreground">Redemptions</h3>
            <div className="overflow-x-auto">
                <table className="w-full text-left text-base">
                    <thead className="text-muted-foreground">
                        <tr className="border-b border-border">
                            <th className="py-2 pr-4 font-medium">When</th>
                            <th className="py-2 pr-4 font-medium">Code</th>
                            <th className="py-2 pr-4 font-medium">Account</th>
                            <th className="py-2 pr-4 font-medium">Gateway</th>
                            <th className="py-2 pr-4 font-medium">Pays</th>
                            <th className="py-2 pr-4 font-medium">Status</th>
                            <th className="py-2 font-medium">Member until</th>
                        </tr>
                    </thead>
                    <tbody>
                        {redemptions?.length === 0 && <tr><td colSpan={7} className="py-3 text-muted-foreground">Nobody has used a code yet.</td></tr>}
                        {redemptions?.map((row) => (
                            <tr key={`${row.code}-${row.email}-${row.created_at}`} className={`border-b border-border last:border-0 ${row.counted ? '' : 'text-muted-foreground'}`}>
                                <td className="py-2 pr-4 font-mono tabular-nums">{new Date(row.created_at).toLocaleString('zh-TW', { hour12: false })}</td>
                                <td className="py-2 pr-4 font-mono">{row.code}</td>
                                <td className="py-2 pr-4">{row.email}</td>
                                <td className="py-2 pr-4">{row.gateway_env}</td>
                                <td className="py-2 pr-4 font-mono tabular-nums">{row.amount === 0 ? 'Free' : `NT$${row.amount}`}</td>
                                <td className="py-2 pr-4">{row.status}{row.counted ? '' : ' (use returned)'}</td>
                                <td className="py-2 font-mono tabular-nums">{row.paid_until ? new Date(row.paid_until).toLocaleDateString('zh-TW') : '—'}</td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>

            <form onSubmit={(event) => { void submit(event); }} className="mt-4 flex flex-wrap items-end gap-3">
                <label className="flex flex-col gap-1 text-sm text-muted-foreground">
                    Code
                    <input value={code} onChange={(event) => setCode(event.target.value)} maxLength={32} autoComplete="off"
                        placeholder="TINBOKER100" className={`${inputClass} w-44 font-mono uppercase`} />
                </label>
                <label className="flex flex-col gap-1 text-sm text-muted-foreground">
                    NT$ off / month
                    <input value={amountOff} onChange={(event) => setAmountOff(event.target.value)} inputMode="numeric"
                        placeholder="100" className={`${inputClass} w-28 font-mono`} />
                </label>
                <label className="flex flex-col gap-1 text-sm text-muted-foreground">
                    Max uses
                    <input value={maxUses} onChange={(event) => setMaxUses(event.target.value)} inputMode="numeric"
                        placeholder="100" className={`${inputClass} w-24 font-mono`} />
                </label>
                <button type="submit" disabled={saving}
                    className="min-h-9 rounded-md bg-primary px-4 text-base font-medium text-primary-foreground hover:opacity-90 disabled:opacity-50">
                    {saving ? 'Saving…' : 'Save code'}
                </button>
                <span className="text-sm text-muted-foreground">Saving an existing code updates its amount and limit.</span>
            </form>
        </div>
    );
};
