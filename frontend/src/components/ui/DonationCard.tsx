import React from 'react';

export const DonationCard: React.FC = () => {
    const donateUrl = 'https://portaly.cc/trendbrief/support';

    return (
        <div className="mt-12 pt-8 border-t border-slate-200 dark:border-slate-800">
            <div className="flex flex-col sm:flex-row items-center justify-between gap-4 px-1">
                <div className="text-center sm:text-left">
                    <div className="flex items-center justify-center sm:justify-start gap-2 mb-1">
                        <span className="text-sm font-bold text-slate-700 dark:text-slate-200">
                            喜歡這篇摘要嗎？
                        </span>
                    </div>
                    <p className="text-xs text-slate-500 dark:text-slate-400">
                        TinBoker 致力於為您精煉投資觀點。如果內容對您有幫助，歡迎小額贊助支持我們持續營運！
                    </p>
                </div>

                <a 
                    href={donateUrl}
                    target="_blank" 
                    rel="noopener noreferrer"
                    className="shrink-0 inline-flex items-center gap-2 bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 hover:border-accent-info dark:hover:border-accent-info text-slate-700 dark:text-slate-300 hover:text-accent-info dark:hover:text-accent-info text-xs font-bold py-2 px-5 rounded-full transition-all shadow-sm hover:shadow-md"
                >
                    <span className="text-red-500">♥</span> 
                    <span>贊助支持</span>
                </a>
            </div>
        </div>
    );
};
