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

  // Handle preset aspect ratios
  if (size === '16:9') return { width: 1280, height: 720 };
  if (size === '4:3') return { width: 960, height: 720 };
  if (size === '1:1') return { width: 1080, height: 1080 };

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

/**
 * Render Marp markdown to HTML (lazy-loads @marp-team/marp-core to
 * avoid Node.js module externalization warnings on every page load)
 */
export async function renderMarpToHTML(markdown: string): Promise<{ html: string; css: string }> {
  const { Marp } = await import('@marp-team/marp-core');
  const marp = new Marp();
  const { html, css } = marp.render(markdown);
  return { html, css };
}

/**
 * Split Marp content into individual slides
 */
export function splitMarpSlides(content: string): string[] {
  // Remove frontmatter first
  let contentWithoutFrontmatter = content.replace(/^---\n[\s\S]*?\n---\n/, '');

  // Split by slide separator
  const slides = contentWithoutFrontmatter.split(/\n---\n/);

  // Filter out empty slides
  return slides.filter((slide) => slide.trim().length > 0);
}
