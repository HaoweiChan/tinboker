/**
 * Test script to check if GET /api/episodes/by-ticker/{ticker} returns data
 * Usage: node scripts/test-episodes-by-ticker.js [ticker]
 * Example: node scripts/test-episodes-by-ticker.js blk
 */

const BASE_URL = process.env.API_BASE_URL || 'https://staging-api.tinboker.com';
const ticker = (process.argv[2] || 'blk').toLowerCase();

async function testEpisodesByTicker() {
  const url = `${BASE_URL}/api/episodes/by-ticker/${ticker}?limit=50`;
  
  console.log(`\n🔍 Testing: GET ${url}`);
  console.log(`📊 Ticker: ${ticker} (normalized to lowercase)\n`);
  
  try {
    const response = await fetch(url, {
      method: 'GET',
      headers: {
        'Content-Type': 'application/json',
      },
    });
    
    console.log(`✅ Status: ${response.status} ${response.statusText}`);
    
    const data = await response.json();
    
    if (Array.isArray(data)) {
      console.log(`📦 Response Type: Array`);
      console.log(`📈 Episodes Count: ${data.length}`);
      
      if (data.length > 0) {
        console.log(`\n✅ SUCCESS: Found ${data.length} episode(s) for ticker "${ticker}"`);
        console.log(`\n📝 First episode preview:`);
        console.log(JSON.stringify(data[0], null, 2).substring(0, 500) + '...');
      } else {
        console.log(`\n⚠️  WARNING: API returned empty array - no episodes found for ticker "${ticker}"`);
        console.log(`\n💡 Possible reasons:`);
        console.log(`   - No episodes mention this ticker in the database`);
        console.log(`   - Ticker format mismatch (check if backend stores as "${ticker}")`);
        console.log(`   - Backend endpoint issue`);
      }
    } else if (data && typeof data === 'object') {
      console.log(`📦 Response Type: Object`);
      console.log(`📋 Response Keys: ${Object.keys(data).join(', ')}`);
      
      if (data.episodes && Array.isArray(data.episodes)) {
        console.log(`📈 Episodes Count: ${data.episodes.length}`);
        if (data.episodes.length > 0) {
          console.log(`\n✅ SUCCESS: Found ${data.episodes.length} episode(s) in response.episodes`);
        } else {
          console.log(`\n⚠️  WARNING: Empty episodes array`);
        }
      }
      
      console.log(`\n📄 Full Response Structure:`);
      console.log(JSON.stringify(data, null, 2).substring(0, 1000));
    } else {
      console.log(`📦 Response Type: ${typeof data}`);
      console.log(`\n📄 Response Data:`);
      console.log(JSON.stringify(data, null, 2));
    }
    
  } catch (error) {
    console.error(`\n❌ ERROR: Failed to fetch episodes`);
    console.error(`   Message: ${error.message}`);
    console.error(`   Stack: ${error.stack}`);
  }
}

testEpisodesByTicker();
