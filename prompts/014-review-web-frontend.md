<objective>
Review the web application (FastAPI backend + React frontend) of the sleep-scoring-demo app for glaring issues.

Focus on security vulnerabilities, API correctness, data integrity, and frontend-backend contract mismatches. This is NOT a style review — only report issues that could cause security breaches, data loss, incorrect behavior, or crashes.
</objective>

<context>
This is a FastAPI + React web application for collaborative sleep scoring. Read `./CLAUDE.md` first for the architecture and deployment setup.

Key constraints:
- Site-wide password auth (not per-user yet)
- File uploads must be validated
- API types are generated from OpenAPI spec (`bun run generate:api-types`)
- Docker deployment via Dokploy
</context>

<research>
Thoroughly analyze these areas for glaring issues:

1. `./sleep_scoring_web/` — FastAPI backend
   - Check for missing auth on endpoints
   - Check for path traversal in file operations
   - Check for SQL injection in database queries
   - Check for missing input validation
   - Check for uncaught exceptions that leak stack traces
   - Check for CORS misconfiguration

2. `./sleep_scoring_web/api/` — API route handlers
   - Check request/response schema correctness
   - Check error handling (proper HTTP status codes)
   - Check for race conditions in concurrent file access

3. `./sleep_scoring_web/services/` — Backend services
   - Check for file system operations without proper sandboxing
   - Check for resource leaks (unclosed files, connections)

4. `./frontend/src/` — React frontend
   - Check for XSS vulnerabilities (unsafe HTML injection patterns, unescaped user content rendering)
   - Check for broken API contract (frontend types vs actual API responses)
   - Check for missing error handling on API calls
   - Check for state management issues (stale data, race conditions)

5. `./docker/` — Deployment configuration
   - Check for exposed secrets in docker-compose files
   - Check for missing health checks
   - Check for insecure default configurations

6. `./frontend/e2e/` — E2E tests
   - Check for flaky patterns
   - Check for missing critical path coverage
</research>

<requirements>
For each issue found, report:
- **Severity**: CRITICAL (security breach/data loss), HIGH (wrong behavior/crashes), MEDIUM (edge case), LOW (minor)
- **File:Line**: Exact location
- **Description**: What's wrong and why it matters
- **Evidence**: The specific code that's problematic

Only report CRITICAL and HIGH issues. Skip style, naming, and minor UI issues.
</requirements>

<output>
Save findings to: `./reviews/014-web-frontend-review.md`
</output>

<verification>
Before completing, verify:
- You read CLAUDE.md and understand the web deployment architecture
- You checked every .py file in sleep_scoring_web/
- You checked every .tsx/.ts file in frontend/src/
- Each reported issue has a specific file:line reference
- Security issues are verified (not speculative)
</verification>

<success_criteria>
- All backend endpoints reviewed for auth and input validation
- All frontend components reviewed for XSS and error handling
- Docker configuration reviewed for security
- API contract consistency verified
</success_criteria>
