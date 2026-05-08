/**
 * Test script to check if GET /api/episodes/by-tag/{tag} has case sensitivity issues
 * Usage: node scripts/test-episodes-by-tag.js [tag]
 * Example: node scripts/test-episodes-by-tag.js NonfarmPayrolls
 */

const BASE_URL = process.env.API_BASE_URL || 'https://staging-api.tinboker.com';
const tag = process.argv[2] || 'NonfarmPayrolls';

async function testEpisodesByTag(testTag, description) {
  const encodedTag = encodeURIComponent(testTag);
  const url = `${BASE_URL}/api/episodes/by-tag/${encodedTag}?limit=50`;
  
  console.log(`\n🔍 Testing: GET ${url}`);
  console.log(`📊 Tag: ${testTag} ${description}\n`);
  
  try {
    const response = await fetch(url, {
      method: 'GET',
      headers: {
        'Content-Type': 'application/json',
      },
    });
    
    console.log(`✅ Status: ${response.status} ${response.statusText}`);
    
    if (!response.ok) {
      const errorText = await response.text();
      console.log(`❌ Error Response: ${errorText}`);
      return { success: false, count: 0 };
    }
    
    const data = await response.json();
    
    if (data && typeof data === 'object') {
      console.log(`📦 Response Type: Object`);
      console.log(`📋 Response Keys: ${Object.keys(data).join(', ')}`);
      
      if (data.episodes && Array.isArray(data.episodes)) {
        console.log(`📈 Episodes Count: ${data.episodes.length}`);
        console.log(`📊 Total: ${data.total || 'N/A'}`);
        
        if (data.episodes.length > 0) {
          console.log(`\n✅ SUCCESS: Found ${data.episodes.length} episode(s) for tag "${testTag}"`);
          return { success: true, count: data.episodes.length };
        } else {
          console.log(`\n⚠️  WARNING: Empty episodes array`);
          return { success: true, count: 0 };
        }
      }
      
      console.log(`\n📄 Response Structure:`);
      console.log(JSON.stringify(data, null, 2).substring(0, 500));
      return { success: true, count: 0 };
    } else if (Array.isArray(data)) {
      console.log(`📦 Response Type: Array`);
      console.log(`📈 Episodes Count: ${data.length}`);
      return { success: true, count: data.length };
    } else {
      console.log(`📦 Response Type: ${typeof data}`);
      console.log(`\n📄 Response Data:`);
      console.log(JSON.stringify(data, null, 2).substring(0, 500));
      return { success: true, count: 0 };
    }
    
  } catch (error) {
    console.error(`\n❌ ERROR: Failed to fetch episodes`);
    console.error(`   Message: ${error.message}`);
    return { success: false, count: 0 };
  }
}

async function main() {
  console.log('='.repeat(60));
  console.log('Testing GET /api/episodes/by-tag/{tag} Case Sensitivity');
  console.log('='.repeat(60));
  
  // Test original case
  const originalResult = await testEpisodesByTag(tag, '(original case)');
  
  // Test lowercase
  const lowerResult = await testEpisodesByTag(tag.toLowerCase(), '(lowercase)');
  
  // Test uppercase
  const upperResult = await testEpisodesByTag(tag.toUpperCase(), '(uppercase)');
  
  console.log('\n' + '='.repeat(60));
  console.log('SUMMARY');
  console.log('='.repeat(60));
  console.log(`Original case (${tag}):     ${originalResult.success ? '✅' : '❌'} ${originalResult.count} episodes`);
  console.log(`Lowercase (${tag.toLowerCase()}):     ${lowerResult.success ? '✅' : '❌'} ${lowerResult.count} episodes`);
  console.log(`Uppercase (${tag.toUpperCase()}):     ${upperResult.success ? '✅' : '❌'} ${upperResult.count} episodes`);
  
  if (originalResult.count !== lowerResult.count || originalResult.count !== upperResult.count) {
    console.log('\n⚠️  CASE SENSITIVITY DETECTED!');
    if (lowerResult.count > originalResult.count) {
      console.log('   → Backend expects LOWERCASE tags');
    } else if (upperResult.count > originalResult.count) {
      console.log('   → Backend expects UPPERCASE tags');
    }
  } else if (originalResult.count === 0 && lowerResult.count === 0 && upperResult.count === 0) {
    console.log('\n⚠️  No episodes found with any case - tag may not exist in database');
  } else {
    console.log('\n✅ No case sensitivity detected - all cases return same results');
  }
}

main();
