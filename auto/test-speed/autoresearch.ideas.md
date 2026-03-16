# Autoresearch Ideas: Test Speed

## Dead Ends (tried and failed)

## Key Insights

## Remaining Ideas
- Reduce fixture setup/teardown overhead
- Share database state across tests where safe
- Parallel test execution (pytest-xdist)
- Profile slow tests with --durations=20
- Reduce unnecessary DB migrations per test
- Mock expensive I/O operations
- Use in-memory SQLite for tests that don't need PostgreSQL features
- Reduce import time of test modules
- Lazy imports in test fixtures
