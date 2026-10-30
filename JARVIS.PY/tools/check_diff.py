"""Check committed whitespace using trusted SHA values from a GitHub event."""

import json
import os
from pathlib import Path
import re
import subprocess
import sys


def revision(value):
    if not isinstance(value, str) or not re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", value):
        raise ValueError("Invalid revision")
    return value


def changed_range(event_name, event):
    if event_name == "pull_request":
        request = event["pull_request"]
        return revision(request["base"]["sha"]) + "..." + revision(request["head"]["sha"])
    if event_name == "push":
        before, after = revision(event["before"]), revision(event["after"])
        if not after.strip("0"):
            raise ValueError("Deleted branch has no tree to check")
        return (before + ".." + after) if before.strip("0") else ("origin/main..." + after)
    if event_name == "workflow_dispatch":
        return "origin/main...HEAD"
    raise ValueError("Unsupported event")


def main():
    try:
        event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text(encoding="utf-8"))
        scope = changed_range(os.environ["GITHUB_EVENT_NAME"], event)
        # Capture Git diagnostics: diff errors may quote private source lines.
        result = subprocess.run(["git", "--no-optional-locks", "diff", "--check", scope, "--"],
                                cwd=Path(__file__).resolve().parents[2],
                                capture_output=True, timeout=30)
        if result.returncode:
            print("Committed whitespace check failed; inspect the changed range locally.")
            return 1
        print("Committed whitespace check passed.")
        return 0
    except (KeyError, TypeError, ValueError, OSError, subprocess.SubprocessError):
        print("Committed whitespace check failed: event or Git data unavailable.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
