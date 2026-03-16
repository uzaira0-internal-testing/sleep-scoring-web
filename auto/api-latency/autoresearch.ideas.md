# Autoresearch Ideas: API Latency

## Dead Ends (tried and failed)

## Key Insights

## Remaining Ideas
- Connection pooling tuning (pool_size, max_overflow, pool_pre_ping)
- Async query batching for marker/activity endpoints
- Response compression (gzip/brotli middleware)
- Eager loading vs lazy loading SQLAlchemy relationships
- Query optimization with proper indexes
- Reduce serialization overhead (orjson instead of json)
- Cache frequently-accessed study/participant metadata
- Reduce middleware stack overhead
- Profile slow queries with SLOW_QUERY_THRESHOLD_MS=0
