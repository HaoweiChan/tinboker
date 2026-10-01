export type Stance = 'BULLISH' | 'BEARISH' | 'NEUTRAL';
export type Relation = 'aligned' | 'opposite' | 'reserved' | 'firmer' | 'split' | 'alone';
export interface CrossShowOthers { shows: number; mentions: number; bull: number; neutral: number; bear: number }
export interface CrossShowRow { ticker: string; name?: string | null; stance?: Stance | null; others: CrossShowOthers; relation: Relation }
export interface CrossShowData { window_days: number; shows_in_window: number; rows: CrossShowRow[] }

export const STANCE_ZH: Record<Stance, string>;
export const RELATION_ZH: Record<Relation, string>;
export function comparableRows<T extends CrossShowData>(data: T | null | undefined): T['rows'];
export function stanceZh(stance: Stance | null | undefined): string;
export function othersLine(o: CrossShowOthers): string;
export function crossShowLead(data: CrossShowData): string;
