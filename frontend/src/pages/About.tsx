import { useEffect } from 'react';
import { useLocation, Link } from 'react-router-dom';
import { Mail, Clock, MessageCircle, AtSign, ShieldAlert } from 'lucide-react';
import { SEO } from '@/components/common/SEO';
import { Section } from '@/components/common/Section';
import { PageContent } from '@/components/layout/PageContent';
import { AppLogo } from '@/components/logo/AppLogo';
import { Rich } from '@/components/common/Rich';
import { ABOUT } from '../../shared/sitePages.js';

/** One page for everything that used to be /about, /contact, /disclaimer and /report:
 *  the old paths redirect here with a hash, so deep links keep working. The /report
 *  comment board was retired — it never received a comment on any environment — so
 *  feedback is simply part of 聯絡我們.
 *  All copy lives in shared/sitePages.js so the crawler body serves the same text. */

function ContactRow({ icon, title, children }: { icon: React.ReactNode; title: string; children: React.ReactNode }) {
  return (
    <div className="flex items-start gap-3.5">
      <div className="w-10 h-10 rounded-md bg-muted text-muted-foreground grid place-items-center shrink-0">{icon}</div>
      <div className="min-w-0">
        <h3 className="text-base font-semibold text-foreground mb-0.5">{title}</h3>
        <div className="text-base text-muted-foreground">{children}</div>
      </div>
    </div>
  );
}

export const About: React.FC = () => {
  const { hash, search } = useLocation();
  const guideParams = new URLSearchParams(search);
  guideParams.set('onboarding', 'tutorial');
  // Deep links (/about#contact, redirected /disclaimer, …) land on their section.
  useEffect(() => {
    const id = hash.replace(/^#/, '');
    if (!id) return;
    const t = window.setTimeout(() => document.getElementById(id)?.scrollIntoView({ block: 'start' }), 50);
    return () => window.clearTimeout(t);
  }, [hash]);

  return (
    <>
      <SEO title={ABOUT.title} description={ABOUT.description} />
      <PageContent className="max-w-3xl">
        <div className="flex items-center gap-2 mb-2 pt-4">
          <h1 className="heading-accent text-2xl font-semibold">關於</h1>
          <AppLogo size={28} />
        </div>
        <p className="text-base text-muted-foreground max-w-xl mb-6 leading-[1.65]">
          {ABOUT.intro}
        </p>

        <div className="mb-6 flex">
          <Link to={{ pathname: '/about', search: guideParams.toString(), hash }} className="inline-flex rounded-md border border-border px-4 py-2 text-sm font-medium text-accent-info hover:bg-muted">使用導覽</Link>
        </div>

        <div className="space-y-4">
          <Section id="about" title="核心功能">
            {ABOUT.features.map((f, i) => (
              <div key={f.title} className="grid grid-cols-[24px_1fr] gap-3">
                <span className="font-mono text-sm text-muted-foreground pt-0.5 tabular-nums">{i + 1}</span>
                <div>
                  <h3 className="text-base font-semibold text-foreground mb-1">{f.title}</h3>
                  <p><Rich body={f.body} /></p>
                </div>
              </div>
            ))}
            <p className="pt-4 border-t border-border">{ABOUT.sourcesIntro}</p>
            <ul className="space-y-2">
              {ABOUT.sources.map((s) => (
                <li key={s.label} className="grid grid-cols-[14px_1fr] gap-2">
                  <span className="mt-[9px] w-1.5 h-1.5 rounded-full bg-foreground" />
                  <span><strong className="text-foreground font-semibold">{s.label}：</strong>{s.body}</span>
                </li>
              ))}
            </ul>
          </Section>

          <Section id="operator" title="經營者與方法">
            {ABOUT.operator.map((para, i) => <p key={i}><Rich body={para} /></p>)}
          </Section>

          <Section id="contact" title="聯絡我們">
            <p>{ABOUT.contactIntro}</p>
            <div className="flex items-center gap-2 text-xs bg-muted px-3.5 py-2.5 rounded-md w-fit">
              <Clock size={14} className="text-accent-info shrink-0" />
              <span>{ABOUT.hours}</span>
            </div>
            <div className="space-y-5 pt-1">
              <ContactRow icon={<Mail size={18} />} title="電子郵件">
                <a href={`mailto:${ABOUT.email}?subject=TinBoker%20%E6%84%8F%E8%A6%8B%E5%9B%9E%E9%A5%8B`} className="text-accent-info hover:underline">{ABOUT.email}</a>
              </ContactRow>
              <ContactRow icon={<MessageCircle size={18} />} title="官方 Line 帳號">
                <span>{ABOUT.line}</span>
              </ContactRow>
              <ContactRow icon={<AtSign size={18} />} title="官方 Threads 帳號">
                <a href={ABOUT.threads.href} target="_blank" rel="noopener noreferrer" className="text-accent-info hover:underline">{ABOUT.threads.text}</a>
              </ContactRow>
            </div>
          </Section>

          <Section id="disclaimer" title="免責聲明">
            <p className="flex items-start gap-2 text-foreground font-medium">
              <ShieldAlert size={18} className="shrink-0 mt-1 text-muted-foreground" />
              {ABOUT.disclaimerLead}
            </p>
            {ABOUT.disclaimer.map((s) => (
              <div key={s.title}>
                <h3 className="text-base font-semibold text-foreground mb-1">{s.title}</h3>
                <p><Rich body={s.body} /></p>
              </div>
            ))}
            <p className="pt-4 border-t border-border">
              <Rich body={ABOUT.policyLink} />
            </p>
          </Section>

        </div>

        <div className="text-center text-2xs text-muted-foreground/50 tabular-nums mt-8 pb-4">
          {__APP_VERSION__}
        </div>
      </PageContent>
    </>
  );
};
