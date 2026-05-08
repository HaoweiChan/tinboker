import puppeteer from 'puppeteer';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const lightThemeHTML = `
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>TinBoker Logo - Light</title>
  <link href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&display=swap" rel="stylesheet">
  <style>
    body {
      margin: 0;
      padding: 200px;
      background: #FFFFFF;
      display: flex;
      justify-content: center;
      align-items: center;
      font-family: 'DM Sans', sans-serif;
    }
    .logo {
      font-size: 200px;
      font-weight: 700;
      line-height: 1;
      display: inline-flex;
      align-items: center;
    }
    .trend {
      background: linear-gradient(135deg, #EC7A3C 0%, #E04F3F 100%);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
      background-clip: text;
    }
    .brief {
      color: #000000;
    }
  </style>
</head>
<body>
  <div class="logo">
    <span class="trend">Trend</span>
    <span class="brief">Brief</span>
  </div>
</body>
</html>
`;

const darkThemeHTML = `
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>TrendBrief Logo - Dark</title>
  <link href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&display=swap" rel="stylesheet">
  <style>
    body {
      margin: 0;
      padding: 200px;
      background: #1A1A1A;
      display: flex;
      justify-content: center;
      align-items: center;
      font-family: 'DM Sans', sans-serif;
    }
    .logo {
      font-size: 200px;
      font-weight: 700;
      line-height: 1;
      display: inline-flex;
      align-items: center;
    }
    .trend {
      background: linear-gradient(135deg, #EC7A3C 0%, #E04F3F 100%);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
      background-clip: text;
    }
    .brief {
      color: #FFFFFF;
    }
  </style>
</head>
<body>
  <div class="logo">
    <span class="trend">Trend</span>
    <span class="brief">Brief</span>
  </div>
</body>
</html>
`;

async function generateLogoPNG(html, outputPath, width = 2400, height = 800) {
  const browser = await puppeteer.launch({
    headless: true,
    args: ['--no-sandbox', '--disable-setuid-sandbox']
  });
  
  try {
    const page = await browser.newPage();
    await page.setViewport({ width, height });
    await page.setContent(html, { waitUntil: 'networkidle0' });
    
    // Wait for fonts to load
    await page.evaluateHandle(() => document.fonts.ready);
    await new Promise(resolve => setTimeout(resolve, 1000));
    
    const logoElement = await page.$('.logo');
    if (!logoElement) {
      throw new Error('Logo element not found');
    }
    
    const boundingBox = await logoElement.boundingBox();
    if (!boundingBox) {
      throw new Error('Could not get bounding box');
    }
    
    // Add padding around the logo
    const padding = 100;
    await page.screenshot({
      path: outputPath,
      clip: {
        x: Math.max(0, boundingBox.x - padding),
        y: Math.max(0, boundingBox.y - padding),
        width: boundingBox.width + (padding * 2),
        height: boundingBox.height + (padding * 2)
      },
      type: 'png'
    });
    
    console.log(`✓ Generated ${outputPath}`);
  } finally {
    await browser.close();
  }
}

async function main() {
  const publicDir = path.join(__dirname, '..', 'public');
  if (!fs.existsSync(publicDir)) {
    fs.mkdirSync(publicDir, { recursive: true });
  }
  
  console.log('Generating logo PNGs...');
  
  await generateLogoPNG(lightThemeHTML, path.join(publicDir, 'trendbrief-logo-light.png'));
  await generateLogoPNG(darkThemeHTML, path.join(publicDir, 'trendbrief-logo-dark.png'));
  
  console.log('Done! Logos saved to public/');
}

main().catch(console.error);

