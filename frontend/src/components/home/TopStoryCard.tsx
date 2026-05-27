import React from 'react';
import { Globe, ChevronRight } from 'lucide-react';

interface TopStoryCardProps {
    source: string;
    time: string;
    title: string;
    children: React.ReactNode;
    graphTypeLabel: string;
    isDark: boolean;
    onClick: () => void;
}

const TopStoryCard: React.FC<TopStoryCardProps> = ({ 
  source, 
  time, 
  title, 
  children, 
  graphTypeLabel,
  isDark,
  onClick
}) => (
  <div 
    onClick={onClick}
    className={`rounded-xl overflow-hidden transition-all duration-300 group h-[450px] flex flex-col cursor-pointer 
      ${isDark 
        ? 'border-t border-white/15 border-b border-black/20 border-x border-white/5 bg-gradient-to-br from-slate-800/60 to-slate-900/60 backdrop-blur-md hover:border-white/20 hover:bg-slate-800/80 hover:shadow-lg hover:shadow-accent-info/10' 
        : 'bg-white border-slate-200 shadow-sm hover:shadow-lg'}`}
  >
    {/* Header */}
    <div className={`p-4 border-b z-10 relative ${isDark ? 'border-white/5 bg-transparent' : 'bg-white border-slate-100'}`}>
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <div className={`w-5 h-5 rounded flex items-center justify-center text-[10px] font-bold ${isDark ? 'bg-slate-700 text-slate-50' : 'bg-slate-900 text-white'}`}>
            N
          </div>
          <span className={`text-xs font-bold ${isDark ? 'text-slate-300' : 'text-slate-700'}`}>{source}</span>
          <span className="text-slate-300 text-xs">•</span>
          <span className="text-xs text-slate-400">{time}</span>
        </div>
        <div className={`px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider rounded ${isDark ? 'bg-[#4b4f63] text-[#c7d4f1]' : 'bg-[#edf0f8] text-[#5c6d92]'}`}>
          {graphTypeLabel}
        </div>
      </div>
      <h3 className={`text-lg font-bold leading-tight transition-colors ${isDark ? 'text-slate-50 group-hover:text-[#c7d4f1]' : 'text-slate-900 group-hover:text-[#5c6d92]'}`}>
        {title}
      </h3>
    </div>

    {/* Graph Area */}
    <div className={`flex-1 relative ${isDark ? 'bg-slate-950' : 'bg-slate-50'}`}>
      <div className="absolute inset-0">
        <div className="pointer-events-none h-full w-full">{children}</div>
      </div>
    </div>

    {/* Footer */}
    <div className={`px-4 py-3 border-t flex items-center justify-between ${isDark ? 'bg-transparent border-white/5' : 'bg-slate-50 border-slate-200'}`}>
      <div className="flex items-center gap-1 text-slate-500 text-xs">
        <Globe size={12} />
        <span>全球影響分析</span>
      </div>
      <button className="text-xs font-semibold text-[#5c6d92] flex items-center gap-1 hover:gap-2 transition-all">
        深入分析 <ChevronRight size={12} />
      </button>
    </div>
  </div>
);

export default TopStoryCard;


