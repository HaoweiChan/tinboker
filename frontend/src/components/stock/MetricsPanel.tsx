import React from 'react';
import type { CompanyDetail } from '@/services/types';

interface MetricsPanelProps {
  company: CompanyDetail;
}

export const MetricsPanel: React.FC<MetricsPanelProps> = ({ company }) => {
  const metrics = [
    {
      label: 'Volume',
      value: (company.stats.volume / 1e6).toFixed(2) + 'M',
      description: 'Trading volume',
    },
    {
      label: 'Beta',
      value: company.stats.beta.toFixed(2),
      description: 'Market correlation',
    },
    {
      label: 'Volatility',
      value: (company.stats.volatility * 100).toFixed(1) + '%',
      description: 'Price variance',
    },
  ];

  return (
    <div className="space-y-4">
      <h3 className="text-xl font-semibold heading-text">Quantitative Metrics</h3>
      
      <div className="grid grid-cols-1 gap-4">
        {metrics.map((metric) => (
          <div
            key={metric.label}
            className="metric-card p-4 rounded-lg"
          >
            <div className="flex items-center justify-between mb-1">
              <span className="text-base text-content">{metric.label}</span>
              <span className="text-xl font-bold heading-text">{metric.value}</span>
            </div>
            <p className="text-xs metric-desc">{metric.description}</p>
          </div>
        ))}
      </div>
    </div>
  );
};

