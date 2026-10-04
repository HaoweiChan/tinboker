// Copy for the plain-text pages (/about, /terms, /methodology), in ONE place.
//
// Two renderers read this: the React pages (src/pages/About.tsx, TermsPage.tsx,
// MethodologyPage.tsx) and the crawler body in functions/_middleware.js. Until 2026-10
// the middleware carried a hand-kept excerpt instead — /terms served crawlers 4
// sentences of a 25-paragraph page, and its privacy excerpt left out the advertising
// cookie disclosure the page itself makes. A copy kept in sync by hand drifts; a shared
// one cannot.
//
// Plain JS (not TS) on purpose: the middleware is also imported by a bare `node` script
// (scripts/validate-crawler-meta.mjs) on Node 20, which cannot load .ts. Types live in
// sitePages.d.ts.
//
// A body is a string, or a list of segments: string | { to, text } (in-site link) |
// { href, text } (external link). The /terms wording is the approved terms-copy.md text
// — restructure freely, do not reword.

export const ABOUT = {
  title: '關於 TinBoker',
  description: 'TinBoker（聽播客）— 結合 Podcast 觀點與即時數據的財經平台。聯絡方式與免責聲明都在這一頁。',
  intro: 'TinBoker（聽播客）把財經 Podcast 的觀點結構化、和即時市場數據對照，幫你用更短的時間掌握重點。',
  features: [
    { title: '智慧摘要', body: '運用 AI 技術，快速梳理財經 Podcast 與新聞重點，讓您在幾分鐘內掌握小時級內容的精華。' },
    { title: '市場數據', body: '即時串接股市數據，將觀點與價格走勢直接連結，驗證市場反應並追蹤標的表現。' },
    { title: '趨勢洞察', body: '透過視覺化工具探索產業關聯與趨勢發展，發現潛在的投資機會與風險。' },
  ],
  sourcesIntro: 'TinBoker 匯集多個可信來源的數據，確保資訊的廣度與深度：',
  sources: [
    { label: '財經媒體', body: '精選高品質的產業分析、Podcast 與新聞報導。' },
    { label: '金融市場', body: '來自全球主要交易所的即時報價與財務指標。' },
    { label: '產業研究', body: '整合公開報告與數據，構建產業知識圖譜。' },
  ],
  operator: [
    'TinBoker 由一位在臺灣的獨立開發者以個人名義經營，不隸屬於任何券商、投顧、投信或媒體集團。',
    [
      '網站上的每一個數字都可以回溯到原始節目或公開市場資料；摘要怎麼產生、看多看空怎麼判定、統計怎麼算，寫在',
      { to: '/methodology', text: '資料來源與方法' },
      '。發現錯誤請來信，我們會更正。',
    ],
  ],
  contactIntro: 'TinBoker 還在很早期的階段，一定有很多不完美的地方。bug 回報、功能許願、產品建議、合作想法或使用疑問，寫信或在 Threads 留言都可以，我們都會看。',
  hours: '客服回覆時間：週一至週五 11:00–17:00（國定及例假日除外）',
  email: 'contact@tinboker.com',
  line: '@tinboker',
  threads: { href: 'https://www.threads.net/@tinboker', text: '@tinboker' },
  disclaimerLead: '本網站（TinBoker）所提供之所有資訊、數據、觀點與分析，僅供參考與學習用途，不構成任何形式的投資建議、要約、誘導或推薦。',
  disclaimer: [
    { title: '資訊來源與準確性', body: '本服務內容整理自公開資訊、各大財經 Podcast 及市場數據。雖然我們盡力確保資訊的準確性與可靠性，但無法保證其完整性、即時性或絕對正確性。市場資訊瞬息萬變，所有數據以來源機構之最終公告為準。' },
    { title: '投資風險告知', body: '金融市場具有高度風險，投資涉及盈虧，過去的績效不代表未來的表現。使用者在做出任何投資決策前，應審慎評估自身風險承受能力、投資目標及財務狀況，並建議諮詢合格的專業財務顧問。' },
    { title: '責任限制', body: 'TinBoker 團隊不對因使用、引用或依賴本網站資訊而產生的任何直接、間接、附帶或衍生之損失負責。使用者應自行承擔所有投資決策之風險與後果。' },
  ],
  policyLink: ['完整的服務條款、會員訂閱與付款、退款政策與隱私權政策，請見', { to: '/terms', text: '服務條款與政策' }, '。'],
};

