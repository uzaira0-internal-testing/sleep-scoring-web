# Autoresearch Ideas: Startup Time

## Dead Ends (tried and failed)

## Key Insights

## Remaining Ideas
- Lazy import heavy modules (numpy, pandas if used)
- Defer database migration checks to first request
- Reduce top-level import chain depth
- Profile import time with `python -X importtime`
- Lazy-load service classes
- Move Sentry init to background task
- Reduce middleware registration overhead
- Pre-compile Pydantic models (model_rebuild)
- Check if SQLAlchemy model metadata creation is slow
- Defer router registration for rarely-used endpoints
