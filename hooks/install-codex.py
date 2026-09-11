#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Install Codex hooks from this checkout (Python 3.11+, no pip needed)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from tasktracker.codex_setup import main  # noqa: E402

sys.exit(main())
