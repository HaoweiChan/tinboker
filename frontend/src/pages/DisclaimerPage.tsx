import React from 'react';
import { Card, CardContent } from '@/components/ui';
import { ShieldAlert } from 'lucide-react';

export const DisclaimerPage: React.FC = () => {
  return (
    <div className="min-h-screen flex flex-col bg-slate-50 dark:bg-slate-950 transition-colors duration-300">

      <main className="flex-1 py-12 md:py-20 relative z-0">
        <div className="container mx-auto max-w-3xl px-4">
          <div className="text-center mb-8">
            <div className="w-16 h-16 bg-accent-info-soft dark:bg-accent-info/20 rounded-full flex items-center justify-center mx-auto mb-6">
              <ShieldAlert size={32} className="text-accent-info dark:text-accent-info" />
            </div>
            <h1 className="text-3xl font-bold text-slate-900 dark:text-slate-50 mb-2">免責聲明</h1>
            <p className="text-slate-500 dark:text-slate-400">
              請在使用本服務前仔細閱讀以下條款
            </p>
          </div>
          
          <Card className="border-none shadow-sm bg-white dark:bg-slate-900">
            <CardContent className="p-8 md:p-12 space-y-8">
              <div className="space-y-4">
                <p className="text-lg text-slate-700 dark:text-slate-300 leading-relaxed font-medium">
                  本網站（TinBoker）所提供之所有資訊、數據、觀點與分析，僅供參考與學習用途，不構成任何形式的投資建議、要約、誘導或推薦。
                </p>
              </div>

              <div className="space-y-6">
                <section>
                  <h3 className="text-xl font-bold text-slate-900 dark:text-slate-50 mb-3 flex items-center gap-2">
                    <span className="w-1.5 h-6 bg-accent-info rounded-full"></span>
                    資訊來源與準確性
                  </h3>
                  <p className="text-slate-600 dark:text-slate-400 leading-relaxed">
                    本服務內容整理自公開資訊、各大財經 Podcast 及市場數據。雖然我們盡力確保資訊的準確性與可靠性，但無法保證其完整性、即時性或絕對正確性。市場資訊瞬息萬變，所有數據以來源機構之最終公告為準。
                  </p>
                </section>

                <section>
                  <h3 className="text-xl font-bold text-slate-900 dark:text-slate-50 mb-3 flex items-center gap-2">
                    <span className="w-1.5 h-6 bg-accent-info rounded-full"></span>
                    投資風險告知
                  </h3>
                  <p className="text-slate-600 dark:text-slate-400 leading-relaxed">
                    金融市場具有高度風險，投資涉及盈虧，過去的績效不代表未來的表現。使用者在做出任何投資決策前，應審慎評估自身風險承受能力、投資目標及財務狀況，並建議諮詢合格的專業財務顧問。
                  </p>
                </section>

                <section>
                  <h3 className="text-xl font-bold text-slate-900 dark:text-slate-50 mb-3 flex items-center gap-2">
                    <span className="w-1.5 h-6 bg-accent-info rounded-full"></span>
                    責任限制
                  </h3>
                  <p className="text-slate-600 dark:text-slate-400 leading-relaxed">
                    TinBoker 團隊不對因使用、引用或依賴本網站資訊而產生的任何直接、間接、附帶或衍生之損失負責。使用者應自行承擔所有投資決策之風險與後果。
                  </p>
                </section>

                <div className="pt-8 border-t border-slate-100 dark:border-slate-800 text-sm text-slate-500 dark:text-slate-500 text-center">
                  最後更新日期：{new Date().getFullYear()} 年 {new Date().getMonth() + 1} 月
                </div>
              </div>
            </CardContent>
          </Card>
        </div>
      </main>

    </div>
  );
};

export default DisclaimerPage;

