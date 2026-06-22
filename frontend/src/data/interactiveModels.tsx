import React from 'react';
import LayeredGraph from '@/components/graph/visuals/LayeredGraph';
import ForceGraph from '@/components/graph/visuals/ForceGraph';
import SankeyGraph from '@/components/graph/visuals/SankeyGraph';
import TreeGraph from '@/components/graph/visuals/TreeGraph';

export interface InteractiveEntity {
  symbol: string;
  name?: string;
  price: string;
  change: string;
  isPositive: boolean;
}

export interface InteractiveModel {
  id: string;
  title: string;
  source: string;
  date: string;
  category: string;
  summary: string;
  graphTypeLabel: string;
  GraphComponent: React.ComponentType<{ isWidget?: boolean }>;
  tickers: InteractiveEntity[];
  indices: InteractiveEntity[];
  tags?: string[];
  content: React.ReactNode;
}

export const INTERACTIVE_MODELS: Record<string, InteractiveModel> = {
  'supply-chain': {
    id: 'supply-chain',
    title: 'EV Supply Chain Shakeup: New Alliances Formed in Asia',
    source: 'Bloomberg',
    date: 'September 24, 2025 • 2 hours ago',
    category: 'Supply Chain',
    summary:
      'Layered analysis revealing upstream battery suppliers, OEM dependencies, and potential choke points across Asia.',
    graphTypeLabel: 'Supply Chain Graph',
    GraphComponent: LayeredGraph,
    tickers: [
      { symbol: 'CATL', price: '185.20', change: '+1.2%', isPositive: true },
      { symbol: 'TSLA', price: '173.80', change: '-0.5%', isPositive: false },
      { symbol: 'BYD', price: '32.40', change: '+2.1%', isPositive: true },
    ],
    indices: [
      { symbol: 'Global Lithium Index', price: '452.10', change: '-1.2%', isPositive: false },
      { symbol: 'Hang Seng Tech', price: '3,890.00', change: '+0.8%', isPositive: true },
    ],
    content: (
      <>
        <p className="mb-4 text-xl leading-relaxed">
          The electric vehicle (EV) battery market is undergoing a significant structural shift as major manufacturers
          seek to diversify their supply chains away from single-source dependencies. Recent regulatory changes in the
          EU and North America have accelerated this trend, pushing automotive giants to forge new upstream alliances.
        </p>
        <p className="mb-4 text-xl leading-relaxed">
          <strong>Key Developments:</strong> Our analysis of recent procurement contracts reveals a tightening web of
          dependencies surrounding CATL and BYD. While these entities remain dominant, legacy automakers like
          Volkswagen and Ford are aggressively financing new mining operations in Australia and South America to bypass
          traditional refining bottlenecks.
        </p>
        <h3 className="text-xl font-bold mt-8 mb-4">The Layered Risk Analysis</h3>
        <p className="mb-4 text-xl leading-relaxed">
          The visualization on the right highlights the critical path nodes in the current battery supply chain. Note
          the high &quot;betweenness centrality&quot; of mid-stream refiners, which serve as potential choke points. A
          disruption in these nodes, indicated by the red warning markers in our model, could cascade downstream to
          multiple OEMs simultaneously.
        </p>
        <p className="mb-4 text-xl leading-relaxed">
          Investors should monitor the &quot;Stability Score&quot; of tier-2 suppliers, as indicated in the graph. Those
          with &apos;Stable&apos; ratings are currently undervalued relative to their strategic importance in the
          revised 2025 ecosystem.
        </p>
      </>
    ),
  },
  governance: {
    id: 'governance',
    title: 'Tech Giants: Boardroom Interlocks Reveal Strategy Alignment',
    source: 'Reuters',
    date: 'September 23, 2025 • 5 hours ago',
    category: 'Governance',
    summary: 'Force-directed ecosystem showing shared boards, major investors, and governance friction points.',
    graphTypeLabel: 'Ecosystem Cluster',
    GraphComponent: ForceGraph,
    tickers: [
      { symbol: 'TSLA', price: '173.80', change: '+3.2%', isPositive: true },
      { symbol: 'TWTR', price: '54.20', change: '0.0%', isPositive: true },
    ],
    indices: [
      { symbol: 'Nasdaq 100', price: '20,394.21', change: '-1.2%', isPositive: false },
      { symbol: 'Corp Gov ETF', price: '88.45', change: '+0.4%', isPositive: true },
    ],
    content: (
      <>
        <p className="mb-4 text-xl leading-relaxed">
          A proprietary analysis of board composition across the technology sector reveals an increasing density of
          &quot;interlocks&quot;—directors sitting on the boards of multiple competing or adjacent firms. This
          phenomenon is particularly pronounced in the AI and Space-Tech sectors.
        </p>
        <p className="mb-4 text-xl leading-relaxed">
          <strong>The Musk Ecosystem:</strong> The graph illustrates the gravitational pull of key figures like Elon
          Musk and his circle of investors. The cluster visualization demonstrates how shared board members (Ghost
          nodes) act as conduits for information flow and strategic alignment between ostensibly separate entities like
          Tesla, SpaceX, and xAI.
        </p>
        <h3 className="text-xl font-bold mt-8 mb-4">Implications for Minority Shareholders</h3>
        <p className="mb-4 text-xl leading-relaxed">
          While such ecosystems can drive rapid innovation through shared resources, they pose governance risks
          regarding conflicts of interest. The &quot;Cluster Ecosystem&quot; model provided highlights the overlap in
          venture capital backing (e.g., Sequoia, Andreessen Horowitz) which further cements these ties.
        </p>
      </>
    ),
  },
  'capital-flow': {
    id: 'capital-flow',
    title: 'Capital Flows: Where is the Smart Money Moving in Q4?',
    source: 'Financial Times',
    date: 'September 23, 2025 • 12 hours ago',
    category: 'Capital Flow',
    summary: 'Sankey flow illustrating institutional inflows and outflows across venture and private equity bets.',
    graphTypeLabel: 'Sankey Flow',
    GraphComponent: SankeyGraph,
    tickers: [
      { symbol: 'SFTBY', price: '28.50', change: '-1.5%', isPositive: false },
      { symbol: 'UBER', price: '76.40', change: '+1.2%', isPositive: true },
      { symbol: 'WE', price: '0.12', change: '-5.0%', isPositive: false },
    ],
    indices: [
      { symbol: 'Venture Index', price: '1,200.45', change: '+0.2%', isPositive: true },
      { symbol: 'Private Equity', price: '450.20', change: '-0.8%', isPositive: false },
    ],
    content: (
      <>
        <p className="mb-4 text-xl leading-relaxed">
          Institutional capital allocation has shifted dramatically in the fourth quarter, with a marked rotation out
          of late-stage gig economy platforms and into hard-tech and defense manufacturing. The Sankey diagram
          illustrates the magnitude of these flows from major aggregation funds (e.g., Softbank Vision Fund) into
          specific equities.
        </p>
        <h3 className="text-xl font-bold mt-8 mb-4">The Exit Liquidity Crisis</h3>
        <p className="mb-4 text-xl leading-relaxed">
          As observed in the flow visualization, the width of the streams connecting funds to consumer-facing apps has
          narrowed by 40% year-over-year. Conversely, flows into real estate holding companies and AI infrastructure
          have widened.
        </p>
        <p className="mb-4 text-xl leading-relaxed">
          This visualization serves as a roadmap for retail investors to understand where institutional &quot;whales&quot;
          are positioning themselves for the coming fiscal year.
        </p>
      </>
    ),
  },
  structuring: {
    id: 'structuring',
    title: 'Corporate Structuring: Siemens Spin-off Analysis',
    source: 'Wall Street Journal',
    date: 'September 22, 2025 • 1 day ago',
    category: 'Structuring',
    summary: 'Ownership tree surfacing parent-subsidiary dynamics and upcoming spin-offs at Siemens.',
    graphTypeLabel: 'Ownership Tree',
    GraphComponent: TreeGraph,
    tickers: [
      { symbol: 'SIEGY', price: '88.20', change: '+0.5%', isPositive: true },
      { symbol: 'ENR', price: '22.10', change: '+4.2%', isPositive: true },
    ],
    indices: [{ symbol: 'DAX', price: '16,400.10', change: '+0.1%', isPositive: true }],
    content: (
      <>
        <p className="mb-4 text-xl leading-relaxed">
          Conglomerates are back in the spotlight, but this time for breaking apart. The &quot;Ownership Tree&quot;
          visualization details the complex subsidiary structure of Siemens AG and its recent spin-offs. This
          hierarchical view allows investors to trace value creation (or destruction) down to the operating unit level.
        </p>
        <p className="mb-4 text-xl leading-relaxed">
          Clicking through the nodes in the interactive tree reveals that while the parent company provides stability,
          the high-growth &quot;energy&quot; and &quot;healthineers&quot; units are where the alpha is currently being
          generated.
        </p>
      </>
    ),
  },
};

export const INTERACTIVE_MODEL_LIST = Object.values(INTERACTIVE_MODELS);


