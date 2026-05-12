import { useState } from 'react';
import SectorPerformance from '@/components/industry/SectorPerformance';
import TreeMap from '@/components/industry/TreeMap';
import PerformanceBarChart from '@/components/industry/PerformanceBarChart';
import { SEO } from '@/components/common/SEO';
import { PageContent } from '@/components/layout/PageContent';
import { Segmented } from '@/components/redesign';

type IndustryView = 'map' | 'bubbles' | 'rotation';

const VIEWS: Record<IndustryView, { label: string; title: string; description: string; render: () => React.ReactNode }> = {
  map: { label: '市場地圖', title: '標普 500 地圖', description: '熱力圖揭示板塊廣度與指數中的異常波動標的。', render: () => <TreeMap variant="embedded" /> },
  bubbles: { label: '板塊泡泡', title: '板塊表現散佈圖', description: '泡泡圖比較相對市值、成交量與近期報酬率。', render: () => <SectorPerformance variant="embedded" /> },
  rotation: { label: '板塊輪動', title: '表現輪動看板', description: '並排柱狀圖辨識短期與週線領漲板塊的變化。', render: () => <PerformanceBarChart variant="embedded" /> },
};

export const IndustryAnalysis: React.FC = () => {
  const [view, setView] = useState<IndustryView>('map');
  const cfg = VIEWS[view];

  return (
    <>
      <SEO title="產業 · 板塊概覽" description="標普 500 板塊地圖、泡泡圖與輪動看板。" />
      <PageContent>
        <div className="flex items-center justify-between flex-wrap gap-3 mb-[18px]">
          <h1 className="text-[22px] font-semibold tracking-[-0.02em]">產業</h1>
          <Segmented
            options={[
              { value: 'map', label: '市場地圖' },
              { value: 'bubbles', label: '板塊泡泡' },
              { value: 'rotation', label: '板塊輪動' },
            ] as const}
            value={view}
            onChange={setView}
          />
        </div>

        <div className="bg-card border border-border rounded-md flex flex-col" style={{ height: 'calc(100vh - 180px)', minHeight: 640 }}>
          <div className="px-5 sm:px-6 py-5 border-b border-border">
            <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-muted-foreground">產業 · {cfg.label}</p>
            <h2 className="text-[22px] font-semibold tracking-[-0.015em] mt-1.5">{cfg.title}</h2>
            <p className="text-[13px] text-muted-foreground mt-1.5">{cfg.description}</p>
          </div>
          <div className="flex-1 min-h-[440px] p-4">{cfg.render()}</div>
        </div>
      </PageContent>
    </>
  );
};

export default IndustryAnalysis;
