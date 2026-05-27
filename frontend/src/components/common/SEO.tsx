import React from 'react';
import { Helmet } from 'react-helmet-async';

interface SEOProps {
  title?: string;
  description?: string;
  image?: string;
  url?: string;
  type?: string;
  structuredData?: Record<string, any>;
}

export const SEO: React.FC<SEOProps> = ({ 
  title, 
  description, 
  image, 
  url,
  type = 'article',
  structuredData
}) => {
  const siteTitle = '聽播客 TinBoker';
  const fullTitle = title ? `${title} | ${siteTitle}` : siteTitle;
  
  // Try to get default description from DOM (index.html), fallback to hardcoded if not found (SSR safety)
  const defaultDescription = typeof document !== 'undefined' 
    ? document.querySelector('meta[name="description"]')?.getAttribute('content') 
    : '';
    
  const metaDescription = description || defaultDescription || '';
  
  return (
    <Helmet>
      {/* Standard metadata */}
      <title>{fullTitle}</title>
      <meta name="description" content={metaDescription} />
      
      {/* Open Graph / Facebook */}
      <meta property="og:type" content={type} />
      <meta property="og:title" content={fullTitle} />
      <meta property="og:description" content={metaDescription} />
      {image && <meta property="og:image" content={image} />}
      {url && <meta property="og:url" content={url} />}
      
      {/* Twitter */}
      <meta name="twitter:card" content="summary_large_image" />
      <meta name="twitter:title" content={fullTitle} />
      <meta name="twitter:description" content={metaDescription} />
      {image && <meta name="twitter:image" content={image} />}

      {/* Canonical URL */}
      {url && <link rel="canonical" href={url} />}

      {/* Structured Data (JSON-LD) */}
      {structuredData && (
        <script type="application/ld+json">
          {JSON.stringify(structuredData)}
        </script>
      )}
    </Helmet>
  );
};

