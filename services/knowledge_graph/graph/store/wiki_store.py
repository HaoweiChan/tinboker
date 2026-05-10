"""Wiki-backed graph store.

Replaces Neo4j with a local JSON file (``wiki-graph/kg_store.json``) for
entity/edge/evidence storage, and writes entity pages into the shared
``wiki/`` directory for human browsing and agent crawling.

All data lives on disk — zero infrastructure cost.
"""

import json
import hashlib
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from graph.models import Edge, Entity, Evidence
from graph.store.base import GraphStore

logger = logging.getLogger(__name__)


class WikiStore(GraphStore):
    """Flat-file graph store backed by JSON + wiki markdown."""

    def __init__(self, store_path: str | None = None, wiki_root: str | None = None):
        base = Path(__file__).resolve().parents[3]
        self._store_path = Path(store_path) if store_path else base / "wiki-graph" / "kg_store.json"
        self._wiki_root = Path(wiki_root) if wiki_root else base / "wiki"
        self._store_path.parent.mkdir(parents=True, exist_ok=True)
        self._data = self._load()

    def _load(self) -> dict:
        if self._store_path.exists():
            return json.loads(self._store_path.read_text(encoding="utf-8"))
        return {"entities": {}, "edges": {}, "evidence": {}, "articles": {}, "ticker_meta": {}}

    def _save(self) -> None:
        self._store_path.write_text(
            json.dumps(self._data, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )

    # --- GraphStore interface ---

    def upsert(
        self,
        entities: list[Entity],
        edges: list[Edge],
        evidence: list[Evidence],
    ) -> None:
        for entity in entities:
            self._data["entities"][entity.id] = {
                "id": entity.id,
                "type": entity.type,
                "props": entity.props,
                "external_ids": entity.external_ids,
                "updated_at": datetime.utcnow().isoformat(),
            }
        for edge in edges:
            key = f"{edge.src}:{edge.rel}:{edge.dst}"
            self._data["edges"][key] = {
                "src": edge.src,
                "dst": edge.dst,
                "rel": edge.rel,
                "props": edge.props,
                "evidence_ids": edge.evidence_ids,
                "updated_at": datetime.utcnow().isoformat(),
            }
        for ev in evidence:
            self._data["evidence"][ev.id] = {
                "id": ev.id,
                "source": str(ev.source),
                "published_at": ev.published_at.isoformat() if ev.published_at else None,
                "snippet": ev.snippet,
                "extractor": ev.extractor,
                "confidence": ev.confidence,
                "hash": ev.hash,
                "updated_at": datetime.utcnow().isoformat(),
            }
        self._save()
        self._write_entity_pages(entities, edges)

    def _write_entity_pages(self, entities: list[Entity], edges: list[Edge]) -> None:
        """Write/update wiki entity pages from upserted graph data."""
        entities_dir = self._wiki_root / "entities"
        sc_dir = self._wiki_root / "supply-chain"
        entities_dir.mkdir(parents=True, exist_ok=True)
        sc_dir.mkdir(parents=True, exist_ok=True)

        entity_map = {e.id: e for e in entities}
        for entity in entities:
            slug = entity.id.lower().replace(" ", "-")
            name = entity.props.get("name", entity.id)
            path = entities_dir / f"{slug}.md"
            if not path.exists():
                lines = [
                    "---",
                    "type: entity",
                    f"id: {slug}",
                    f'name: "{name}"',
                    f"entity_type: {entity.type}",
                    f"tickers: [{entity.props.get('ticker', '')}]",
                    "---",
                    "",
                    f"# {name}",
                    "",
                ]
                path.write_text("\n".join(lines), encoding="utf-8")

        for edge in edges:
            src_name = entity_map.get(edge.src, Entity(id=edge.src, type="unknown")).props.get("name", edge.src)
            dst_name = entity_map.get(edge.dst, Entity(id=edge.dst, type="unknown")).props.get("name", edge.dst)
            src_slug = edge.src.lower().replace(" ", "-")
            dst_slug = edge.dst.lower().replace(" ", "-")

            sc_path = sc_dir / f"{src_slug}.md"
            existing = sc_path.read_text(encoding="utf-8") if sc_path.exists() else ""
            link = f"[[entities/{dst_slug}]]"
            if link not in existing:
                if not existing:
                    existing = (
                        f"---\ntype: supply_chain\nentity: {src_slug}\n---\n\n"
                        f"# {src_name} — Supply Chain\n\n"
                        f"## Relationships\n\n"
                    )
                status = edge.props.get("status", "active")
                existing += f"- {link} — {edge.rel} ({status})\n"
                sc_path.write_text(existing, encoding="utf-8")

    def upsert_infographic(
        self,
        entity_id: str,
        context: str,
        image_prompt: str,
        image_path: str,
        article_text: str,
        article_headline: str,
    ) -> None:
        infographics = self._data.setdefault("infographics", {})
        key = f"{entity_id}_{context.replace(' ', '_')}"
        infographics[key] = {
            "entity_id": entity_id,
            "context": context,
            "image_prompt": image_prompt,
            "image_path": image_path,
            "article_text": article_text,
            "article_headline": article_headline,
            "updated_at": datetime.utcnow().isoformat(),
        }
        self._save()

    def query(self, cypher: str, parameters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """Emulate simple Cypher queries against the JSON store.

        Only a small subset of patterns is supported — enough for the existing
        ``ArticleCache`` and ``GraphService`` callers.
        """
        params = parameters or {}
        cypher_lower = cypher.lower().strip()

        # CREATE CONSTRAINT / CREATE INDEX — no-ops
        if cypher_lower.startswith("create constraint") or cypher_lower.startswith("create index"):
            return []

        # MERGE (a:Article {url: $url}) ...
        if "article" in cypher_lower and ("merge" in cypher_lower or "match" in cypher_lower):
            return self._handle_article_query(cypher, params)

        # MATCH (t:TickerMeta ...) / MERGE (t:TickerMeta ...)
        if "tickermeta" in cypher_lower:
            return self._handle_ticker_meta_query(cypher, params)

        # count(a) — cache stats
        if "count(a)" in cypher_lower or "count(*)" in cypher_lower:
            return self._handle_count_query(cypher, params)

        # Entity-related queries
        if "entity" in cypher_lower:
            return self._handle_entity_query(cypher, params)

        logger.warning(f"WikiStore.query: unsupported Cypher pattern — returning empty. query={cypher[:80]}")
        return []

    def _handle_article_query(self, cypher: str, params: dict) -> list[dict]:
        articles = self._data.setdefault("articles", {})
        url = params.get("url", "")

        if "merge" in cypher.lower() or "set" in cypher.lower():
            article = articles.setdefault(url, {"url": url})
            for key in ["content_hash", "title", "gcs_path", "published_at", "fetched_at",
                        "ticker", "extraction_status", "processed_at", "entities_extracted",
                        "edges_extracted", "extraction_error", "failed_at", "text"]:
                alias = {"content_hash": "hash"}.get(key, key)
                if alias in params:
                    article[key] = params[alias]
                elif key in params:
                    article[key] = params[key]
            # Handle REMOVE a.text
            if "remove a.text" in cypher.lower():
                article.pop("text", None)
            self._save()
            return []

        if "return" in cypher.lower():
            if url and url in articles:
                art = articles[url]
                cutoff = params.get("cutoff")
                if cutoff and art.get("processed_at", "") <= cutoff:
                    return []
                return [{"a.url": url, **{f"a.{k}": v for k, v in art.items()}}]

            # Bulk queries (extraction_status filter)
            status = params.get("status")
            ticker = params.get("ticker")
            limit = params.get("limit", 100)
            results = []
            for art in articles.values():
                if status and art.get("extraction_status") != status:
                    continue
                if ticker and art.get("ticker") != ticker:
                    continue
                if "properties(a)" in cypher.lower():
                    results.append({"article": art})
                elif "a.extraction_status as status" in cypher.lower():
                    results.append({"status": art.get("extraction_status", "unknown"), "count": 1})
                else:
                    results.append(art)
                if len(results) >= limit:
                    break

            # Aggregate counts if needed
            if "count" in cypher.lower() and "a.extraction_status as status" in cypher.lower():
                counts: dict[str, int] = {}
                for art in articles.values():
                    s = art.get("extraction_status", "unknown")
                    counts[s] = counts.get(s, 0) + 1
                return [{"status": s, "count": c} for s, c in counts.items()]

            return results

        return []

    def _handle_ticker_meta_query(self, cypher: str, params: dict) -> list[dict]:
        meta = self._data.setdefault("ticker_meta", {})
        ticker = params.get("ticker", "")

        if "merge" in cypher.lower() or "set" in cypher.lower():
            entry = meta.setdefault(ticker, {"ticker": ticker})
            if "processed_at" in params:
                entry["last_processed_at"] = params["processed_at"]
            self._save()
            return []

        if ticker in meta:
            return [{"t.last_processed_at": meta[ticker].get("last_processed_at")}]
        return []

    def _handle_count_query(self, cypher: str, params: dict) -> list[dict]:
        articles = self._data.get("articles", {})
        cutoff = params.get("cutoff")
        if cutoff:
            count = sum(
                1 for a in articles.values()
                if a.get("processed_at", "") > cutoff
            )
            return [{"recent_articles": count}]
        return [{"total_articles": len(articles)}]

    def _handle_entity_query(self, cypher: str, params: dict) -> list[dict]:
        ticker = params.get("ticker", "")
        entities = self._data.get("entities", {})
        edges = self._data.get("edges", {})

        # Find matching entity
        matched = None
        for eid, edata in entities.items():
            if eid.lower() == ticker.lower() or edata.get("props", {}).get("name", "").lower() == ticker.lower():
                matched = edata
                break

        if not matched:
            return []

        # Collect neighbors
        result_entities = [matched]
        result_edges = []
        center_id = matched["id"]
        for key, edge in edges.items():
            if edge["src"] == center_id or edge["dst"] == center_id:
                result_edges.append(edge)
                neighbor_id = edge["dst"] if edge["src"] == center_id else edge["src"]
                if neighbor_id in entities:
                    result_entities.append(entities[neighbor_id])

        return [{"entities": result_entities, "edges": result_edges}]

    def initialize_schema(self) -> None:
        for key in ["entities", "edges", "evidence", "articles", "ticker_meta"]:
            self._data.setdefault(key, {})
        self._save()

    def get_all_entities(self) -> dict[str, dict]:
        return dict(self._data.get("entities", {}))

    def get_all_edges(self) -> dict[str, dict]:
        return dict(self._data.get("edges", {}))

    def get_all_evidence(self) -> dict[str, dict]:
        return dict(self._data.get("evidence", {}))

    def close(self) -> None:
        self._save()
