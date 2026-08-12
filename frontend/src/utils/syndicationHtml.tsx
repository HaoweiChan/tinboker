/** Render a summary to clipboard-ready HTML for 方格子 / Substack.
 *
 *  Both are WYSIWYG editors: pasting raw markdown leaves literal `##` and `**` on the
 *  page, while pasting HTML keeps headings, bold, lists and links. So we hand the
 *  clipboard both flavours and let the editor pick — `text/html` for the rich editors,
 *  `text/plain` (markdown) as the fallback for anything that only takes text.
 *
 *  No custom components here on purpose: the on-site renderers hang Tailwind classes
 *  off every node, which is dead weight in someone else's editor. Bare semantic HTML
 *  is what these editors want to ingest. */
import { renderToStaticMarkup } from 'react-dom/server';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { toSyndicationMarkdown, type SyndicationOptions } from './syndicationMarkdown';

export function toSyndicationHtml(
  content: string,
  episodeId: string,
  options: SyndicationOptions = {},
): string {
  const markdown = toSyndicationMarkdown(content, episodeId, options);
  if (!markdown) return '';
  return renderToStaticMarkup(
    <ReactMarkdown remarkPlugins={[remarkGfm]}>{markdown}</ReactMarkdown>,
  );
}

/** Put the syndication copy on the clipboard. Resolves to the flavour actually
 *  written so the caller can tell the user what they got. */
export async function copySyndicationToClipboard(
  content: string,
  episodeId: string,
  options: SyndicationOptions = {},
): Promise<'html' | 'markdown'> {
  const markdown = toSyndicationMarkdown(content, episodeId, options);
  if (!markdown) throw new Error('empty summary');

  // ClipboardItem is unavailable on http:// and in older Safari. Falling back to
  // markdown-as-text still pastes something usable, just unformatted.
  if (typeof ClipboardItem === 'function' && navigator.clipboard?.write) {
    const html = toSyndicationHtml(content, episodeId, options);
    await navigator.clipboard.write([
      new ClipboardItem({
        'text/html': new Blob([html], { type: 'text/html' }),
        'text/plain': new Blob([markdown], { type: 'text/plain' }),
      }),
    ]);
    return 'html';
  }

  await navigator.clipboard.writeText(markdown);
  return 'markdown';
}
