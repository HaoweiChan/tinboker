#!/usr/bin/env node

/**
 * Setup CORS configuration for Google Cloud Storage bucket
 * 
 * This script applies CORS rules to the GCS bucket to allow cross-origin requests
 * from Vercel deployments and local development.
 * 
 * Prerequisites:
 * 1. Install Google Cloud SDK: https://cloud.google.com/sdk/docs/install
 * 2. Authenticate: gcloud auth login
 * 3. Set your project: gcloud config set project YOUR_PROJECT_ID
 * 4. Install gsutil (comes with Cloud SDK)
 * 
 * Usage:
 *   node scripts/setup-gcs-cors.mjs [bucket-name]
 * 
 * Example:
 *   node scripts/setup-gcs-cors.mjs tinboker-articles
 */

import { execSync } from 'child_process';
import { readFileSync } from 'fs';
import { fileURLToPath } from 'url';
import { dirname, join } from 'path';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

// Get bucket name from command line argument or use default
const bucketName = process.argv[2] || 'tinboker-articles';
const corsConfigPath = join(__dirname, 'cors.json');

console.log('🚀 Setting up CORS configuration for GCS bucket...\n');
console.log(`Bucket: ${bucketName}`);
console.log(`CORS config: ${corsConfigPath}\n`);

// Check if gsutil is available
try {
  execSync('which gsutil', { stdio: 'ignore' });
  console.log('✓ gsutil found\n');
} catch (error) {
  console.error('❌ Error: gsutil not found!');
  console.error('\nPlease install Google Cloud SDK:');
  console.error('  https://cloud.google.com/sdk/docs/install');
  console.error('\nAfter installation, authenticate:');
  console.error('  gcloud auth login');
  console.error('  gcloud config set project YOUR_PROJECT_ID');
  process.exit(1);
}

// Check if cors.json exists
try {
  const corsConfig = readFileSync(corsConfigPath, 'utf-8');
  console.log('✓ CORS configuration file found');
  console.log('\nConfiguration:');
  console.log(corsConfig);
  console.log('');
} catch (error) {
  console.error(`❌ Error: Could not read ${corsConfigPath}`);
  process.exit(1);
}

// Apply CORS configuration
try {
  console.log(`Applying CORS configuration to gs://${bucketName}...\n`);
  execSync(`gsutil cors set ${corsConfigPath} gs://${bucketName}`, {
    stdio: 'inherit',
  });
  console.log('\n✅ CORS configuration applied successfully!\n');
  
  // Verify the configuration
  console.log('Verifying CORS configuration...\n');
  execSync(`gsutil cors get gs://${bucketName}`, {
    stdio: 'inherit',
  });
  
  console.log('\n✨ Done! Your bucket is now configured to allow CORS requests.');
  console.log('\nNote: It may take a few minutes for changes to propagate.');
} catch (error) {
  console.error('\n❌ Error applying CORS configuration:');
  console.error(error.message);
  console.error('\nTroubleshooting:');
  console.error('1. Make sure you are authenticated: gcloud auth login');
  console.error('2. Check your project: gcloud config get-value project');
  console.error('3. Verify bucket name is correct');
  console.error('4. Ensure you have Storage Admin permissions');
  process.exit(1);
}

