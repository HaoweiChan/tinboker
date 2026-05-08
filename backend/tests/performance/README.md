# Performance Tests

This directory contains performance and load testing scripts for the TinBoker backend.

## Running Performance Tests

```bash
# Run all performance tests
python -m pytest tests/performance/ -v

# Run specific benchmark
python tests/performance/test_search_latency.py

# Run with custom iterations
BENCHMARK_ITERATIONS=10 python tests/performance/test_search_latency.py
```

## Test Files

- `test_search_latency.py`: Search API latency benchmarks

## Performance Targets

| Endpoint | Target (p50) | Target (p99) |
|----------|--------------|--------------|
| `/api/search` | < 500ms | < 2000ms |
| `/api/search/suggest` | < 50ms | < 100ms |
