"""Visual graph service: enriches graph structures with real financial data from StockService"""
import json
import random
from typing import Dict, List, Optional, Any
from datetime import datetime
from src.services.stock import StockService
from src.cache.redis_client import cache_get, cache_set
from src.cache.cache_config import CACHE_TTL


# ── Static graph structures ─────────────────────────────────────

_SUPPLY_CHAIN_ENTITIES = [
    {"id": "qs", "label": "QuantumScape", "ticker": "QS", "status": "Active", "layerLabel": "Tier 2: Battery"},
    {"id": "rivn", "label": "Rivian", "ticker": "RIVN", "status": "Active", "layerLabel": "Tier 2: Battery"},
    {"id": "enph", "label": "Enphase Energy", "ticker": "ENPH", "status": "Active", "layerLabel": "Tier 2: Battery"},
    {"id": "tesla", "label": "Tesla", "ticker": "TSLA", "status": "Active", "layerLabel": "OEM"},
    {"id": "ford", "label": "Ford", "ticker": "F", "status": "Stable", "layerLabel": "OEM"},
    {"id": "gm", "label": "GM", "ticker": "GM", "status": "Stable", "layerLabel": "OEM"},
]
_SUPPLY_CHAIN_EDGES = [
    {"id": "e1", "source": "qs", "target": "tesla", "animated": True},
    {"id": "e2", "source": "rivn", "target": "tesla", "animated": True},
    {"id": "e3", "source": "enph", "target": "gm", "animated": True},
    {"id": "e4", "source": "enph", "target": "ford", "animated": True},
]

_OWNERSHIP_ENTITIES = [
    {"id": "root", "label": "General Electric", "ticker": "GE", "isRoot": True, "ownership": None},
    {"id": "sub1", "label": "GE Vernova", "ticker": "GEV", "isRoot": False, "ownership": "Spin-off"},
    {"id": "sub2", "label": "GE HealthCare", "ticker": "GEHC", "isRoot": False, "ownership": "75%"},
    {"id": "child1", "label": "Varian", "ticker": None, "isRoot": False, "ownership": "100%"},
]
_OWNERSHIP_EDGES = [
    {"id": "e1", "source": "root", "target": "sub1", "label": "Spin-off"},
    {"id": "e2", "source": "root", "target": "sub2", "label": "75%"},
    {"id": "e3", "source": "sub2", "target": "child1", "label": "100%"},
]

_CLUSTER_ENTITIES = [
    {"id": "center", "label": "Tesla", "ticker": "TSLA", "group": "market_leader"},
    {"id": "c1", "label": "General Motors", "ticker": "GM", "group": "competitor"},
    {"id": "c2", "label": "Rivian", "ticker": "RIVN", "group": "competitor"},
    {"id": "c3", "label": "Lucid", "ticker": "LCID", "group": "competitor"},
    {"id": "s1", "label": "Enphase Energy", "ticker": "ENPH", "group": "partner"},
]
_CLUSTER_EDGES = [
    {"id": "e1", "source": "center", "target": "c1", "type": "default", "data": {"category": "automation"}},
    {"id": "e2", "source": "center", "target": "c2", "type": "default", "data": {"category": "automation"}},
    {"id": "e3", "source": "center", "target": "c3", "type": "default", "data": {"category": "automation"}},
    {"id": "e4", "source": "center", "target": "s1", "type": "default", "data": {"category": "automation"}},
]

_INTERACTIVE_MODELS = [
    {
        "id": "supply-chain", "title": "EV Supply Chain Shakeup", "source": "Bloomberg",
        "date": "September 24, 2025 \u2022 2 hours ago", "category": "Supply Chain",
        "summary": "Major shifts in electric vehicle supply chain relationships",
        "graphTypeLabel": "Supply Chain Graph", "graphType": "layered",
        "tickers": ["TSLA", "F", "GM"], "indices": [],
    },
    {
        "id": "ownership", "title": "Corporate Ownership Restructuring", "source": "Reuters",
        "date": "September 23, 2025 \u2022 5 hours ago", "category": "Ownership",
        "summary": "Recent corporate spin-offs and ownership changes",
        "graphTypeLabel": "Ownership Tree", "graphType": "tree",
        "tickers": ["GE", "GEV", "GEHC"], "indices": [],
    },
    {
        "id": "competition", "title": "EV Market Competition Analysis", "source": "Financial Times",
        "date": "September 22, 2025 \u2022 1 day ago", "category": "Market Analysis",
        "summary": "Competitive landscape in electric vehicle market",
        "graphTypeLabel": "Cluster Graph", "graphType": "force",
        "tickers": ["TSLA", "RIVN", "LCID"], "indices": [],
    },
]


