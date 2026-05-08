const fs = require('fs');
const path = require('path');

// Create a simple HTML file that renders the logo in both themes
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
      padding: 100px;
      background: #FFFFFF;
      display: flex;
      justify-content: center;
      align-items: center;
      font-family: 'DM Sans', sans-serif;
    }
    .logo {
      font-size: 120px;
      font-weight: 700;
      line-height: 1;
      display: inline-flex;
      align-items: center;
    }
    .graph {
      background: linear-gradient(135deg, #EC7A3C 0%, #E04F3F 100%);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
      background-clip: text;
    }
    .folio {
      color: #000000;
    }
  </style>
</head>
<body>
  <div class="logo">
    <span class="graph">Graph</span>
    <span class="folio">folio</span>
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
  <title>TinBoker Logo - Dark</title>
  <link href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&display=swap" rel="stylesheet">
  <style>
    body {
      margin: 0;
      padding: 100px;
      background: #1A1A1A;
      display: flex;
      justify-content: center;
      align-items: center;
      font-family: 'DM Sans', sans-serif;
    }
    .logo {
      font-size: 120px;
      font-weight: 700;
      line-height: 1;
      display: inline-flex;
      align-items: center;
    }
    .graph {
      background: linear-gradient(135deg, #EC7A3C 0%, #E04F3F 100%);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
      background-clip: text;
    }
    .folio {
      color: #FFFFFF;
    }
  </style>
</head>
<body>
  <div class="logo">
    <span class="graph">Graph</span>
    <span class="folio">folio</span>
  </div>
</body>
</html>
`;

// Create public directory if it doesn't exist
const publicDir = path.join(__dirname, '..', 'public');
if (!fs.existsSync(publicDir)) {
  fs.mkdirSync(publicDir, { recursive: true });
}

// Write HTML files
fs.writeFileSync(path.join(publicDir, 'logo-light.html'), lightThemeHTML);
fs.writeFileSync(path.join(publicDir, 'logo-dark.html'), darkThemeHTML);

console.log('Logo HTML files created in public/');
console.log('Open logo-light.html and logo-dark.html in a browser to generate PNGs');
console.log('Or use a tool like Puppeteer to automate PNG generation');

