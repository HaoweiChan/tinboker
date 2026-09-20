import { useEffect } from 'react';
import { useLocation, Link } from 'react-router-dom';
import { SEO } from '@/components/common/SEO';
import { Section } from '@/components/common/Section';
import { PageContent } from '@/components/layout/PageContent';

/** /terms — 服務條款、會員訂閱與付款、退款政策、隱私權政策, all on one page (anchors
 *  #subscription / #refund / #privacy). /privacy and /refund redirect here with a hash
 *  (App.tsx), the same pattern About.tsx uses for its own retired standalone pages.
 *  Copy is verbatim from the approved terms-copy.md — do not edit the wording here. */

const TERMS: { title: string; body: React.ReactNode }[] = [
  {
    title: '服務內容',
    body: '本服務整理公開的財經 Podcast 與新聞內容，提供 AI 摘要、個股與題材的提及紀錄，以及提及後的股價統計。瀏覽網站不需註冊；收藏、留言、通知等功能需以 Google 帳號登入。',
  },
  {
    title: '不構成投資建議',
    body: (
      <>
        本服務所有內容，皆為第三方公開言論與公開市場資料的整理與統計，不是對任何有價證券的推介、評等或買賣建議，也不保證任何報酬。投資決策及其結果由您自行負責。完整說明請見
        <Link to="/about#disclaimer" className="text-accent-info hover:underline">免責聲明</Link>。
      </>
    ),
  },
  {
    title: '帳號與使用規範',
    body: '您應妥善保管登入帳號，並對該帳號下的行為負責。請勿以自動化方式大量擷取內容、干擾服務運作、冒用他人身分，或張貼違法、侵權、騷擾性的留言。違反時，我們得移除內容、暫停或終止帳號。',
  },
  {
    title: '智慧財產權',
    body: 'Podcast 節目與新聞的著作權屬於原創作者及媒體。本服務的摘要、統計、介面與程式，著作權屬本服務所有；您可以為個人、非商業目的使用與分享，並請註明出處。',
  },
  {
    title: '服務變更與中斷',
    body: (
      <>
        我們會持續調整功能，也可能因維護、第三方資料來源或不可抗力而暫時中斷。付費功能若有重大變更或終止，會事先公告，並依
        <Link to="/terms#refund" className="text-accent-info hover:underline">退款政策</Link>處理。
      </>
    ),
  },
  {
    title: '條款修改、準據法與管轄',
    body: '條款修改時會更新本頁的日期；重大修改會另以站內公告或電子郵件通知。本條款以中華民國法律為準據法；因本服務所生爭議，以臺灣臺北地方法院為第一審管轄法院。',
  },
];

const SUBSCRIPTION: { title: string; body: React.ReactNode }[] = [
  {
    title: '會員內容',
    body: (
      <>
        付費會員可使用會員專屬功能，目前的內容與價格以
        <Link to="/membership" className="text-accent-info hover:underline">會員方案</Link>頁面所示為準。未列為會員專屬的功能維持免費。
      </>
    ),
  },
  {
    title: '價格與創始會員',
    body: '訂閱以新臺幣計價、按月收費。以創始會員價訂閱者，在該筆訂閱持續期間內維持同一價格；訂閱一旦取消或終止，重新訂閱時適用當時的價格。',
  },
  {
    title: '自動續訂與扣款',
    body: '訂閱為每月自動續訂：首次訂閱時立即收取第一期費用，之後每月於相同日期（當月無該日時為月底）由您授權的信用卡自動扣款，直到您取消為止。',
  },
  {
    title: '付款處理',
    body: '刷卡由藍新金流（NewebPay）處理。您的完整卡號、有效期限與安全碼由藍新金流保存，本服務不會經手，也不會儲存。',
  },
  {
    title: '取消訂閱',
    body: '您可以隨時在會員頁面取消，不需要理由，也沒有違約金。取消後不再扣款，會員資格保留到已付費的該期結束。',
  },
  {
    title: '扣款失敗',
    body: '某一期扣款失敗時，會員資格於該期到期後暫停；下一期扣款成功即自動恢復。信用卡到期或換發時，請取消後以新卡重新訂閱。',
  },
];

const REFUND: { title: string; body: string }[] = [
  {
    title: '首次訂閱七日內全額退款',
    body: '第一次訂閱本服務的會員，自首次付款日起七日內，可以來信申請全額退款，不需要理由。退款後會員資格立即終止。',
  },
  {
    title: '其他情形',
    body: '會員內容為線上即時提供的數位服務，除上述情形外，已收取的當期費用不按比例退還；取消訂閱後不會再有新的扣款。',
  },
  {
    title: '可歸責於本服務的情形',
    body: '重複扣款、金額錯誤，或會員功能因本服務的原因連續無法使用達七日以上時，您可以申請退還受影響期間的費用。',
  },
  {
    title: '申請方式與時程',
    body: '請以註冊的電子郵件寄信到 contact@tinboker.com，註明帳號信箱與扣款日期。我們會在七個工作日內回覆；核准的退款經由藍新金流退回原信用卡，實際入帳時間依發卡銀行作業而定。',
  },
];

