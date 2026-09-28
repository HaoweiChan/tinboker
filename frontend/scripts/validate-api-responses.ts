/**
 * API Response Validation Script
 * 
 * Tests API endpoints and validates response structures match OpenAPI schema.
 * Generates a report of mismatches and transformation issues.
 * 
 * Usage: npm run validate:api
 * Or: tsx scripts/validate-api-responses.ts
 */

import axios from 'axios';
import {
  GraphResponseSchema,
  CompanyDetailSchema,
  EventsResponseSchema,
  InteractiveModelsResponseSchema,
} from '../src/validation/schemas';
import { safeParseResponse } from '../src/validation/schemas';

// Get base URL from environment or use defaults
const getBaseURL = (): string => {
  const envUrl = process.env.VITE_API_BASE_URL;
  if (envUrl) {
    return envUrl;
  }
  // Default to localhost for validation script
  return 'http://localhost:3000';
};

// Create axios instance for validation script
const apiClient = axios.create({
  baseURL: getBaseURL(),
  timeout: 30000, // 30 seconds for validation script (more lenient for testing)
  headers: {
    'Content-Type': 'application/json',
  },
});

interface ValidationResult {
  endpoint: string;
  method: string;
  success: boolean;
  error?: string;
  responseTime?: number;
  dataShape?: string;
}

const results: ValidationResult[] = [];

async function validateEndpoint(
  name: string,
  method: 'GET' | 'POST' | 'PUT' | 'DELETE',
  url: string,
  schema?: any,
  data?: any
): Promise<void> {
  const startTime = Date.now();
  const fullUrl = `${getBaseURL()}${url}`;
  console.log(`🔗 Testing: ${method} ${fullUrl}`);
  
  try {
    const config: any = { method, url };
    if (data) {
      config.data = data;
    }

    const response = await apiClient(config);
    const responseTime = Date.now() - startTime;

    if (schema) {
      const result = safeParseResponse(schema, response.data);
      if (result.success) {
        results.push({
          endpoint: name,
          method,
          success: true,
          responseTime,
          dataShape: 'Validated against schema',
        });
        console.log(`✅ ${name} - Valid (${responseTime}ms)`);
      } else {
        results.push({
          endpoint: name,
          method,
          success: false,
          error: result.error,
          responseTime,
          dataShape: 'Schema validation failed',
        });
        console.error(`❌ ${name} - Schema validation failed:`, result.error);
      }
    } else {
      results.push({
        endpoint: name,
        method,
        success: true,
        responseTime,
        dataShape: typeof response.data,
      });
      console.log(`⚠️  ${name} - No schema defined (${responseTime}ms)`);
    }
  } catch (error: any) {
    const responseTime = Date.now() - startTime;
    const errorMessage = error.response?.data?.detail || error.message || 'Unknown error';
    results.push({
      endpoint: name,
      method,
      success: false,
      error: errorMessage,
      responseTime,
    });
    console.error(`❌ ${name} - Error:`, errorMessage);
  }
}

async function main() {
  console.log('🔍 Starting API Response Validation...\n');
  console.log(`Backend URL: ${getBaseURL()}\n`);

  // Test Graph Endpoints
  console.log('📊 Testing Graph Endpoints...');
  await validateEndpoint('GET /api/graphs', 'GET', '/api/graphs');
  // Note: createGraph requires valid data, skip for now
  // await validateEndpoint('POST /api/graphs', 'POST', '/api/graphs', null, { ... });
  
  // Test Stock Endpoints
  console.log('\n📈 Testing Stock Endpoints...');
  await validateEndpoint(
    'GET /api/stocks/{ticker}',
    'GET',
    '/api/stocks/TSLA',
    CompanyDetailSchema
  );
  await validateEndpoint('GET /api/stocks/{ticker}/basic', 'GET', '/api/stocks/TSLA/basic');

  // Test News Endpoints
  console.log('\n📰 Testing News Endpoints...');
  await validateEndpoint('GET /api/news', 'GET', '/api/news', EventsResponseSchema);

  // Test Visual Endpoints
  console.log('\n🎨 Testing Visual Endpoints...');
  await validateEndpoint('GET /api/visuals/supply-chain', 'GET', '/api/visuals/supply-chain');
  await validateEndpoint('GET /api/visuals/ownership', 'GET', '/api/visuals/ownership');
  await validateEndpoint('GET /api/visuals/cluster', 'GET', '/api/visuals/cluster');
  await validateEndpoint(
    'GET /api/visuals/interactive-models',
    'GET',
    '/api/visuals/interactive-models'
  );

  // Generate Report
  console.log('\n📋 Validation Report:');
  console.log('='.repeat(60));
  
  const successful = results.filter((r) => r.success).length;
  const failed = results.filter((r) => !r.success).length;
  const total = results.length;

  console.log(`Total Endpoints Tested: ${total}`);
  console.log(`✅ Successful: ${successful}`);
  console.log(`❌ Failed: ${failed}`);
  console.log(`Success Rate: ${((successful / total) * 100).toFixed(1)}%`);

  if (failed > 0) {
    console.log('\n❌ Failed Endpoints:');
    results
      .filter((r) => !r.success)
      .forEach((r) => {
        console.log(`  - ${r.method} ${r.endpoint}`);
        console.log(`    Error: ${r.error}`);
      });
  }

  console.log('\n⚠️  Endpoints Without Schema Validation:');
  results
    .filter((r) => r.success && r.dataShape && r.dataShape !== 'Validated against schema')
    .forEach((r) => {
      console.log(`  - ${r.method} ${r.endpoint} (${r.dataShape})`);
    });

  console.log('\n⏱️  Response Times:');
  const avgTime =
    results.reduce((sum, r) => sum + (r.responseTime || 0), 0) / results.length;
  console.log(`  Average: ${avgTime.toFixed(0)}ms`);
  const slowest = results.reduce(
    (max, r) => Math.max(max, r.responseTime || 0),
    0
  );
  console.log(`  Slowest: ${slowest}ms`);

  // Exit with error code if any validations failed
  process.exit(failed > 0 ? 1 : 0);
}

main().catch((error) => {
  console.error('Fatal error:', error);
  process.exit(1);
});
