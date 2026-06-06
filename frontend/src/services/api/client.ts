/**
 * API Client Base
 * 
 * HTTP client configuration for backend API calls using axios.
 * Provides base URL configuration, error handling, timeout, and logging.
 */

import axios from 'axios';
import type { AxiosInstance, AxiosError, AxiosRequestConfig } from 'axios';



// Extract branch name from Cloudflare Pages preview URL
// Format: {branch-name}.tinboker-platform.pages.dev or {commit-hash}.tinboker-platform.pages.dev
// NOTE: the CF Pages project is named "tinboker-platform" (immutable; predates the
// repo rename to "tinboker"), so this subdomain intentionally differs from the repo name.
// Do not "fix" it to tinboker.pages.dev unless the CF Pages project is actually migrated.
const extractBranchFromPagesUrl = (hostname: string): string | null => {
  // Match Cloudflare Pages preview URLs: something.tinboker-platform.pages.dev
  const match = hostname.match(/^([^.]+)\.tinboker-platform\.pages\.dev$/);
  if (match) {
    const prefix = match[1];
    // Skip if it looks like a commit hash (8+ hex chars only)
    if (/^[a-f0-9]{8,}$/i.test(prefix)) {
      return null;
    }
    return prefix;
  }
  return null;
};

// Check if a URL is accessible (with timeout)
const checkUrlAvailability = async (url: string, timeoutMs: number = 3000): Promise<boolean> => {
  try {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), timeoutMs);
    const response = await fetch(`${url}/health`, {
      method: 'HEAD',
      signal: controller.signal,
      mode: 'cors',
    });
    clearTimeout(timeoutId);
    return response.ok;
  } catch {
    return false;
  }
};

// Cached API URL to avoid repeated availability checks
let cachedApiUrl: string | null = null;

// Get base URL from environment or use defaults
const getBaseURL = (): string => {
  // Return cached URL if already determined
  if (cachedApiUrl) {
    return cachedApiUrl;
  }

  const envUrl = import.meta.env.VITE_API_BASE_URL;
  if (envUrl) {
    cachedApiUrl = envUrl;
    return envUrl;
  }

  // Development: use local backend by default
  if (!import.meta.env.PROD) {
    cachedApiUrl = 'http://localhost:3000';
    return cachedApiUrl;
  }

  // Production builds - check hostname
  if (typeof window === 'undefined') {
    cachedApiUrl = 'https://dev-api.tinboker.com';
    return cachedApiUrl;
  }

  const hostname = window.location.hostname;

  // Production domains
  if (hostname === 'tinboker.com' || hostname === 'www.tinboker.com') {
    cachedApiUrl = 'https://api.tinboker.com';
    console.info('Production domain detected. Using API:', cachedApiUrl);
    return cachedApiUrl;
  }

  // Dev domain
  if (hostname === 'dev.tinboker.com') {
    cachedApiUrl = 'https://dev-api.tinboker.com';
    console.info('Dev domain detected. Using API:', cachedApiUrl);
    return cachedApiUrl;
  }

  // Staging domain
  if (hostname === 'staging.tinboker.com') {
    cachedApiUrl = 'https://staging-api.tinboker.com';
    console.info('Staging domain detected. Using API:', cachedApiUrl);
    return cachedApiUrl;
  }

  // Cloudflare Pages preview deployment
  if (hostname.includes('pages.dev') || hostname.includes('vercel.app')) {
    const branchPrefix = extractBranchFromPagesUrl(hostname);
    // API selection based on branch type and PR target:
    // - hotfix/* branches → main: use production API
    // - develop branch: use dev API
    // - feat/*, fix/* branches → develop: use staging API
    if (branchPrefix && branchPrefix.startsWith('hotfix-')) {
      cachedApiUrl = 'https://api.tinboker.com';
      console.info('Hotfix preview detected. Using production API:', cachedApiUrl);
      return cachedApiUrl;
    }
    if (branchPrefix === 'develop') {
      cachedApiUrl = 'https://dev-api.tinboker.com';
      console.info('Develop preview detected. Using dev API:', cachedApiUrl);
      return cachedApiUrl;
    }
    // Default: feat/fix branches use staging API
    cachedApiUrl = 'https://staging-api.tinboker.com';
    console.info('Preview deployment detected. Using staging API:', cachedApiUrl);
    return cachedApiUrl;
  }

  // Unknown domain - use dev API
  cachedApiUrl = 'https://dev-api.tinboker.com';
  console.info('Unknown domain. Using dev API:', cachedApiUrl);
  return cachedApiUrl;
};

