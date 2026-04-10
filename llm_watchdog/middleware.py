"""ASGI / WSGI middleware for automatic LLM response monitoring."""
from __future__ import annotations

import json
import logging
from typing import Any, Callable, List, Optional

from .watcher import LlmWatchdog

logger = logging.getLogger(__name__)


def create_fastapi_middleware(watcher: LlmWatchdog, monitored_paths: Optional[List[str]] = None):
    """
    Create a Starlette/FastAPI middleware that auto-monitors LLM responses.

    Expects the request body to contain ``prompt`` and the response body
    to contain ``response`` fields (JSON).
    """
    try:
        from starlette.middleware.base import BaseHTTPMiddleware
        from starlette.requests import Request
    except ImportError as exc:
        raise ImportError("Install 'starlette' or 'fastapi' to use FastAPI middleware.") from exc

    class LlmWatchdogMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request: Request, call_next: Callable) -> Any:
            paths = monitored_paths or ["/"]
            if not any(str(request.url.path).startswith(p) for p in paths):
                return await call_next(request)

            # Read request body
            body_bytes = await request.body()
            prompt = ""
            try:
                body = json.loads(body_bytes)
                prompt = body.get("prompt", body.get("messages", ""))
                if isinstance(prompt, list):
                    prompt = " ".join(m.get("content", "") for m in prompt)
            except Exception:
                pass

            response = await call_next(request)

            # Attempt to read response body for monitoring
            response_body = b""
            async for chunk in response.body_iterator:
                response_body += chunk

            llm_response = ""
            try:
                resp_data = json.loads(response_body)
                llm_response = resp_data.get("response", resp_data.get("content", ""))
            except Exception:
                llm_response = response_body.decode("utf-8", errors="ignore")

            if prompt and llm_response:
                try:
                    await watcher.awatch(prompt, llm_response)
                except Exception as exc:
                    logger.error("Middleware watch error: %s", exc)

            from starlette.responses import Response
            return Response(
                content=response_body,
                status_code=response.status_code,
                headers=dict(response.headers),
                media_type=response.media_type,
            )

    return LlmWatchdogMiddleware


def create_flask_middleware(watcher: LlmWatchdog):
    """Create a Flask after_request hook for LLM response monitoring."""
    try:
        from flask import request as flask_request
    except ImportError as exc:
        raise ImportError("Install 'flask' to use Flask middleware.") from exc

    def after_request_hook(response: Any) -> Any:
        prompt = ""
        llm_response = ""
        try:
            data = flask_request.get_json(silent=True) or {}
            prompt = data.get("prompt", "")
            resp_data = response.get_json() or {}
            llm_response = resp_data.get("response", resp_data.get("content", ""))
        except Exception:
            pass

        if prompt and llm_response:
            try:
                watcher.watch(prompt, llm_response)
            except Exception as exc:
                logger.error("Flask middleware watch error: %s", exc)
        return response

    return after_request_hook
