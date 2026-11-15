#!/usr/bin/env python3
"""Freeze the real selector corpus used by this lab.

The corpus is extracted from files that ship with the upstream repository:

* ``tests/test_cssselect.py``  (Python string constants, via ``ast``)
* ``tests/test_hypothesis.py`` (Python string constants, via ``ast``)
* ``docs/index.rst``           (RST ``::`` literal blocks and ``inline literals``)

Every candidate string is kept only if the upstream parser accepts it, it is
1..120 characters long, contains no newline, and it is unique after stripping
trailing whitespace.  Order is preserved so the frozen file is reproducible.

Usage::

    python benchmark/extract_corpus.py \
        --upstream-dir /path/to/pristine/cssselect \
        --out benchmark/corpus/selectors.txt
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import pathlib
import re
import sys

RST_BLOCK = re.compile(r"::\n\n((?:[ \t]+.+\n|\n)+)")
RST_INLINE = re.compile(r"``([^`\n]+)``")


def python_strings(path: pathlib.Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    ]


def rst_strings(path: pathlib.Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    found: list[str] = []
    for block in RST_BLOCK.findall(text):
        for line in block.splitlines():
            found.append(line.strip())
    found.extend(RST_INLINE.findall(text))
    return found


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--upstream-dir", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    upstream = pathlib.Path(args.upstream_dir).resolve()
    sys.path.insert(0, str(upstream))
    from cssselect import SelectorSyntaxError, parse  # noqa: PLC0415

    candidates: list[str] = []
    for rel in ("tests/test_cssselect.py", "tests/test_hypothesis.py"):
        candidates += python_strings(upstream / rel)
    candidates += rst_strings(upstream / "docs/index.rst")

    kept: list[str] = []
    seen: set[str] = set()
    rejected = 0
    for raw in candidates:
        css = raw.strip()
        if not (1 <= len(css) <= 120) or "\n" in css or "\r" in css:
            continue
        try:
            css.encode("utf-8")
        except UnicodeEncodeError:
            continue  # lone surrogates only exist inside the test suite
        try:
            parsed = parse(css)
        except SelectorSyntaxError:
            rejected += 1
            continue
        except Exception:
            continue
        if not parsed:
            continue
        if css in seen:
            continue
        seen.add(css)
        kept.append(css)

    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256("\n".join(kept).encode("utf-8")).hexdigest()
    header = (
        "# Real CSS selectors extracted verbatim from the upstream cssselect repository\n"
        "# (tests/test_cssselect.py, tests/test_hypothesis.py, docs/index.rst).\n"
        f"# selectors: {len(kept)}  rejected_as_invalid: {rejected}  sha256: {digest}\n"
    )
    out.write_text(header + "\n".join(kept) + "\n", encoding="utf-8")
    print(f"selectors={len(kept)} rejected={rejected} sha256={digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
