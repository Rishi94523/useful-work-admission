# Useful Work Admission — current status, 28 September 2026

Repository: https://github.com/Rishi94523/useful-work-admission

## Manuscript review correction and replication

Amendment 12 is complete: **1,120 simulations, 224 cells × five seeds**, with
exact 1.52 s replay events instead of the historical 1.75 s tick-rounded
service. The original ledgers below remain historical evidence, not corrected
measurements. Corrected C1 full-patience checks pass **230/240 (46/48 in each
seed)**; follow-price checks pass 153/240. Attestation A1/A3/A4/A6 pass all
eligible checks; A2 passes 557/600 and A5 315/330. These checks test specified
finite-horizon models, not deployed resilience or an exact threshold law.

Results: `local-research/admission-amendment12-2026-09-25/memory-sqlite/`;
reproduce with `scripts/evaluate_admission_amendment12.py` and
`scripts/analyze_admission_amendment12.py`. An initial 12-cell disk-backed
attempt is preserved in the parent directory. In-memory SQLite accelerates
the simulator only, with identical SQL/transaction semantics checked against
disk-backed fixtures. It does not accelerate or benchmark production replay.

The revised manuscript distinguishes measurements, simulations and projections.
Attacker-cost estimates near 1 do not establish a lower bound of 1. The
0.034 AUC poisoning loss is an exploratory projection at **10%** corruption;
the measured **5%** result is 22/33 re-finalised jobs worsened. Attestation
uses a mock issuer and assumed quotas. Corrected bootstrap results differ from
historical values: without tokens at eight workers, flagship trust is 0.030
on average (range 0–0.050), rather than universally zero. See Section 5.6 of
`docs/paper/MANUSCRIPT.md` for corrected tables and all prediction misses.

## Project overview and historical experiment record

This repository implements **browser admission backed by auditable useful
scientific computation**. A visitor's browser runs a bounded unit of real
molecular docking work; the server samples complete units for replay, and
scientific output is aggregated across contributors. Sampled bundle auditing
costs less than executing the whole bundle; replay of a single unit is not
cheaper than that unit's own molecular computation.

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
preserves the guarantee exactly, since hash equality is byte equality, and is
implemented as `research/trace_commitment.py`: across all 4,397 corpus units
the median upload falls from 163 KB to 19 KB, an 88% reduction (215 KB to 23 KB
at the 95th percentile). The browser worker still sends the full trace, because
the device experiments compare it. Predictions P5 and P6 failed as literally
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

**Trust threshold — enforced.** `grant_trust` now refuses an identity until it
has three bundle-tier admissions that were replayed and accepted (amendment 5);
bypassing it requires an explicit `trust_bundles=0`. On the real scheduler at
p = 0.1, an attacker planning trust after one bundle obtained no trusted
admission across 3,000 identities, spending 12,000 units of honest work, while
one earning three bundles paid a factor of 2.04.

With reseeding, no audit reveal and an enforced threshold, every deployed
configuration measured costs an attacker at least as much as honest work.

**Identity cost.** The simulation prices a fresh identity at zero. For the
original design to reach parity on identity cost alone, each fresh identity
would have had to cost the attacker 0.5–3.3 honest units in the bundle tier
(the upper end for an attacker reusing one identity across walk-aways) and
2.4–5.1 units in the trusted tier with trust after one bundle, one unit being
about 1.5 s of CPU. After the fixes, parity holds with identities free, so it
no longer rests on any assumption about identity cost. This is the precise
difference from proof-of-work, whose per-admission cost never depended on
identity.

**Scientific integrity — phase 6.** The original finalizer was run over pools
from the 33 corpus jobs with units replaced or altered, against amendment 6.
The untouched baseline reproduced the campaign's recorded score in 33 of 33
jobs.

