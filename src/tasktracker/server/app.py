#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The FastAPI application: the API router, then the panel's files."""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from .. import __version__
from . import routes_api, webui

logger = logging.getLogger(__name__)


def envelope(message: str) -> dict[str, dict[str, str]]:
    """The one shape every failure leaves this application in.

    `{"error": {"message": …}}`, for the reason lmgateway's admin API settled
    on the same thing: seven screens each unwrapping a different envelope means
    the same 403 reads as a sentence on one and as raw JSON on the next, and
    anything an operator has to parse by eye is a message they learn to skip.
    """
    return {"error": {"message": message}}


def sentence(detail: object) -> str:
    """A validation failure, as one line rather than as a list of dictionaries.

    FastAPI answers a body it could not validate with a list of failures, each
    naming a location and a message. Rendered verbatim in a toast that is four
    lines of JSON; rendered here it is "done_hide_days: Input should be greater
    than or equal to 0", which says what to type instead.
    """
    if isinstance(detail, str):
        return detail
    if isinstance(detail, dict):
        inner = detail.get("error")
        if isinstance(inner, dict) and inner.get("message"):
            return str(inner["message"])
        return str(detail.get("msg") or detail)
    if isinstance(detail, list):
        parts = []
        for item in detail:
            if not isinstance(item, dict):
                parts.append(str(item))
                continue
            where = ".".join(str(bit) for bit in item.get("loc", []) if bit != "body")
            what = item.get("msg") or item.get("type") or "is not valid"
            parts.append(f"{where}: {what}" if where else str(what))
        return "; ".join(parts)
    return str(detail)


def build() -> FastAPI:
    app = FastAPI(
        title="TaskTracker",
        version=__version__,
        # No interactive docs on a board with no authentication. There is
        # nothing secret behind them, but they are three more routes at the root
        # of a mount that has to stay predictable, and the API is nine endpoints
        # described in the README.
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )

    @app.exception_handler(StarletteHTTPException)
    async def http_failure(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        """Every raised failure, in the envelope.

        Registered for Starlette's exception rather than FastAPI's subclass so
        it also catches the 404 the static mount raises for a file that is not
        there - which is the failure the panel meets most often, and the one
        FastAPI would otherwise answer as `{"detail": "Not Found"}`.
        """
        return JSONResponse(envelope(sentence(exc.detail)), status_code=exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def bad_body(request: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(envelope(sentence(exc.errors())), status_code=422)

    app.include_router(routes_api.router)
    # Last, and it matters: a mount at `/` matches every path there is, so
    # registering it before the router would answer /api/projects out of the
    # file system - a 404 with nothing in the browser to say why.
    webui.mount(app)
    return app