const DATA_COLLECTED: { label: string; body: string }[] = [
  { label: '帳號資料', body: '以 Google 登入時取得的姓名、電子郵件與大頭貼。' },
  { label: '使用資料', body: '您的收藏、訂閱的節目與標籤、留言、通知設定。' },
  { label: '訂閱資料', body: '訂閱狀態、金額、扣款時間與藍新金流的交易編號。不包含完整卡號。' },
  { label: '瀏覽資料', body: '透過 Cookie 與 Google Analytics 蒐集的匿名瀏覽統計。' },
];

const PRIVACY: { title: string; body: React.ReactNode }[] = [
  {
    title: '使用目的',
    body: '提供並維持服務、依您的設定發送通知、處理訂閱與客服、統計分析以改善產品，以及履行法律義務。',
  },
  {
    title: '廣告與 Cookie',
    body: (
      <>
        未登入的訪客會看到 Google AdSense 廣告，Google 及其合作夥伴可能使用 Cookie 依您的瀏覽紀錄顯示廣告；您可以在 Google 的
        <a href="https://adssettings.google.com" target="_blank" rel="noopener noreferrer" className="text-accent-info hover:underline">廣告設定</a>
        中管理。登入後不載入廣告。
      </>
    ),
  },
  {
    title: '與第三方分享',
    body: '我們不會出售您的個人資料。只在提供服務所必要的範圍內，交由下列服務處理：Google（登入、流量分析、廣告）、藍新金流（付款）、Cloudflare（網站傳輸與安全）。法律要求時，我們會依法配合。',
  },
  {
    title: '保存期間',
    body: '帳號資料保存到您要求刪除為止；交易紀錄依稅務及相關法令要求的年限保存。',
  },
  {
    title: '您的權利',
    body: '依個人資料保護法，您可以查詢、閱覽、取得複本、更正、要求停止蒐集、處理或利用，以及刪除您的個人資料。請來信 contact@tinboker.com，我們會在三十日內處理。仍有有效訂閱時，請先取消訂閱再申請刪除帳號。',
  },
  {
    title: '資料安全與未成年人',
    body: '資料傳輸全程以 HTTPS 加密，存取受到權限控管。本服務不以未滿十八歲者為對象；未成年人使用付費功能，應先取得法定代理人同意。',
  },
];

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
      <SEO title="服務條款與政策" description="TinBoker 服務條款、會員訂閱與付款、退款政策與隱私權政策。" />
      <PageContent className="max-w-3xl">
        <div className="text-center pt-4 mb-2">
          <h1 className="text-2xl font-semibold tracking-[-0.02em]">服務條款與政策</h1>
        </div>
        <p className="text-center text-sm text-muted-foreground/70 mb-2">最後更新：2026 年 9 月 20 日</p>
        <p className="text-center text-base text-muted-foreground max-w-xl mx-auto mb-6 leading-[1.65]">
          使用 TinBoker（聽播客，以下稱「本服務」）即表示您同意以下條款。本頁包含服務條款、會員訂閱與付款、退款政策與隱私權政策。
        </p>

        <div className="space-y-4">
          <Section id="terms" title="服務條款">
            {TERMS.map((s) => (
              <div key={s.title}>
                <h3 className="text-base font-semibold text-foreground mb-1">{s.title}</h3>
                <p>{s.body}</p>
              </div>
            ))}
          </Section>

          <Section id="subscription" title="會員訂閱與付款">
            {SUBSCRIPTION.map((s) => (
              <div key={s.title}>
                <h3 className="text-base font-semibold text-foreground mb-1">{s.title}</h3>
                <p>{s.body}</p>
              </div>
            ))}
          </Section>

          <Section id="refund" title="退款政策">
            {REFUND.map((s) => (
              <div key={s.title}>
                <h3 className="text-base font-semibold text-foreground mb-1">{s.title}</h3>
                <p>{s.body}</p>
              </div>
            ))}
          </Section>

          <Section id="privacy" title="隱私權政策">
            <div>
              <h3 className="text-base font-semibold text-foreground mb-1">我們蒐集的資料</h3>
              <ul className="space-y-2">
                {DATA_COLLECTED.map((d) => (
                  <li key={d.label} className="grid grid-cols-[14px_1fr] gap-2">
                    <span className="mt-[9px] w-1.5 h-1.5 rounded-full bg-foreground" />
                    <span><strong className="text-foreground font-semibold">{d.label}：</strong>{d.body}</span>
                  </li>
                ))}
              </ul>
            </div>
            {PRIVACY.map((s) => (
              <div key={s.title}>
                <h3 className="text-base font-semibold text-foreground mb-1">{s.title}</h3>
                <p>{s.body}</p>
              </div>
            ))}
          </Section>
        </div>

        <p className="text-center text-sm text-muted-foreground mt-6 pb-4">
          對本頁內容有任何疑問，請來信 <a href="mailto:contact@tinboker.com" className="text-accent-info hover:underline">contact@tinboker.com</a>。客服回覆時間：週一至週五 11:00–17:00（國定及例假日除外）。
        </p>
      </PageContent>
    </>
  );
};

export default TermsPage;