| Experiment | Predicted | Measured |
| --- | --- | --- |
| I-d unit with the wrong atom count | rejected on read | rejected 33/33 ✓ |
| I-a stored coordinates moved 2 Å, conformation untouched | change ≤ 0.12 kcal/mol | −0.10 to +0.02 ✓ |
| I-a conformation moved 2 Å, coordinates untouched | like phase-1 A8c | −0.42 to +1.37 ✗ |
| I-b duplicated units, f = 0.05 → 0.75 | no gain > 0.12; losses grow with f; median 0 at small f | best gain −0.10; jobs worse 2 → 12; median 0 throughout ✓ |
| I-c duplicated units claiming −20 kcal/mol | same as I-b | **22 of 33 jobs worse at f = 0.05, by up to 1.859 kcal/mol; maximum worsening 2.632 at f = 0.10** ✗ |
| I-e ROC-AUC change from I-b, f ≤ 0.25 | within ±0.01 | within ±0.004; within ±0.009 at f = 0.75 ✓ |

**Fabricated reported energies did not survive final rescoring in these tests.**
The finalizer recomputed output energies from conformations; this does not
establish biological validity or exclude screening false positives. The largest
score improvement was 0.466 kcal/mol, at 5% fabricated-energy units. Honest
duplication, the cheapest fabrication that parses, leaves projected screening
ROC-AUC changes within ±0.004 at up to a quarter of units fabricated.

**Falsified energies hijack the merge.** The value is laundered, but the merge
still ranks and clusters minima by the energies clients report, and keeps only
a bounded set for refinement. Fabricated minima claiming −20 kcal/mol displace
honest minima from that set, so the best pose is lost before refinement ever
sees it. Five per cent of units suffice. Propagated onto the campaign
(exploratory, not predeclared), ROC-AUC falls by up to 0.034 on average at
f = 0.10, with 95% intervals excluding zero on several targets. The effect does
not grow with f: once fabricated minima dominate the retained set, more of them
do no further harm.

The remedy is to rescore every submitted minimum from its conformation before
merging, so no client-reported energy influences selection. That costs about
nine energy evaluations per unit against 256,000 for the search. It changes the
frozen driver's merge path and is not implemented.

**v2 driver, rescoring before merge — verified, deployment candidate.** v2
recomputes every submitted minimum's energy and coordinates from its
conformation before merge selection. Only `parallel_mc.cpp` differs from v1,
which stays frozen as the historical baseline for every result above; roles and
hashes are pinned in `benchmarks/driver_registry.json`. Against amendment 8:

| Check | v1 | v2 |
| --- | --- | --- |
| G1, G2, replay and re-finalization, five targets | pass | **pass, 5/5** |
| Honest corpus pools finalized | — | **byte-identical to v1, 33/33** |
| Falsified-energy attack, mean ΔAUC | as low as −0.034 | **within ±0.0016 at every fraction** |
| Jobs worsened at 5% falsified units | 22/33 | **2/33, same as honest duplication** |
| Coordinate-only tampering changes result | 16/33 | **0/33** |
| Rescoring overhead per ligand state | — | **+91 ms median, 0.046% of client work** |

With rescoring, a falsified energy has no effect beyond honest duplication, and
screening results are unchanged within ±0.004 AUC at up to a quarter of units
fabricated. Honest science is untouched, so no new matched campaign is needed.
The overhead was measured while crystal docking loaded the machine, and
per-state differences ranged from −196 to +265 ms.

**Device timing, docking unit against puzzle — four phones.** A test page on
the benchmark Worker runs real WASM Vina units and hashcash puzzles on the same
device, alternating one unit with four puzzles over twelve rounds so thermal
effects hit both equally, with puzzle difficulty calibrated on the device to the
median warm unit. The Worker re-checks every unit's pool and trace hashes before
storing. The page holds a screen wake lock and timestamps every hidden period,
flagging overlapping measurements for exclusion.

| Device | Unit median / max | Puzzle median / p95 / max | Units exact |
| --- | --- | --- | --- |
| iPhone 15, Low Power Mode | 2.04 / 2.10 s | 1.85 / 6.57 / 8.24 s | 17/17 |
| Samsung Galaxy A57 | 2.02 / 2.10 s | 2.09 / 7.82 / 10.5 s | 17/17 |
| Moto Edge 50, Low Power Mode | 2.44 / 2.73 s | 1.86 / 8.83 / 10.4 s | 17/17 |
| Samsung Galaxy M30s (2019 budget) | 7.55 / 10.1 s | 5.86 / 36.1 / 53.2 s | 17/17 |

Pooled with each device scaled to its own median unit time:

