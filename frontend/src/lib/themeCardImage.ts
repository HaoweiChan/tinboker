/**
 * Draws a theme card as a 1080×1080 PNG in the browser, from the numbers already on
 * screen. Same palette and square format as the server-rendered stock card
 * (backend/src/services/card_theme.py) so the two read as one family; drawn client-side
 * because theme cards are members-only and the member already holds every value.
 */
import type { PickWindowReturns } from '@/services/types';
import type { ThemeCardData } from '@/services/api/themeViews';
import { formatDate } from '@/lib/date';

const SIZE = 1080;
const MARGIN = 56;
const BG = '#07090e';
const INK = '#e0e6eb';
const AMBER = '#fbac23';
const BORDER = '#1c2531';
const LABEL = '#c8d2dd';
const FAINT = '#8b97a6';
const RED = '#ef4444';
const GREEN = '#22c55e';
const FONT = "'JetBrains Mono', 'Noto Sans TC', system-ui, sans-serif";
const METRICS = [['since', '自提及'], ['d7', '7天'], ['d30', '30天'], ['d90', '90天']] as const;
const STANCE = { bullish: '看多', bearish: '看空', mixed: '多空並陳' } as const;
const MAX_ROWS = 6;

export interface ThemeCardImageInput {
  card: ThemeCardData;
  /** Channel cover. Needs CORS to be drawn; otherwise the card shows the show's initial. */
  podcastImage?: string;
  rows: { ticker: string; name: string; windows?: PickWindowReturns }[];
  averages: { key: string; label: string; value: number | null }[];
  /** 'TW' paints gains red; anything else paints them green. */
  colorMode: string;
}

/** Break text to `width`, character by character (CJK has no spaces to break on). */
function wrap(ctx: CanvasRenderingContext2D, text: string, width: number, maxLines: number): string[] {
  const lines: string[] = [];
  let line = '';
  for (const ch of text) {
    if (ctx.measureText(line + ch).width > width && line) {
      lines.push(line);
      line = ch;
    } else line += ch;
  }
  if (line) lines.push(line);
  if (lines.length <= maxLines) return lines;
  const kept = lines.slice(0, maxLines);
  kept[maxLines - 1] = `${kept[maxLines - 1].slice(0, -1)}…`;
  return kept;
}

function fit(ctx: CanvasRenderingContext2D, text: string, width: number): string {
  if (ctx.measureText(text).width <= width) return text;
  let out = text;
  while (out.length > 1 && ctx.measureText(`${out}…`).width > width) out = out.slice(0, -1);
  return `${out}…`;
}

/** The cover as a canvas-safe image, or null. `crossOrigin` makes a host without CORS
 *  fail to load instead of tainting the canvas, which would break the PNG export. */
function loadCover(url?: string): Promise<HTMLImageElement | null> {
  if (!url) return Promise.resolve(null);
  return new Promise((resolve) => {
    const img = new Image();
    const timer = setTimeout(() => resolve(null), 4000);
    img.crossOrigin = 'anonymous';
    img.onload = () => { clearTimeout(timer); resolve(img); };
    img.onerror = () => { clearTimeout(timer); resolve(null); };
    img.src = url;
  });
}

