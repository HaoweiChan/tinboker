import React from 'react';
import { Badge } from '@/components/ui';
import type { CompanyDetail } from '@/services/types';

interface StockCardProps {
  company: CompanyDetail;
}

export const StockCard: React.FC<StockCardProps> = ({ company }) => {
  const isPositive = company.change >= 0;

  return (
    <div className="space-y-4">
      <div>
        <div className="flex items-center justify-between mb-2">
          <h2 className="text-2xl font-bold heading">{company.name}</h2>
          <span className="text-xl font-semibold text-secondary">{company.ticker}</span>
        </div>
        <div className="flex items-center space-x-3">
          <span className="text-3xl font-bold heading">
            ${company.price.toFixed(2)}
          </span>
          <Badge variant={isPositive ? 'success' : 'danger'}>
            {isPositive ? '+' : ''}
            {company.change.toFixed(2)} ({isPositive ? '+' : ''}
            {company.changePercent.toFixed(2)}%)
          </Badge>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-4 pt-4 border-t divider">
        <div>
          <div className="text-base text-secondary mb-1">Market Cap</div>
          <div className="text-xl font-semibold heading">
            ${(company.marketCap / 1e9).toFixed(2)}B
          </div>
        </div>
        {company.pe && (
          <div>
            <div className="text-base text-secondary mb-1">P/E Ratio</div>
            <div className="text-xl font-semibold heading">
              {company.pe.toFixed(2)}
            </div>
          </div>
        )}
        {company.dividendYield !== undefined && company.dividendYield > 0 && (
          <div>
            <div className="text-base text-secondary mb-1">Div Yield</div>
            <div className="text-xl font-semibold heading">
              {company.dividendYield.toFixed(2)}%
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

