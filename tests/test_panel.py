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


def test_the_ago_filter_names_the_right_unit():
    """The panel's "how long ago", run from app.js itself under node.

    Its unit steps were once off by one - minutes divided by 24, hours by 7 - so
    a card finished fifteen hours earlier read "1 week ago". This extracts the
    filter from app.js, runs it against a fixed clock, and checks each unit.
    """
    import json
    import shutil
    import subprocess

    import pytest

    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    source = (webui.WWW_DIR / "js" / "app.js").read_text()
    found = re.search(r"Vue\.filter\('ago', function \(value\) \{.*?\n\}\);", source, re.DOTALL)
    assert found, "the ago filter is not where this test looks for it"

    now = 1_000_000_000
    ages = {
        30: "just now",
        90: "1 minute ago",
        30 * 60: "30 minutes ago",
        15 * 3600: "15 hours ago",
        3 * 86400: "3 days ago",
        14 * 86400: "2 weeks ago",
        60 * 86400: "1 month ago",
        400 * 86400: "1 year ago",
    }
    script = (
        "var filters = {};\n"
        "var Vue = { filter: function (name, fn) { filters[name] = fn; } };\n"
        f"Date.now = function () {{ return {now * 1000}; }};\n"
        + found.group(0)
        + f"\nconsole.log(JSON.stringify({json.dumps(list(ages))}.map(function (s) {{"
        f" return filters.ago({now} - s); }})));\n"
    )
    done = subprocess.run([node, "-e", script], capture_output=True, text=True, check=True)
    assert json.loads(done.stdout) == list(ages.values())
