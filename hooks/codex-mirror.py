#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Run the Codex hook from this checkout, without pip or server dependencies."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

try:
    from tasktracker.codex_hook import main
except Exception as exc:  # noqa: BLE001 - a hook must not interrupt editing
    print(f"tasktracker: the Codex hook source is not importable: {exc}", file=sys.stderr)
    sys.exit(0)

sys.exit(main())
