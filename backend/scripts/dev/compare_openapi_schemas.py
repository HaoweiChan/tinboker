#!/usr/bin/env python3
"""
Compare OpenAPI schemas to identify differences
"""
import json
import yaml
from pathlib import Path

def load_yaml(filepath):
    """Load YAML file"""
    with open(filepath, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)

def get_endpoints(schema):
    """Extract all endpoint paths from schema"""
    return set(schema.get('paths', {}).keys())

def get_schemas(schema):
    """Extract all component schemas"""
    return set(schema.get('components', {}).get('schemas', {}).keys())

def compare_endpoints(old_schema, new_schema):
    """Compare endpoints between schemas"""
    old_endpoints = get_endpoints(old_schema)
    new_endpoints = get_endpoints(new_schema)
    
    added = new_endpoints - old_endpoints
    removed = old_endpoints - new_endpoints
    common = old_endpoints & new_endpoints
    
    return {
        'added': sorted(added),
        'removed': sorted(removed),
        'common': sorted(common)
    }

def compare_schemas(old_schema, new_schema):
    """Compare component schemas"""
    old_schemas = get_schemas(old_schema)
    new_schemas = get_schemas(new_schema)
    
    added = new_schemas - old_schemas
    removed = old_schemas - new_schemas
    modified = []
    
    common = old_schemas & new_schemas
    for schema_name in common:
        old_def = old_schema.get('components', {}).get('schemas', {}).get(schema_name, {})
        new_def = new_schema.get('components', {}).get('schemas', {}).get(schema_name, {})
        if old_def != new_def:
            modified.append(schema_name)
    
    return {
        'added': sorted(added),
        'removed': sorted(removed),
        'modified': sorted(modified)
    }

def get_endpoint_details(schema, endpoint):
    """Get details about an endpoint"""
    path_info = schema.get('paths', {}).get(endpoint, {})
    methods = list(path_info.keys())
    return {
        'methods': methods,
        'info': path_info
    }

def main():
    base_dir = Path(__file__).parent.parent.parent
    
    old_file = base_dir / 'src/schemas/old_yamls/251214-willy.yaml'
    new_file = base_dir / 'src/schemas/openapi_current.yaml'
    
    print("="*80)
    print("OpenAPI Schema Comparison")
    print("="*80)
    print(f"Old Schema: {old_file}")
    print(f"New Schema: {new_file}")
    print("="*80)
    
    # Load schemas
    old_schema = load_yaml(old_file)
    new_schema = load_yaml(new_file)
    
    # Compare endpoints
    endpoint_diff = compare_endpoints(old_schema, new_schema)
    
    print("\n" + "="*80)
    print("ENDPOINT CHANGES")
    print("="*80)
    
    print(f"\n✅ ADDED ENDPOINTS ({len(endpoint_diff['added'])}):")
    if endpoint_diff['added']:
        for ep in endpoint_diff['added']:
            details = get_endpoint_details(new_schema, ep)
            print(f"  • {ep}")
            for method in details['methods']:
                if method.upper() != 'OPTIONS':
                    summary = details['info'].get(method, {}).get('summary', 'N/A')
                    print(f"    - {method.upper()}: {summary}")
    else:
        print("  (none)")
    
    print(f"\n❌ REMOVED ENDPOINTS ({len(endpoint_diff['removed'])}):")
    if endpoint_diff['removed']:
        for ep in endpoint_diff['removed']:
            print(f"  • {ep}")
    else:
        print("  (none)")
    
    print(f"\n📊 TOTAL ENDPOINTS:")
    print(f"  Old: {len(get_endpoints(old_schema))}")
    print(f"  New: {len(get_endpoints(new_schema))}")
    print(f"  Common: {len(endpoint_diff['common'])}")
    
    # Compare schemas
    schema_diff = compare_schemas(old_schema, new_schema)
    
    print("\n" + "="*80)
    print("SCHEMA COMPONENT CHANGES")
    print("="*80)
    
    print(f"\n✅ ADDED SCHEMAS ({len(schema_diff['added'])}):")
    if schema_diff['added']:
        for schema in schema_diff['added']:
            print(f"  • {schema}")
    else:
        print("  (none)")
    
    print(f"\n❌ REMOVED SCHEMAS ({len(schema_diff['removed'])}):")
    if schema_diff['removed']:
        for schema in schema_diff['removed']:
            print(f"  • {schema}")
    else:
        print("  (none)")
    
    print(f"\n🔄 MODIFIED SCHEMAS ({len(schema_diff['modified'])}):")
    if schema_diff['modified']:
        for schema in schema_diff['modified']:
            print(f"  • {schema}")
    else:
        print("  (none)")
    
    # Check for specific new endpoints we implemented
    print("\n" + "="*80)
    print("NEWLY IMPLEMENTED ENDPOINTS (from our implementation)")
    print("="*80)
    
    expected_new = [
        '/api/episodes/recent',
        '/api/episodes/by-ticker/{ticker}',
        '/api/stocks/{ticker}/history',
        '/api/tags',
        '/api/episodes/by-tag/{tag}',
        '/api/market/indices',
        '/api/concepts',
        '/api/top-movers'
    ]
    
    for expected in expected_new:
        if expected in endpoint_diff['added']:
            print(f"  ✅ {expected}")
        else:
            print(f"  ❌ {expected} (not found)")
    
    # Check Episode schema for tags field
    print("\n" + "="*80)
    print("EPISODE SCHEMA CHANGES")
    print("="*80)
    
    old_episode = old_schema.get('components', {}).get('schemas', {}).get('Episode', {})
    new_episode = new_schema.get('components', {}).get('schemas', {}).get('Episode', {})
    
    old_props = set(old_episode.get('properties', {}).keys())
    new_props = set(new_episode.get('properties', {}).keys())
    
    added_props = new_props - old_props
    removed_props = old_props - new_props
    
    if added_props:
        print(f"\n✅ Added properties to Episode schema:")
        for prop in added_props:
            prop_info = new_episode.get('properties', {}).get(prop, {})
            print(f"  • {prop}: {prop_info.get('type', 'N/A')} - {prop_info.get('description', 'N/A')}")
    
    if removed_props:
        print(f"\n❌ Removed properties from Episode schema:")
        for prop in removed_props:
            print(f"  • {prop}")
    
    if not added_props and not removed_props:
        print("\n  (No changes to Episode schema properties)")
    
    # Check stocks endpoint for search parameter
    print("\n" + "="*80)
    print("STOCKS ENDPOINT CHANGES")
    print("="*80)
    
    old_stocks = old_schema.get('paths', {}).get('/api/stocks', {}).get('get', {})
    new_stocks = new_schema.get('paths', {}).get('/api/stocks', {}).get('get', {})
    
    old_params = {p['name']: p for p in old_stocks.get('parameters', [])}
    new_params = {p['name']: p for p in new_stocks.get('parameters', [])}
    
    added_params = set(new_params.keys()) - set(old_params.keys())
    
    if added_params:
        print(f"\n✅ Added parameters to GET /api/stocks:")
        for param in added_params:
            param_info = new_params[param]
            print(f"  • {param}: {param_info.get('schema', {}).get('type', 'N/A')} - {param_info.get('description', 'N/A')}")
    else:
        print("\n  (No new parameters added to GET /api/stocks)")
    
    print("\n" + "="*80)
    print("Comparison Complete")
    print("="*80)

if __name__ == "__main__":
    main()


