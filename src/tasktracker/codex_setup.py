#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Install TaskTracker's Codex hooks without replacing unrelated hooks."""

from __future__ import annotations

import argparse
import copy
import json
import os
import shlex
import stat
import sys
import tempfile
from pathlib import Path

from .codex_hook import EVENTS


def merge_hooks(document: dict, command: str) -> dict:
    """Replace only our own handlers, retaining other groups and metadata."""
    merged = copy.deepcopy(document)
    hooks = merged.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        raise ValueError("hooks must be an object")
    for event, groups in hooks.items():
        if not isinstance(groups, list):
            raise ValueError(f"hooks.{event} must be a list")
        kept = []
        for group in groups:
            if not isinstance(group, dict) or not isinstance(group.get("hooks"), list):
                raise ValueError(f"invalid group in hooks.{event}")
            handlers = group["hooks"]
            if not all(isinstance(handler, dict) for handler in handlers):
                raise ValueError(f"invalid handler in hooks.{event}")
            remaining = [
                handler
                for handler in handlers
                if not (
                    handler.get("statusMessage") == "TaskTracker"
                    and "codex-mirror.py" in str(handler.get("command", ""))
                )
            ]
            if remaining or not handlers:
                kept.append({**group, "hooks": remaining})
        hooks[event] = kept
    for event in EVENTS:
        group = {
            "hooks": [
                {
                    "type": "command",
                    "command": command,
                    "timeout": 10,
                    "statusMessage": "TaskTracker",
                }
            ]
        }
        if event == "PostToolUse":
            group["matcher"] = "^update_plan$"
        hooks.setdefault(event, []).append(group)
    return merged


def install(target: Path, wrapper: Path) -> bool:
    """Back up a changed file, then replace it atomically. Return whether changed."""
    target = target.expanduser().resolve()
    original = target.read_text(encoding="utf-8") if target.exists() else None
    document = json.loads(original) if original is not None else {}
    if not isinstance(document, dict):
        raise ValueError("the hooks file must contain a JSON object")
    if not wrapper.is_file():
        raise ValueError(f"hook script not found: {wrapper}")
    command = shlex.join([sys.executable, str(wrapper.resolve())])
    merged = merge_hooks(document, command)
    if merged == document:
        return False
    rendered = json.dumps(merged, ensure_ascii=False, indent=2) + "\n"
    target.parent.mkdir(parents=True, exist_ok=True)
    mode = stat.S_IMODE(target.stat().st_mode) if original is not None else 0o600
    if original is not None:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=target.parent,
            prefix=target.name + ".",
            suffix=".bak",
            delete=False,
        ) as backup:
            backup.write(original)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=target.parent,
        prefix=target.name + ".",
        suffix=".tmp",
        delete=False,
    ) as pending:
        staged = Path(pending.name)
        try:
            pending.write(rendered)
            pending.flush()
            os.fchmod(pending.fileno(), mode)
        except BaseException:
            staged.unlink(missing_ok=True)
            raise
    try:
        staged.replace(target)
    finally:
        staged.unlink(missing_ok=True)
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    directory = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")
    parser.add_argument("--hooks-file", type=Path, default=directory / "hooks.json")
    args = parser.parse_args(argv)
    wrapper = Path(__file__).resolve().parents[2] / "hooks" / "codex-mirror.py"
    try:
        changed = install(args.hooks_file, wrapper)
    except (OSError, ValueError) as exc:
        print(f"tasktracker: Codex hooks were not installed: {exc}", file=sys.stderr)
        return 1
    print(f"{'Installed' if changed else 'Already installed'}: {args.hooks_file.expanduser()}")
    print("Restart Codex, then review and trust the TaskTracker hooks in /hooks.")
    print("Connect the board: codex mcp add tasktracker --url http://127.0.0.1:8787/mcp")
    return 0


if __name__ == "__main__":
    sys.exit(main())
