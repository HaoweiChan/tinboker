/**
 * Mock sector/industry data for visualizations
 * 
 * SOURCE: Extracted from src/utils/graphUtils.ts
 */

import type { SectorBubbleData, SectorStat, TreeMapItem } from './types';

/**
 * Get sector bubble data for sector bubble chart
 * Used in industry analysis visualizations
 */
export const getSectorBubbleData = (): SectorBubbleData[] => [
  { id: 'semi', name: 'Semiconductors', label: 'Semiconductors', value: 10.5, marketCap: 10.5, return: 18, returnRate: 18, volume: 100 },
  { id: 'fin', name: 'Finance', label: 'Finance', value: 5.2, marketCap: 5.2, return: -2, returnRate: -2, volume: 60 },
  { id: 'ev', name: 'EV & Auto', label: 'EV & Auto', value: 4.8, marketCap: 4.8, return: 15, returnRate: 15, volume: 55 },
  { id: 'pcb', name: 'PCB Components', label: 'PCB Components', value: 5.5, marketCap: 5.5, return: 32, returnRate: 32, volume: 40 },
  { id: 'network', name: 'Networking', label: 'Networking', value: 5.1, marketCap: 5.1, return: 8, returnRate: 8, volume: 45 },
  { id: 'passive', name: 'Passive Comp.', label: 'Passive Comp.', value: 0.8, marketCap: 0.8, return: 12, returnRate: 12, volume: 30 },
  { id: 'space', name: 'Aerospace', label: 'Aerospace', value: 1.2, marketCap: 1.2, return: 26, returnRate: 26, volume: 25 },
  { id: 'plastic', name: 'Petrochemical', label: 'Petrochemical', value: 0.6, marketCap: 0.6, return: 5, returnRate: 5, volume: 20 },
  { id: 'textile', name: 'Textile', label: 'Textile', value: 0.4, marketCap: 0.4, return: 2, returnRate: 2, volume: 15 },
  { id: 'paper', name: 'Paper', label: 'Paper', value: 0.3, marketCap: 0.3, return: -1, returnRate: -1, volume: 10 },
  { id: 'shipping', name: 'Shipping', label: 'Shipping', value: 2.1, marketCap: 2.1, return: -4, returnRate: -4, volume: 35 },
  { id: 'steel', name: 'Steel', label: 'Steel', value: 1.5, marketCap: 1.5, return: 1, returnRate: 1, volume: 28 },
  { id: 'bio', name: 'Biotech', label: 'Biotech', value: 1.8, marketCap: 1.8, return: -8, returnRate: -8, volume: 22 },
  { id: 'retail', name: 'Retail', label: 'Retail', value: 2.5, marketCap: 2.5, return: 6, returnRate: 6, volume: 32 },
];

/**
 * Get sector performance stats for performance bars
 * Includes daily and weekly performance data
 */
export const getSectorPerformanceStats = (): { day: SectorStat[]; week: SectorStat[] } => {
  return {
    day: [
      { label: 'Energy', value: 0.58 },
      { label: 'Real Estate', value: 0.39 },
      { label: 'Healthcare', value: 0.28 },
      { label: 'Basic Materials', value: 0.08 },
      { label: 'Communication Services', value: 0.02 },
      { label: 'Consumer Defensive', value: -0.02 },
      { label: 'Financial', value: -0.2 },
      { label: 'Industrials', value: -0.35 },
      { label: 'Utilities', value: -0.36 },
      { label: 'Technology', value: -1.5 },
      { label: 'Consumer Cyclical', value: -1.89 },
    ],
    week: [
      { label: 'Healthcare', value: 0.59 },
      { label: 'Energy', value: -0.71 },
      { label: 'Utilities', value: -0.84 },
      { label: 'Consumer Defensive', value: -1.18 },
      { label: 'Real Estate', value: -2.23 },
      { label: 'Basic Materials', value: -2.48 },
      { label: 'Communication Services', value: -2.78 },
      { label: 'Financial', value: -3.34 },
      { label: 'Industrials', value: -3.55 },
      { label: 'Technology', value: -4.81 },
      { label: 'Consumer Cyclical', value: -6.59 },
    ],
  };
};