| | 95th pct | 99th pct | Worst | Over 2× median |
| --- | ---: | ---: | ---: | ---: |
| Docking unit, 64 | 1.19× | 1.33× | 1.33× | 0% |
| Puzzle, 192 | 3.83× | 6.84× | 7.04× | 21.9% |

Matched at the median, more than one visitor in five waits over twice as long
for a puzzle; no docking unit reached 1.35 times its device's median. All 68
units were bitwise exact across iOS and Android. The wake lock was granted on
all three phones that ran the current page.

The budget phone is 3.7 times slower than the iPhone at docking but 5.2 times
slower at JavaScript hashing, so at equal flagship cost a puzzle would burden it
more than a unit would. That is one device pair against a plain-JavaScript
solver, not a general result. Its first contribution takes about 13 s (3.8 s
assets, 1.5 s restore, 7.5 s first unit) against about 2 s on the iPhone, a real
accessibility cost. Its units rose from 7.4 to 10.1 s mid-run and recovered,
consistent with thermal throttling.

An earlier iPhone run on the previous page, which could not flag hidden
periods, lost one unit to the Low Power Mode auto-lock (11.1 s against a 1.9 s
median). It is reported but excluded from the pooled figures.

**Subpuzzle proof-of-work baseline on five phones (amendment 11).** A second
page interleaved each warm docking unit with two single puzzles and two
64-subpuzzle puzzles, all calibrated on the device to the median unit. Five
phones ran it: iPhone 15 (Low Power Mode), Samsung Galaxy A57, Moto Edge 50,
Samsung Galaxy M30s and Infinix Note 40 Pro; all units were exact and no
measurement overlapped a hidden page.

| Pooled, scaled as predeclared by each device's median unit | p95/median | Over 2× median |
| --- | ---: | ---: |
| Docking unit, 80 | 1.15 | 0% |
| Single puzzle, 120 | 4.40 | 25.8% |
| 64-subpuzzle puzzle, 120 | 2.02 | 5.8% |

S2 (single puzzles at least 15% over twice the median) and S3 (unit
p95/median at most 1.35) held. S1 failed: subpuzzles did not stay within 1.35.
S4 failed too, and explains S1: calibration missed on two phones, the Moto's
subpuzzle median landing at 1.66 times its unit median and the M30s's at 0.70,
so pooling by unit median mixes shifted distributions. Measured within each
device instead (post hoc), 64-subpuzzle solves had p95/median 1.14–1.40 and
none over twice their own median, pooled 1.21, against 1.15 for units. As
stated in advance, lower latency variance is therefore not an advantage of
useful work over a well-designed puzzle; the paper claims parity with
subpuzzle proof of work and an advantage only over a single puzzle. One Moto
unit ran 1.83 times its median, the largest unit excursion measured.

**Proof-of-work gate baseline (amendment 13).** The amendment-12 queue and
attacker grid were rerun with 0.77 µs hash-check verification in place of a
1.52 s replay: fixed 16-bit and 18-bit puzzles and the full-patience priority
queue, 1-8 workers, 0-16 attacker cores, five seeds, 360 runs. P1 held in 72
of 72 cells: every device class at least 90% served as a five-seed mean. P2
held in 23 of 23: where useful-work service fell below 0.2, the proof-of-work
gate served every class at 0.95-1.00 (lowest class at 8 workers and 16 cores:
0.110 with replay, 0.950 with proof of work). The gate never became the
bottleneck. Downstream load from attackers admitted by paying the puzzle is
not modelled, so this isolates the availability price of replay verification
at the gate, not a whole-deployment comparison.

**Verification leverage across two workloads (amendment 14).** Five image
classifiers for data labelling were verified by one exact-integer Freivalds
implementation restored from the earlier inference work: MNIST perceptron,
MNIST and CIFAR convolutional networks, VGG11-BN on CIFAR-10.1 and a
784-2048-2048-10 perceptron. Leverage is the server's best native inference
time divided by verification time.

