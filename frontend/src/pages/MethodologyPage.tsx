import { useEffect } from 'react';
import { useLocation } from 'react-router-dom';
import { SEO } from '@/components/common/SEO';
import { Section } from '@/components/common/Section';
import { Rich } from '@/components/common/Rich';
import { PageContent } from '@/components/layout/PageContent';
import { METHODOLOGY as COPY } from '../../shared/sitePages.js';

/** /methodology — where the data comes from and how each number is computed. Copy lives
 *  in shared/sitePages.js so the crawler body serves exactly what this page renders. */
export const MethodologyPage: React.FC = () => {
  const { hash } = useLocation();
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
        <p className="text-base text-muted-foreground max-w-xl mb-6 leading-[1.65]">{COPY.intro}</p>
        <div className="space-y-4 pb-4">
          {COPY.sections.map((sec) => (
            <Section key={sec.id} id={sec.id} title={sec.title}>
              {sec.items.map((item) => (
                <div key={item.title}>
                  <h3 className="text-base font-semibold text-foreground mb-1">{item.title}</h3>
                  <p><Rich body={item.body} /></p>
                </div>
              ))}
            </Section>
          ))}
        </div>
      </PageContent>
    </>
  );
};

export default MethodologyPage;
