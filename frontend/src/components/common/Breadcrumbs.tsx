import React from 'react';
import { Link } from 'react-router-dom';
import { ChevronRight, Home } from 'lucide-react';
import { Helmet } from 'react-helmet-async';

export interface BreadcrumbItem {
  label: string;
  href?: string;
}

interface BreadcrumbsProps {
  items: BreadcrumbItem[];
  className?: string;
}

export const Breadcrumbs: React.FC<BreadcrumbsProps> = ({ items, className = '' }) => {
  // Generate JSON-LD Schema
  const structuredData = {
    '@context': 'https://schema.org',
    '@type': 'BreadcrumbList',
    'itemListElement': items.map((item, index) => ({
      '@type': 'ListItem',
      'position': index + 1,
      'name': item.label,
      'item': item.href ? `https://trendbrief.com${item.href}` : undefined
    }))
  };

  return (
    <>
      <Helmet>
        <script type="application/ld+json">
          {JSON.stringify(structuredData)}
        </script>
      </Helmet>

      <nav aria-label="Breadcrumb" className={`text-sm text-slate-500 dark:text-slate-400 min-w-0 ${className}`}>
        <ol className="flex items-center flex-nowrap gap-1 md:gap-2 min-w-0 w-full whitespace-nowrap !m-0 !p-0">
          {/* Home Link */}
          <li className="flex items-center flex-shrink-0 !m-0 !p-0">
            <Link
              to="/"
              className="hover:text-accent-info dark:hover:text-accent-info transition-colors flex items-center gap-1"
              aria-label="Home"
            >
              <Home size={14} />
              <span className="sr-only">Home</span>
            </Link>
          </li>

          {items.map((item, index) => {
            const isLast = index === items.length - 1;

            return (
              <li key={index} className={`flex items-center !m-0 !p-0 ${isLast ? 'flex-1 min-w-0' : 'flex-shrink-0'}`}>
                <ChevronRight size={14} className="text-slate-400 dark:text-slate-600 mx-1 flex-shrink-0" />
                {item.href && !isLast ? (
                  <Link
                    to={item.href}
                    className="hover:text-accent-info dark:hover:text-accent-info transition-colors font-medium"
                  >
                    {item.label}
                  </Link>
                ) : (
                  <span
                    className={`font-medium truncate block flex-1 min-w-0 ${isLast ? 'text-slate-900 dark:text-slate-200' : ''}`}
                    aria-current={isLast ? 'page' : undefined}
                    title={item.label}
                  >
                    {item.label}
                  </span>
                )}
              </li>
            );
          })}
        </ol>
      </nav>
    </>
  );
};