| Model | Accuracy | Central / verify (ms) | Leverage, 0% / 8% audit | Trace | Weights |
| --- | ---: | ---: | ---: | ---: | ---: |
| MNIST MLP | 96.8% | 0.078 / 0.219 | 0.37 / 0.36 | 0.8 KB | 0.11 MB |
| MNIST CNN | 98.7% | 0.262 / 0.377 | 0.73 / 0.69 | 37.9 KB | 0.05 MB |
| CIFAR CNN | 76.2% | 0.985 / 1.13 | 0.93 / 0.87 | 115.2 KB | 0.16 MB |
| VGG11-BN | 83.1% | 3.87 / 5.69 | 1.08 / 0.68 | 610.3 KB | 9.76 MB |
| Wide MNIST MLP | 97.6% | 1.60 / 1.12 | 1.80 / 1.43 | 16.4 KB | 5.84 MB |

L1 (every trace perturbation rejected), L2 (ordinary models below 1.5 at 8%
audits), L4 (every class at least 90% served in all 360 availability cells,
1,800 runs) and L5 (no workload with verification under 10 ms and leverage
above 4) held. L3 failed: the wide perceptron reached 1.80 and 1.43, not 10
and 2.5. The prediction came from an earlier micro-benchmark against an exact
double-precision baseline; against optimised native inference the verifier's
fixed per-layer work dominates. Docking has leverage 4 per newcomer bundle and
1/p in the trusted tier. Across both classes, the work worth delegating was
expensive to verify and the work cheap to verify was not worth delegating.

**Phones (amendment 14b).** Six reports from four phones (iPhone 15 and Samsung
M30s twice each, Galaxy A57, Infinix Note 40 Pro); no measurement overlapped a
hidden page. Medians pool each phone's runs; ratios are native ÷ phone speed
against 1.25 million SHA-256 hashes/s and 62.4 ms scrypt per core.

| Phone | SHA-256/s | × native | scrypt (ms) | × native | VGG11-BN (ms) |
| --- | ---: | ---: | ---: | ---: | ---: |
| iPhone 15 | 368,066 | 3.4 | 96 | 1.5 | 255 |
| Galaxy A57 | 153,501 | 8.1 | 168 | 2.7 | 443 |
| Infinix Note 40 Pro | 69,678 | 17.9 | 371 | 6.0 | 718 |
| Samsung M30s (2019) | 36,063 | 34.7 | 500 | 8.0 | 1,458 |

D1 held (all 270 trace hashes matched the export), D2 held (the budget phone's
scrypt gap, 8.0x, is below a third of its SHA-256 gap, 34.7x) and D3 held
(budget VGG11-BN 5.7x the iPhone 15; 5.7x warm-only). The memory-hard puzzle
cuts an attacker core's advantage over the budget phone about fourfold and the
budget-to-flagship spread from 10x to 5.2x, but does not remove it; labelling
work on the same phones spreads 5.7x, like scrypt.

## What is not established

- **Device coverage is small**: four phones, one workload, 64 unit timings.
- **v2 is not serving production traffic.** No production finalizer service
  exists yet.
- **A one-run trusted tier** is not an unconditional proof of work by anonymous
  users: an unaudited trusted admission is still granted on the identity's
  history, not on the unit.
- **Scientific quarantine** after failed replay is implemented: the scheduler
  quarantines contributors and blocks aggregate-output retrieval when their
  contributions are present. A dedicated late-failure test covers this guard.
  Automatic campaign repair and retraction of already-produced scientific
  results have not been demonstrated.
- **Latency advantage over proof of work holds only against a single
  puzzle.** A 64-subpuzzle puzzle on phones was as predictable as a docking
  unit (see the subpuzzle result above); an optimized or WebAssembly solver
  was not tested.
- **Availability under attack is only partly resolved, and only in isolated
  prototypes.** Stateless tickets and reserved tiers end the idle-lease attack
  and protect established users; an effort-priority queue keeps newcomers served
  below a budget of (R − λ) × phone hash rate × patience, but budget phones lose
  first, every newcomer pays about 10 s under attack, and about 16 attacker
  cores defeated every puzzle-only configuration tested. An attested-newcomer
  lane admits token holders, budget phones included, and lets them earn trust
  against 16 cores, but only while tokens are costly to the attacker, not for
  anonymous visitors, and only on platforms with unlinkable attestation. None of this is integrated into
  `PoolAdmission`, and puzzle costs were accounted, not executed. A separate fractional-refill bug was
  fixed: rejected requests now preserve token credit. All 72 research tests
  passed at the time, including a regression that failed before the fix.
