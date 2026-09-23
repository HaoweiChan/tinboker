import { SEO } from '@/components/common/SEO';
import { PageContent } from '@/components/layout/PageContent';
import { ServiceLinks } from '@/components/membership/ServiceLinks';

export default function ContactPage() {
  return (
    <>
      <SEO title="客服聯絡" description="聽播客 TinBoker 客服信箱與回覆時間。" url="https://tinboker.com/contact" />
      <PageContent className="max-w-3xl">
        <h1 className="text-2xl font-semibold tracking-[-0.02em]">客服聯絡</h1>
        <p className="mt-2 mb-5 text-base text-muted-foreground">產品使用、帳號資料、合作與消費權益相關問題，都可以透過以下信箱聯絡我們。</p>
        <ServiceLinks />
        <section className="mt-6 rounded-md border border-border bg-card p-5 sm:p-6 space-y-4">
          <div><h2 className="text-sm font-medium text-muted-foreground">客服電子郵件</h2><a href="mailto:contact@tinboker.com" className="mt-1 inline-block break-all text-xl font-semibold text-accent-info hover:underline">contact@tinboker.com</a></div>
          <div><h2 className="text-sm font-medium text-muted-foreground">客服回覆時間</h2><p className="mt-1 text-base">週一至週五 11:00–17:00</p><p className="mt-1 text-sm text-muted-foreground">國定及例假日除外。</p></div>
          <p className="text-sm leading-relaxed text-muted-foreground">來信時請說明遇到的問題及相關頁面；帳號問題可提供登入信箱。請勿寄送密碼、完整信用卡號或安全碼。</p>
        </section>
      </PageContent>
    </>
  );
}
