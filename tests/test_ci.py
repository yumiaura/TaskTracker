#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The GitHub Actions workflow: it tests what the project says it supports.

Read as data. The workflow cannot be run from here, but the two ways it drifts
from the project can be checked: a Python floor raised in pyproject.toml and not
in the matrix, and a check dropped from the steps.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = yaml.safe_load((ROOT / ".github" / "workflows" / "ci.yml").read_text())


def test_the_matrix_starts_at_the_python_the_package_requires():
    requires = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["requires-python"]
    floor = requires.removeprefix(">=")
    versions = WORKFLOW["jobs"]["test"]["strategy"]["matrix"]["python-version"]
    assert min(versions, key=lambda v: tuple(map(int, v.split(".")))) == floor


def test_the_workflow_runs_lint_format_and_the_suite_with_coverage():
    commands = " ".join(step.get("run", "") for step in WORKFLOW["jobs"]["test"]["steps"])
    assert "ruff check" in commands
    assert "ruff format --check" in commands
    assert "pytest --cov" in commands


def test_it_runs_on_pull_requests_and_on_main():
    # YAML 1.1 reads the bare key `on` as True.
    triggers = WORKFLOW.get("on", WORKFLOW.get(True))
    assert "pull_request" in triggers
    assert triggers["push"]["branches"] == ["main"]
