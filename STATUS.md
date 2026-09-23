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

**Unit-level attacks under real replay — phase 1 complete.** 693 trials on 99
units sampled by salted hash from 33 preserved campaign jobs, all five targets,
judged by re-executing the unit with the frozen driver or by running the
original finalizer over a tampered pool. Predictions were committed before
execution (`docs/ADVERSARIAL_EVALUATION_PROTOCOL_2026-09-22.md`, amendment 1).

| Attack | Outcome |
| --- | --- |
| Honest unit | accepted 99/99 |
| A1 substitution of another unit's result | accepted 0/99 |
| A3 cached resubmission | accepted 99/99, by design; only one-use credits refuse it |
| A2 quarter / half work, pool-only commitment | **accepted 20/99 and 45/99** |
| A2 quarter / half work, pool and trace commitment | accepted 0/198 |
| A8e best energy falsified by 0.1–3.0 kcal/mol | falsified value never reaches output; merge-order effect ≤0.11 kcal/mol in either direction, independent of lie size |
| A8c best pose moved 0.1–2.0 Å | no effect at 0.1 and 0.5 Å; one genuine 0.118 kcal/mol improvement at 2.0 Å |

Committing to the minima pool alone does not enforce work: retained minima often
stabilise before the budget is spent, so truncated searches reproduce the pool
byte for byte. Binding the per-step trace closes this completely. The browser
worker already uploads the trace. Committing to a SHA-256 of the trace instead
would preserve the guarantee while cutting upload from about 167 KB to 18 KB;
that change is not implemented. Predictions P5 and P6 failed as literally
stated, but the original finalizer recomputes every energy, so neither
falsification nor single-unit displacement can be steered by an attacker.

**Puzzle baseline — measured.** Hashcash calibrated natively to the same median
client time under the same load (21 bits, 240 solves).

| | Puzzle | Vina unit |
| --- | ---: | ---: |
| Client median | 1.38 s | 1.52 s |
| Client p99 | 6.50 s | 3.38 s |
| Client maximum | 13.4 s | 3.4 s |
| Coefficient of variation | 0.95 | 0.48 |
| Verifier cost per admission | 0.77 µs | q × 1.52 s |
| Freshness guaranteed | yes | no |
| Useful output | none | one docking unit |

The puzzle wins decisively on verification cost and on freshness, as predicted.
Useful work costs the verifier a fraction q of client work, which is roughly
five orders of magnitude above a hash check at q = 0.1. The unit has half the
latency variance and a far shorter tail, because its evaluation budget is
bounded while a puzzle solve is geometric.

**Admission economics on the real scheduler — phase 2 complete.** Attackers
drove the committed `PoolAdmission` scheduler under a simulated clock, with every
audit verdict resampled from phase-1 replay records. 118 configurations; 110 ran
to completion and 8 were stopped at 5.9 hours with their measured counts
recorded. The metric is the attacker discount factor: attacker work per
admission divided by honest work per admission in the same tier. A proof-of-work
puzzle is 1.0 by construction; below 1.0, cheating is cheaper than honesty.

| Configuration | Predicted | Measured |
| --- | --- | --- |
| Deployed bundle tier, attacker computes 1/2/3/4 of 4 units | 0.43 / 0.57 / 0.76 / 1.0 | **0.46 / 0.57 / 0.76 / 1.00** |
| Same, always submitting instead of walking away | as above | 0.42 |
| Reseed a unit after any failed or abandoned attempt | 1.0 | 0.98–1.08 |
| Attempt cap 1 / cap 16, one unit computed | 1.0 / 0.25 | 0.98 / 0.25 |
| Two audit draws, 2 or 3 units computed | 1.19 / 0.86 | 1.19 / 0.85 |
| Reduced-budget units, pool-only commitment, 64k / 128k | 0.51 / 0.60 | 0.54 / 0.60 |
| Reduced-budget units, pool and trace commitment | never admitted | never admitted |
| Trusted tier, trust after 1 honest bundle, p = 0.1, immediate / deferred | ~0.5 / ~0.61 | 0.60 / 0.63 |
| Disappearing workers, 4 / 8 / 12 / 16 lease holders | refusals ≈ D/16 | **0% / 0% / 0% / 81%** |

Every prediction but the last held. Capacity exhaustion is a threshold, not a
proportional effect: holders cost nothing until they occupy all 16 leases, then
honest service collapses.

Two structural causes explain every sub-1.0 factor, and both are fixable:

