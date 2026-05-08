/**
 * API call wrapper with in-memory caching and request deduplication.
 * Falls back to provided default value on API failure.
 */

interface CacheEntry<T> {
  data: T;
  timestamp: number;
}

const apiCache = new Map<string, CacheEntry<unknown>>();
const CACHE_TTL_MS = 30000;
const inFlightRequests = new Map<string, Promise<unknown>>();

/**
 * Call an API endpoint with caching, deduplication, and fallback on failure.
 */
export async function fetchWithFallback<T>(
  apiCall: () => Promise<T>,
  fallback: T,
  endpointName: string
): Promise<T> {
  const cached = apiCache.get(endpointName);
  if (cached && Date.now() - cached.timestamp < CACHE_TTL_MS) {
    return cached.data as T;
  }

  const inFlight = inFlightRequests.get(endpointName);
  if (inFlight) {
    return inFlight as Promise<T>;
  }

  const requestPromise = (async () => {
    try {
      const result = await apiCall();
      apiCache.set(endpointName, { data: result, timestamp: Date.now() });
      return result;
    } catch (error) {
      console.warn(`[API] ${endpointName} failed, using fallback:`, error instanceof Error ? error.message : error);
      return fallback;
    } finally {
      inFlightRequests.delete(endpointName);
    }
  })();

  inFlightRequests.set(endpointName, requestPromise);
  return requestPromise;
}

/**
 * Variant with custom error handler.
 */
export async function fetchWithFallbackAndErrorHandler<T>(
  apiCall: () => Promise<T>,
  fallback: T,
  endpointName: string,
  onError?: (error: unknown) => void
): Promise<T> {
  try {
    return await apiCall();
  } catch (error) {
    if (onError) {
      onError(error);
    } else {
      console.warn(`[API] ${endpointName} failed, using fallback:`, error instanceof Error ? error.message : error);
    }
    return fallback;
  }
}

/**
 * Check if backend API is reachable.
 */
export async function checkBackendAvailability(): Promise<boolean> {
  try {
    const response = await fetch(
      `${import.meta.env.VITE_API_BASE_URL || 'http://localhost:3000'}/health`,
      { method: 'GET', signal: AbortSignal.timeout(1000) }
    );
    return response.ok;
  } catch {
    return false;
  }
}
