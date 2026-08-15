"""P1-E6-T01: minimal secret scan over git-tracked files.

Fails when a common secret pattern appears in tracked source/config files.
Lines containing the marker "SECRET-SCAN" are intentionally allowed
(e.g. test fixtures that simulate secrets).
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"sk-[A-Za-z0-9]{20,}"), "OpenAI-style API key"),
    (re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"), "private key block"),
    (re.compile(r"AKIA[0-9A-Z]{16}"), "AWS access key"),
    (re.compile(r"(?i)api[_-]?key\s*=\s*['\"][^'\"\n]{8,}"), "inline api key assignment"),
]

ALLOW_MARKER = "SECRET-SCAN"

# Binary/derived files that are never interesting for secrets.
SKIP_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".ico", ".woff2", ".db", ".db-wal", ".db-shm"}


def tracked_files() -> list[Path]:
    out = subprocess.run(
        ["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout
    return [ROOT / line for line in out.splitlines() if line.strip()]


def main() -> int:
    findings: list[str] = []
    for path in tracked_files():
        if path.suffix.lower() in SKIP_SUFFIXES:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for line_no, line in enumerate(text.splitlines(), start=1):
            if ALLOW_MARKER in line:
                continue
            for pattern, label in PATTERNS:
                if pattern.search(line):
                    findings.append(f"{path.relative_to(ROOT)}:{line_no} [{label}]")
                    break
    if findings:
        print("Secret scan FAILED — found potential secrets:")
        for finding in findings:
            print(f"  {finding}")
        return 1
    print("Secret scan: clean")
    return 0


if __name__ == "__main__":
    sys.exit(main())