export const TERMS = {
  title: '服務條款與政策',
  description: 'TinBoker 服務條款、會員訂閱與付款、退款政策與隱私權政策。',
  updated: '最後更新：2026 年 10 月 4 日',
  intro: '使用 TinBoker（聽播客，以下稱「本服務」）即表示您同意以下條款。本頁包含服務條款、會員訂閱與付款、退款政策與隱私權政策。',
  terms: [
    { title: '服務內容', body: '本服務整理公開的財經 Podcast 與新聞內容，提供 AI 摘要、個股與題材的提及紀錄，以及提及後的股價統計。瀏覽網站不需註冊；收藏、留言、通知等功能需以 Google 帳號登入。' },
    { title: '不構成投資建議', body: ['本服務所有內容，皆為第三方公開言論與公開市場資料的整理與統計，不是對任何有價證券的推介、評等或買賣建議，也不保證任何報酬。投資決策及其結果由您自行負責。完整說明請見', { to: '/about#disclaimer', text: '免責聲明' }, '。'] },
    { title: '帳號與使用規範', body: '您應妥善保管登入帳號，並對該帳號下的行為負責。請勿以自動化方式大量擷取內容、干擾服務運作、冒用他人身分，或張貼違法、侵權、騷擾性的留言。違反時，我們得移除內容、暫停或終止帳號。' },
    { title: '智慧財產權', body: 'Podcast 節目與新聞的著作權屬於原創作者及媒體。本服務的摘要、統計、介面與程式，著作權屬本服務所有；您可以為個人、非商業目的使用與分享，並請註明出處。' },
    { title: '服務變更與中斷', body: ['我們會持續調整功能，也可能因維護、第三方資料來源或不可抗力而暫時中斷。付費功能若有重大變更或終止，會事先公告，並依', { to: '/terms#refund', text: '退款政策' }, '處理。'] },
    { title: '條款修改、準據法與管轄', body: '條款修改時會更新本頁的日期；重大修改會另以站內公告或電子郵件通知。本條款以中華民國法律為準據法；因本服務所生爭議，以臺灣臺北地方法院為第一審管轄法院。' },
  ],
  subscription: [
    { title: '會員內容', body: ['付費會員可使用會員專屬功能，目前的內容與價格以', { to: '/membership', text: '會員方案' }, '頁面所示為準。未列為會員專屬的功能維持免費。'] },
    { title: '價格與優惠碼', body: '訂閱以新臺幣計價、按月收費。使用優惠碼訂閱者，在該筆訂閱持續期間內維持折扣後的價格；訂閱一旦取消或終止，重新訂閱時適用當時的價格。優惠碼數量有限，每個帳號限用一次。可全額折抵的優惠碼會直接開通一段期間的會員資格，不需付款，到期後也不會自動扣款。' },
    { title: '自動續訂與扣款', body: '訂閱為每月自動續訂：首次訂閱時立即收取第一期費用，之後每月於相同日期（當月無該日時為月底）由您授權的信用卡自動扣款，直到您取消為止。' },
    { title: '付款處理', body: '刷卡由藍新金流（NewebPay）處理。您的完整卡號、有效期限與安全碼由藍新金流保存，本服務不會經手，也不會儲存。' },
    { title: '取消訂閱', body: '您可以隨時在會員頁面取消，不需要理由，也沒有違約金。取消後不再扣款，會員資格保留到已付費的該期結束。' },
    { title: '扣款失敗', body: '某一期扣款失敗時，會員資格於該期到期後暫停；下一期扣款成功即自動恢復。信用卡到期或換發時，請取消後以新卡重新訂閱。' },
  ],
  refund: [
    { title: '首次訂閱七日內全額退款', body: '第一次訂閱本服務的會員，自首次付款日起七日內，可以來信申請全額退款，不需要理由。退款後會員資格立即終止。' },
    { title: '其他情形', body: '會員內容為線上即時提供的數位服務，除上述情形外，已收取的當期費用不按比例退還；取消訂閱後不會再有新的扣款。' },
    { title: '可歸責於本服務的情形', body: '重複扣款、金額錯誤，或會員功能因本服務的原因連續無法使用達七日以上時，您可以申請退還受影響期間的費用。' },
    { title: '申請方式與時程', body: '請以註冊的電子郵件寄信到 contact@tinboker.com，註明帳號信箱與扣款日期。我們會在七個工作日內回覆；核准的退款經由藍新金流退回原信用卡，實際入帳時間依發卡銀行作業而定。' },
  ],
  dataCollectedTitle: '我們蒐集的資料',
  dataCollected: [
    { label: '帳號資料', body: '以 Google 登入時取得的姓名、電子郵件與大頭貼。' },
    { label: '使用資料', body: '您的收藏、訂閱的節目與標籤、留言、通知設定。' },
    { label: '訂閱資料', body: '訂閱狀態、金額、扣款時間與藍新金流的交易編號。不包含完整卡號。' },
    { label: '瀏覽資料', body: '透過 Cookie 與 Google Analytics 蒐集的匿名瀏覽統計。' },
  ],
  privacy: [
    { title: '使用目的', body: '提供並維持服務、依您的設定發送通知、處理訂閱與客服、統計分析以改善產品，以及履行法律義務。' },
    { title: '廣告與 Cookie', body: ['未登入的訪客會看到 Google AdSense 廣告，Google 及其合作夥伴可能使用 Cookie 依您的瀏覽紀錄顯示廣告；您可以在 Google 的', { href: 'https://adssettings.google.com', text: '廣告設定' }, '中管理。登入後不載入廣告。'] },
    { title: '與第三方分享', body: '我們不會出售您的個人資料。只在提供服務所必要的範圍內，交由下列服務處理：Google（登入、流量分析、廣告）、藍新金流（付款）、Cloudflare（網站傳輸與安全）。法律要求時，我們會依法配合。' },
    { title: '保存期間', body: '帳號資料保存到您要求刪除為止；交易紀錄依稅務及相關法令要求的年限保存。' },
    { title: '您的權利', body: '依個人資料保護法，您可以查詢、閱覽、取得複本、更正、要求停止蒐集、處理或利用，以及刪除您的個人資料。請來信 contact@tinboker.com，我們會在三十日內處理。仍有有效訂閱時，請先取消訂閱再申請刪除帳號。' },
    { title: '資料安全與未成年人', body: '資料傳輸全程以 HTTPS 加密，存取受到權限控管。本服務不以未滿十八歲者為對象；未成年人使用付費功能，應先取得法定代理人同意。' },
  ],
  outro: ['對本頁內容有任何疑問，請來信 ', { href: 'mailto:contact@tinboker.com', text: 'contact@tinboker.com' }, '。客服回覆時間：週一至週五 11:00–17:00（國定及例假日除外）。'],
};

