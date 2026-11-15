#!/usr/bin/env python3
"""Differential test: memoized ``parse`` vs the original, uncached ``parse``.

The patched ``cssselect.parser.parse`` keeps the original function available as
``parse.__wrapped__`` (``functools.wraps`` sets it).  For every distinct input we
build one *signature* per arm -- cached and uncached -- containing

1. the parsed selector structures (``repr`` of every ``Selector``),
2. the XPath from ``GenericTranslator``/``HTMLTranslator.css_to_xpath`` with the
   translator-side ``parse`` name swapped to the matching arm,
3. the per-selector XPath with ``translate_pseudo_elements`` in both states.

Exceptions are part of the signature (type + message), so an invalid selector
must fail identically in both arms rather than being silently skipped.

Distinct inputs are deduplicated with sha256.  The report prints the number of
*independent* samples, never the raw loop count.  Exit code is non-zero on any
mismatch.
"""

from __future__ import annotations

import hashlib
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import cssselect  # noqa: E402
import cssselect.xpath as xpath_mod  # noqa: E402
from cssselect import parser  # noqa: E402

CACHED = parser.parse
UNCACHED = getattr(CACHED, "__wrapped__", None)

PREFIXES = ("descendant-or-self::", "self::")
EDGE_CASES = [
    "",
    " ",
    "\t",
    "a,",
    ",",
    ">",
    "a > ",
    "#",
    ".",
    "[",
    "]",
    ":::",
    "a b c d e",
    ":not()",
    ":nth-child(2n+1)",
    "a[href^='http']",
    "dÁv.lv > *",
    "*",
    "a" * 5000,
    "a" + ".b" * 500,
    "a::before",
    "a::first-line",
    "e[foo|bar]",
    "e|f",
    ":has(> a)",
    "a:nth-of-type(-0n+3)",
    "e::foo",
    "\U0001f600",  # emoji, not an identifier
]


def corpus() -> list[str]:
    text = (ROOT / "benchmark" / "corpus" / "selectors.txt").read_text(encoding="utf-8")
    return [ln for ln in text.splitlines() if ln and not ln.startswith("#")]


def digest_case(css: str, translator: str, prefix: str, pseudo: bool) -> str:
    return hashlib.sha256(
        f"{translator}|{prefix}|{int(pseudo)}|{css}".encode("utf-8")
    ).hexdigest()


def signature(css: str, translator, prefix: str, pseudo: bool, parse_fn, xpath_parse):
    try:
        selectors = parse_fn(css)
    except Exception as exc:  # noqa: BLE001
        return ("parse_error", type(exc).__name__, str(exc))

    parts: list[object] = [("selectors", tuple(repr(s) for s in selectors))]

    xpath_mod.parse = xpath_parse
    try:
        parts.append(("css_to_xpath", translator.css_to_xpath(css, prefix)))
    except Exception as exc:  # noqa: BLE001
        parts.append(("css_error", type(exc).__name__, str(exc)))

    try:
        parts.append(
            (
                "selector_to_xpath",
                tuple(
                    translator.selector_to_xpath(
                        s, prefix, translate_pseudo_elements=pseudo
                    )
                    for s in selectors
                ),
            )
        )
    except Exception as exc:  # noqa: BLE001
        parts.append(("pseudo_error", type(exc).__name__, str(exc)))
    return tuple(parts)


def run_case(css: str, translator_name: str, prefix: str, pseudo: bool):
    cls = cssselect.GenericTranslator if translator_name == "generic" else cssselect.HTMLTranslator
    translator = cls()
    cached_sig = signature(css, translator, prefix, pseudo, CACHED, CACHED)
    uncached_sig = signature(css, translator, prefix, pseudo, UNCACHED, UNCACHED)
    return cached_sig, uncached_sig


def main() -> int:
    if UNCACHED is None:
        print("FAIL: parser.parse has no __wrapped__; is the patch applied?")
        return 2

    seen: set[str] = set()
    inputs: list[tuple[str, str, str, bool]] = []
    for css in corpus() + EDGE_CASES:
        for translator in ("generic", "html"):
            for prefix in PREFIXES:
                for pseudo in (False, True):
                    key = digest_case(css, translator, prefix, pseudo)
                    if key in seen:
                        continue
                    seen.add(key)
                    inputs.append((css, translator, prefix, pseudo))

    mismatches: list[dict] = []
    for css, translator, prefix, pseudo in inputs:
        cached_sig, uncached_sig = run_case(css, translator, prefix, pseudo)
        if cached_sig != uncached_sig:
            mismatches.append(
                {
                    "case": "signature",
                    "css": css[:120],
                    "translator": translator,
                    "prefix": prefix,
                    "pseudo": pseudo,
                    "cached": repr(cached_sig)[:400],
                    "uncached": repr(uncached_sig)[:400],
                }
            )

    print(f"distinct_inputs={len(inputs)}")
    print("dedup=sha256(translator|prefix|translate_pseudo_elements|css)")
    print(f"parse_level_comparisons={len(inputs)}")
    print(f"xpath_level_comparisons={len(inputs) * 2}")
    print(f"mismatches={len(mismatches)}")
    if mismatches:
        print("first_mismatch=" + repr(mismatches[0])[:800])
        return 1
    return 0


def test_cached_matches_uncached() -> None:
    assert main() == 0


def test_cache_returns_fresh_list() -> None:
    first = CACHED("a")
    second = CACHED("a")
    assert first is not second
    first.clear()
    assert CACHED("a")  # the cached sequence itself was not mutated


if __name__ == "__main__":
    raise SystemExit(main())
