import { ShieldAlert } from 'lucide-react';
import { SEO } from '@/components/common/SEO';
import { PageContent } from '@/components/layout/PageContent';

const SECTIONS: { title: string; body: string }[] = [
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

export const DisclaimerPage: React.FC = () => (
  <>
    <SEO title="免責聲明" description="TinBoker 免責聲明 — 所有資訊僅供參考與學習用途。" />
    <PageContent className="max-w-2xl">
      <div className="text-center mb-6 pt-4">
        <div className="w-14 h-14 rounded-full bg-muted text-muted-foreground grid place-items-center mx-auto mb-4">
          <ShieldAlert size={26} />
        </div>
        <h1 className="text-2xl font-semibold tracking-[-0.02em]">免責聲明</h1>
        <p className="text-sm text-muted-foreground mt-1">請在使用本服務前仔細閱讀以下條款</p>
      </div>
      <div className="bg-card border border-border rounded-md p-6 sm:p-8 space-y-7">
        <p className="text-md font-medium leading-[1.65]">
          本網站（TinBoker）所提供之所有資訊、數據、觀點與分析，僅供參考與學習用途，不構成任何形式的投資建議、要約、誘導或推薦。
        </p>
        <div className="space-y-6">
          {SECTIONS.map((s) => (
            <section key={s.title}>
              <h3 className="text-md font-semibold mb-2 flex items-center gap-2">
                <span className="w-1 h-5 bg-foreground rounded-full" />
                {s.title}
              </h3>
              <p className="text-base text-muted-foreground leading-[1.65]">{s.body}</p>
            </section>
          ))}
          <div className="pt-6 border-t border-border text-xs text-muted-foreground text-center">
            最後更新日期：{new Date().getFullYear()} 年 {new Date().getMonth() + 1} 月
          </div>
        </div>
      </div>
    </PageContent>
  </>
);

export default DisclaimerPage;
