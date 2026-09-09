#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The panel's files: everything it asks the server for is actually shipped.

There is no build step, so nothing checks these references until a browser
fetches one and gets a 404 - and a missing vendored library fails as a blank
page with an error in a console nobody has open. These tests are that check.
"""

from __future__ import annotations

import re

from fastapi.testclient import TestClient

from tasktracker.server import webui
from tasktracker.server.app import build

# Every absolute path the panel's own files name: `url(...)` in the stylesheet,
# src/href in the document, and the two shapes the loader is called with.
CSS_URL = re.compile(r"url\(\s*['\"]?(/[^)'\"]+)")
HTML_REF = re.compile(r"(?:src|href)=\"(/[^\"]+)\"")
VIEW_REF = re.compile(r"httpVueLoader\('(/views/[^']+)'\)")
SCREEN_REF = re.compile(r"screen\('([A-Za-z]+)'\)")


def test_the_document_asks_for_nothing_that_is_not_shipped():
    text = (webui.WWW_DIR / "index.html").read_text()
    referenced = set(HTML_REF.findall(text))
    # A page that references nothing is a page this test would pass without
    # having looked at anything.
    assert len(referenced) >= 6
    for path in referenced:
        assert (webui.WWW_DIR / path.lstrip("/")).is_file(), path


def test_the_stylesheet_asks_for_nothing_that_is_not_shipped():
    text = (webui.WWW_DIR / "css" / "main.css").read_text()
    fonts = CSS_URL.findall(text)
    assert len(fonts) == 4, "the four Montserrat faces"
    for path in fonts:
        assert (webui.WWW_DIR / path.lstrip("/")).is_file(), path


def test_every_component_and_screen_the_app_names_exists():
    text = (webui.WWW_DIR / "js" / "app.js").read_text()
    named = set(VIEW_REF.findall(text))
    named |= {f"/views/{name}.vue" for name in SCREEN_REF.findall(text)}
    assert {"/views/Board.vue", "/views/Projects.vue", "/views/Settings.vue"} <= named
    for path in named:
        assert (webui.WWW_DIR / path.lstrip("/")).is_file(), path


def test_the_panel_is_served_and_is_read_only(home):
    client = TestClient(build())
    assert client.get("/").status_code == 200
    assert client.get("/css/main.css").headers["cache-control"] == "no-cache"
    assert client.get("/views/Board.vue").status_code == 200
    # A write method against the static mount is 404, not 405: there is nothing
    # at that path to have had a wrong method for.
    assert client.post("/css/main.css").status_code == 404
