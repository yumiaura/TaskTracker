#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Serving the panel's static files.

Lifted in shape from lmgateway's own `server/webui.py`, for the reasons written
into it there: the mount goes last so it cannot swallow the API's paths, a
write method answers 404 rather than 405, and everything it serves carries
`Cache-Control: no-cache` so a redeploy is not half of one version wired to half
of another.
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException
from starlette.staticfiles import StaticFiles
from starlette.types import Scope

logger = logging.getLogger(__name__)

# Shipped inside the package, so an installed wheel serves the same files a
# checkout does and there is nothing to point a path at.
WWW_DIR = Path(__file__).resolve().parent.parent / "www"

# Revalidate every time, and let the ETag make that cheap.
#
# Starlette sends `ETag` and `Last-Modified` and no `Cache-Control` at all, and
# with no explicit freshness a browser invents one - so after an edit the panel
# keeps serving the copy it already had without the request reaching this
# process. `no-cache` does not mean "do not store": the stored copy is kept and
# a conditional request answers 304 with no body, which on a loopback bind costs
# one small round trip per file.
CACHE_CONTROL = "no-cache"


class ReadOnlyStatic(StaticFiles):
    """Static files that answer a write method with 404 rather than 405."""

    async def get_response(self, path: str, scope: Scope):
        if scope["method"] not in ("GET", "HEAD"):
            raise HTTPException(status_code=404)
        response = await super().get_response(path, scope)
        # On the 304 as well as the 200: a revalidation answered without the
        # header would let the cache go back to guessing.
        response.headers["Cache-Control"] = CACHE_CONTROL
        return response


def mount(app: FastAPI, directory: Path = WWW_DIR) -> bool:
    """Mount the panel at `/`, after every API route has claimed its path.

    Order is the whole point. Starlette walks its routes in registration order
    and a mount at `/` matches every path there is, so mounting before the
    router would answer `/api/projects` out of the file system - a 404 with
    nothing in the browser to say why.

    A missing directory is reported and skipped rather than raised: the API is
    useful to the MCP server and to curl without a browser, and refusing to
    start over an absent static directory would take the board down with it.
    """
    if not directory.is_dir():
        logger.warning(
            f"the panel directory {directory} is missing - the API is served, "
            "the browser panel is not.",
        )
        return False
    app.mount("/", ReadOnlyStatic(directory=directory, html=True), name="panel")
    logger.info("panel served at /")
    return True
