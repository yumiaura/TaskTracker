#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The hook Claude Code runs, as three lines and a path.

The work is in `tasktracker.hook`; this file exists to find it. The package is
put on the path from the plugin's own directory rather than expected to be
installed, because the mirror is the part of this plugin that has to work the
moment it is installed and before anybody has run pip - it is standard library
only for the same reason.

An installed copy still wins: `sys.path.append` rather than `insert`, so a
`pip install -e .` in a checkout is what gets imported and the bundled source
is the fallback.
"""

import os
import sys

ROOT = os.environ.get("CLAUDE_PLUGIN_ROOT") or os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))
)
sys.path.append(os.path.join(ROOT, "src"))

try:
    from tasktracker.hook import main
except Exception as exc:  # noqa: BLE001
    # The board cannot be written to, and that is all. A hook that exits
    # non-zero here would put an import error in front of somebody's editing
    # session over a task list that was never the point of what they were doing.
    print(f"tasktracker: the plugin's own source is not importable: {exc}", file=sys.stderr)
    sys.exit(0)

sys.exit(main())
