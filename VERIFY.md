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

Not re-run: the cProfile attribution (73.8%) and the four-release-tag matrix in
`benchmark/version_matrix.json`. Those claims are outside this verification.

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

## Verdict

The published claims reproduce within run-to-run noise: the `spider` speedups
are 3.709x (medium) and 3.950x (large) versus 3.709x/3.915x in the README, the
no-reuse control is 0.981x (README 0.962x), the diff test still reports 6800
distinct inputs and 0 mismatches, and the patched tree passes the same upstream
suite. Nothing here changes the README's honest boundary: the gain requires
reusing a selector list across pages; with no reuse the patch is a small loss.
