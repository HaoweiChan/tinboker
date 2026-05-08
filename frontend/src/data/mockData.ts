export interface Highlight {
  text: string;
  symbol?: string;
  type?: 'stock';
}

export interface SummaryPoint {
  text: string;
  highlights?: Highlight[];
}

export interface Episode {
  id: string;
  showName: string;
  showAvatar: string;
  showColorClass: string;
  title: string;
  timeAgo: string;
  isHot?: boolean;
  tags: string[];
  summary: SummaryPoint[];
  imageUrl?: string;
  spotifyUri?: string;
  keyInsights?: string[];
}
