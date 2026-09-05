import React, { useMemo } from 'react';
import { Link } from 'react-router-dom';
import { forceCenter, forceCollide, forceLink, forceManyBody, forceSimulation, type SimulationLinkDatum, type SimulationNodeDatum } from 'd3-force';
import type { Episode as ApiEpisode } from '@/services/api';

interface CoMentionGraphProps {
  episodes: ApiEpisode[];
  /** Ticker → display name (translation map). */
  names?: Map<string, string>;
  maxNodes?: number;
}

interface Node extends SimulationNodeDatum { id: string; n: number }
interface Edge extends SimulationLinkDatum<Node> { w: number }

const W = 640, H = 360;

/** Which tickers get discussed together in this sector's episodes: nodes are tickers
 *  (sized by episode count), edges are episodes that mention both (weight >= 2 only).
 *  Layout is a one-shot d3-force run at render time — no animation, no chart library. */
export const CoMentionGraph: React.FC<CoMentionGraphProps> = ({ episodes, names, maxNodes = 24 }) => {
  const graph = useMemo(() => {
    const count = new Map<string, number>();
    const pair = new Map<string, number>();
    for (const ep of episodes) {
      const ts = [...new Set((ep.related_tickers ?? []).map((t) => t.toUpperCase()))].sort();
      for (const t of ts) count.set(t, (count.get(t) ?? 0) + 1);
      for (let i = 0; i < ts.length; i++) for (let j = i + 1; j < ts.length; j++) {
        const k = `${ts[i]}|${ts[j]}`;
        pair.set(k, (pair.get(k) ?? 0) + 1);
      }
    }
    const keep = new Set([...count.entries()].sort((a, b) => b[1] - a[1]).slice(0, maxNodes).map(([t]) => t));
    // Sector episodes mention ~13 tickers each, so nearly every pair co-occurs; keep
    // only the strongest edges (about two per node) or the graph is a hairball.
    const edges: Edge[] = [...pair.entries()]
      .map(([k, w]) => { const [s, t] = k.split('|'); return { source: s, target: t, w }; })
      .filter((e) => e.w >= 2 && keep.has(e.source as string) && keep.has(e.target as string))
      .sort((a, b) => b.w - a.w)
      .slice(0, keep.size * 2);
    const linked = new Set<string>();
    for (const e of edges) { linked.add(e.source as string); linked.add(e.target as string); }
    const nodes: Node[] = [...keep].filter((t) => linked.has(t)).map((id) => ({ id, n: count.get(id) ?? 0 }));
    if (nodes.length < 3) return null;

    const sim = forceSimulation<Node>(nodes)
      .force('link', forceLink<Node, Edge>(edges).id((d) => d.id).distance((e) => 90 - Math.min(e.w, 8) * 6))
      .force('charge', forceManyBody().strength(-260))
      .force('center', forceCenter(W / 2, H / 2))
      .force('collide', forceCollide<Node>((d) => 22 + Math.sqrt(d.n) * 3))
      .stop();
    for (let i = 0; i < 200; i++) sim.tick();
    const maxW = edges.reduce((m, e) => Math.max(m, e.w), 1);
    const maxN = nodes.reduce((m, d) => Math.max(m, d.n), 1);
    return { nodes, edges, maxW, maxN };
  }, [episodes, maxNodes]);

  if (!graph) return null;
  const { nodes, edges, maxW, maxN } = graph;
  const clamp = (v: number, lo: number, hi: number) => Math.max(lo, Math.min(hi, v));

  return (
    <div className="bg-card border border-border rounded-md p-5 mb-7">
      <h3 className="text-xs font-semibold uppercase tracking-[0.08em] text-muted-foreground mb-1">同集共同提及</h3>
      <p className="text-2xs text-muted-foreground/70 mb-3">節點大小 = 被提到的集數；連線粗細 = 同一集一起被提到的次數（至少 2 集）。</p>
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-auto" role="img" aria-label="個股共同提及網路圖">
        {edges.map((e, i) => {
          const s = e.source as Node, t = e.target as Node;
          return <line key={i} x1={s.x} y1={s.y} x2={t.x} y2={t.y} className="stroke-muted-foreground" strokeOpacity={0.2 + (e.w / maxW) * 0.5} strokeWidth={0.8 + (e.w / maxW) * 3} />;
        })}
        {nodes.map((d) => {
          const r = 4 + Math.sqrt(d.n / maxN) * 9;
          const x = clamp(d.x ?? W / 2, r + 2, W - r - 2), y = clamp(d.y ?? H / 2, r + 2, H - r - 2);
          const label = names?.get(d.id) ? `${d.id} ${names.get(d.id)}` : d.id;
          return (
            <Link key={d.id} to={`/stock/${encodeURIComponent(d.id)}`}>
              <circle cx={x} cy={y} r={r} className="fill-primary/70 hover:fill-primary transition-colors" />
              <text x={x} y={y + r + 11} textAnchor="middle" className="fill-foreground" fontSize={10} fontFamily="JetBrains Mono, monospace">{label}</text>
            </Link>
          );
        })}
      </svg>
    </div>
  );
};
