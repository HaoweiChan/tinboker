import { useEffect } from 'react';
import { useLocation } from 'react-router-dom';
import { SEO } from '@/components/common/SEO';
import { Section } from '@/components/common/Section';
import { PageContent } from '@/components/layout/PageContent';
import { Rich } from '@/components/common/Rich';
import { TERMS as COPY } from '../../shared/sitePages.js';

/** /terms — 服務條款、會員訂閱與付款、退款政策、隱私權政策, all on one page (anchors
 *  #subscription / #refund / #privacy). /privacy and /refund redirect here with a hash
 *  (App.tsx), the same pattern About.tsx uses for its own retired standalone pages.
 *  Copy lives in shared/sitePages.js (verbatim from the approved terms-copy.md — do not
 *  reword it), so the crawler body serves exactly what this page renders. */

export const TermsPage: React.FC = () => {
  const { hash } = useLocation();
  // Deep links (/terms#refund, redirected /privacy and /refund, …) land on their section.
  useEffect(() => {
    const id = hash.replace(/^#/, '');
    if (!id) return;
    const t = window.setTimeout(() => document.getElementById(id)?.scrollIntoView({ block: 'start' }), 50);
    return () => window.clearTimeout(t);
  }, [hash]);

  return (
    <>
      <SEO title={COPY.title} description={COPY.description} />
      <PageContent className="max-w-3xl">
        <div className="pt-4 mb-2">
          <h1 className="heading-accent text-2xl font-semibold tracking-[-0.02em]">{COPY.title}</h1>
        </div>
        <p className="text-sm text-muted-foreground/70 mb-2">{COPY.updated}</p>
        <p className="text-base text-muted-foreground max-w-xl mb-6 leading-[1.65]">
          {COPY.intro}
        </p>

        <div className="space-y-4">
          <Section id="terms" title="服務條款">
            {COPY.terms.map((s) => (
              <div key={s.title}>
                <h3 className="text-base font-semibold text-foreground mb-1">{s.title}</h3>
                <p><Rich body={s.body} /></p>
              </div>
            ))}
          </Section>

          <Section id="subscription" title="會員訂閱與付款">
            {COPY.subscription.map((s) => (
              <div key={s.title}>
                <h3 className="text-base font-semibold text-foreground mb-1">{s.title}</h3>
                <p><Rich body={s.body} /></p>
              </div>
            ))}
          </Section>

          <Section id="refund" title="退款政策">
            {COPY.refund.map((s) => (
              <div key={s.title}>
                <h3 className="text-base font-semibold text-foreground mb-1">{s.title}</h3>
                <p><Rich body={s.body} /></p>
              </div>
            ))}
          </Section>

          <Section id="privacy" title="隱私權政策">
            <div>
              <h3 className="text-base font-semibold text-foreground mb-1">{COPY.dataCollectedTitle}</h3>
              <ul className="space-y-2">
                {COPY.dataCollected.map((d) => (
                  <li key={d.label} className="grid grid-cols-[14px_1fr] gap-2">
                    <span className="mt-[9px] w-1.5 h-1.5 rounded-full bg-foreground" />
                    <span><strong className="text-foreground font-semibold">{d.label}：</strong>{d.body}</span>
                  </li>
                ))}
              </ul>
            </div>
            {COPY.privacy.map((s) => (
              <div key={s.title}>
                <h3 className="text-base font-semibold text-foreground mb-1">{s.title}</h3>
                <p><Rich body={s.body} /></p>
              </div>
            ))}
          </Section>
        </div>

        <p className="text-center text-sm text-muted-foreground mt-6 pb-4">
          <Rich body={COPY.outro} />
        </p>
      </PageContent>
    </>
  );
};

export default TermsPage;
