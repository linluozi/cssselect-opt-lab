# cssselect-opt-lab

Memoizes `cssselect.parser.parse` behind a bounded cache so that a crawler which
reuses the same selector list on every page translates each selector only once.
The change is 22 inserted lines, no deletions, in `cssselect/parser.py`.
`cssselect` is the CSS-selector parser + CSS→XPath translator used by
Scrapy/parsel; `parse()` is 73.8% of the cumtime of a `GenericTranslator.css_to_xpath`
call (cProfile, see `benchmark/`).

Upstream: https://github.com/scrapy/cssselect

## What changed

`parse(css)` is a pure function of the selector string, but every
`css_to_xpath()` call re-tokenizes and re-parses the selector. The patch wraps
`parse` in a helper that runs `functools.lru_cache(maxsize=4096)` internally and
returns `list(cached(css))`, so callers still get a **fresh list** per call (a
plain `lru_cache` would hand out the same mutable list). No public signature,
return value, or upstream test file is touched. The decorator body, the fast
paths, and the error behaviour are unchanged.

## Result (median of 7 timed reps, 3 warmups; raw samples in `benchmark/raw/`)

`spider` = a crawler applies one fixed selector list to every page, alternating
`GenericTranslator`/`HTMLTranslator`. `unique` = each selector translated once
with the cache cleared before every rep (the no-reuse control).

| scale | selectors × pages | baseline median | optimized median | speedup (spider) |
| --- | --- | --- | --- | --- |
| small | 150 × 6 | 26.03 ms | 9.04 ms | **2.879x** |
| medium | 400 × 12 | 164.47 ms | 44.35 ms | **3.709x** |
| large | 743 × 20 | 474.59 ms | 121.22 ms | **3.915x** |

| scale | selectors × pages | baseline median | optimized median | speedup (unique, no reuse) |
| --- | --- | --- | --- | --- |
| small | 150 × 1 | 4.39 ms | 4.42 ms | 0.994x |
| medium | 400 × 1 | 13.55 ms | 13.76 ms | 0.985x |
| large | 743 × 1 | 23.53 ms | 24.47 ms | 0.962x |

**Honest reading.** The gain is exactly selector reuse: with zero reuse the
wrapper costs 0.6–3.8% (lru_cache lookup + list copy) and buys nothing. A
crawler reusing its selector list per page (the scrapy/parsel case) is the only
condition where this pays. Both rows are from the same real corpus and the same
command; the synthetic part is only how many pages are replayed.

## 本轮创新

B 档：把「selector 复用」立成 cssselect 性能的第一等测量变量，并给出**冷/热两侧的交叉证据**。
与既有 `httpx`/`slugify` 一类"上游已缓存"结论不同，这里首次量化了 cssselect 的
`parse` 占 `css_to_xpath` cumtime 73.8%、并证明收益是 **per-selector reuse 的阶跃**
（复用 6/12/20 页 = 2.88x/3.71x/3.92x），而不做复用反而 0.96–0.99x。
台账无同题条目；同一补丁在 v1.3.0–v1.6.0 四个发布版本上重放（见
`benchmark/version_matrix.json`），是本轮新增的跨版本证据。

## Gates (each with its reproducible command)

| gate | result | command |
| --- | --- | --- |
| G1 upstream tests green | 46 passed, 1 xfailed, 81 subtests (patched HEAD, 2.82 s) | `python -m pytest cssselect tests docs -q -p no:cacheprovider` |
| G2 differential | **6800 sha256-deduped distinct inputs, 0 mismatches** | `python tests/test_diff.py` |
| G3 median speedup | spider 2.879x / 3.709x / 3.915x → median **3.709x** ≥ 1.15x | `python benchmark/bench.py --impl optimized --cssselect-path <tree> --scale <s> --mode spider` |
| G3b real corpus | real selector corpus extracted from upstream tests/docs; reuse workload ≥1.15x (unique control 0.96–0.99x disclosed above) | `python benchmark/extract_corpus.py --upstream-dir <pristine> --out benchmark/corpus/selectors.txt` |
| G4 largest scale ≥0.95x | spider 3.915x; unique large 0.962x | see table |
| G5 peak RSS ≤1.10x | 15616 KB → 16384 KB = **1.049x** (`/usr/bin/time -v`, large spider) | `/usr/bin/time -v python benchmark/bench.py --impl optimized --cssselect-path <tree> --scale large --mode spider` |

`git diff --stat`: `cssselect/parser.py | 22 ++++++++++++++++++++++`, 1 file changed,
22 insertions(+), 0 deletions. `git apply --check patch.diff` succeeds on a clean
clone of the base commit.

Differential detail: each arm is one signature containing (a) `repr` of every
`Selector` plus its specificity, (b) `css_to_xpath` XPath, (c) per-selector
`selector_to_xpath` with `translate_pseudo_elements` in both states. Exceptions
are part of the signature, so invalid selectors must raise the same type and
message. Inputs = 838 frozen corpus selectors + 27 edge cases (empty, comma,
bracket, 5000-char, 500-class, non-ASCII, emoji, pseudo-elements…), crossed with
2 translators × 2 prefixes × 2 pseudo states, deduped by
`sha256(translator|prefix|translate_pseudo_elements|css)`. 6800 distinct inputs,
13600 XPath-level comparisons, 0 mismatches.

## Reproduce

```bash
git clone --depth=1 git@github-linluozi:scrapy/cssselect.git /tmp/enoch-cssselect
python3 -m venv /tmp/enoch-venv && /tmp/enoch-venv/bin/pip install pytest hypothesis "lxml>=4.4" sybil
cp -r src/cssselect /tmp/enoch-cssselect/cssselect   # patched source
cd /tmp/enoch-cssselect && /tmp/enoch-venv/bin/python -m pytest cssselect tests docs -q -p no:cacheprovider
cd - && /tmp/enoch-venv/bin/python tests/test_diff.py
/tmp/enoch-venv/bin/python benchmark/bench.py --impl optimized --cssselect-path /tmp/enoch-cssselect --scale large --mode spider --raw-dir benchmark/raw
```

Baseline numbers are produced by running the same `bench.py` against an
unpatched checkout of `1730a489` (``--impl baseline``), with `benchmark/baseline.json`
recording the exact environment.

## Environment

AMD EPYC 7K62 (4 vCPU), 3.6 GiB RAM, CPython 3.12.3, Linux 6.x x86_64.
No randomness in the workload (`seed: null` in the JSON); the corpus is frozen
and replayed in the same order. Relative stdev of all 12 timed runs is ≤3.5%.
Python 3.10/3.11 are not installed on this machine, so no cross-interpreter
matrix is claimed; the version evidence is the four upstream release tags
(v1.3.0, v1.4.0, v1.5.0, v1.6.0) in `benchmark/version_matrix.json`.

## License

BSD-3-Clause, same as upstream. `LICENSE` keeps the upstream text verbatim and
carries the source/scope note; the patched source keeps the original copyright
headers. See `AUTHORS`.
