import React from 'react';
import { Link } from 'react-router-dom';
import { SEO } from '@/components/common/SEO';
import { PageContent } from '@/components/layout/PageContent';

interface ComingSoonProps {
  /** Page name shown to the user (e.g. "節目"). */
  title: string;
  /** A short note about what's coming. */
  note?: string;
}

/** Transitional placeholder for redesigned routes that aren't built yet (Phase 4 fills these in). */
export const ComingSoon: React.FC<ComingSoonProps> = ({ title, note }) => (
  <>
    <SEO title={title} description={`TinBoker ${title}`} />
    <PageContent>
      <div className="bg-card border border-border rounded-md p-10 text-center">
        <h1 className="text-[22px] font-semibold tracking-[-0.02em] mb-2">{title}</h1>
        <p className="text-[13px] text-muted-foreground mb-6">{note ?? '這個頁面正在重新設計，很快上線。'}</p>
        <Link to="/" className="filter-pill">回首頁</Link>
      </div>
    </PageContent>
  </>
);
