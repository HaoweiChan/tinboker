import { useEffect } from 'react';
import { useLocation } from 'react-router-dom';
import { Mail, Clock, MessageCircle, AtSign, ShieldAlert } from 'lucide-react';
import { SEO } from '@/components/common/SEO';
import { PageContent } from '@/components/layout/PageContent';
import { AppLogo } from '@/components/logo/AppLogo';

/** One page for everything that used to be /about, /contact, /disclaimer and /report:
 *  the old paths redirect here with a hash, so deep links keep working. The /report
 *  comment board was retired — it never received a comment on any environment — so
 *  feedback is simply part of 聯絡. */
const NAV: { id: string; label: string }[] = [
  { id: 'about', label: '關於' },
  { id: 'contact', label: '聯絡與回饋' },
  { id: 'disclaimer', label: '免責聲明' },
];

function Section({ id, title, children }: { id: string; title: string; children: React.ReactNode }) {
  return (
    <section id={id} className="bg-card border border-border rounded-md p-5 sm:p-6 scroll-mt-24">
      <h2 className="text-lg font-semibold tracking-[-0.01em] mb-4">{title}</h2>
      <div className="text-base leading-[1.65] text-muted-foreground space-y-4">{children}</div>
    </section>
  );
}

const FEATURES: { n: number; title: string; body: string }[] = [
  { n: 1, title: '智慧摘要', body: '運用 AI 技術，快速梳理財經 Podcast 與新聞重點，讓您在幾分鐘內掌握小時級內容的精華。' },
  { n: 2, title: '市場數據', body: '即時串接股市數據，將觀點與價格走勢直接連結，驗證市場反應並追蹤標的表現。' },
  { n: 3, title: '趨勢洞察', body: '透過視覺化工具探索產業關聯與趨勢發展，發現潛在的投資機會與風險。' },
];

const SOURCES: { label: string; body: string }[] = [
  { label: '財經媒體', body: '精選高品質的產業分析、Podcast 與新聞報導。' },
  { label: '金融市場', body: '來自全球主要交易所的即時報價與財務指標。' },
  { label: '產業研究', body: '整合公開報告與數據，構建產業知識圖譜。' },
];

