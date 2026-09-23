# Current status — 20 September 2026

This repository implements **browser admission backed by auditable useful
scientific computation**. A visitor's browser runs a bounded unit of real
molecular docking work; the server verifies that work far more cheaply than
producing it, and the scientific output is aggregated across contributors.

The workload is AutoDock Vina docking, not ML inference. The earlier MNIST
demonstrator is project history and no longer describes this system.

## What is established

**Scientific controls — complete.** A frozen five-target stock Vina campaign
finished all 706 jobs with no execution failures: 480 compounds, 691 supplied
molecular states, 15 crystal-redocking jobs. All five targets passed the
predeclared ranking and redocking gates.

| Target | Stock ROC-AUC | EF10 | Gates |
| --- | ---: | ---: | --- |
| WEE1 | 0.9927 | 3.0 | Pass |
| PUR2 | 0.9478 | 2.7 | Pass |
| FA7 | 0.9023 | 3.0 | Pass |
| TGFR1 | 0.8745 | 2.7 | Pass |
| KIF11 | 0.9087 | 2.7 | Pass |

Each panel is 32 actives and 64 decoys. These are small-panel results, not a
reproduction of full-library published AUCs. DYR, AKT1 and PPARG are retained
negative results.

**Build equivalence — passed.** Three binaries built from the same sources with
the same compiler and flags were compared against the official prebuilt Vina
1.2.7 binary on all five targets. The split instrumentation and the distributed
driver are coordinate-identical to an uninstrumented reference on every
retained pose, and all three agree with the official binary on how many poses
survive the energy window. Divergence from the official binary is confined to
last-bit C runtime differences amplified by Monte Carlo search, which is a
property of the method rather than a defect. See
`docs/BUILD_EQUIVALENCE_PROTOCOL_2026-09-20.md`.

**Architecture — implemented.** Independent task decomposition with exact
reproduction of monolithic results, commitment and post-commit whole-run
challenge, campaign scheduling with disjoint leases, one-use work credits, the
original Vina finalizer, and lossless prepared-state delivery to browsers over
a CDN.

**Matched compute — passed on all five targets.** 2,073 paired state jobs, three
seeds, zero failures. Each ligand state was docked as a monolithic
exhaustiveness-32 run and as independent 256k-evaluation units (median 140 per
state) merged by the original finalizer, at matched evaluation budget.

| Target | Mean ΔAUC | Paired 95% | Evaluation ratio | Search-time ratio |
| --- | ---: | --- | ---: | ---: |
| WEE1 | −0.0003 | [−0.0015, +0.0000] | 1.0040 | 0.961 |
| PUR2 | +0.0033 | [−0.0067, +0.0164] | 1.0025 | 0.933 |
| FA7 | +0.0020 | [−0.0093, +0.0163] | 1.0034 | 0.959 |
| TGFR1 | −0.0008 | [−0.0060, +0.0036] | 1.0045 | 0.964 |
| KIF11 | +0.0003 | [−0.0042, +0.0049] | 1.0045 | 0.974 |

The predeclared noninferiority margin of −0.05 is generous relative to these
effects and is not a discriminating test; the substantive finding is that every
interval lies within ±0.017 and straddles or touches zero, with EF10 identical
on 14 of 15 target-seed pairs. Decomposition costs under 0.5% extra evaluations
and no search time. These remain 96-compound panels, not full-library results.

## What is not established

- **Admission security** is analysed but not demonstrated end to end. Existing
  attack experiments use modelled molecular verdicts. A predeclared evaluation
  against real molecular replay, with a puzzle baseline, is specified in
  `docs/ADVERSARIAL_EVALUATION_PROTOCOL_2026-09-22.md` and not yet run. A one-run
  trusted tier is not an unconditional proof of work by anonymous users; at 0.1
  audit probability, zero-work trusted requests can pass unaudited.
- **Device evidence** covers one iPhone 15 and one desktop. There is no
  population-level claim.
- **Novelty positioning** against prior useful-work puzzles, volunteer computing
  and probabilistic verification remains outstanding.

The project is not submission-ready.

## Layout

```text
benchmarks/          predeclared protocol definitions with hashes
scripts/             campaign runners, verification gates, analysis
research/native/     instrumented Vina drivers and task transport
research/            browser workers, campaign and admission modules
research/tests/      scheduler, admission and validation tests
cloudflare/vina-cdn/ prepared-state static delivery configuration
```

Working reports, generated evidence and raw device logs are kept locally and
are not tracked. The remaining inference stack, datasets, models and historical setup documents
are archived locally in `../legacy-capstone/cleanup-2026-09-20/`.
The MNIST and CIFAR phases were moved out of this repository;
the committed history retains the earlier pipeline as a record of the project's
development.
