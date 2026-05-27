import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

// Mock data imports - in a real app, this would fetch from your API/CMS
// We need to use relative paths from the script execution location or absolute imports if configured
const MOCK_DATA = {
  episodes: [
    { id: 'EP156', title: 'EP156: AI 供應鏈大解密' },
    { id: 'EP155', title: 'EP155: 機器人產業革命' }
  ],
  stocks: ['2330', '2317', '2454', 'NVDA', 'AAPL']
};

const BASE_URL = 'https://tinboker.com';

const STATIC_ROUTES = [
  '/',
  '/podcaster',
  '/stock',
  '/topics',
  '/watchlist',
  '/story',
  '/industry',
  '/about',
  '/contact',
  '/disclaimer',
];

function generateSitemap() {
  const currentDate = new Date().toISOString().split('T')[0];

  let sitemap = `<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
`;

  // Add static routes
  STATIC_ROUTES.forEach(route => {
    sitemap += `  <url>
    <loc>${BASE_URL}${route}</loc>
    <lastmod>${currentDate}</lastmod>
    <changefreq>weekly</changefreq>
    <priority>${route === '/' ? '1.0' : '0.8'}</priority>
  </url>
`;
  });

  // Add Dynamic Routes (Mock)
  
  // Episodes (the legacy /news/:id route redirects to /episode/:id)
  MOCK_DATA.episodes.forEach(ep => {
    sitemap += `  <url>
    <loc>${BASE_URL}/episode/${ep.id}</loc>
    <lastmod>${currentDate}</lastmod>
    <changefreq>monthly</changefreq>
    <priority>0.7</priority>
  </url>
`;
  });

  // Stocks
  MOCK_DATA.stocks.forEach(ticker => {
    sitemap += `  <url>
    <loc>${BASE_URL}/stock/${ticker}</loc>
    <lastmod>${currentDate}</lastmod>
    <changefreq>daily</changefreq>
    <priority>0.6</priority>
  </url>
`;
  });

  sitemap += `</urlset>`;

  const publicDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../public');
  
  // Ensure public directory exists
  if (!fs.existsSync(publicDir)){
      fs.mkdirSync(publicDir);
  }

  fs.writeFileSync(path.join(publicDir, 'sitemap.xml'), sitemap);
  console.log('✅ Sitemap generated at public/sitemap.xml');
}

generateSitemap();