const DISCLAIMER: { title: string; body: string }[] = [
  {
    title: '資訊來源與準確性',
    body: '本服務內容整理自公開資訊、各大財經 Podcast 及市場數據。雖然我們盡力確保資訊的準確性與可靠性，但無法保證其完整性、即時性或絕對正確性。市場資訊瞬息萬變，所有數據以來源機構之最終公告為準。',
  },
  {
    title: '投資風險告知',
    body: '金融市場具有高度風險，投資涉及盈虧，過去的績效不代表未來的表現。使用者在做出任何投資決策前，應審慎評估自身風險承受能力、投資目標及財務狀況，並建議諮詢合格的專業財務顧問。',
  },
  {
    title: '責任限制',
    body: 'TinBoker 團隊不對因使用、引用或依賴本網站資訊而產生的任何直接、間接、附帶或衍生之損失負責。使用者應自行承擔所有投資決策之風險與後果。',
  },
];

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
  const { hash } = useLocation();
  // Deep links (/about#contact, redirected /disclaimer, …) land on their section.
  useEffect(() => {
    const id = hash.replace(/^#/, '');
    if (!id) return;
    const t = window.setTimeout(() => document.getElementById(id)?.scrollIntoView({ block: 'start' }), 50);
    return () => window.clearTimeout(t);
  }, [hash]);

  return (
    <>
      <SEO title="關於 TinBoker" description="TinBoker（聽播客）— 結合 Podcast 觀點與即時數據的財經平台。聯絡方式與免責聲明都在這一頁。" />
      <PageContent className="max-w-3xl">
        <div className="flex items-center justify-center gap-2 mb-2 pt-4">
          <span className="text-2xl font-semibold tracking-[-0.02em]">關於</span>
          <AppLogo size={28} />
        </div>
        <p className="text-center text-base text-muted-foreground max-w-xl mx-auto mb-5 leading-[1.65]">
          TinBoker（聽播客）把財經 Podcast 的觀點結構化、和即時市場數據對照，幫你用更短的時間掌握重點。
        </p>
        <nav className="flex justify-center gap-2 flex-wrap mb-6" aria-label="頁內導覽">
          {NAV.map((n) => (
            <a key={n.id} href={`#${n.id}`} className="filter-pill" data-active={hash === `#${n.id}` || undefined}>{n.label}</a>
          ))}
        </nav>

        <div className="space-y-4">
          <Section id="about" title="核心功能">
            {FEATURES.map((f) => (
              <div key={f.n} className="grid grid-cols-[24px_1fr] gap-3">
                <span className="font-mono text-sm text-muted-foreground pt-0.5 tabular-nums">{f.n}</span>
                <div>
                  <h3 className="text-base font-semibold text-foreground mb-1">{f.title}</h3>
                  <p>{f.body}</p>
                </div>
              </div>
            ))}
            <p className="pt-4 border-t border-border">TinBoker 匯集多個可信來源的數據，確保資訊的廣度與深度：</p>
            <ul className="space-y-2">
              {SOURCES.map((s) => (
                <li key={s.label} className="grid grid-cols-[14px_1fr] gap-2">
                  <span className="mt-[9px] w-1.5 h-1.5 rounded-full bg-foreground" />
                  <span><strong className="text-foreground font-semibold">{s.label}：</strong>{s.body}</span>
                </li>
              ))}
            </ul>
          </Section>

          <Section id="contact" title="聯絡與意見回饋">
            <p>TinBoker 還在很早期的階段，一定有很多不完美的地方。bug 回報、功能許願、產品建議、合作想法或使用疑問，寫信或在 Threads 留言都可以，我們都會看。</p>
            <div className="flex items-center gap-2 text-xs bg-muted px-3.5 py-2.5 rounded-md w-fit">
              <Clock size={14} className="text-accent-info shrink-0" />
              <span>客服回覆時間：週一至週五 11:00–17:00（國定及例假日除外）</span>
            </div>
            <div className="space-y-5 pt-1">
              <ContactRow icon={<Mail size={18} />} title="電子郵件">
                <a href="mailto:contact@tinboker.com?subject=TinBoker%20%E6%84%8F%E8%A6%8B%E5%9B%9E%E9%A5%8B" className="text-accent-info hover:underline">contact@tinboker.com</a>
              </ContactRow>
              <ContactRow icon={<MessageCircle size={18} />} title="官方 Line 帳號">
                <span>@tinboker</span>
              </ContactRow>
              <ContactRow icon={<AtSign size={18} />} title="官方 Threads 帳號">
                <a href="https://www.threads.net/@tinboker" target="_blank" rel="noopener noreferrer" className="text-accent-info hover:underline">@tinboker</a>
              </ContactRow>
            </div>
          </Section>

          <Section id="disclaimer" title="免責聲明">
            <p className="flex items-start gap-2 text-foreground font-medium">
              <ShieldAlert size={18} className="shrink-0 mt-1 text-muted-foreground" />
              本網站（TinBoker）所提供之所有資訊、數據、觀點與分析，僅供參考與學習用途，不構成任何形式的投資建議、要約、誘導或推薦。
            </p>
            {DISCLAIMER.map((s) => (
              <div key={s.title}>
                <h3 className="text-base font-semibold text-foreground mb-1">{s.title}</h3>
                <p>{s.body}</p>
              </div>
            ))}
          </Section>

        </div>

        <div className="text-center text-2xs text-muted-foreground/50 tabular-nums mt-8 pb-4">
          {__APP_VERSION__}
        </div>
      </PageContent>
    </>
  );
};