export async function renderThemeCardPng({ card, podcastImage, rows, averages, colorMode }: ThemeCardImageInput): Promise<Blob> {
  const [cover] = await Promise.all([loadCover(podcastImage), document.fonts.ready]);
  const canvas = document.createElement('canvas');
  canvas.width = SIZE;
  canvas.height = SIZE;
  const ctx = canvas.getContext('2d');
  if (!ctx) throw new Error('canvas unavailable');
  const [up, down] = colorMode === 'TW' ? [RED, GREEN] : [GREEN, RED];
  const pct = (v: number | null | undefined) =>
    v == null || !Number.isFinite(v) ? '—' : `${v >= 0 ? '+' : ''}${v.toFixed(2)}%`;
  const tone = (v: number | null | undefined) => (v == null || !Number.isFinite(v) ? FAINT : v >= 0 ? up : down);
  const text = (s: string, x: number, y: number, font: string, fill: string, align: CanvasTextAlign = 'left') => {
    ctx.font = font;
    ctx.fillStyle = fill;
    ctx.textAlign = align;
    ctx.fillText(s, x, y);
  };
  const right = SIZE - MARGIN;
  const inner = SIZE - 2 * MARGIN;
  const latest = card.mentions[card.mentions.length - 1];

  ctx.fillStyle = BG;
  ctx.fillRect(0, 0, SIZE, SIZE);
  ctx.textBaseline = 'alphabetic';

  // Channel: cover (or the show's initial on a tile) and its name, then the brand.
  const ICON = 84;
  const iconY = 44;
  ctx.save();
  ctx.beginPath();
  ctx.roundRect(MARGIN, iconY, ICON, ICON, 12);
  ctx.clip();
  if (cover) {
    // Centre-crop to a square.
    const side = Math.min(cover.naturalWidth, cover.naturalHeight);
    ctx.drawImage(cover, (cover.naturalWidth - side) / 2, (cover.naturalHeight - side) / 2, side, side, MARGIN, iconY, ICON, ICON);
  } else {
    ctx.fillStyle = BORDER;
    ctx.fillRect(MARGIN, iconY, ICON, ICON);
    text(card.podcaster.trim().charAt(0), MARGIN + ICON / 2, iconY + ICON / 2 + 16, `700 44px ${FONT}`, INK, 'center');
  }
  ctx.restore();
  ctx.font = `700 26px ${FONT}`;
  const brandWidth = ctx.measureText('TinBoker 聽播客').width;
  ctx.font = `600 42px ${FONT}`;
  text(fit(ctx, card.podcaster, inner - ICON - 24 - brandWidth - 32), MARGIN + ICON + 24, iconY + ICON / 2 + 15, `600 42px ${FONT}`, INK);
  text('TinBoker 聽播客', right, iconY + ICON / 2 + 10, `700 26px ${FONT}`, AMBER, 'right');

  ctx.font = `700 68px ${FONT}`;
  text(fit(ctx, card.theme_label, inner), MARGIN, 226, `700 68px ${FONT}`, INK);
  const stance = STANCE[latest.stance];
  const stanceColor = latest.stance === 'mixed' ? LABEL : latest.stance === 'bullish' ? up : down;
  text(stance, MARGIN, 282, `700 30px ${FONT}`, stanceColor);
  ctx.font = `700 30px ${FONT}`;
  const stanceWidth = ctx.measureText(stance).width;
  text(`${formatDate(card.first_ms)} 起${card.mentions.length > 1 ? ` · 連續提及 ${card.mentions.length} 集` : ''}`,
    MARGIN + stanceWidth + 24, 282, `400 28px ${FONT}`, LABEL);

  ctx.font = `400 34px ${FONT}`;
  let y = 350;
  for (const line of wrap(ctx, card.mentions[0].thesis, inner, 3)) {
    text(line, MARGIN, y, `400 34px ${FONT}`, INK);
    y += 50;
  }

  if (rows.length === 0) {
    text('節目沒有點名個股，這個題材沒有可計算的走勢。', MARGIN, y + 60, `400 30px ${FONT}`, LABEL);
  } else {
    y += 26;
    ctx.strokeStyle = BORDER;
    ctx.lineWidth = 2;
    ctx.beginPath(); ctx.moveTo(MARGIN, y); ctx.lineTo(right, y); ctx.stroke();
    y += 50;
    text(card.tickers_source === 'members' ? '題材成分股（節目未點名）' : '節目點名個股', MARGIN, y, `400 26px ${FONT}`, LABEL);
    if (rows.length > 1) text(`${rows.length} 檔平均`, right, y, `400 26px ${FONT}`, LABEL, 'right');

    const cell = inner / 4;
    y += 56;
    averages.forEach((m, i) => {
      const cx = MARGIN + cell * i + cell / 2;
      text(m.label, cx, y, `400 26px ${FONT}`, LABEL, 'center');
      text(pct(m.value), cx, y + 62, `700 50px ${FONT}`, tone(m.value), 'center');
    });
    y += 110;
    ctx.beginPath(); ctx.moveTo(MARGIN, y); ctx.lineTo(right, y); ctx.stroke();

    // Per-stock table: name column, then the four windows right-aligned.
    const cols = [right - 3 * 170, right - 2 * 170, right - 170, right];
    y += 46;
    METRICS.forEach(([, label], i) => text(label, cols[i], y, `400 24px ${FONT}`, FAINT, 'right'));
    const shown = rows.slice(0, MAX_ROWS);
    const rowHeight = Math.min(64, (SIZE - MARGIN - 40 - y) / (shown.length + (rows.length > MAX_ROWS ? 1 : 0)));
    for (const r of shown) {
      y += rowHeight;
      ctx.font = `400 30px ${FONT}`;
      text(fit(ctx, `${r.name} ${r.ticker}`, cols[0] - 170 - MARGIN), MARGIN, y, `400 30px ${FONT}`, INK);
      METRICS.forEach(([key], i) => text(pct(r.windows?.[key]), cols[i], y, `400 28px ${FONT}`, tone(r.windows?.[key]), 'right'));
    }
    if (rows.length > MAX_ROWS) text(`… 另 ${rows.length - MAX_ROWS} 檔`, MARGIN, y + rowHeight, `400 26px ${FONT}`, FAINT);
  }

  text('從第一次提及當日收盤起算 · tinboker.com · 非投資建議', MARGIN, SIZE - MARGIN + 4, `400 22px ${FONT}`, FAINT);

  return new Promise((resolve, reject) =>
    canvas.toBlob((blob) => (blob ? resolve(blob) : reject(new Error('canvas export failed'))), 'image/png'));
}
