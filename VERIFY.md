# Independent verification (2026-11-15)

This file records a re-run of the lab's claims performed **after** publication,
in a fresh clone, with a separately built patched tree. It is not a copy of the
original numbers: every number below was produced by the commands shown, in
`/tmp`, from the published commit `07d54c6f3912ba73046fe1a84710de3d68fee9da`
and upstream `scrapy/cssselect@1730a489cc4f0962ff42560c6fcb3a93b9c81ada`.

## What was re-run

1. Upstream test suite on the patched tree.
2. `tests/test_diff.py` (cached vs uncached `parse`, sha256-deduped inputs).
3. `benchmark/bench.py` on `medium`/`large` × `spider`, and the `large` ×
   `unique` no-reuse control, against both the pristine and the patched tree.

Spot-checked: two of the four release tags (`v1.6.0`, `v1.3.0`), see below.
Not re-run: the cProfile attribution (73.8%) and the other two tags in
`benchmark/version_matrix.json`.

## Setup

```
git clone --depth=1 git@github-linluozi:scrapy/cssselect.git /tmp/cssup      # pristine
git clone --depth=1 git@github-linluozi:linluozi/cssselect-opt-lab.git /tmp/cs
cp -r /tmp/cssup /tmp/csspat && rm -rf /tmp/csspat/cssselect
cp -r /tmp/cs/src/cssselect /tmp/csspat/cssselect                            # patched tree
python3 -m venv /tmp/csv-venv && /tmp/csv-venv/bin/pip install pytest hypothesis 'lxml>=4.4' sybil
```

Environment: AMD EPYC 7K62 (4 vCPU), 3.6 GiB RAM, CPython 3.12.3, Linux
6.8.0-124-generic. No seed: the workload is a frozen, deterministically replayed
corpus (`benchmark/corpus/selectors.txt`).

## Results

Upstream tests (patched tree):

```
$ cd /tmp/csspat && /tmp/csv-venv/bin/python -m pytest cssselect tests docs -q -p no:cacheprovider
46 passed, 1 xfailed, 81 subtests passed in 3.87s
```

Differential test:

```
$ cd /tmp/cs && /tmp/csv-venv/bin/python tests/test_diff.py
distinct_inputs=6800
dedup=sha256(translator|prefix|translate_pseudo_elements|css)
parse_level_comparisons=6800
xpath_level_comparisons=13600
mismatches=0
```

Benchmarks (median of 7 timed reps after 3 warmups, `time.perf_counter`;
raw samples in `benchmark/verify-20261115/`):

| workload | scale | baseline median | patched median | speedup | README |
| --- | --- | --- | --- | --- | --- |
| spider | medium (400 × 12) | 162.4749 ms | 43.8037 ms | **3.709x** | 3.709x |
| spider | large (743 × 20) | 478.8670 ms | 121.2416 ms | **3.950x** | 3.915x |
| unique | large (743 × 1) | 23.7987 ms | 24.2552 ms | **0.981x** | 0.962x |

Commands (one per arm; `--raw-dir /tmp/vraw` for the verification pass):

```
/tmp/csv-venv/bin/python benchmark/bench.py --impl baseline  --cssselect-path /tmp/cssup --scale large --mode spider --raw-dir /tmp/vraw
/tmp/csv-venv/bin/python benchmark/bench.py --impl optimized --cssselect-path /tmp/csspat --scale large --mode spider --raw-dir /tmp/vraw
```

## Release-tag spot check: v1.6.0

`patch.diff` applied cleanly to a fresh `--depth=1` clone of tag `v1.6.0`
(`805705c5a204721d3c486250377a756bd6fa54a5`), the upstream suite passed, and the
`small`/`spider` benchmark reproduced the matrix entry:

```
$ git clone --depth=1 --branch v1.6.0 git@github-linluozi:scrapy/cssselect.git /tmp/cs16
$ cp -r /tmp/cs16 /tmp/cs16p && cd /tmp/cs16p && git apply /tmp/cs/patch.diff
$ /tmp/csv-venv/bin/python -m pytest cssselect tests docs -q -p no:cacheprovider
27 passed in 0.61s
```

| arm | median (7 reps, 3 warmups) | speedup |
| --- | --- | --- |
| pristine v1.6.0 | 26.0308 ms | — |
| v1.6.0 + patch | 8.6742 ms | **3.001x** |

The matrix records 25.6942 ms / 8.6876 ms = 2.9576x for the same tag; the two
runs differ by 1.5%, inside the run-to-run spread. Raw samples for this tag are
in `benchmark/verify-20261115/v1.6.0/`. The other two tags were not re-run.

## Release-tag spot check: v1.3.0

Same procedure on the oldest tag in the matrix, `v1.3.0`
(`e99c506b8e8be0753250622633df8a68dc76268e`):

```
$ /tmp/csv-venv/bin/python -m pytest cssselect tests docs -q -p no:cacheprovider
22 passed in 0.44s
```

| arm | median (7 reps, 3 warmups) | speedup |
| --- | --- | --- |
| pristine v1.3.0 | 37.2888 ms | — |
| v1.3.0 + patch | 19.5608 ms | **1.906x** |

The matrix records 38.2411 ms / 19.2057 ms = 1.9911x for this tag; the re-run is
4.3% lower (1.906x). Both are above the 1.15x gate, so the matrix's `guard:
enabled` verdict stands, but the matrix number should be read as run-specific,
not as a fixed constant. Raw samples are in `benchmark/verify-20261115/v1.3.0/`.

## Verdict

The published claims reproduce within run-to-run noise: the `spider` speedups
are 3.709x (medium) and 3.950x (large) versus 3.709x/3.915x in the README, the
no-reuse control is 0.981x (README 0.962x), the diff test still reports 6800
distinct inputs and 0 mismatches, the patched tree passes the same upstream
suite, and the v1.6.0 tag reproduces at 3.001x versus 2.958x in the matrix, while v1.3.0
reproduces at 1.906x versus 1.991x (4.3% lower, still above the 1.15x gate). Nothing here changes the README's honest boundary: the gain requires
reusing a selector list across pages; with no reuse the patch is a small loss.
