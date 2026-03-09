"""Web interface for sleep scoring algorithms.

Future Feature: Web API for running sleep scoring algorithms via HTTP.
This module is a placeholder for future development.

Planned features:
    - RESTful API for algorithm execution
    - WebSocket support for real-time progress updates
    - File upload and download endpoints
    - Authentication and rate limiting
    - API documentation with OpenAPI/Swagger

Example future usage:
    ```python
    # FastAPI or Flask app
    from sleep_scoring_app.web import create_app

    app = create_app()

    # Use algorithm service (recommended):
    from sleep_scoring_app.services.algorithm_service import get_algorithm_service
    from sleep_scoring_app.core.constants import AlgorithmType

    @app.post("/api/score")
    async def score_activity(data: ActivityData):
        service = get_algorithm_service()
        algorithm = service.create_sleep_algorithm(AlgorithmType.SADEH_1994_ACTILIFE, config)
        results = algorithm.score(data.activity_counts)
        return {"scores": results}
    ```

Dependencies:
    - FastAPI or Flask for web framework
    - Core algorithms from sleep_scoring_app.core.algorithms
    - No PyQt dependencies

See: /docs/web_api_design.md (to be created)
"""

from __future__ import annotations

__all__: list[str] = []
