import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { SEO } from '@/components/common/SEO';
import { PageContent } from '@/components/layout/PageContent';
import { ServiceLinks } from '@/components/membership/ServiceLinks';
import { getMembershipPlans, type MembershipPlans } from '@/services/api/billing';

export default function MembershipPage() {
  const [plans, setPlans] = useState<MembershipPlans | null>(null);
  const [error, setError] = useState(false);
  useEffect(() => {
    let alive = true;
    getMembershipPlans().then(value => { if (alive) setPlans(value); }).catch(() => { if (alive) setError(true); });
    return () => { alive = false; };
  }, []);

  return (
    <>
      <SEO title="服務與會員方案" description="聽播客 TinBoker 的財經 Podcast 摘要、個股提及整理與會員方案介紹。付費訂閱尚未開放。" url="https://tinboker.com/membership" />
      <PageContent className="max-w-5xl">
        <h1 className="text-2xl font-semibold tracking-[-0.02em]">服務與會員方案</h1>
        <p className="mt-2 mb-5 max-w-2xl text-base leading-relaxed text-muted-foreground">聽播客 TinBoker 將財經 Podcast 的公開內容整理為摘要、個股提及與主題索引，協助讀者查找來源、掌握討論重點。</p>
        <ServiceLinks />
        <section className="mt-6 rounded-md border border-border bg-card p-5 sm:p-6">
          <h2 className="text-lg font-semibold">目前可使用的服務</h2>
          <div className="mt-4 grid gap-5 sm:grid-cols-3">
            <div><h3 className="font-medium">節目摘要</h3><p className="mt-1 text-sm leading-relaxed text-muted-foreground">瀏覽節目與集數，閱讀整理後的討論重點，並連回原始 Podcast。</p></div>
            <div><h3 className="font-medium">個股與話題</h3><p className="mt-1 text-sm leading-relaxed text-muted-foreground">查找個股在哪些節目被提及，依主題探索相關內容。</p></div>
            <div><h3 className="font-medium">個人收藏</h3><p className="mt-1 text-sm leading-relaxed text-muted-foreground">以 Google 帳號登入後，可收藏集數、追蹤節目與自選個股。</p></div>
          </div>
          <p className="mt-5 text-sm text-muted-foreground">目前網站提供免費瀏覽。內容是公開言論與市場資料的整理，不構成投資建議，也不保證投資報酬。</p>
          <Link to="/" className="mt-4 inline-block text-sm text-accent-info hover:underline">瀏覽目前服務 →</Link>
        </section>

        <section className="mt-5 rounded-md border border-border bg-card p-5 sm:p-6">
          <div className="flex flex-wrap items-center gap-3"><h2 className="text-lg font-semibold">規劃中的會員方案</h2><span className="rounded bg-muted px-2 py-1 text-xs text-muted-foreground">付費訂閱尚未開放</span></div>
          <p className="mt-3 text-sm leading-relaxed text-muted-foreground">預計提供個股提及後的 7／30／90 天走勢整理，以及最近 7 天的個股觀點摘要。這些付費內容尚未在正式網站開放；目前不接受付款。</p>
          {plans ? <div className="mt-5 grid gap-4 sm:grid-cols-2">
            <div className="rounded border border-border p-4"><p className="text-xs text-muted-foreground">規劃月費</p><p className="mt-1 text-2xl font-semibold tabular-nums">NT$ {plans.list_price.toLocaleString('zh-TW')} <span className="text-sm font-normal text-muted-foreground">/ 月</span></p></div>
            {plans.founding_open && <div className="rounded border border-border p-4"><p className="text-xs text-muted-foreground">規劃創始會員月費</p><p className="mt-1 text-2xl font-semibold tabular-nums">NT$ {plans.founding_price.toLocaleString('zh-TW')} <span className="text-sm font-normal text-muted-foreground">/ 月</span></p></div>}
          </div> : <p role="status" className="mt-4 text-sm text-muted-foreground">{error ? '價格資訊暫時無法載入，請稍後再查看。' : '正在載入方案價格…'}</p>}
          <p className="mt-4 text-sm leading-relaxed text-muted-foreground">預計採新臺幣按月訂閱。自動續訂、取消方式及退款條件尚待確認，將於開放付費前清楚公告。本頁不是付款或訂閱申請。</p>
          <button type="button" disabled className="mt-4 rounded bg-muted px-4 py-2.5 text-sm font-medium text-muted-foreground">尚未開放訂閱</button>
        </section>

        <section className="mt-5 rounded-md border border-border bg-card p-5 sm:p-6">
          <h2 className="text-lg font-semibold">服務畫面</h2>
          <p className="mt-2 mb-4 text-sm text-muted-foreground">以下為目前免費服務的實際畫面（2026 年 9 月 23 日），內容會隨節目與資料更新。</p>
          <div className="grid gap-4 sm:grid-cols-2">
            <figure><img src="/screenshots/merchant-home.png" alt="聽播客首頁的近期討論與市場話題" className="w-full rounded border border-border" loading="lazy" /><figcaption className="mt-2 text-xs text-muted-foreground">首頁近期討論與市場話題</figcaption></figure>
            <figure><img src="/screenshots/merchant-stock.png" alt="聽播客個股列表中的節目提及索引" className="w-full rounded border border-border" loading="lazy" /><figcaption className="mt-2 text-xs text-muted-foreground">個股提及索引</figcaption></figure>
          </div>
        </section>
      </PageContent>
    </>
  );
}
