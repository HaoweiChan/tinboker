import { SEO } from '@/components/common/SEO';
import { PageContent } from '@/components/layout/PageContent';
import { AppLogo } from '@/components/logo/AppLogo';

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="bg-card border border-border rounded-md p-5 sm:p-6">
      <h2 className="text-[16px] font-semibold tracking-[-0.01em] mb-4">{title}</h2>
      <div className="text-[14px] leading-[1.65] text-muted-foreground space-y-4">{children}</div>
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

export const About: React.FC = () => (
  <>
    <SEO title="關於 TinBoker" description="TinBoker（聽播客）— 結合 Podcast 觀點與即時數據的財經平台。" />
    <PageContent className="max-w-3xl">
      <div className="flex items-center justify-center gap-2 mb-2 pt-4">
        <span className="text-[22px] font-semibold tracking-[-0.02em]">關於</span>
        <AppLogo size={28} />
      </div>
      <p className="text-center text-[14px] text-muted-foreground max-w-xl mx-auto mb-8 leading-[1.65]">
        TinBoker（聽播客）把財經 Podcast 的觀點結構化、和即時市場數據對照，幫你用更短的時間掌握重點。
      </p>

      <div className="space-y-4">
        <Section title="核心功能">
          {FEATURES.map((f) => (
            <div key={f.n} className="grid grid-cols-[24px_1fr] gap-3">
              <span className="font-mono text-[13px] text-muted-foreground pt-0.5 tabular-nums">{f.n}</span>
              <div>
                <h3 className="text-[14px] font-semibold text-foreground mb-1">{f.title}</h3>
                <p>{f.body}</p>
              </div>
            </div>
          ))}
        </Section>

        <Section title="資料來源">
          <p>TinBoker 匯集多個可信來源的數據，確保資訊的廣度與深度：</p>
          <ul className="space-y-2">
            {SOURCES.map((s) => (
              <li key={s.label} className="grid grid-cols-[14px_1fr] gap-2">
                <span className="mt-[9px] w-1.5 h-1.5 rounded-full bg-foreground" />
                <span>
                  <strong className="text-foreground font-semibold">{s.label}：</strong>
                  {s.body}
                </span>
              </li>
            ))}
          </ul>
          <p className="text-[12px] pt-4 border-t border-border">
            <strong className="text-foreground">免責聲明：</strong>
            TinBoker 提供的資訊僅供參考和教育目的，不應視為投資建議。在做出投資決策前，請務必自行研究並諮詢合格的財務顧問。
          </p>
        </Section>
      </div>
    </PageContent>
  </>
);
