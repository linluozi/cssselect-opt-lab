#!/usr/bin/env python3
"""Benchmark the selector-translation hot path of cssselect.

Two workloads are measured, both driven by the frozen *real* selector corpus
(``benchmark/corpus/selectors.txt``) and upstream's own translators:

``spider``  A crawler keeps one selector list and applies it to every page.
            Page *i* is parsed/translated with ``GenericTranslator`` when *i*
            is even and ``HTMLTranslator`` when it is odd, so each page costs
            the full list.  This is the realistic scrapy/parsel loop.
``unique``  Every selector is translated exactly once per timed repetition and
            the parse cache is cleared first (when the implementation exposes
            one).  This is the "no reuse at all" control.

Timing uses ``time.perf_counter``; every sample is written to ``--raw-dir``.

Usage::

    python benchmark/bench.py --impl baseline  --cssselect-path /tmp/base-css \
        --scale large --mode spider --raw-dir benchmark/raw
"""

from __future__ import annotations

import argparse
import json
import pathlib
import statistics
import sys
import time

SCALES = {
    "small": {"selectors": 150, "pages": 6},
    "medium": {"selectors": 400, "pages": 12},
    "large": {"selectors": 743, "pages": 20},
}


def load_corpus(path: pathlib.Path) -> list[str]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#"):
            continue
        rows.append(line)
    return rows


def translatable(module, selectors: list[str]) -> tuple[list[str], int]:
    """Keep selectors both upstream translators accept (pseudo-elements raise)."""
    generic = module.GenericTranslator()
    html = module.HTMLTranslator()
    kept, dropped = [], 0
    for css in selectors:
        try:
            generic.css_to_xpath(css)
            html.css_to_xpath(css)
        except Exception:  # noqa: BLE001 - ExpressionError for pseudo-elements
            dropped += 1
            continue
        kept.append(css)
    return kept, dropped


def clear_cache(module) -> bool:
    fn = getattr(module, "parse", None)
    clear = getattr(fn, "cache_clear", None)
    if clear is None:
        return False
    clear()
    return True


def run_once(module, selectors: list[str], pages: int, mode: str) -> int:
    generic = module.GenericTranslator()
    html = module.HTMLTranslator()
    translations = 0
    if mode == "spider":
        for page in range(pages):
            translator = generic if page % 2 == 0 else html
            for css in selectors:
                translator.css_to_xpath(css)
                translations += 1
    else:  # unique
        for css in selectors:
            generic.css_to_xpath(css)
            translations += 1
    return translations


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--impl", required=True, choices=["baseline", "optimized"])
    ap.add_argument("--cssselect-path", required=True)
    ap.add_argument("--selector-file", default="benchmark/corpus/selectors.txt")
    ap.add_argument("--scale", required=True, choices=sorted(SCALES))
    ap.add_argument("--mode", default="spider", choices=["spider", "unique"])
    ap.add_argument("--warmup", type=int, default=3)
    ap.add_argument("--reps", type=int, default=7)
    ap.add_argument("--raw-dir", default="benchmark/raw")
    args = ap.parse_args()

    root = pathlib.Path(__file__).resolve().parent.parent
    selector_file = pathlib.Path(args.selector_file)
    if not selector_file.is_absolute():
        selector_file = root / selector_file
    selectors = load_corpus(selector_file)

    sys.path.insert(0, str(pathlib.Path(args.cssselect_path).resolve()))
    import cssselect as module  # noqa: PLC0415

    cfg = SCALES[args.scale]
    usable, dropped = translatable(module, selectors)
    subset = usable[: cfg["selectors"]]
    pages = 1 if args.mode == "unique" else cfg["pages"]

    # warmup (caches + allocator + CPU frequency)
    for _ in range(args.warmup):
        run_once(module, subset, pages, args.mode)
        clear_cache(module)

    samples: list[float] = []
    raw_dir = root / args.raw_dir
    raw_dir.mkdir(parents=True, exist_ok=True)
    per_rep: list[dict] = []
    for i in range(args.reps):
        clear_cache(module)
        t0 = time.perf_counter()
        translations = run_once(module, subset, pages, args.mode)
        elapsed = time.perf_counter() - t0
        samples.append(elapsed)
        info = None
        fn = getattr(module, "parse", None)
        if hasattr(fn, "cache_info"):
            ci = fn.cache_info()
            info = {"hits": ci.hits, "misses": ci.misses, "maxsize": ci.maxsize}
        rec = {
            "impl": args.impl,
            "scale": args.scale,
            "mode": args.mode,
            "selectors": len(subset),
            "pages": pages,
            "translations": translations,
            "rep": i,
            "seconds": elapsed,
            "seconds_per_translation": elapsed / translations,
            "cache": info,
        }
        per_rep.append(rec)
        (raw_dir / f"{args.impl}-{args.scale}-{args.mode}-{i}.json").write_text(
            json.dumps(rec, indent=2) + "\n", encoding="utf-8"
        )

    med = statistics.median(samples)
    q = statistics.quantiles(samples, n=4, method="inclusive") if len(samples) > 1 else [med]
    summary = {
        "impl": args.impl,
        "scale": args.scale,
        "mode": args.mode,
        "selectors": len(subset),
        "corpus_selectors": len(selectors),
        "pseudo_dropped": dropped,
        "pages": pages,
        "translations_per_rep": per_rep[0]["translations"],
        "reps": args.reps,
        "warmup": args.warmup,
        "median_s": med,
        "p25_s": q[0],
        "p75_s": q[-1],
        "min_s": min(samples),
        "max_s": max(samples),
        "rel_stdev": (
            statistics.stdev(samples) / med if len(samples) > 1 and med else 0.0
        ),
        "python": sys.version.split()[0],
        "file": args.cssselect_path,
    }
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