- **Cached reuse (bundle tier).** An abandoned or failed unit returns to the
  pool with the same seed, so an attacker who computed one of four units reuses
  that answer across up to three attempts until the audit draw lands on it. The
  remaining fabricated units are then stored unreplayed, three per admission at
  one computed unit. Reseeding on retry restores 1.0 at unchanged verifier cost.
  Walking away is not needed: submitting and being rejected costs the same,
  because a fresh identity is free in this tier.
- **Early audit reveal (trusted tier).** `commit()` tells the client whether and
  which unit will be replayed before any output is uploaded. The pool path
  uploads every output anyway, so the reveal buys nothing, but it lets a trusted
  identity abandon when selected and never be quarantined.

Trust thresholds are a measured defence. Requiring three admitted honest bundles
before trust raises the trusted-tier factor to 1.3–4.0 at every audit rate
tested. Acquiring trust cheaply through cached reuse costs 5–15 times honest
work at three bundles. At ten bundles it earned trust about 720 times per
configuration, from roughly 7,450 bundle admissions, and never produced a single
trusted admission: the abandonments left every identity above the trusted-tier
risk limit after the strategy's fixed 30-minute backoff. A more patient
attacker might do better; this bounds a 30-minute-backoff attacker only.

Verifier cost in the bundle tier is one replayed unit per four-unit admission at
one draw, 25% of client work. Identities cost zero in this simulation; the
break-even identity cost for each attack is not yet computed.

**Reseed on retry — implemented and verified.** A unit re-issued after expiry
or a failed audit now carries a fresh server-drawn seed, so an earlier answer is
worthless. Rerun on the committed scheduler with no counterfactual code, against
predictions recorded beforehand (protocol amendment 3):

| Deployed bundle tier, one draw | Before | After | Predicted |
| --- | ---: | ---: | --- |
| Attacker computes 1 of 4 units | 0.46 | **0.96** | 0.95–1.10 |
| Attacker computes 2 of 4 units | 0.57 | **1.03** | 0.95–1.10 |
| Attacker computes 3 of 4 units | 0.76 | **1.00** | 0.95–1.10 |
| Honest client | 1.00 | 1.00 | 1.0 |
| Reduced-budget units, pool-only, 64k / 128k | 0.54 / 0.60 | 1.39 / 1.12 | ~1.25 / ~1.10 |

Cheating in the bundle tier no longer costs less than honest work, and verifier
cost is unchanged at one replayed unit per admission. The 64k figure ran about
two standard errors above its prediction; the direction held. Fabricated units
retained per admission are unchanged at 3, 2 and 1, as predicted: reseeding fixes
what cheating costs, not what an admitted cheat leaves in storage.

**Audit reveal removed — implemented and verified.** `commit()` now returns
only the challenge identifier; the trusted verifier reads the draw through a
server-side accessor. Rerun on the committed scheduler against amendment 4:

| Immediate policy, trust after 1 bundle | p = 0.02 | 0.05 | 0.10 | 0.25 |
| --- | ---: | ---: | ---: | ---: |
| Factor with reveal | 0.44 | 0.48 | 0.60 | 1.19 |
| Factor without reveal | 0.44 | 0.55 | 0.65 | 1.40 |
| Predicted, (1-p)(1-(1-p)^10)/p admissions per identity | 0.45 | 0.53 | 0.68 | 1.41 |
| Identities quarantined (none before) | 4 | 18 | 34 | 99 |

Cheating trusted identities are now caught and quarantined; before, abandoning
on selection meant none ever were. As predicted, this alone leaves the factor
below 1.0 at one honest bundle for audit rates up to 10%. With trust after three
bundles it is 1.36–4.04 at every rate. Deferred policy and the bundle tier are
unchanged within noise.

**Trust threshold � enforced.** `grant_trust` now refuses an identity until it
has three bundle-tier admissions that were replayed and accepted (amendment 5);
bypassing it requires an explicit `trust_bundles=0`. On the real scheduler at
p = 0.1, an attacker planning trust after one bundle obtained no trusted
admission across 3,000 identities, spending 12,000 units of honest work, while
one earning three bundles paid a factor of 2.04.

With reseeding, no audit reveal and an enforced threshold, every deployed
configuration measured costs an attacker at least as much as honest work.

## What is not established

- **Scientific integrity is separate from admission cost.** At parity, an
  admitted bundle that computed one unit of four still leaves three unreplayed
  fabricated units, and an unaudited trusted admission leaves one. Their effect
  on screening results and the cost of repair are not measured.
- **A one-run trusted tier** is not an unconditional proof of work by anonymous
  users: an unaudited trusted admission is still granted on the identity's
  history, not on the unit.
- **Scientific quarantine and repair** after late detection is not implemented.
- **Timing is native.** Browser and phone comparisons of unit against puzzle
  remain to be measured.
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