- **Novelty positioning** is drafted locally against 53 checked sources. The
  closest prior proposal is a password-cracking proof-of-work CAPTCHA (FedCSIS
  2023): a design without measurements that trusts a 51% majority of visitors.
  The effort-priority queue is Tor's onion-service design, puzzle auctions and
  subpuzzles are older still, and the attested lane applies Privacy Pass. What
  remains ours is the measured, replay-verified system, its admission economics
  with free identities, the aggregation attack and the replay-capacity cost.
  Claiming lower latency variance than proof of work in general needs the
  subpuzzle baseline measured on phones first.

**Isolated ticket-admission prototype — tested, not deployed.** Authenticated
tickets without audit seats, independent byte/queue reservations, commitment
checks and an overload entry puzzle were exercised together through loopback
HTTP. At 64 tickets/s issuance and four attacker arrivals/s, idle and unpaid
fabrication cases completed 60/60 newcomers and 60/60 established users. A paid
16-bit-puzzle flood reduced newcomers to 1/60; established users stayed at 60/60.
Arrival and replay time are simulated in these cases; puzzles and protocol
operations are real. A separate two-bundle native Vina smoke check accepted
honest output and rejected corrupted trace commitments using actual full-unit
replay. All 82 research tests passed. Paid-flood fairness and pricing remain open.

**Pricing newcomer admission under a CPU budget — effort-priority queue on the
ticket prototype.** Under overload a newcomer proves effort as a count of small
subpuzzles bound to its ticket and commitment; newcomers are replayed highest
effort first; a full newcomer queue evicts its lowest bid for a strictly higher
one; a published suggested effort rises only under pressure. Seven tests with
real solving cover the mechanism; 89 research tests pass. The evaluation drives
the real queue code, with arrivals, 1.52 s replays and puzzle costs simulated
and accounted from measured hash rates (phones' JavaScript rates, 1.25 M
hashes/s per native attacker core), over 1–8 verifier workers and 0–16 attacker
cores (amendments 9 and 9b).

A fake submission costs its sender only the entry puzzle but costs the verifier
a full molecular replay, so spare replay capacity is the scarce resource, a
pressure proof-of-work, which verifies in microseconds, does not face. The
predicted rule is that honest newcomers stay served while the attacker's
budget is below (R − λ) × phone hash rate × patience, with R the verifier's
audit rate and λ honest arrivals.

| Newcomers served, budget / mid / flagship phone | 0.25 cores | 1 core | 4 cores | 16 cores |
| --- | --- | --- | --- | --- |
| Fixed 16-bit puzzle, 8 workers | 0.88 / 0.90 / 1.00 | 0.33 / 0.35 / 0.30 | 0.25 / 0.23 / 0.17 | 0.25 / 0.23 / 0.17 |
| Fixed 18-bit puzzle, 8 workers | 0.97 / 1.00 / 1.00 | 0.95 / 0.93 / 0.97 | 0.15 / 0.25 / 0.42 | 0.07 / 0.17 / 0.12 |
| Priority, full-patience bids, 8 workers | 0.90 / 0.88 / 0.93 | 0.95 / 0.95 / 1.00 | **0.05 / 0.95 / 1.00** | 0.05 / 0.03 / 0.05 |
| Priority, full-patience bids, 4 workers | 0.97 / 0.95 / 0.97 | 0.03 / 0.97 / 1.00 | 0.03 / 0.05 / 1.00 | 0.03 / 0.03 / 0.05 |

With honest newcomers bidding their full 10 s of patience, the rule held in 46
of 48 testable cells. Against a 4-core attacker on eight workers the priority
queue kept mid-range and flagship phones at 95–100% served where the fixed
18-bit puzzle fell to 25–42%. Without an attack nobody pays; under any attack
every newcomer pays about 10 s.

Three findings qualify this.

- **Budget phones lose first.** A native core hashes about 36 times faster than
  the budget phone's JavaScript, so its threshold is lowest: denied at one core
  with up to four workers and at four cores with eight. No pricing of a hash
  puzzle removes that asymmetry.
- **Client bidding strategy decides the outcome.** In the first run honest
  clients bid 1.25 times the published suggestion against an attacker bidding
  1.5 times; the attacker won every low-budget contest, C1 failed with 15
  violations and service was non-monotonic in attacker budget. Following a
  public price is exploitable.
