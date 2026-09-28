import React from 'react';

/** Card-style page section: anchor id (for hash deep links), title, body.
 *  Shared by About.tsx and TermsPage.tsx. */
export function Section({ id, title, children }: { id: string; title: string; children: React.ReactNode }) {
  return (
    <section id={id} className="bg-card border border-border rounded-md p-5 sm:p-6 scroll-mt-24">
      <h2 className="heading-accent text-lg font-semibold text-foreground mb-4">{title}</h2>
      <div className="text-base leading-[1.65] text-muted-foreground space-y-4">{children}</div>
    </section>
  );
}
