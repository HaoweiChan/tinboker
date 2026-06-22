import React from 'react';
import { StockCard } from '@/components/stock/StockCard';
import { PriceChart } from '@/components/stock/PriceChart';
import { MetricsPanel } from '@/components/stock/MetricsPanel';
import { Card } from '@/components/ui';
import type { CompanyDetail } from '@/services/types';

interface CompanyOverviewPageProps {
  ticker: string;
  stockData: CompanyDetail;
}

export const CompanyOverviewPage: React.FC<CompanyOverviewPageProps> = ({
  stockData,
}) => {
  return (
    <div className="w-full max-w-xl mx-auto space-y-6">
      <Card className="w-full shadow-lg border border-border/60 bg-card/95">
        <StockCard company={stockData} />
      </Card>

      <Card className="w-full shadow-lg border border-border/60 bg-card/95 overflow-hidden p-0">
        <PriceChart data={stockData.chartData} ticker={stockData.ticker} />
      </Card>

      <Card className="w-full shadow-lg border border-border/60 bg-card/95">
        <MetricsPanel company={stockData} />
      </Card>

      <Card className="w-full shadow-lg border border-border/60 bg-card/95">
        <h3 className="text-xl font-semibold mb-3 text-foreground">
          About
        </h3>
        <p className="text-base leading-relaxed text-muted-foreground">
          {stockData.about}
        </p>
      </Card>
    </div>
  );
};

