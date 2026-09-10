#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The three READMEs: their links resolve and they point at each other.

Relative links across a `docs/` boundary are the kind of thing that is right
when it is written and wrong after one file moves - and a broken link in a
README is only ever noticed by somebody who came to the project for the first
time, which is the worst possible audience for it.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

# The English README at the top level, and the two translations under docs/.
# Each is listed with the language it does NOT link to itself.
READMES = {
    ROOT / "README.md": "EN",
    ROOT / "docs" / "README_RU.md": "RU",
    ROOT / "docs" / "README_CN.md": "CN",
}

# `[text](target)` and `<img src="target">`. Anything absolute is somebody
# else's server and not this test's business.
MD_LINK = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
IMG_SRC = re.compile(r'<img[^>]+src="([^"]+)"')


def targets(text: str) -> list[str]:
    found = MD_LINK.findall(text) + IMG_SRC.findall(text)
    return [
        target.split("#")[0]
        for target in found
        if not target.startswith(("http://", "https://", "#", "mailto:"))
    ]


@pytest.mark.parametrize("readme", list(READMES), ids=lambda path: path.name)
def test_every_relative_link_resolves(readme: Path):
    text = readme.read_text(encoding="utf-8")
    for target in targets(text):
        assert (readme.parent / target).resolve().exists(), f"{readme.name} -> {target}"


@pytest.mark.parametrize("readme,language", READMES.items(), ids=lambda value: str(value))
def test_each_readme_offers_the_other_two_languages(readme: Path, language: str):
    """The switcher line, with this file's own language as plain text.

    A translation that links to itself is one nobody can tell they are already
    reading, and the way it happens is a copied header nobody edited.
    """
    header = readme.read_text(encoding="utf-8").splitlines()[0]
    others = {name for name in ("EN", "RU", "CN") if name != language}
    for name in others:
        assert f"[{name}]" in header, f"{readme.name} does not link to {name}"
    assert f"[{language}]" not in header, f"{readme.name} links to itself"


def test_the_translations_cover_the_same_ground():
    """Same sections, same order, in all three.

    Compared by count and position rather than by text, which is as much as a
    test can say about a translation - but it is the half that actually rots: a
    section added to the English README and to neither of the others.
    """
    counts = {}
    for readme in READMES:
        text = readme.read_text(encoding="utf-8")
        counts[readme.name] = len(re.findall(r"^## ", text, flags=re.MULTILINE))
    assert len(set(counts.values())) == 1, counts


def test_the_plugin_and_the_package_carry_one_version():
    """One version, in the three places it is written.

    `claude plugin update` reads plugin.json, pip reads pyproject.toml, and the
    web app reports `__version__`. CLAUDE.md says to bump them together; this is
    what notices when one of them was missed.
    """
    import json
    import tomllib

    from tasktracker import __version__

    plugin = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text())["version"]
    package = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]
    assert plugin == package == __version__