// Async version that checks branch-specific staging API availability
// Call this after initial page load for feat/fix branch previews
export const initializeApiUrl = async (): Promise<string> => {
  if (cachedApiUrl) {
    return cachedApiUrl;
  }

  const envUrl = import.meta.env.VITE_API_BASE_URL;
  if (envUrl) {
    cachedApiUrl = envUrl;
    return envUrl;
  }

  if (!import.meta.env.PROD || typeof window === 'undefined') {
    return getBaseURL();
  }

  const hostname = window.location.hostname;

  // For Cloudflare Pages feat/fix branch previews, try branch-specific staging API
  if (hostname.includes('pages.dev')) {
    const branchName = extractBranchFromPagesUrl(hostname);
    
    if (branchName && (branchName.startsWith('feat-') || branchName.startsWith('fix-'))) {
      // Sanitize branch name for subdomain (replace invalid chars)
      const sanitizedBranch = branchName.replace(/[^a-z0-9-]/gi, '-').toLowerCase();
      const branchApiUrl = `https://staging-api-${sanitizedBranch}.tinboker.com`;
      
      console.info(`Checking branch-specific staging API: ${branchApiUrl}`);
      const isAvailable = await checkUrlAvailability(branchApiUrl);
      
      if (isAvailable) {
        cachedApiUrl = branchApiUrl;
        console.info(`Branch-specific staging API available: ${cachedApiUrl}`);
        return cachedApiUrl;
      }
      
      console.info(`Branch-specific API not available, falling back to staging-api`);
    }
    
    // Fallback to staging API for all preview deployments
    cachedApiUrl = 'https://staging-api.tinboker.com';
    console.info(`Using staging API: ${cachedApiUrl}`);
    return cachedApiUrl;
  }

  return getBaseURL();
};

// Create axios instance with default configuration
const createApiClient = (): AxiosInstance => {
  const client = axios.create({
    baseURL: getBaseURL(),
    timeout: 30000, // 30 seconds default timeout
    headers: {
      'Content-Type': 'application/json',
    },
  });

  // Request interceptor for logging (development only)
  client.interceptors.request.use(
    (config) => {
      if (import.meta.env.DEV) {
        console.log(`[API] ${config.method?.toUpperCase()} ${config.url}`, {
          baseURL: config.baseURL,
          url: config.url,
          fullURL: `${config.baseURL}${config.url}`,
          params: config.params,
          data: config.data,
          timeout: config.timeout,
        });
      }
      return config;
    },
    (error) => {
      if (import.meta.env.DEV) {
        console.error('[API] Request interceptor error:', error);
      }
      return Promise.reject(error);
    }
  );

  // Response interceptor for error handling and logging
  client.interceptors.response.use(
    (response) => {
      if (import.meta.env.DEV) {
        console.log(`[API] ${response.config.method?.toUpperCase()} ${response.config.url} - Success`, {
          status: response.status,
          statusText: response.statusText,
          data: response.data,
          dataType: typeof response.data,
          dataKeys: response.data ? Object.keys(response.data) : 'null/undefined',
          dataLength: Array.isArray(response.data) ? response.data.length : 'not array',
        });
      }
      return response;
    },
    (error: AxiosError) => {
      // Check for silent mode (suppress error logging)
      // We check config headers or a custom config property if we cast it
      const isSilent = (error.config?.headers as any)?.['X-Silent-Error'] === 'true' || (error.config as any)?.silent === true;

      if (import.meta.env.DEV && !isSilent) {
        console.error(`[API] ${error.config?.method?.toUpperCase()} ${error.config?.url} - Error`, {
          status: error.response?.status,
          statusText: error.response?.statusText,
          data: error.response?.data,
          message: error.message,
          code: error.code,
          name: error.name,
          request: {
            status: error.request?.status,
            statusText: error.request?.statusText,
            response: error.request?.response,
            responseText: error.request?.responseText,
            responseURL: error.request?.responseURL,
            readyState: error.request?.readyState,
          },
          isNetworkError: !error.response && error.request,
          hasResponse: !!error.response,
          hasRequest: !!error.request,
        });
      }

      // Handle network errors (CORS, connection refused, etc.)
      if (!error.response && error.request) {
        // Try to recover data from the request object
        const raw = error.request.responseText || error.request.response;
        if (raw) {
          try {
            const responseData = typeof raw === 'string' ? JSON.parse(raw) : raw;
            return {
              ...error.request,
              data: responseData,
              status: error.request.status || 200,
              statusText: error.request.statusText || 'OK',
              headers: error.request.getAllResponseHeaders ? error.request.getAllResponseHeaders() : {},
              config: error.config || {},
            } as any;
          } catch {
            // Data is not parseable — fall through to rejection
          }
        }
      }

      return Promise.reject(error);
    }
  );

  return client;
};

// Export singleton instance
export const apiClient = createApiClient();

// Export types for use in other modules
export type { AxiosError, AxiosRequestConfig };