def _build_nodes(entities: List[dict]) -> List[dict]:
    """Convert entity dicts into graph node dicts with default positions"""
    nodes = []
    for i, entity in enumerate(entities):
        data = {k: v for k, v in entity.items() if k != "id" and v is not None}
        nodes.append({"id": entity["id"], "type": "company", "data": data, "position": {"x": 0, "y": 0}})
    return nodes


def _get_supply_chain_structure() -> dict:
    return {"nodes": _build_nodes(_SUPPLY_CHAIN_ENTITIES), "edges": _SUPPLY_CHAIN_EDGES}


def _get_ownership_structure() -> dict:
    return {"nodes": _build_nodes(_OWNERSHIP_ENTITIES), "edges": _OWNERSHIP_EDGES}


def _get_cluster_structure() -> dict:
    nodes = []
    for i, entity in enumerate(_CLUSTER_ENTITIES):
        pos = {"x": 250, "y": 250} if i == 0 else {"x": random.random() * 500, "y": random.random() * 500}
        data = {k: v for k, v in entity.items() if k != "id"}
        nodes.append({"id": entity["id"], "type": "company", "data": data, "position": pos})
    return {"nodes": nodes, "edges": _CLUSTER_EDGES}


class VisualGraphService:
    """Service for visual graph operations"""
    
    def __init__(self, stock_service: Optional[StockService] = None):
        """
        Initialize visual graph service
        
        Args:
            stock_service: Optional stock service for fetching financial data
        """
        self.stock_service = stock_service or StockService()
    
    def _enrich_node_with_financials(self, node: Dict[str, Any]) -> Dict[str, Any]:
        """
        Enrich a node with real financial data from StockService
        
        Args:
            node: Node dict with basic structure
            
        Returns:
            Enriched node with financial data
        """
        ticker = node.get("data", {}).get("ticker")
        if not ticker:
            return node
        
        # Fetch real financial data
        stock_info = self.stock_service.get_stock_basic_info(ticker)
        if not stock_info:
            # If API fails, leave financial fields as None/0
            return node
        
        # Get price history for history array (sparkline)
        history = []
        try:
            # Get OHLCV data and extract close prices for history
            ohlcv_data = self.stock_service.get_ohlcv_data(ticker, limit=20)
            if ohlcv_data:
                # Get last 20 price points for history (reverse to get chronological order)
                history = [float(point.close) for point in ohlcv_data[-20:]]
        except Exception:
            pass  # If history fetch fails, leave empty
        
        # Format market cap and revenue
        market_cap_val = stock_info.get("marketCap") or 0
        revenue_val = stock_info.get("revenue") or 0
        
        # Format as string (e.g., "1.2T" or "500.5B")
        if market_cap_val >= 1_000_000_000_000:
            market_cap_str = f"{market_cap_val / 1_000_000_000_000:.2f}T"
        elif market_cap_val >= 1_000_000_000:
            market_cap_str = f"{market_cap_val / 1_000_000_000:.1f}B"
        else:
            market_cap_str = str(market_cap_val)
        
        if revenue_val >= 1_000_000_000_000:
            revenue_str = f"{revenue_val / 1_000_000_000_000:.2f}T"
        elif revenue_val >= 1_000_000_000:
            revenue_str = f"{revenue_val / 1_000_000_000:.1f}B"
        else:
            revenue_str = str(revenue_val)
        
        # Enrich node data with financial information
        node["data"].update({
            "price": stock_info.get("price"),
            "changePct": stock_info.get("changePercent") / 100 if stock_info.get("changePercent") else None,
            "marketCap": market_cap_str,
            "marketCapVal": market_cap_val,
            "revenue": revenue_str,
            "revenueVal": revenue_val,
            "history": history,
        })
        
        return node
    
    def _enrich_interactive_entity(self, ticker: str) -> Optional[Dict[str, Any]]:
        """
        Create InteractiveEntity from ticker using real stock data
        
        Args:
            ticker: Stock ticker symbol
            
        Returns:
            InteractiveEntity dict or None if not found
        """
        stock_info = self.stock_service.get_stock_basic_info(ticker)
        if not stock_info:
            return None
        
        price = stock_info.get("price") or 0.0
        change_percent = stock_info.get("changePercent") or 0.0
        is_positive = change_percent >= 0
        
        return {
            "symbol": ticker,
            "price": f"{price:.2f}",
            "change": f"{'+' if is_positive else ''}{change_percent:.2f}%",
            "isPositive": is_positive,
        }
    
    async def get_supply_chain_data(self) -> Dict[str, Any]:
        """
        Get supply chain visualization data with caching
        
        Returns:
            Dict with data and timestamp matching VisualGraphResponse format
        """
        cache_key = "visual:supply-chain"
        
        # Check cache first
        cached = await cache_get(cache_key)
        if cached:
            try:
                return json.loads(cached)
            except Exception:
                pass  # If deserialization fails, generate fresh data
        
        # Cache miss - generate visualization
        graph_structure = _get_supply_chain_structure()
        
        # Enrich nodes with real financial data (use async cached stock service)
        enriched_nodes = []
        for node in graph_structure["nodes"]:
            enriched_node = await self._enrich_node_with_financials_async(node)
            enriched_nodes.append(enriched_node)
        
        result = {
            "data": {
                "nodes": enriched_nodes,
                "edges": graph_structure["edges"],
            },
            "timestamp": datetime.utcnow().isoformat() + "Z",
        }
        
        # Store in cache
        try:
            await cache_set(
                cache_key,
                json.dumps(result, default=str),
                CACHE_TTL["visual_graph"]
            )
        except Exception:
            pass  # Cache failure shouldn't break the request
        
        return result
    
    def get_supply_chain_data_sync(self) -> Dict[str, Any]:
        """Synchronous version for backward compatibility"""
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            return loop.run_until_complete(self.get_supply_chain_data())
        except RuntimeError:
            return asyncio.run(self.get_supply_chain_data())
    
    async def get_ownership_data(self) -> Dict[str, Any]:
        """
        Get ownership tree visualization data with caching
        
        Returns:
            Dict with data and timestamp matching VisualGraphResponse format
        """
        cache_key = "visual:ownership"
        
        # Check cache first
        cached = await cache_get(cache_key)
        if cached:
            try:
                return json.loads(cached)
            except Exception:
                pass  # If deserialization fails, generate fresh data
        
        # Cache miss - generate visualization
        graph_structure = _get_ownership_structure()
        
        # Enrich nodes with real financial data
        enriched_nodes = []
        for node in graph_structure["nodes"]:
            enriched_node = await self._enrich_node_with_financials_async(node)
            enriched_nodes.append(enriched_node)
        
        result = {
            "data": {
                "nodes": enriched_nodes,
                "edges": graph_structure["edges"],
            },
            "timestamp": datetime.utcnow().isoformat() + "Z",
        }
        
        # Store in cache
        try:
            await cache_set(
                cache_key,
                json.dumps(result, default=str),
                CACHE_TTL["visual_graph"]
            )
        except Exception:
            pass  # Cache failure shouldn't break the request
        
        return result
    
    def get_ownership_data_sync(self) -> Dict[str, Any]:
        """Synchronous version for backward compatibility"""
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            return loop.run_until_complete(self.get_ownership_data())
        except RuntimeError:
            return asyncio.run(self.get_ownership_data())
    
    async def get_cluster_data(self) -> Dict[str, Any]:
        """
        Get cluster visualization data with caching
        
        Returns:
            Dict with data and timestamp matching VisualGraphResponse format
        """
        cache_key = "visual:cluster"
        
        # Check cache first
        cached = await cache_get(cache_key)
        if cached:
            try:
                return json.loads(cached)
            except Exception:
                pass  # If deserialization fails, generate fresh data
        
        # Cache miss - generate visualization
        graph_structure = _get_cluster_structure()
        
        # Enrich nodes with real financial data
        enriched_nodes = []
        for node in graph_structure["nodes"]:
            enriched_node = await self._enrich_node_with_financials_async(node)
            enriched_nodes.append(enriched_node)
        
        result = {
            "data": {
                "nodes": enriched_nodes,
                "edges": graph_structure["edges"],
            },
            "timestamp": datetime.utcnow().isoformat() + "Z",
        }
        
        # Store in cache
        try:
            await cache_set(
                cache_key,
                json.dumps(result, default=str),
                CACHE_TTL["visual_graph"]
            )
        except Exception:
            pass  # Cache failure shouldn't break the request
        
        return result
    
    def get_cluster_data_sync(self) -> Dict[str, Any]:
        """Synchronous version for backward compatibility"""
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            return loop.run_until_complete(self.get_cluster_data())
        except RuntimeError:
            return asyncio.run(self.get_cluster_data())
    
    async def get_interactive_models(self) -> Dict[str, Any]:
        """
        Get interactive models data with caching
        
        Returns:
            Dict with data and timestamp matching InteractiveModelsResponse format
        """
        cache_key = "visual:interactive-models"
        
        # Check cache first
        cached = await cache_get(cache_key)
        if cached:
            try:
                return json.loads(cached)
            except Exception:
                pass  # If deserialization fails, generate fresh data
        
        # Cache miss - generate data
        models = list(_INTERACTIVE_MODELS)
        
        # Enrich each model with real ticker data (use async cached stock service)
        enriched_models = []
        for model in models:
            # Enrich tickers
            enriched_tickers = []
            for ticker in model.get("tickers", []):
                entity = await self._enrich_interactive_entity_async(ticker)
                if entity:
                    enriched_tickers.append(entity)
            
            # Enrich indices (if any)
            enriched_indices = []
            for index in model.get("indices", []):
                entity = await self._enrich_interactive_entity_async(index)
                if entity:
                    enriched_indices.append(entity)
            
            enriched_model = {
                **model,
                "tickers": enriched_tickers,
                "indices": enriched_indices,
            }
            enriched_models.append(enriched_model)
        
        result = {
            "data": enriched_models,
            "timestamp": datetime.utcnow().isoformat() + "Z",
        }
        
        # Store in cache
        try:
            await cache_set(
                cache_key,
                json.dumps(result, default=str),
                CACHE_TTL["visual_graph"]
            )
        except Exception:
            pass  # Cache failure shouldn't break the request
        
        return result
    
    def get_interactive_models_sync(self) -> Dict[str, Any]:
        """Synchronous version for backward compatibility"""
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            return loop.run_until_complete(self.get_interactive_models())
        except RuntimeError:
            return asyncio.run(self.get_interactive_models())
    
    async def _enrich_node_with_financials_async(self, node: Dict[str, Any]) -> Dict[str, Any]:
        """
        Async version of _enrich_node_with_financials using cached stock service
        """
        ticker = node.get("data", {}).get("ticker")
        if not ticker:
            return node
        
        # Fetch real financial data using async cached method
        stock_info = await self.stock_service.get_stock_basic_info_async(ticker)
        if not stock_info:
            return node
        
        # Get price history for history array (sparkline)
        history = []
        try:
            # Get OHLCV data and extract close prices for history
            ohlcv_data = self.stock_service.get_ohlcv_data(ticker, limit=20)
            if ohlcv_data:
                history = [float(point.close) for point in ohlcv_data[-20:]]
        except Exception:
            pass
        
        # Format market cap and revenue
        market_cap_val = stock_info.get("marketCap") or 0
        revenue_val = stock_info.get("revenue") or 0
        
        if market_cap_val >= 1_000_000_000_000:
            market_cap_str = f"{market_cap_val / 1_000_000_000_000:.2f}T"
        elif market_cap_val >= 1_000_000_000:
            market_cap_str = f"{market_cap_val / 1_000_000_000:.1f}B"
        else:
            market_cap_str = str(market_cap_val)
        
        if revenue_val >= 1_000_000_000_000:
            revenue_str = f"{revenue_val / 1_000_000_000_000:.2f}T"
        elif revenue_val >= 1_000_000_000:
            revenue_str = f"{revenue_val / 1_000_000_000:.1f}B"
        else:
            revenue_str = str(revenue_val)
        
        # Enrich node data
        node["data"].update({
            "price": stock_info.get("price"),
            "changePct": stock_info.get("changePercent") / 100 if stock_info.get("changePercent") else None,
            "marketCap": market_cap_str,
            "marketCapVal": market_cap_val,
            "revenue": revenue_str,
            "revenueVal": revenue_val,
            "history": history,
        })
        
        return node
    
    async def _enrich_interactive_entity_async(self, ticker: str) -> Optional[Dict[str, Any]]:
        """
        Async version of _enrich_interactive_entity using cached stock service
        """
        stock_info = await self.stock_service.get_stock_basic_info_async(ticker)
        if not stock_info:
            return None
        
        price = stock_info.get("price") or 0.0
        change_percent = stock_info.get("changePercent") or 0.0
        is_positive = change_percent >= 0
        
        return {
            "symbol": ticker,
            "price": f"{price:.2f}",
            "change": f"{'+' if is_positive else ''}{change_percent:.2f}%",
            "isPositive": is_positive,
        }