- **The defender's lever is replay capacity.** Protection grows with spare
  verifier capacity, which costs real CPU; an attacker of about 16 cores
  defeated every configuration tested. That cost is a price of utility.

Fixed-price predictions: the 18-bit puzzle's threshold of about 1.1 cores at
eight workers held; the prototype's 16-bit puzzle served 17–38% of newcomers
at one worker under attack rather than the predicted at most 10%.

**An attested-newcomer lane — outside trust instead of CPU.** Newcomers who
present a device-attestation token get a third lane: no puzzle, their own seats,
and replay ahead of anonymous bidding. The token is modelled on the
rate-limited Privacy Pass tokens behind Apple's Private Access Tokens:
single-use, bound to one site, unlinkable, and assumed capped per device by the
issuer.
A mock issuer stands in; the blind-signature cryptography is not implemented.
Six tests cover the lane; 95 research tests pass. The evaluation reuses the
amendment 9b harness and rates unchanged, varying the share of honest
newcomers holding a token (0, 50%, 90%) and the attacker's token supply (none,
0.1/s, 1/s, 10/s) as well as its CPU (amendment 10, 128 runs).

| Newcomers served, 50% attested, budget / mid / flagship | 1 core | 16 cores |
| --- | --- | --- |
| 8 workers, attacker has no tokens: attested | 1.00 / 1.00 / 1.00 | **1.00 / 1.00 / 1.00** |
| 8 workers, attacker has no tokens: anonymous | 0.95 / 0.90 / 1.00 | 0.25 / 0.00 / 0.10 |
| 8 workers, attacker has 10 tokens/s: attested | 0.45 / 0.50 / 0.50 | 0.45 / 0.50 / 0.50 |
| 8 workers, attacker has 10 tokens/s: anonymous | 0.00 / 0.00 / 0.00 | 0.05 / 0.00 / 0.00 |
| 2 workers, attacker has 1 token/s: attested | 0.80 / 1.00 / 0.70 | 0.80 / 1.00 / 0.70 |

Newcomers reaching trust (three granted bundles) under a 16-core attack, with
each bundle taking four of its device's measured unit times:

| 8 workers, budget / mid / flagship | Reached trust | Median time |
| --- | --- | --- |
| No attestation | 0.00 / 0.00 / 0.00 | — |
| 90% attested, attacker 0–1 tokens/s | 1.00 / 1.00 / 1.00 | 69 / 24 / 24 s |
| 90% attested, attacker 10 tokens/s | 0.92 / 0.89 / 0.97 | 112 / 100 / 100 s |
| Same at 4 workers | 0.08 / 0.44 / 0.42 | 278 / 123 / 142 s |

Predictions held: A1 in 120/120 checks (a token-holding budget phone was served
at every CPU budget, 16 cores included, while its lane was not overloaded), A3
in 118/118 (anonymous newcomers follow (R − λ − a) × phone hash rate ×
patience, so the attacker's tokens lower their threshold), A4 in 24/24 (without
tokens the lane is inert and matches amendment 9b), A6 in 192/192 (token holders
paid no puzzle unless they fell back). Two missed.

- **A2, 112/120.** All eight misses were one-shot cells without a CPU attacker
  and 10 tokens/s, served above the bound. A post-hoc diagnostic run with the
  attack continuing through the drain phase brought them within the bound
  (0.14–0.45 attested): submissions that fell back to the anonymous lane were
  being served after the attack stopped. The misses are recorded as they were.
- **A5, 63/66.** The lockout reproduced (no class reached trust without
  attestation) and 90% attestation broke it for every class when tokens were
  costly. The prediction that 10 tokens/s would hold trust below half failed at
  eight workers (0.89–0.97): a newcomer served on about half its attempts
  still reaches three grants by retrying. At four workers the same attack held
  budget phones to 0.08, because their 30 s bundles allow fewer retries; under
  token saturation the budget phone loses again, on docking speed rather than
  hashing.

What this means:

- **Attestation replaces the CPU asymmetry with the attacker's cost of tokens.**
  With tokens costly, budget phones holding one are admitted and earn trust in
  about a minute against 16 cores, where every puzzle-only configuration
  locked them out. The whole defence then rests on the issuer's per-device
  cap: tokens are unlinkable, so a device whose output fails audit cannot be
  penalised.
