export type Stance = 'BULLISH' | 'BEARISH' | 'NEUTRAL';
export type Relation = 'aligned' | 'opposite' | 'reserved' | 'firmer' | 'split' | 'alone';
export interface CrossShowOthers { shows: number; mentions: number; bull: number; neutral: number; bear: number; unknown?: number; lean?: Stance | null }
export interface CrossShowRow { mention_type: 'ticker' | 'sector'; ticker: string | null; exposure_id: string | null; name?: string | null; stance?: Stance | null; others: CrossShowOthers; relation: Relation }
export interface CrossShowData { window_days: number; compared: number; opposite: number; rows: CrossShowRow[] }

export const STANCE_ZH: Record<Stance, string>;
export const CROSS_SHOW_LOCKED: string;
export function stanceZh(stance: Stance | null | undefined): string;
export function isOpposite(row: CrossShowRow): boolean;
export function comparableRows<T extends CrossShowData>(data: T | null | undefined): T['rows'];
export function othersLean(row: CrossShowRow): Stance | null;
export function othersCounts(o: CrossShowOthers): string;
export function crossShowLead(data: CrossShowData): string;
