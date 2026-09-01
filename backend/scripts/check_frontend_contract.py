"""Frontend -> Backend REST contract anti-regression checker (自主迭代 09).

Scans the React frontend for every `api.<method>(<path>)` call site and asserts
each (method, path-pattern) is still exposed by the FastAPI OpenAPI spec. It
catches the P0 class of contract break found in the full-stack audit: a frontend
call pointing at a route the backend no longer serves (renamed / removed /
method changed / typo'd path).

Why a spec from `app.openapi()`: the backend is the single source of truth and
the schema is generated live from the same routers the tests exercise, so there
is zero staleness risk vs a checked-in snapshot.

Path normalization (segment-wise):
  - `${expr}` / `"..." + expr` segments become a single-segment wildcard `*`
  - OpenAPI `{param}` segments become `*`
  - query strings are dropped (they are filters, not path structure)
  - matching = same segment count AND each pair is equal or either side is `*`
  - this also covers ternary-produced segments (e.g.
    `${cond ? "approve" : "reject"}` -> `*`) and dynamic prefixes
    (EntityVersionBlock's `${base}${entityId}/versions` -> `* */versions`)

Usage:
  # pytest (CI): backend/tests/test_frontend_contract.py imports this module.
  # standalone, in-process spec (no server needed):
  uv run python scripts/check_frontend_contract.py --app
  # standalone against a running backend:
  uv run python scripts/check_frontend_contract.py --openapi-url http://127.0.0.1:17820/api/v1/openapi.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]  # repo root
FRONTEND_SRC = ROOT / "frontend" / "src"
API_PREFIX = "/api/v1"
METHODS = ("GET", "POST", "PUT", "PATCH", "DELETE")

# api.get<T>(...) / api.post(`/x/${id}`) / api.upload<...>(...)
_CALL_RE = re.compile(r"api\.(get|post|put|patch|delete|upload)\s*(?:<[^>()]*>)?\s*\(")


@dataclass(frozen=True)
class CallSite:
    file: str
    line: int
    method: str
    raw: str
    segments: tuple[str, ...]


def _read_call_arg(source: str, open_idx: int) -> str:
    """First argument of a call: text from after '(' to the first top-level
    ',' or ')', honoring quotes, backticks, ${...} and nested brackets."""
    i = open_idx + 1
    n = len(source)
    quote: str | None = None
    in_template = False
    template_depth = 0
    paren = bracket = brace = 0
    while i < n:
        ch = source[i]
        if quote:
            if ch == "\\":
                i += 2
                continue
            if ch == quote:
                quote = None
            i += 1
            continue
        if in_template:
            if template_depth == 0 and ch == "`":
                in_template = False
                i += 1
                continue
            if ch == "$" and i + 1 < n and source[i + 1] == "{":
                template_depth += 1
                i += 2
                continue
            if ch == "}" and template_depth > 0:
                template_depth -= 1
                i += 1
                continue
            i += 1
            continue
        if ch in ('"', "'", "`"):
            if ch == "`":
                in_template = True
            else:
                quote = ch
            i += 1
            continue
        if ch == "(":
            paren += 1
        elif ch == ")":
            if paren == 0:
                break
            paren -= 1
        elif ch == "[":
            bracket += 1
        elif ch == "]":
            bracket = max(0, bracket - 1)
        elif ch == "{":
            brace += 1
        elif ch == "}":
            brace = max(0, brace - 1)
        elif ch == "," and paren == 0 and bracket == 0 and brace == 0:
            break
        i += 1
    return source[open_idx + 1 : i].strip()


def _normalize_arg_to_segments(arg: str) -> list[str]:
    """Reduce a path argument to path segments; dynamic parts become '*'.

    Handles: plain/template string literals, `"a" + x + "b"` concatenation,
    `${cond ? "x" : "y"}` ternaries, and drops `?query=...` (incl. its values).
    """
    segs: list[str] = []
    query_started = False
    i = 0
    n = len(arg)

    def emit(text: str) -> None:
        nonlocal query_started
        if "?" in text:
            query_started = True
            text = text.split("?", 1)[0]
        for part in text.split("/"):
            if part:
                segs.append(part)

    while i < n:
        ch = arg[i]
        if ch in ('"', "'", "`"):
            is_tmpl = ch == "`"
            q = ch
            i += 1
            pieces: list[str] = []
            if is_tmpl:
                while i < n:
                    if arg[i] == "`":
                        i += 1
                        break
                    if arg[i] == "$" and i + 1 < n and arg[i + 1] == "{":
                        j = i + 2
                        depth = 1
                        while j < n and depth:
                            if arg[j] == "{":
                                depth += 1
                            elif arg[j] == "}":
                                depth -= 1
                            j += 1
                        emit("".join(pieces))
                        pieces = []
                        if not query_started:
                            segs.append("*")
                        i = j
                        continue
                    if not query_started:
                        pieces.append(arg[i])
                    i += 1
            else:
                while i < n and arg[i] != q:
                    if arg[i] == "\\":
                        i += 1
                    if not query_started:
                        pieces.append(arg[i])
                    i += 1
                i += 1
            emit("".join(pieces))
            continue
        if ch == "+":
            i += 1
            continue
        start = i
        while i < n and arg[i] != "+" and arg[i] not in ('"', "'", "`"):
            i += 1
        expr = arg[start:i].strip()
        if expr and not query_started:
            segs.append("*")
    return segs


def _matches(front: tuple[str, ...], openapi: tuple[str, ...]) -> bool:
    if len(front) != len(openapi):
        return False
    return all(a == b or a == "*" or b == "*" for a, b in zip(front, openapi, strict=True))


def load_openapi_ops(spec: dict) -> dict[str, set[tuple[str, ...]]]:
    """method -> set of normalized path segment-tuples (`{param}` -> `*`)."""
    ops: dict[str, set[tuple[str, ...]]] = {}
    for path, item in spec.get("paths", {}).items():
        if path.startswith(API_PREFIX):
            path = path[len(API_PREFIX) :]
        segments = []
        for part in path.split("/"):
            if not part:
                continue
            segments.append("*" if part.startswith("{") and part.endswith("}") else part)
        seg_tuple = tuple(segments)
        for method in ("get", "post", "put", "patch", "delete"):
            if method in item:
                ops.setdefault(method.upper(), set()).add(seg_tuple)
    return ops


def scan_call_sites(src_dir: Path) -> list[CallSite]:
    src_dir = src_dir.resolve()
    sites: list[CallSite] = []
    files = sorted(src_dir.rglob("*.ts")) + sorted(src_dir.rglob("*.tsx"))
    for path in files:
        if "__tests__" in path.parts or path.name.endswith((".test.ts", ".test.tsx")):
            continue
        try:
            source = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        rel = path.relative_to(ROOT).as_posix()
        for m in _CALL_RE.finditer(source):
            method = m.group(1).upper()
            if method == "UPLOAD":
                method = "POST"
            open_idx = m.end() - 1
            arg = _read_call_arg(source, open_idx)
            segments = tuple(_normalize_arg_to_segments(arg))
            if not segments:
                continue
            line = source.count("\n", 0, m.start()) + 1
            sites.append(CallSite(rel, line, method, arg, segments))
    return sites


def check_contract(spec: dict, src_dir: Path) -> tuple[list[str], list[CallSite]]:
    """Return (violations, all_call_sites). Each violation is a human-readable line."""
    ops = load_openapi_ops(spec)
    violations: list[str] = []
    sites = scan_call_sites(src_dir)
    for site in sites:
        method_ops = ops.get(site.method, set())
        if not any(_matches(site.segments, o) for o in method_ops):
            violations.append(
                f"{site.file}:{site.line}  {site.method} {site.raw}  "
                f"-> backend has no matching route (normalized /{'/'.join(site.segments)})"
            )
    return violations, sites


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--openapi-url", help="fetch spec from a running backend")
    source.add_argument("--app", action="store_true", help="build the spec in-process from app.main")
    parser.add_argument("--src", type=Path, default=FRONTEND_SRC)
    args = parser.parse_args(argv)

    if args.openapi_url:
        with urllib.request.urlopen(args.openapi_url, timeout=30) as resp:  # noqa: S310
            spec = json.load(resp)
    else:
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/
        from app.main import app

        spec = app.openapi()

    ops = load_openapi_ops(spec)
    total_ops = sum(len(v) for v in ops.values())
    violations, sites = check_contract(spec, args.src)
    print(f"scanned {len(sites)} frontend api call sites against {total_ops} backend operations")
    if violations:
        print(f"FAIL: {len(violations)} contract violation(s):")
        for v in violations:
            print("  -", v)
        return 1
    print("OK: all frontend api call sites are exposed by the backend")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