- **Cheap tokens are worse than none for anonymous visitors.** Attested
  replays take priority, so at 1–10 tokens/s the attacker starves the anonymous
  lane without spending any CPU.
- **Platform reach is the practical limit.** Private Access Tokens exist on
  Apple devices. Android browsers have no deployed web attestation: Play
  Integrity attests apps, not web pages, and Google abandoned its Web
  Environment Integrity proposal in 2023. The budget Android phones this lane
  is meant to protect currently cannot obtain such a token at all.
- **The per-device cap is an assumption.** The IETF draft for per-origin
  rate-limited tokens expired in 2024, and Apple says its attester can
  rate-limit devices but publishes no limits. The lane's protection rests on a
  cap no deployed issuer documents.
- The mock issuer capped honest devices at ten tokens per hour, which some
  retrying users exhausted under the 10 tokens/s attack; bootstrap figures in
  that cell are therefore conservative.

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
are kept in a separate local legacy archive.
The MNIST and CIFAR phases were moved out of this repository;
the committed history retains the earlier pipeline as a record of the project's
development.

**Batched verification (amendment 15).** One admission labels B inputs,
B in {1, 8, 32, 128}, checked by a batched exact verifier (numpy, one thread)
against the server's batched CPU inference and, secondarily, its RTX 4060 GPU.
M1 held (every perturbation rejected; outputs equal to the per-input
verifier). M2 failed: batching cut verification per input only for the dense
models (to 0.06x and 0.21x at B = 32); convolutional models stayed flat or
worsened, because the verifier's work per activation dominates and those
models have many activations per multiply-accumulate. M3 failed: no model
reached leverage 4 at B = 32 (best 1.05, the wide perceptron); leverage fell
with batch size for every model, as the server's own batched inference gained
more than verification. M4 failed: at small batches the GPU was slower than
one CPU thread (launch and transfer overhead), so leverage against it reached
2.7 for the MNIST perceptron at B = 1, falling below 1 by B = 128. Cells whose
verification exceeds 5.69 ms per admission are not claimed as available.

Post-hoc diagnostic, not a result: per-input verification of the wide
perceptron spends about 220 us, mostly Python-level overhead (SHA-256 of the
trace is 8 us), against 700 us of native inference. An optimised native
verifier could therefore reach much higher leverage for wide dense layers;
this is untested.

**Native fused verification (amendment 15b).** A C kernel verifies a whole
dense network per call and provides an exact native audit and a native forward
pass, the last added to the central baselines (fastest of PyTorch FP32, INT8,
native forward and the amendment-15 GPU). N1 held (exact; every perturbation
rejected). N2 failed: native verification of the wide perceptron took 0.183 ms
at B = 1, 1.9x faster than the numpy verifier, not 5x; per-admission fixed
costs (hashing, input quantisation, the call boundary, cold caches between
interleaved requests) remain. N3 failed: the wide perceptron reached leverage
2.21 at 8% audits against the fastest baseline (the GPU; 3.15 against the
fastest CPU-only baseline, the native forward pass), below 4. N4 held: the
MNIST perceptron stayed below 1. As stated in advance, the paper will report
that the trade-off held with an optimised native verifier. Post-hoc
diagnostic: with verification reduced to hashing alone, 8% exact audits would
cap the wide perceptron near 7 against the GPU.

**Adaptive attacks on trace commitment (amendment 16).** Three attacker-built
driver variants replayed the 99 phase-1 units against the preserved honest
outputs; a control build of the unchanged sources reproduced all 99. None was
accepted (Q1 held), and every variant trace diverged at the first or second
Monte Carlo step (Q2 held): reordered arithmetic (-ffast-math -march=native)
at step 0, a halved local-search step limit at step 0, skipped refinement at
step 1. Q3 failed for two variants: fast-math saved only 5.7% of wall time per
evaluation (predicted 10%) and skipped refinement 2.4% of evaluations per step
(predicted 5%); the halved local search would have saved 41.6%. Q4 held: no
per-step energy recurred between units of the same job, over 23.1 million
steps in 4,397 units of the 33 traced corpus jobs.
