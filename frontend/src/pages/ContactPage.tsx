import { Mail, Clock, MessageCircle, AtSign } from 'lucide-react';
import { SEO } from '@/components/common/SEO';
import { PageContent } from '@/components/layout/PageContent';
import { AppLogo } from '@/components/logo/AppLogo';

function ContactRow({ icon, title, children }: { icon: React.ReactNode; title: string; children: React.ReactNode }) {
  return (
    <div className="flex items-start gap-3.5">
      <div className="w-10 h-10 rounded-md bg-muted text-muted-foreground grid place-items-center shrink-0">{icon}</div>
      <div className="min-w-0">
        <h3 className="text-[14px] font-semibold mb-0.5">{title}</h3>
        <div className="text-[14px] text-muted-foreground">{children}</div>
      </div>
    </div>
  );
}

export const ContactPage: React.FC = () => (
  <>
    <SEO title="聯絡我們" description="產品建議、合作想法或使用疑問 — 歡迎與 TinBoker 聯繫。" />
    <PageContent className="max-w-2xl">
      <div className="flex items-center justify-center gap-2 mb-6 pt-4">
        <span className="text-[22px] font-semibold tracking-[-0.02em]">聯絡</span>
        <AppLogo size={28} />
      </div>
      <div className="bg-card border border-border rounded-md p-6 sm:p-8">
        <p className="text-[14px] text-muted-foreground leading-[1.65] mb-5">
          我們重視每一位使用者的聲音。若您有任何產品建議、合作想法或使用疑問，歡迎隨時與我們聯繫。
        </p>
        <div className="flex items-center gap-2 text-[12px] text-muted-foreground mb-8 bg-muted px-3.5 py-2.5 rounded-md w-fit">
          <Clock size={14} className="text-accent-info shrink-0" />
          <span>客服回覆時間：週一至週五 11:00–17:00（國定及例假日除外）</span>
        </div>
        <div className="space-y-6">
          <ContactRow icon={<Mail size={18} />} title="電子郵件">
            <a href="mailto:contact@tinboker.com" className="text-accent-info hover:underline">contact@tinboker.com</a>
          </ContactRow>
          <ContactRow icon={<MessageCircle size={18} />} title="官方 Line 帳號">
            <a href="#" className="text-accent-info hover:underline">@tinboker</a>
          </ContactRow>
          <ContactRow icon={<AtSign size={18} />} title="官方 Threads 帳號">
            <a href="https://www.threads.net/@tinboker" target="_blank" rel="noopener noreferrer" className="text-accent-info hover:underline">@tinboker</a>
          </ContactRow>
        </div>
      </div>
    </PageContent>
  </>
);

export default ContactPage;
