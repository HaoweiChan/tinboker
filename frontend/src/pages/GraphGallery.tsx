import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Search } from 'lucide-react';
import TopStoryCard from '@/components/home/TopStoryCard';
import { SEO } from '@/components/common/SEO';
import { PageContent } from '@/components/layout/PageContent';
import { cn } from '@/lib/utils';
import { useAppStore } from '@/store/useAppStore';
import { INTERACTIVE_MODEL_LIST } from '@/data/interactiveModels';

export const GraphGallery: React.FC = () => {
  const navigate = useNavigate();
  const isDark = useAppStore((state) => state.theme === 'dark');
  const [q, setQ] = useState('');
  const [activeCategory, setActiveCategory] = useState<'all' | string>('all');

  const categories = useMemo(() => ['all', ...Array.from(new Set(INTERACTIVE_MODEL_LIST.map((m) => m.category)))], []);
  const filtered = useMemo(() => {
    const query = q.toLowerCase();
    return INTERACTIVE_MODEL_LIST.filter((m) => {
      const okCat = activeCategory === 'all' || m.category === activeCategory;
      const okQ = !query || m.title.toLowerCase().includes(query) || m.summary.toLowerCase().includes(query) || m.graphTypeLabel.toLowerCase().includes(query);
      return okCat && okQ;
    });
  }, [activeCategory, q]);

  return (
    <>
      <SEO title="探索 · 互動模型" description="TinBoker 編輯室的互動式論點與知識圖譜。" />
      <PageContent>
        <div className="mb-7">
          <p className="text-2xs uppercase tracking-[0.18em] text-muted-foreground mb-1.5">Interactive Models</p>
          <h1 className="text-2xl sm:text-3xl font-semibold tracking-[-0.02em] leading-[1.25]">探索編輯室的互動式論點</h1>
          <p className="text-sm text-muted-foreground mt-2 max-w-[60ch]">把產業關聯、供應鏈與所有權結構視覺化 — 點任一張卡片進入完整的互動圖譜。</p>
        </div>

        <div className="flex flex-col gap-3 mb-6">
          <label className="flex items-center gap-2 max-w-2xl bg-card border border-border rounded-full px-4 py-2.5">
            <Search size={15} className="text-muted-foreground shrink-0" />
            <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="搜尋互動模型…" className="flex-1 bg-transparent outline-none text-sm" />
          </label>
          <div className="flex flex-wrap gap-2">
            {categories.map((c) => (
              <button
                key={c}
                type="button"
                onClick={() => setActiveCategory(c)}
                data-active={activeCategory === c || undefined}
                className="filter-pill"
              >
                {c === 'all' ? '全部' : c}
              </button>
            ))}
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
          {filtered.map((model) => {
            const Graph = model.GraphComponent;
            return (
              <TopStoryCard
                key={model.id}
                source={model.source}
                time={model.date}
                title={model.title}
                graphTypeLabel={model.graphTypeLabel}
                isDark={isDark}
                onClick={() => navigate(`/episode/${encodeURIComponent(model.id)}`)}
              >
                <Graph isWidget />
              </TopStoryCard>
            );
          })}
          {filtered.length === 0 && (
            <div className={cn('bg-card border border-border rounded-md p-10 text-center text-sm text-muted-foreground', 'md:col-span-2')}>找不到符合「{q}」的模型。</div>
          )}
        </div>
      </PageContent>
    </>
  );
};
