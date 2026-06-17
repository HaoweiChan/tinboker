export interface MarpMetadata {
  size?: string;
  theme?: string;
  paginate?: boolean;
  header?: string;
  footer?: string;
  [key: string]: any;
}

/**
 * Parse Marp frontmatter from content string
 */
export function parseMarpFrontmatter(content: string): MarpMetadata {
  const frontmatterMatch = content.match(/^---\n([\s\S]*?)\n---\n/);
  if (!frontmatterMatch) {
    return {};
  }

  const frontmatterText = frontmatterMatch[1];
  const metadata: MarpMetadata = {};

  // Parse YAML-like frontmatter (simple parser)
  frontmatterText.split('\n').forEach((line) => {
    const match = line.match(/^(\w+):\s*(.+)$/);
    if (match) {
      const key = match[1].trim();
      let value: any = match[2].trim();

      // Parse boolean values
      if (value === 'true') value = true;
      else if (value === 'false') value = false;
      // Parse numbers
      else if (/^\d+$/.test(value)) value = parseInt(value, 10);
      // Remove quotes from strings
      else if ((value.startsWith('"') && value.endsWith('"')) || 
               (value.startsWith("'") && value.endsWith("'"))) {
        value = value.slice(1, -1);
      }

      metadata[key] = value;
    }
  });

  return metadata;
}

/**
 * Extract size dimensions from Marp size directive
 * Supports formats like: "1080x1080", "16:9", "4:3", "1280x720"
 */
export function parseMarpSize(size?: string): { width: number; height: number } {
  if (!size) {
    // Default to 16:9 (1280x720)
    return { width: 1280, height: 720 };
  }

  // Handle preset aspect ratios + the tinboker-cards named sizes
  if (size === '16:9') return { width: 1280, height: 720 };
  if (size === '4:3') return { width: 960, height: 720 };
  if (size === '1:1') return { width: 1080, height: 1080 };
  if (size === 'wide') return { width: 1240, height: 780 };

  // Handle explicit dimensions (e.g., "1080x1080", "1280x720")
  const dimensionMatch = size.match(/^(\d+)x(\d+)$/);
  if (dimensionMatch) {
    return {
      width: parseInt(dimensionMatch[1], 10),
      height: parseInt(dimensionMatch[2], 10),
    };
  }

  // Fallback to default
  return { width: 1280, height: 720 };
}

// The TinBoker card decks (convert_marp output) use `theme: tinboker-cards` with
// `size: 1:1` (podcast, 1080²) or `size: wide` (ticker, 1240×780). marp-core only
// honours a `size:` directive whose dimensions a registered theme DECLARES via
// `@size`, and its built-in themes only declare 16:9/4:3 — so without this the
// deck renders inside a 16:9 SVG viewBox and letterboxes (white band) in the
// square container. This theme only declares the sizes; the visual styling stays
// in each deck's inline <style> block (hoisted per slide by SlideViewer).
const TINBOKER_CARDS_THEME = `
/* @theme tinboker-cards */
/* @size 1:1 1080px 1080px */
/* @size wide 1240px 780px */
section { box-sizing: border-box; }
`;

/**
 * Render Marp markdown to HTML (lazy-loads @marp-team/marp-core to
 * avoid Node.js module externalization warnings on every page load)
 */
export async function renderMarpToHTML(markdown: string): Promise<{ html: string; css: string }> {
  const { Marp } = await import('@marp-team/marp-core');
  const marp = new Marp();
  // Register the card-deck theme so its `size: 1:1` / `size: wide` are honoured.
  try {
    marp.themeSet.add(TINBOKER_CARDS_THEME);
  } catch {
    // Already registered (or duplicate) — safe to ignore.
  }
  const { html, css } = marp.render(markdown);
  return { html, css };
}

const STYLE_BLOCK_RE = /<style[\s\S]*?<\/style>/gi;

/**
 * Extract all global `<style>` blocks from Marp content, joined together.
 *
 * Marp treats a `<style>` block as deck-wide CSS, but it must be present in the
 * markdown that marp-core actually renders. Because SlideViewer renders each
 * slide in isolation, the style block (which lives in just one slide chunk after
 * splitting) has to be re-injected into every slide — otherwise only the slide
 * carrying it gets the theme and the rest fall back to the bare base theme.
 */
export function extractMarpStyles(content: string): string {
  const matches = content.match(STYLE_BLOCK_RE);
  return matches ? matches.join('\n') : '';
}

/**
 * Split Marp content into individual slides
 */
export function splitMarpSlides(content: string): string[] {
  // Remove frontmatter first
  let contentWithoutFrontmatter = content.replace(/^---\n[\s\S]*?\n---\n/, '');

  // Drop global <style> blocks so a style-only chunk doesn't become a blank
  // slide (they're re-injected per slide at render time).
  contentWithoutFrontmatter = contentWithoutFrontmatter.replace(STYLE_BLOCK_RE, '');

  // Split by slide separator
  const slides = contentWithoutFrontmatter.split(/\n---\n/);

  // Filter out empty slides (incl. doubled `---` separators)
  return slides.filter((slide) => slide.trim().length > 0);
}
