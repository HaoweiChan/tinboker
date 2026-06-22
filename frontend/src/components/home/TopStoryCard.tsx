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
        ? 'border-t border-white/15 border-b border-black/20 border-x border-white/5 bg-card/60 backdrop-blur-md hover:border-white/20 hover:bg-card/80 hover:shadow-lg hover:shadow-accent-info/10'
        : 'bg-card border-border shadow-sm hover:shadow-lg'}`}
  >
    {/* Header */}
    <div className={`p-4 border-b z-10 relative ${isDark ? 'border-white/5 bg-transparent' : 'bg-card border-border'}`}>
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <div className="w-5 h-5 rounded flex items-center justify-center text-2xs font-bold bg-muted text-foreground">
            N
          </div>
          <span className="text-xs font-bold text-foreground">{source}</span>
          <span className="text-muted-foreground/50 text-xs">•</span>
          <span className="text-xs text-muted-foreground">{time}</span>
        </div>
        <div className={`px-2 py-0.5 text-2xs font-bold uppercase tracking-wider rounded ${isDark ? 'bg-muted text-muted-foreground' : 'bg-muted text-muted-foreground'}`}>
          {graphTypeLabel}
        </div>
      </div>
      <h3 className={`text-xl font-bold leading-tight transition-colors ${isDark ? 'text-foreground group-hover:text-muted-foreground' : 'text-foreground group-hover:text-muted-foreground'}`}>
        {title}
      </h3>
    </div>

    {/* Graph Area */}
    <div className={`flex-1 relative ${isDark ? 'bg-background' : 'bg-muted'}`}>
      <div className="absolute inset-0">
        <div className="pointer-events-none h-full w-full">{children}</div>
      </div>
    </div>

    {/* Footer */}
    <div className={`px-4 py-3 border-t flex items-center justify-between ${isDark ? 'bg-transparent border-white/5' : 'bg-muted border-border'}`}>
      <div className="flex items-center gap-1 text-muted-foreground text-xs">
        <Globe size={12} />
        <span>全球影響分析</span>
      </div>
      <button className="text-xs font-semibold text-muted-foreground flex items-center gap-1 hover:gap-2 transition-all">
        深入分析 <ChevronRight size={12} />
      </button>
    </div>
  </div>
);

export default TopStoryCard;


