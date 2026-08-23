#!/usr/bin/env python3
"""Pre-commit hook (TASK-005): deny debug artifacts & personal tooling from being committed.

Checks the filenames of files staged for commit (from `git diff --cached --name-only`)
and fails the commit if any match repository-unrelated debug/smoke/personal patterns.

The patterns mirror `.gitignore` additions made during P0 cleanup; this is the hard
gate that stops the same class of files from silently re-entering git (e.g. via
`git add -A`).

Exit code: 0 = ok, 1 = violation found (commit blocked).
"""

from __future__ import annotations

import re
import subprocess
import sys

# Patterns matched against the basename of each staged file path (POSIX separators).
# Also block the exact known personal startup tooling scripts by directory.
DENY_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(^|/)\.plib-debug(/|$)"),
    re.compile(r"(^|/)(\.r0-smoke|\.root-smoke)(/|$)"),
    re.compile(r"[\\/]vinput-asr-dummy\.(js|py|log)$"),
    re.compile(r"[\\/]whatever\.proxy\.pac$"),
    re.compile(r"[\\/]scripts[\\/](Disable|Enable)-Startup.*\.ps1$"),
    re.compile(r"[\\/]scripts[\\/].*Startup-Restore.*\.ps1$"),
)


def _staged_files() -> list[str]:
    try:
        out = subprocess.run(
            ["git", "diff", "--cached", "--name-only", "-z"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (subprocess.CalledProcessError, OSError):
        return []
    return [f for f in out.stdout.split("\x00") if f]


def main() -> int:
    violations = [p for p in _staged_files() if any(rx.search(p) for rx in DENY_PATTERNS)]
    if not violations:
        return 0
    print("pre-commit: refusing to commit debug/personal files:")
    for path in violations:
        print(f"  - {path}")
    print("Unerase via `git rm --cached <file>` and add to .gitignore (or keep locally).")
    return 1


if __name__ == "__main__":
    sys.exit(main())