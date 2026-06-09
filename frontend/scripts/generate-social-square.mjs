// Generate square social-profile / og images from the TinBoker 「」 bracket mark.
// The mark occupies ~57% of the canvas (viewBox 9..33 of 42) which keeps every
// element inside the inscribed circle that Threads/IG/X apply when cropping
// avatars to a circle. Outputs land in public/brand/.
import sharp from 'sharp';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const outDir = path.join(__dirname, '..', 'public', 'brand');
fs.mkdirSync(outDir, { recursive: true });

const mark = (lFill, dotFill) => `
  <path d="M9 9 H21 V13 H13 V21 H9 Z" fill="${lFill}"/>
  <path d="M33 33 H21 V29 H29 V21 H33 Z" fill="#ffd23f"/>
  <circle cx="18" cy="24" r="1.5" fill="${dotFill}"/>
  <circle cx="22" cy="20" r="1.5" fill="${dotFill}" opacity="0.7"/>
  <circle cx="26" cy="16" r="1.5" fill="#ffd23f" opacity="0.85"/>`;

const svg = (bg, lFill, dotFill) =>
  `<svg width="1080" height="1080" viewBox="0 0 42 42" xmlns="http://www.w3.org/2000/svg">` +
  `<rect width="42" height="42" fill="${bg}"/>${mark(lFill, dotFill)}</svg>`;

const variants = [
  { name: 'tinboker-square-light', svg: svg('#ffffff', '#0e1014', '#0e1014') },
  { name: 'tinboker-square-dark', svg: svg('#0e1014', '#f1ead8', '#f1ead8') },
];

for (const v of variants) {
  const buf = Buffer.from(v.svg);
  for (const size of [1080, 512]) {
    const out = path.join(outDir, `${v.name}-${size}.png`);
    await sharp(buf, { density: 384 }).resize(size, size).png().toFile(out);
    console.log(`✓ ${out}`);
  }
}
console.log('Done.');
