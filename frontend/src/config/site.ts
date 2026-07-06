/**
 * Site-level configuration (config-driven, not hardcoded into pages).
 *
 * Newsletter / subscription CTA config lives here so the article surfaces
 * (/articles hero, /article/:slug mid + end) render from a single source of
 * truth. The external destination is currently a Substack URL; swap it via the
 * `VITE_NEWSLETTER_URL` env var without touching component code.
 *
 * Degrade-safe contract: when `newsletter.url` is empty, `isNewsletterEnabled`
 * is false and every CTA placement renders nothing.
 */

export type NewsletterPlacement = 'hero' | 'mid' | 'end';

export interface NewsletterCopy {
  /** Short eyebrow / kicker label. */
  eyebrow: string;
  /** Headline. */
  title: string;
  /** Supporting sentence. */
  description: string;
  /** Button label. */
  cta: string;
}

export interface NewsletterConfig {
  /** External subscription destination (Substack). Empty string = disabled. */
  url: string;
  /** Copy variants per placement (zh-TW). */
  copy: Record<NewsletterPlacement, NewsletterCopy>;
}

const rawUrl = (import.meta.env.VITE_NEWSLETTER_URL as string | undefined)?.trim() ?? '';

export const newsletter: NewsletterConfig = {
  url: rawUrl,
  copy: {
    hero: {
      eyebrow: '訂閱電子報',
      title: '每週投資情報，直送你的信箱',
      description:
        '從 podcast、法說會與經營層訪談中萃取的深度分析與市場觀察，一週一封，讀完就能上手。',
      cta: '免費訂閱',
    },
    mid: {
      eyebrow: '喜歡這篇分析嗎？',
      title: '訂閱電子報，不錯過下一篇',
      description: '把這樣的深度內容固定送到你的信箱，隨時掌握第一手市場觀點。',
      cta: '訂閱電子報',
    },
    end: {
      eyebrow: '讀到這裡了',
      title: '想要更多這樣的內容？',
      description: '訂閱 TinBoker 電子報，每週收到精選的投資情報與市場分析。',
      cta: '免費訂閱電子報',
    },
  },
};

/** Whether the newsletter CTA system has a valid destination configured. */
export const isNewsletterEnabled = (): boolean => newsletter.url.length > 0;
