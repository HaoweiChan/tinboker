/**
 * Unified Service Exports
 *
 * Central export point for API services.
 * Components should import from here or directly from api/.
 */

export * from './api/index';
export * from './api/transformers';
export { fetchWithFallback, fetchWithFallbackAndErrorHandler, checkBackendAvailability } from './api/migration';

export type {
  CompanyDetail,
  ConceptMetadata,
  ContentAsset,
  ContentIndexResponse,
  GraphData,
  StockEvent,
  TimeframeOption,
} from './types';
