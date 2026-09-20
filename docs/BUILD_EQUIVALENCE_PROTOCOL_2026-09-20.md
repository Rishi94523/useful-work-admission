# Revised Vina equivalence protocol — 20 September 2026

Local working note. Supersedes the official-binary pose-parity gate in
`scripts/run_published_matched.py`. The superseded gate and both of its failure
artifacts are retained; nothing is deleted or relabelled.

## Why the previous gate is replaced

The parity gate in `run_published_matched.py` required the instrumented harness
to reproduce, coordinate for coordinate, the retained poses of the prebuilt
official `vina_1.2.7_win.exe`, with top scores agreeing to 0.001 kcal/mol.

The official binary is an MSVC build against its own Boost and C runtime. The
harness is a MinGW g++ 14.2 build of the same upstream sources. AutoDock Vina
searches by Monte Carlo with BFGS local optimisation. A last-bit difference in a
C runtime transcendental changes a BFGS step, which changes a Metropolis
accept/reject, which diverges the remainder of the trajectory. Exact
cross-toolchain agreement is therefore not attainable, and no compiler flag
removes it; `-ffp-contract=off` is already set and does not address libm.

Two distinct defects were found while the gate was failing, and the second is
the reason the gate is being replaced rather than merely relaxed:

1. A real bug: the C++ API defaults to 0.5 A grid spacing while the command line
   defaults to 0.375 A. Fixed; comparisons predating the fix stay under review.
2. A category error: the gate conflated three independent claims and tested the
   only one that cannot hold.

## The three claims, separated

| Claim | What it supports | Gate |
| --- | --- | --- |
| The split instrumentation does not alter the search | The distributed design measures the same science as stock Vina | Exact, required |
| The harness driver reproduces the command-line protocol | Harness runs are comparable to the stock campaign | Exact, required |
| This toolchain agrees with the official prebuilt binary | External comparability of absolute numbers | Reported, then gated at panel level |

The first two are exact equalities between binaries built from the same sources
with the same compiler and flags. Exact equality has no threshold, so neither
can be fitted after seeing results.

## Instruments

- `O` — official prebuilt AutoDock Vina 1.2.7 Windows binary, MSVC.
- `R1` — unpatched upstream library plus the official `main.cpp`, local g++.
- `R2` — the harness's split-task library objects plus the same official
  `main.cpp`, local g++.
- `D` — the distributed harness driver, same split-task objects, C++ API.

`R1` carries `boost/thread` and two Windows API version defines that the patched
library does not require, because unpatched `vina.h` includes `boost/thread` and
this Boost build declares its atomic wait operations only from Windows 8. This
asymmetry between `R1` and `R2` is recorded in the build manifest. It is a build
configuration difference, not a source change, and it is disclosed rather than
waived.

All four read inputs with CRLF normalised to LF, per-line bytes asserted, as the
harness already does. MinGW text-mode streams mis-parse the ADFR-prepared files
at buffer boundaries; FA7 and PUR2 fail to parse without this. The existing
`line_ending_control.json` shows the official binary produces identical poses
from CRLF and LF inputs on TGFR1.

## Gates

**G1 — instrumentation.** For every eligible target's crystal redocking at seed
104729 under the published stock protocol, `R1` and `R2` must produce identical
records on every retained pose: atom name, element, and all three coordinates as
written. Any difference fails, and the campaign does not start.

**G2 — driver protocol.** Under the same conditions, `R1` and `D` must be
identical on the same terms.

**G3 — external concordance, panel level.** Declared here, before computation.
`R1` runs one complete 96-compound panel under the stock protocol on the
eligible target selected by SHA256 order under the salt
`build-equivalence-2026-09-20:`, so the target is fixed by rule rather than by
inspection. The resulting ROC-AUC must fall inside the bootstrap 95% interval
already recorded for that target in `stock_gates.json`, and the panel must be
complete; an incomplete panel fails. This is the level at which the paper's
claims actually rest: the two builds must agree on screening outcome, not on
trajectories.

Remaining eligible targets are run under the same rule after the matched
campaign launches, as additional evidence. They do not retroactively change the
G3 verdict, and each result is recorded whether it agrees or not.

G3 is genuinely predeclared. G1 and G2 are exact. The per-target crystal
deviations between `O` and `R1` are **reported as diagnostics and not gated**,
because five crystal comparisons were already inspected on 20 September before
this note was written, and it would not be honest to present a threshold chosen
afterwards as a prediction. Those observed values are recorded below so the
disclosure is explicit.

## Disclosed prior observations

Crystal top-pose comparison, official binary against the harness driver, seed
104729, inspected before this protocol was written:

| Target | Official top score | Harness top score | Delta | Top-pose RMSD |
| --- | ---: | ---: | ---: | ---: |
| FA7 | -9.242 | -9.324 | -0.082 | 0.85 A |
| TGFR1 | -11.164 | -11.151 | +0.013 | 0.04 A |
| WEE1 | -11.018 | -11.092 | -0.074 | 0.33 A |
| PUR2 | -10.395 | -10.452 | -0.057 | 0.82 A |
| KIF11 | -12.314 | -12.317 | -0.003 | 0.30 A |

Same binding mode throughout. These are diagnostics, not a validated
equivalence result, and they do not by themselves establish G3.

## What a G3 failure would mean

A panel-level disagreement would mean this toolchain does not reproduce the
published screening behaviour, and the distributed comparison could not be
reported against the official stock campaign. That would be a genuine negative
result and would be preserved as one. It would not be waived by falling back to
trajectory-level arguments.

## Artifacts

- `scripts/build_vina_reference.py`, `scripts/verify_build_equivalence.py`
- `tmp/vina-reference/reference_build.json` — compiler, flags, source and object
  hashes for `R1`, `R2` and `O`
- `local-research/build-equivalence-2026-09-20/` (local, untracked) — execution manifest and results
- Retained failures: `local-research/published-matched-2026-09-20/` and
  `local-research/published-matched-2026-09-20-spacing0375/`