/**
 * Get tree map data for S&P 500 market cap visualization.
 * Simplified representation with major sector constituents.
 */
export const getTreeMapData = (): TreeMapItem[] => [
  {
    id: 'tech', name: 'Technology', value: 12000, change: 1.2,
    children: [
      { id: 'AAPL', name: 'Apple', ticker: 'AAPL', value: 3400, change: 0.8, price: '189.84' },
      { id: 'MSFT', name: 'Microsoft', ticker: 'MSFT', value: 3100, change: 1.5, price: '420.21' },
      { id: 'NVDA', name: 'NVIDIA', ticker: 'NVDA', value: 2600, change: 3.2, price: '131.29' },
      { id: 'AVGO', name: 'Broadcom', ticker: 'AVGO', value: 800, change: 2.1, price: '172.33' },
      { id: 'ORCL', name: 'Oracle', ticker: 'ORCL', value: 400, change: -0.4, price: '164.87' },
      { id: 'CRM', name: 'Salesforce', ticker: 'CRM', value: 300, change: -1.2, price: '272.44' },
      { id: 'AMD', name: 'AMD', ticker: 'AMD', value: 280, change: 2.8, price: '160.55' },
      { id: 'INTC', name: 'Intel', ticker: 'INTC', value: 140, change: -2.5, price: '30.18' },
    ],
  },
  {
    id: 'comm', name: 'Communication Services', value: 4500, change: 0.6,
    children: [
      { id: 'GOOGL', name: 'Alphabet', ticker: 'GOOGL', value: 2200, change: 0.9, price: '176.43' },
      { id: 'META', name: 'Meta', ticker: 'META', value: 1500, change: 1.1, price: '510.92' },
      { id: 'NFLX', name: 'Netflix', ticker: 'NFLX', value: 300, change: -0.3, price: '628.15' },
      { id: 'DIS', name: 'Disney', ticker: 'DIS', value: 200, change: -1.8, price: '112.46' },
    ],
  },
  {
    id: 'fin', name: 'Financials', value: 3200, change: -0.3,
    children: [
      { id: 'BRK.B', name: 'Berkshire', ticker: 'BRK.B', value: 900, change: 0.2, price: '441.50' },
      { id: 'JPM', name: 'JPMorgan', ticker: 'JPM', value: 700, change: -0.5, price: '205.13' },
      { id: 'V', name: 'Visa', ticker: 'V', value: 550, change: 0.4, price: '281.37' },
      { id: 'MA', name: 'Mastercard', ticker: 'MA', value: 450, change: 0.3, price: '467.28' },
      { id: 'BAC', name: 'BofA', ticker: 'BAC', value: 320, change: -1.1, price: '38.92' },
      { id: 'GS', name: 'Goldman', ticker: 'GS', value: 180, change: -0.8, price: '462.91' },
    ],
  },
  {
    id: 'health', name: 'Healthcare', value: 3000, change: 0.4,
    children: [
      { id: 'LLY', name: 'Eli Lilly', ticker: 'LLY', value: 800, change: 1.4, price: '790.55' },
      { id: 'UNH', name: 'UnitedHealth', ticker: 'UNH', value: 550, change: -0.6, price: '522.18' },
      { id: 'JNJ', name: 'J&J', ticker: 'JNJ', value: 400, change: 0.2, price: '155.40' },
      { id: 'ABBV', name: 'AbbVie', ticker: 'ABBV', value: 350, change: 0.8, price: '176.93' },
      { id: 'MRK', name: 'Merck', ticker: 'MRK', value: 320, change: -0.4, price: '127.88' },
      { id: 'PFE', name: 'Pfizer', ticker: 'PFE', value: 160, change: -1.9, price: '28.12' },
    ],
  },
  {
    id: 'cons-disc', name: 'Consumer Discretionary', value: 2800, change: -0.8,
    children: [
      { id: 'AMZN', name: 'Amazon', ticker: 'AMZN', value: 1900, change: -0.5, price: '186.49' },
      { id: 'TSLA', name: 'Tesla', ticker: 'TSLA', value: 600, change: -2.7, price: '177.58' },
      { id: 'HD', name: 'Home Depot', ticker: 'HD', value: 380, change: 0.3, price: '345.12' },
    ],
  },
  {
    id: 'industrials', name: 'Industrials', value: 1800, change: -0.2,
    children: [
      { id: 'GE', name: 'GE Aerospace', ticker: 'GE', value: 500, change: 0.6, price: '167.33' },
      { id: 'CAT', name: 'Caterpillar', ticker: 'CAT', value: 400, change: -0.9, price: '341.88' },
      { id: 'RTX', name: 'RTX Corp', ticker: 'RTX', value: 350, change: 0.1, price: '108.54' },
      { id: 'UNP', name: 'Union Pacific', ticker: 'UNP', value: 300, change: -0.3, price: '244.76' },
    ],
  },
  {
    id: 'cons-stap', name: 'Consumer Staples', value: 1500, change: 0.1,
    children: [
      { id: 'WMT', name: 'Walmart', ticker: 'WMT', value: 500, change: 0.5, price: '67.12' },
      { id: 'PG', name: 'P&G', ticker: 'PG', value: 400, change: 0.2, price: '165.30' },
      { id: 'KO', name: 'Coca-Cola', ticker: 'KO', value: 300, change: -0.1, price: '63.44' },
      { id: 'PEP', name: 'PepsiCo', ticker: 'PEP', value: 280, change: -0.4, price: '174.28' },
    ],
  },
  {
    id: 'energy', name: 'Energy', value: 1200, change: 1.5,
    children: [
      { id: 'XOM', name: 'Exxon', ticker: 'XOM', value: 500, change: 1.8, price: '117.55' },
      { id: 'CVX', name: 'Chevron', ticker: 'CVX', value: 350, change: 1.2, price: '161.30' },
      { id: 'COP', name: 'ConocoPhillips', ticker: 'COP', value: 200, change: 1.5, price: '114.62' },
    ],
  },
  {
    id: 'utilities', name: 'Utilities', value: 600, change: -0.5,
    children: [
      { id: 'NEE', name: 'NextEra', ticker: 'NEE', value: 250, change: -0.3, price: '76.88' },
      { id: 'SO', name: 'Southern Co', ticker: 'SO', value: 200, change: -0.7, price: '82.15' },
      { id: 'DUK', name: 'Duke Energy', ticker: 'DUK', value: 150, change: -0.4, price: '104.32' },
    ],
  },
  {
    id: 'materials', name: 'Materials', value: 500, change: 0.3,
    children: [
      { id: 'LIN', name: 'Linde', ticker: 'LIN', value: 220, change: 0.5, price: '462.71' },
      { id: 'APD', name: 'Air Products', ticker: 'APD', value: 150, change: 0.1, price: '293.44' },
      { id: 'SHW', name: 'Sherwin-Williams', ticker: 'SHW', value: 130, change: 0.2, price: '338.92' },
    ],
  },
  {
    id: 'realestate', name: 'Real Estate', value: 400, change: -1.0,
    children: [
      { id: 'PLD', name: 'Prologis', ticker: 'PLD', value: 180, change: -1.2, price: '126.88' },
      { id: 'AMT', name: 'American Tower', ticker: 'AMT', value: 120, change: -0.8, price: '210.54' },
      { id: 'EQIX', name: 'Equinix', ticker: 'EQIX', value: 100, change: -0.9, price: '832.17' },
    ],
  },
];

