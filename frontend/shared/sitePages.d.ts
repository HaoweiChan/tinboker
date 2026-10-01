export type Seg = string | { to: string; text: string } | { href: string; text: string };
export type Body = string | Seg[];
export interface Titled { title: string; body: Body }
export interface Labelled { label: string; body: string }

export const ABOUT: {
  title: string; description: string; intro: string;
  features: Titled[]; sourcesIntro: string; sources: Labelled[];
  operator: Body[];
  contactIntro: string; hours: string; email: string; line: string;
  threads: { href: string; text: string };
  disclaimerLead: string; disclaimer: Titled[]; policyLink: Seg[];
};
export const TERMS: {
  title: string; description: string; updated: string; intro: string;
  terms: Titled[]; subscription: Titled[]; refund: Titled[];
  dataCollectedTitle: string; dataCollected: Labelled[]; privacy: Titled[];
  outro: Seg[];
};
export const METHODOLOGY: {
  title: string; description: string; intro: string;
  sections: { id: string; title: string; items: Titled[] }[];
};
