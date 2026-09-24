# Current status — 24 September 2026

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
| I-c duplicated units claiming −20 kcal/mol | same as I-b | **22 of 33 jobs worse at f = 0.05, by up to 2.6 kcal/mol** ✗ |
| I-e ROC-AUC change from I-b, f ≤ 0.25 | within ±0.01 | within ±0.004; within ±0.009 at f = 0.75 ✓ |

**No false positives were observed.** Every final score is an energy the
finalizer recomputed for a physically valid conformation; no falsified value
reached any output, and no gain exceeded 0.42 kcal/mol, a genuine minimum
reached from a displaced start. Honest duplication, the cheapest fabrication
that parses, costs only lost search effort and leaves screening results
unchanged within ±0.004 AUC at up to a quarter of units fabricated.

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

## What is not established

- **Device coverage is small**: four phones, one workload, 64 unit timings.
- **v2 is not serving production traffic.** No production finalizer service
  exists yet.
- **A one-run trusted tier** is not an unconditional proof of work by anonymous
  users: an unaudited trusted admission is still granted on the identity's
  history, not on the unit.
- **Scientific quarantine and repair** after late detection is not implemented.
- **Stronger puzzle baselines** remain to be tested on phones. The four-phone
  study compares against one pure-JavaScript hash puzzle, not optimized or
  multi-subpuzzle proof of work. A separate Node/OpenSSL experiment with 96
  trials per configuration reduced p95/median from 4.86 for one puzzle to 1.33
  for 64 subpuzzles at equal expected hash count. This is desktop evidence,
  not a new device result or a median-matched comparison.
- **Availability under attack is only partly resolved, and only in isolated
  prototypes.** Stateless tickets and reserved tiers end the idle-lease attack
  and protect established users; an effort-priority queue keeps newcomers served
  below a budget of (R − λ) × phone hash rate × patience, but budget phones lose
  first, every newcomer pays about 10 s under attack, and about 16 attacker
  cores defeated every configuration tested. None of this is integrated into
  `PoolAdmission`, and puzzle costs were accounted, not executed. A separate fractional-refill bug was
  fixed: rejected requests now preserve token credit. All 72 research tests
  passed, including a regression that failed before the fix.
- **Novelty positioning** against prior useful-work puzzles, volunteer computing
  and probabilistic verification remains outstanding.

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
