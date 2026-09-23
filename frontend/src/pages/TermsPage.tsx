import { useEffect } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { SEO } from '@/components/common/SEO';
import { PageContent } from '@/components/layout/PageContent';
import { ServiceLinks } from '@/components/membership/ServiceLinks';

export default function TermsPage() {
  const { hash } = useLocation();
  useEffect(() => { document.getElementById(hash.slice(1))?.scrollIntoView({ block: 'start' }); }, [hash]);
  return (
    <>
      <SEO title="服務條款與政策" description="聽播客 TinBoker 目前服務說明、隱私權政策與付費方案開放前的退款資訊。" url="https://tinboker.com/terms" />
      <PageContent className="max-w-3xl">
        <h1 className="text-2xl font-semibold tracking-[-0.02em]">服務條款與政策</h1>
        <p className="mt-2 mb-5 text-base leading-relaxed text-muted-foreground">目前網站提供免費服務，付費會員訂閱尚未開放。付款、續訂及退款條件將於開放前另行公告。</p>
        <ServiceLinks />
        <div className="mt-6 space-y-5">
          <section id="service" className="scroll-mt-24 rounded-md border border-border bg-card p-5 sm:p-6 space-y-3">
            <h2 className="text-lg font-semibold">服務內容</h2>
            <p className="text-sm leading-relaxed text-muted-foreground">聽播客 TinBoker 整理公開財經 Podcast、新聞與市場資料，提供摘要、個股與話題索引。瀏覽公開內容不需付費；收藏、追蹤與留言等個人功能需要登入。</p>
            <p className="text-sm leading-relaxed text-muted-foreground">內容整理自公開資訊，無法保證其完整性、即時性或絕對正確性。所有數據以來源機構之最終公告為準。本服務不是投資建議，過去績效不代表未來表現。</p>
            <Link to="/about#disclaimer" className="inline-block text-sm text-accent-info hover:underline">完整免責聲明</Link>
          </section>
          <section id="subscription" className="scroll-mt-24 rounded-md border border-border bg-card p-5 sm:p-6 space-y-3">
            <h2 className="text-lg font-semibold">會員與收費</h2>
            <p className="text-sm leading-relaxed text-muted-foreground">會員付費方案目前處於規劃階段，預計以新臺幣按月收費。本站目前不提供付款入口，也不會因瀏覽方案頁而建立付費訂閱。</p>
            <p className="text-sm leading-relaxed text-muted-foreground">實際開放日期、付款方式、自動續訂與取消流程尚待確認，開放前會一併說明。</p>
            <Link to="/membership" className="inline-block text-sm text-accent-info hover:underline">查看服務內容與規劃價格</Link>
          </section>
          <section id="refund" className="scroll-mt-24 rounded-md border border-border bg-card p-5 sm:p-6 space-y-3">
            <h2 className="text-lg font-semibold">退款政策</h2>
            <p className="text-sm leading-relaxed text-muted-foreground">付費訂閱尚未開放，目前不接受付款。付費服務的退款條件、申請方式及處理時程尚待確認，將在開放付款前公告。</p>
            <p className="text-sm leading-relaxed text-muted-foreground">如有付款或消費權益疑問，請寄信至 <a href="mailto:contact@tinboker.com" className="text-accent-info hover:underline">contact@tinboker.com</a>，並說明問題。請勿透過電子郵件提供完整信用卡號、安全碼或密碼。</p>
          </section>
          <section id="privacy" className="scroll-mt-24 rounded-md border border-border bg-card p-5 sm:p-6 space-y-3">
            <h2 className="text-lg font-semibold">隱私權政策</h2>
            <p className="text-sm leading-relaxed text-muted-foreground">使用 Google 登入時，本服務取得帳號識別資訊、姓名、電子郵件與大頭貼，用於建立及識別您的帳號。您使用收藏、追蹤、留言或通知設定時，系統會保存這些設定及內容，以提供相應功能。</p>
            <p className="text-sm leading-relaxed text-muted-foreground">網站使用 Google Analytics 了解瀏覽情形，並使用 Google AdSense 提供廣告；這些第三方服務可能使用 Cookie 等技術。網站也透過 Cloudflare 提供網頁傳輸與安全服務。</p>
            <p className="text-sm leading-relaxed text-muted-foreground">若對帳號資料有疑問，或希望查詢、更正或刪除您的資料，請以帳號信箱聯絡 <a href="mailto:contact@tinboker.com" className="text-accent-info hover:underline">contact@tinboker.com</a>。本頁不要求您提交信用卡資料。</p>
          </section>
        </div>
      </PageContent>
    </>
  );
}