// /methodology — how every number on the site is produced. Written to be checkable:
// each statement names the thing a reader can go and look at.
export const METHODOLOGY = {
  title: '資料來源與方法',
  description: 'TinBoker 的摘要怎麼產生、看多看空怎麼判定、聲量與週報怎麼統計，以及這些數字的限制。',
  intro: 'TinBoker 做的事情只有一件：把財經 Podcast 裡「誰、在哪一天、對哪一檔股票、說了什麼」記下來，再和公開的市場資料放在一起看。這一頁說明每個步驟怎麼做，以及哪些地方會出錯。',
  sections: [
    {
      id: 'sources',
      title: '資料來源',
      items: [
        { title: '節目', body: ['目前追蹤的節目列在', { to: '/podcaster', text: '所有節目' }, '。我們只處理節目公開發布的集數，並在每一頁標明節目名稱、集數與發布日期，附上回到原節目的連結。'] },
        { title: '股價與成交資料', body: '臺股的日線、成交值與三大法人買賣超，來自臺灣證券交易所與證券櫃檯買賣中心的公開資料及 FinMind；美股報價來自授權的行情服務商。價格可能延遲，一律以交易所公告為準。' },
        { title: '產業與題材分類', body: ['個股屬於哪個產業或題材，以櫃買中心「產業價值鏈資訊平台」與證交所產業分類為骨幹，再逐檔寫下納入的理由；每個', { to: '/topics', text: '題材頁' }, '都列出成分股與理由，可以逐一檢查。'] },
      ],
    },
    {
      id: 'summary',
      title: '摘要怎麼產生',
      items: [
        { title: '逐字稿', body: '每一集先由語音辨識模型轉成逐字稿。逐字稿長度明顯短於音檔的集數會被擋下，不會進入摘要。' },
        { title: '結構化摘要', body: '大型語言模型依逐字稿整理出重點、分段章節與時間點。摘要只能使用該集實際講到的內容，章節標題附的時間可以直接跳到節目的那一段對照。' },
        { title: '摘要不是逐字引述', body: '摘要是整理與改寫，不是節目的逐字內容，也不代表主持人或來賓的完整立場。要引用請回到原節目。' },
      ],
    },
    {
      id: 'stance',
      title: '個股觀點與看多、看空',
      items: [
        { title: '一則觀點是什麼', body: '節目談到某檔個股並表達了看法時，我們記下一則觀點：日期、節目、個股、一句話的論點、提到的理由與風險，以及談的是短期、中期還是長期。只是順口提到公司名稱、沒有看法的不算。' },
        { title: '看多、中立、看空', body: '標籤反映的是「講者在那一集對這檔個股的態度」，由模型依逐字稿判定：明確看好為看多，明確看壞為看空，條件式、觀望或正反並陳為中立。這是對一段話的分類，不是 TinBoker 對這檔股票的評等。' },
        { title: '同一集、同一檔只算一次', body: '一集節目對同一檔個股不論提到幾次，都只計為一則觀點，所以「提及集數」不會因為某一集講得久而膨脹。' },
      ],
    },
    {
      id: 'stats',
      title: '統計怎麼算',
      items: [
        { title: '提及集數與多空分布', body: '個股頁的「近 30 天 N 集提及：幾看多、幾中立、幾看空」，是把那 30 天內所有節目對該檔個股的觀點逐則相加。' },
        { title: '聲量水位', body: '把某檔個股近期被提及的熱度（越近的提及權重越高），放回它自己過去一年的分布裡，看落在第幾個百分位。拿自己跟自己比，是因為大型權值股天天有人講，絕對次數高不代表現在特別熱；資料還不滿約 60 個交易日的個股不顯示水位。' },
        { title: '升溫與降溫', body: '首頁「升溫最快」與週報的排序，看的是提及次數相較前一期的變化量，不是總次數；依總次數排名每週都是同一批大型股，沒有資訊。' },
        { title: '其他節目怎麼看', body: '單集頁會列出這一集談到的個股，在該集發布前 30 天內被幾個其他節目談到、多空如何分布，以及本集的態度和其他節目相同、相反或比較保留。其他節目的提及有六成以上偏向同一邊，才算有共同方向，否則記為看法不一。這是公開說法之間的比較，不涉及股價。' },
        { title: '週報', body: ['每週一頁，統計該週所有節目談到的個股、題材與多空變化，見', { to: '/weekly', text: 'Podcast 週報' }, '。'] },
      ],
    },
    {
      id: 'limits',
      title: '限制與更正',
      items: [
        { title: '會出錯的地方', body: '語音辨識會聽錯公司名稱與數字，模型可能把反話或轉述別人的看法判成講者自己的立場，同名或簡稱相近的公司也可能配錯代號。我們持續抽查並修正，但不保證每一則都正確。' },
        { title: '提及不是推薦', body: '節目提到某檔股票，不代表節目或 TinBoker 建議買賣；被很多節目談到，也不代表之後會漲。本站所有統計都是對已發生之公開言論的整理，不預測價格。' },
        { title: '最近七天的觀點', body: '個股頁最近七天的逐則觀點為會員內容；七天以前的觀點與所有集數摘要對所有人開放。' },
        { title: '更正', body: ['發現摘要、標籤或個股配對有誤，請來信 contact@tinboker.com 並附上頁面網址，我們確認後會更正。其他說明見', { to: '/about#disclaimer', text: '免責聲明' }, '。'] },
      ],
    },
  ],
};
